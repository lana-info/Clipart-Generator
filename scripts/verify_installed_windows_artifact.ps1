param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedAppVersion
)

$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:AGENT_TEMPDIRECTORY "vibix-installed-smoke"
$internalRoot = Join-Path $installRoot "_internal"
$markerPath = Join-Path $internalRoot "stale-runtime-marker.txt"

function Invoke-BoundedProcess {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [int]$TimeoutSeconds,
        [string]$Description
    )

    $process = Start-Process -FilePath $FilePath -ArgumentList $Arguments -PassThru
    if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw "$Description exceeded $TimeoutSeconds seconds"
    }
    if ($process.ExitCode -ne 0) {
        throw "$Description failed with exit code $($process.ExitCode)"
    }
}

New-Item -ItemType Directory -Force -Path $internalRoot | Out-Null
[System.IO.File]::WriteAllText($markerPath, "stale", [System.Text.UTF8Encoding]::new($false))

Invoke-BoundedProcess `
    -FilePath $InstallerPath `
    -Arguments "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$installRoot" `
    -TimeoutSeconds 600 `
    -Description "Installed-artifact setup"
if (Test-Path -LiteralPath $markerPath) {
    throw "Installer left stale native runtime files in place"
}

$installedExe = Join-Path $installRoot "Vibix Images.exe"
if (-not (Test-Path -LiteralPath $installedExe)) {
    throw "Installed executable is missing: $installedExe"
}

$env:QT_QPA_PLATFORM = "offscreen"
Invoke-BoundedProcess `
    -FilePath $installedExe `
    -Arguments "--release-entrypoint-smoke", "--expected-app-version=$ExpectedAppVersion" `
    -TimeoutSeconds 120 `
    -Description "Installed release smoke"

$smokeReport = Join-Path $env:AGENT_TEMPDIRECTORY "windows-local-processing-smoke.txt"
try {
    Invoke-BoundedProcess `
        -FilePath $installedExe `
        -Arguments "--local-processing-smoke", "--local-processing-smoke-report=$smokeReport" `
        -TimeoutSeconds 1200 `
        -Description "Installed local-processing smoke"
}
catch {
    if (Test-Path -LiteralPath $smokeReport) {
        Get-Content -LiteralPath $smokeReport
    }
    throw
}
