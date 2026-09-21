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

# Only a signing build may request uiAccess. Windows will not start a
# uiAccess="true" executable without a trusted Authenticode signature, so an
# unsigned build that embedded it would ship a binary nobody can launch.
#
# What it buys when a certificate is available: live Grid 3 editing drives the
# Grid 3 UI across the UIPI boundary without elevating, so the app stops asking
# for administrator approval on every launch. That matters most where the
# person doing the editing is not a local administrator, which in a school
# district is the normal case.
$manifestMode = if ($Sign) { "uiaccess" } else { "asinvoker" }

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
        $env:AAC_EDITOR_MANIFEST = $manifestMode
        python -m PyInstaller packaging/tdsnap.spec --noconfirm --clean
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
        # Sign before verifying: the uiAccess check in verify_manifest.ps1 is a
        # signature check, and an unsigned uiAccess binary is exactly what it
        # exists to catch.
        if ($Sign) { Sign-File $exe }
        & "$PSScriptRoot\verify_manifest.ps1" -Executable $exe -Expect $manifestMode
        Write-Output "Built app: $exe ($manifestMode manifest)"
    }

    if ($Stage -in @("All", "Installer")) {
        if (-not (Test-Path -LiteralPath $exe)) {
            throw "Packaged executable not found: $exe"
        }
        & "$PSScriptRoot\verify_manifest.ps1" -Executable $exe -Expect $manifestMode
        $iscc = Find-Tool "iscc.exe" "C:\Program Files*\Inno Setup *\ISCC.exe"
        & $iscc "/DAppVersion=$Version" "packaging\installer.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }

        if ($Sign) { Sign-File $installer }
        Write-Output "Built installer: $installer"
    }
} finally {
    Pop-Location
}
