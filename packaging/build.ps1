param(
    [string]$Version = "0.0.0",
    [ValidateSet("All", "App", "Installer")]
    [string]$Stage = "All",
    [switch]$Sign
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $root "dist\AACEditor\AAC Editor.exe"
$installer = Join-Path $root "dist\installer\AACEditor-$Version-windows-x64-setup.exe"
$thumbprint = $env:AAC_EDITOR_SIGNING_THUMBPRINT

if ($Sign -and [string]::IsNullOrWhiteSpace($thumbprint)) {
    throw "Signing was requested, but AAC_EDITOR_SIGNING_THUMBPRINT is not configured."
}

function Find-Tool([string]$Name, [string]$FallbackPattern) {
    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $match = Get-ChildItem $FallbackPattern -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($match) { return $match.FullName }
    throw "$Name was not found. Install the Windows SDK/Inno Setup build tools."
}

function Sign-File([string]$Path) {
    $signTool = Find-Tool "signtool.exe" "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe"
    $arguments = @("sign", "/sha1", $thumbprint, "/fd", "SHA256", "/d", "AAC Editor")
    $timestamp = $env:AAC_EDITOR_TIMESTAMP_URL
    if ($timestamp -ne "none") {
        if ([string]::IsNullOrWhiteSpace($timestamp)) { $timestamp = "http://timestamp.digicert.com" }
        $arguments += @("/tr", $timestamp, "/td", "SHA256")
    }
    & $signTool @arguments $Path
    if ($LASTEXITCODE -ne 0) { throw "Signing failed for $Path" }
    & $signTool verify /pa /v $Path
    if ($LASTEXITCODE -ne 0) { throw "Signature verification failed for $Path" }
}

Push-Location $root
try {
    if ($Stage -in @("All", "App")) {
        python -m PyInstaller packaging/tdsnap.spec --noconfirm --clean
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
        & "$PSScriptRoot\verify_manifest.ps1" -Executable $exe
        if ($Sign) { Sign-File $exe }
        Write-Output "Built app: $exe"
    }

    if ($Stage -in @("All", "Installer")) {
        if (-not (Test-Path -LiteralPath $exe)) {
            throw "Packaged executable not found: $exe"
        }
        & "$PSScriptRoot\verify_manifest.ps1" -Executable $exe
        $iscc = Find-Tool "iscc.exe" "C:\Program Files*\Inno Setup *\ISCC.exe"
        & $iscc "/DAppVersion=$Version" "packaging\installer.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

        if ($Sign) { Sign-File $installer }
        Write-Output "Built installer: $installer"
    }
} finally {
    Pop-Location
}
