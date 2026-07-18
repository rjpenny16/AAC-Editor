param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedVersion,
    [switch]$AllowInstall
)

$ErrorActionPreference = "Stop"
if (-not $AllowInstall -and $env:CI -ne "true") {
    throw "This check installs and uninstalls AAC Editor. Pass -AllowInstall explicitly."
}

$installerPath = (Resolve-Path -LiteralPath $Installer).Path
$installerSignature = Get-AuthenticodeSignature -LiteralPath $installerPath
if ($installerSignature.Status -ne "Valid") {
    throw "Installer signature is not trusted: $($installerSignature.Status)"
}

$appDir = Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "AAC Editor"
$exe = Join-Path $appDir "AAC Editor.exe"
$uninstaller = Join-Path $appDir "unins000.exe"
if (Test-Path -LiteralPath $appDir) {
    throw "Refusing to replace an existing AAC Editor install: $appDir"
}

$install = Start-Process -FilePath $installerPath -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
    "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"
)
if ($install.ExitCode -ne 0) { throw "Installer exited with code $($install.ExitCode)." }

$appProcess = $null
try {
    if (-not (Test-Path -LiteralPath $exe)) { throw "Installed executable not found: $exe" }
    $appSignature = Get-AuthenticodeSignature -LiteralPath $exe
    if ($appSignature.Status -ne "Valid") {
        throw "Installed executable signature is not trusted: $($appSignature.Status)"
    }
    & "$PSScriptRoot\verify_manifest.ps1" -Executable $exe

    $port = 8876
    $base = "http://127.0.0.1:$port"
    $appProcess = Start-Process -FilePath $exe -WindowStyle Hidden -PassThru -ArgumentList @(
        "--port", $port, "--replace-instance"
    )
    $health = $null
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($appProcess.HasExited) {
            throw "Packaged app exited before its health endpoint became ready."
        }
        try {
            $health = Invoke-RestMethod "$base/api/health" -TimeoutSec 1
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }
    if (-not $health -or -not $health.ok) { throw "Packaged app health check timed out." }
    if ($health.version -ne $ExpectedVersion) {
        throw "Packaged version $($health.version) did not match $ExpectedVersion."
    }

    $config = Invoke-RestMethod "$base/api/config" -TimeoutSec 2
    Invoke-RestMethod "$base/api/quit" -Method Post -TimeoutSec 5 -Headers @{
        "X-TDSnap-Token" = $config.token
    } | Out-Null
    $appProcess.WaitForExit(10000) | Out-Null
} finally {
    if ($appProcess -and -not $appProcess.HasExited) {
        Stop-Process -Id $appProcess.Id -Force
    }
    if (Test-Path -LiteralPath $uninstaller) {
        $uninstall = Start-Process -FilePath $uninstaller -WindowStyle Hidden -Wait -PassThru -ArgumentList @(
            "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
        )
        if ($uninstall.ExitCode -ne 0) {
            throw "Uninstaller exited with code $($uninstall.ExitCode)."
        }
    }
}

Write-Output "Verified signed install, startup, health endpoint, and uninstall: $installerPath"
