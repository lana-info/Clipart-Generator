param(
    [Parameter(Mandatory = $true)]
    [string]$InstallerPath,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedAppVersion,
    [Parameter(Mandatory = $true)]
    [string]$EvidenceDir,
    [ValidateSet("production", "acceptance")]
    [string]$ExpectedProfile = "production"
)

$ErrorActionPreference = "Stop"
$temporaryRoot = if ($env:AGENT_TEMPDIRECTORY) {
    $env:AGENT_TEMPDIRECTORY
} elseif ($env:RUNNER_TEMP) {
    $env:RUNNER_TEMP
} else {
    [System.IO.Path]::GetTempPath()
}
$installRoot = Join-Path $temporaryRoot "vibix-installed-smoke"
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

if ($ExpectedProfile -eq "acceptance") {
    $protectedRoot = Join-Path $temporaryRoot "vibix-production-sentinel"
    New-Item -ItemType Directory -Force -Path $protectedRoot | Out-Null
    $protectedExe = Join-Path $protectedRoot "Vibix Images.exe"
    [System.IO.File]::WriteAllText($protectedExe, "production-sentinel")
    $beforeHash = (Get-FileHash -LiteralPath $protectedExe -Algorithm SHA256).Hash
    $guard = Start-Process -FilePath $InstallerPath -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/DIR=$protectedRoot" -PassThru
    if (-not $guard.WaitForExit(120000)) {
        Stop-Process -Id $guard.Id -Force -ErrorAction SilentlyContinue
        throw "Acceptance overwrite guard timed out"
    }
    if ($guard.ExitCode -eq 0 -or (Get-FileHash -LiteralPath $protectedExe -Algorithm SHA256).Hash -ne $beforeHash) {
        throw "Acceptance installer did not protect the production executable"
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

New-Item -ItemType Directory -Force -Path $EvidenceDir | Out-Null
$env:QT_QPA_PLATFORM = "windows"
Invoke-BoundedProcess `
    -FilePath $installedExe `
    -Arguments "--release-entrypoint-smoke", "--expected-app-version=$ExpectedAppVersion", "--expected-profile=$ExpectedProfile", "--ui-evidence-dir=$EvidenceDir" `
    -TimeoutSeconds 120 `
    -Description "Installed release smoke"

foreach ($evidenceName in @(
    "mode-selection.png",
    "clipart-prompts.png",
    "clipart-prompt-review.png"
)) {
    $evidencePath = Join-Path $EvidenceDir $evidenceName
    if (-not (Test-Path -LiteralPath $evidencePath)) {
        throw "Installed application UI evidence is missing: $evidencePath"
    }
}

$env:QT_QPA_PLATFORM = "offscreen"
$smokeReport = Join-Path $temporaryRoot "windows-local-processing-smoke.txt"
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
