# Release automation helper for Clipart Generator.
# Modes:
#   full       - update version.json, run workflow, download artifacts, copy to _updates_repo_tmp
#   copy       - download artifacts from an existing release, then copy to _updates_repo_tmp
#   post-build - skip workflow and downloads, use files already present in release/

param(
    [Parameter(Mandatory)]
    [string]$PrivateRepoPath,

    [Parameter(Mandatory)]
    [string]$UpdatesRepoPath,

    [string]$AppVersion,

    [ValidateSet('full','copy','post-build')]
    [string]$Mode = 'full'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = (Get-Location).ProviderPath

function Normalize-Path {
    param([string]$RelativePath)

    if ([string]::IsNullOrWhiteSpace($RelativePath)) {
        throw 'Path is empty.'
    }

    if ([System.IO.Path]::IsPathRooted($RelativePath)) {
        return $RelativePath
    }

    return (Join-Path -Path $projectRoot -ChildPath $RelativePath)
}

function Ensure-Command {
    param([string]$Name, [string]$InstallHint)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "Required command not found: $Name. $InstallHint"
    }
}

function Ensure-DefaultRepo {
    $repoInfo = & gh repo view --json nameWithOwner 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoInfo)) {
        throw 'GitHub CLI default repository is not configured. Run: gh repo set-default lana-info/Clipart-Generator'
    }
}

function Start-Workflow {
    param([string]$Version)

    Write-Host "Dispatching workflow release-multi-platform.yml for version $Version..."
    & gh workflow run release-multi-platform.yml --ref main --field "app_version=$Version"

    $deadline = (Get-Date).AddMinutes(30)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 8
        $runsJson = & gh run list --workflow release-multi-platform.yml --branch main --limit 10 --json databaseId,event,createdAt,status,displayTitle
        if ([string]::IsNullOrWhiteSpace($runsJson)) {
            continue
        }

        $runs = $runsJson | ConvertFrom-Json
        foreach ($run in $runs) {
            if ($run.event -ne 'workflow_dispatch') {
                continue
            }

            $createdAt = [datetime]::Parse($run.createdAt).ToUniversalTime()
            if ($createdAt -lt (Get-Date).ToUniversalTime().AddMinutes(-10)) {
                continue
            }

            Write-Host "Watching workflow run #$($run.databaseId)..."
            & gh run watch $run.databaseId --exit-status
            return
        }
    }

    throw 'Timed out while waiting for the workflow to finish.'
}

function Download-Artifacts {
    param([string]$Version)

    Write-Host "Downloading release artifacts for v$Version into release/..."
    & gh release download "v$Version" --pattern "ClipartGenerator-Setup-$Version.exe" -D "$projectRoot\release"
    & gh release download "v$Version" --pattern "ClipartGenerator-macOS-apple-silicon-$Version.zip" -D "$projectRoot\release"
    & gh release download "v$Version" --pattern "ClipartGenerator-macOS-intel-$Version.zip" -D "$projectRoot\release"
}

Ensure-Command -Name 'gh' -InstallHint 'Install GitHub CLI from https://cli.github.com/'
Ensure-DefaultRepo

$privateRoot = Normalize-Path -RelativePath $PrivateRepoPath
$updatesRoot = Normalize-Path -RelativePath $UpdatesRepoPath

$versionFileDefault = Join-Path -Path $projectRoot -ChildPath 'release\VERSION.txt'
if ([string]::IsNullOrWhiteSpace($AppVersion)) {
    if (-not (Test-Path -LiteralPath $versionFileDefault)) {
        throw "Cannot determine AppVersion. File not found: $versionFileDefault"
    }

    $AppVersion = (Get-Content -LiteralPath $versionFileDefault -Raw).Trim()
}

Write-Host "Mode: $Mode"
Write-Host "Version: $AppVersion"
Write-Host "Project root: $projectRoot"
Write-Host "Updates repo path: $updatesRoot"

switch ($Mode) {
    'full' {
        Write-Host 'Step 1/4: update version.json'
        & powershell -ExecutionPolicy Bypass -File "$projectRoot\update_version.ps1" -AppVersion $AppVersion

        Write-Host 'Step 2/4: run GitHub Actions workflow'
        Start-Workflow -Version $AppVersion

        Write-Host 'Step 3/4: download release artifacts'
        Download-Artifacts -Version $AppVersion
    }
    'copy' {
        Write-Host 'Step 1/2: download release artifacts'
        Download-Artifacts -Version $AppVersion
    }
    'post-build' {
        Write-Host 'Step 1/1: use existing local files from release/'
    }
}

$versionJsonSrc = Join-Path -Path $projectRoot -ChildPath 'version.json'
$exeSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-Setup-$AppVersion.exe"
$macArmSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-macOS-apple-silicon-$AppVersion.zip"
$macIntelSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-macOS-intel-$AppVersion.zip"

foreach ($path in @($versionJsonSrc, $exeSrc)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file is missing: $path"
    }
}

Write-Host 'Copying files into _updates_repo_tmp...'
Copy-Item -LiteralPath $versionJsonSrc -Destination (Join-Path -Path $updatesRoot -ChildPath 'version.json') -Force
Copy-Item -LiteralPath $exeSrc -Destination (Join-Path -Path $updatesRoot -ChildPath "ClipartGenerator-Setup-$AppVersion.exe") -Force

if (Test-Path -LiteralPath $macArmSrc) {
    Copy-Item -LiteralPath $macArmSrc -Destination (Join-Path -Path $updatesRoot -ChildPath "ClipartGenerator-macOS-apple-silicon-$AppVersion.zip") -Force
}

if (Test-Path -LiteralPath $macIntelSrc) {
    Copy-Item -LiteralPath $macIntelSrc -Destination (Join-Path -Path $updatesRoot -ChildPath "ClipartGenerator-macOS-intel-$AppVersion.zip") -Force
}

Write-Host ''
Write-Host 'Done.'
Write-Host 'Next steps:'
Write-Host "1. cd \"$updatesRoot\""
Write-Host '2. git status'
Write-Host "3. git add version.json ClipartGenerator-Setup-$AppVersion.exe ClipartGenerator-macOS-apple-silicon-$AppVersion.zip ClipartGenerator-macOS-intel-$AppVersion.zip"
Write-Host '4. git commit and git push in _updates_repo_tmp'
Write-Host '5. Update the public GitHub Release in Clipart-Generator-Updates if needed'