<#
PowerShell helper covers full release automation and partial steps:
- full: update version, dispatch Release Multi Platform, download artifacts, copy into `_updates_repo_tmp`.
- copy: download artifacts + copy into `_updates_repo_tmp` (assumes workflow run already happened).
- post-build: skip workflow/downloads (macos/Windows already in release/), just copy artifacts to `_updates_repo_tmp`.
#>
param(
    [Parameter(Mandatory)][string]$PrivateRepoPath,
    [Parameter(Mandatory)][string]$UpdatesRepoPath,
    [string]$AppVersion,
    [ValidateSet('full','copy','post-build')][string]$Mode = 'full'
)

Set-StrictMode -Version Latest
$projectRoot = (Get-Item '.').FullName

function Resolve-PathFromRoot([string]$relativePath) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        throw 'Relative path is empty.'
    }

    return if ([System.IO.Path]::IsPathRooted($relativePath)) {
        $relativePath
    } else {
        Join-Path -Path $projectRoot -ChildPath $relativePath
    }
}

$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghCommand) {
    throw 'GitHub CLI (gh) not found. Install it from https://cli.github.com/ and rerun the script.'
}

$privateRoot = Resolve-PathFromRoot $PrivateRepoPath
$updatesRoot = Resolve-PathFromRoot $UpdatesRepoPath

$versionFileDefault = Join-Path -Path $projectRoot -ChildPath 'release\VERSION.txt'
if (-not $AppVersion) {
    if (-not (Test-Path -LiteralPath $versionFileDefault)) {
        throw "Unable to determine app version: $versionFileDefault missing and -AppVersion not provided."
    }

    $AppVersion = (Get-Content -Raw $versionFileDefault).Trim()
}

function StartWorkflow([string]$version) {
    Write-Host "Dispatching release workflow for $version..."
    & gh workflow run release-multi-platform.yml --ref main --field "app_version=$version"

    $deadline = (Get-Date).AddMinutes(30)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 6
        $runsJson = & gh run list --workflow release-multi-platform.yml --branch main --limit 5 --json databaseId,event,status,createdAt
        if ([string]::IsNullOrWhiteSpace($runsJson)) {
            continue
        }

        $runs = $runsJson | ConvertFrom-Json
        foreach ($run in $runs) {
            if ($run.event -ne 'workflow_dispatch') {
                continue
            }

            $createdAt = [datetime]::Parse($run.createdAt).ToUniversalTime()
            if ($createdAt -lt (Get-Date).ToUniversalTime().AddMinutes(-6)) {
                continue
            }

            Write-Host "Watching workflow run #$($run.databaseId)..."
            & gh run watch $run.databaseId --exit-status
            return
        }
    }

    throw 'Timed out while waiting for a GitHub workflow run.'
}

function DownloadArtifacts([string]$version) {
    Write-Host "Downloading artifacts for v$version into release/..."
    try {
        & gh release download "v$version" --pattern "ClipartGenerator-Setup-$version.exe" -D "${projectRoot}\release"
        & gh release download "v$version" --pattern "ClipartGenerator-macOS-$version.zip" -D "${projectRoot}\release"
    } catch {
        throw "Failed to download release artifacts for v$version. $_"
    }
}

Write-Host "Verifying version: $AppVersion"
if ($Mode -eq 'full') {
    Write-Host 'Mode=full: update `version.json`, dispatch workflow, download artifacts.'
    & powershell -ExecutionPolicy Bypass -File "${projectRoot}\update_version.ps1" -AppVersion $AppVersion
    StartWorkflow $AppVersion
    DownloadArtifacts $AppVersion
} elseif ($Mode -eq 'copy') {
    Write-Host 'Mode=copy: download artifacts only (workflow assumed already run).'
    DownloadArtifacts $AppVersion
} else {
    Write-Host 'Mode=post-build: skip workflow/downloads, rely on existing release/ artifacts.'
}

$versionJsonSrc = Join-Path -Path $projectRoot -ChildPath 'version.json'
$exeSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-Setup-$AppVersion.exe"
$macSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-macOS-$AppVersion.zip"
foreach ($path in @($versionJsonSrc, $exeSrc, $macSrc)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required file missing: $path"
    }
}

Write-Host 'Copying version.json + installers into `_updates_repo_tmp`...'
Copy-Item -LiteralPath $versionJsonSrc -Destination (Join-Path $updatesRoot 'version.json') -Force
Copy-Item -LiteralPath $exeSrc -Destination (Join-Path $updatesRoot "ClipartGenerator-Setup-$AppVersion.exe") -Force
Copy-Item -LiteralPath $macSrc -Destination (Join-Path $updatesRoot "ClipartGenerator-macOS-$AppVersion.zip") -Force

Write-Host 'Copy complete. Next steps:'
Write-Host " 1. cd $updatesRoot"
Write-Host ' 2. git status'
Write-Host " 3. git add version.json ClipartGenerator-Setup-$AppVersion.exe ClipartGenerator-macOS-$AppVersion.zip"
Write-Host ' 4. git commit / git push in _updates_repo_tmp and update the public release.'