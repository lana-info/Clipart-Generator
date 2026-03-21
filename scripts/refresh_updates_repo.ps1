<#
Скрипт обновляет публичный репозиторий обновлений (_updates_repo_tmp) из приватного:
1. очищает папку, оставляя только .git,
2. копирует version.json и указанный установщик из release/,
3. делает коммит и пуш в Clipart-Generator-Updates.
#>
param(
    [Parameter(Mandatory)]
    [string]
    $PrivateRepoPath,

    [Parameter(Mandatory)]
    [string]
    $UpdatesRepoPath,

    [Parameter(Mandatory)]
    [string]
    $SetupName,

    [string]
    $VersionFileName = 'version.json',

    [switch]
    $DryRun
)

Set-StrictMode -Version Latest

$projectRoot = (Get-Item '.').FullName
$scriptRoot = (Get-Item $PSScriptRoot).FullName

function Resolve-RepoPath([string]$relativePath) {
    $fullPath = if ([System.IO.Path]::IsPathRooted($relativePath)) {
        $relativePath
    } else {
        Join-Path -Path $projectRoot -ChildPath $relativePath
    }

    return (Resolve-Path -LiteralPath $fullPath -ErrorAction Stop).ProviderPath
}

$privateRoot = Resolve-RepoPath $PrivateRepoPath
$updatesRoot = Resolve-RepoPath $UpdatesRepoPath

$versionSource = Join-Path -Path $privateRoot -ChildPath $VersionFileName
if (-not (Test-Path -LiteralPath $versionSource)) {
    throw "Не удалось найти $VersionFileName в $privateRoot"
}

$releaseDir = Join-Path -Path $privateRoot -ChildPath 'release'
$setupSource = Join-Path -Path $releaseDir -ChildPath $SetupName
if (-not (Test-Path -LiteralPath $setupSource)) {
    throw "Не удалось найти установщик $SetupName в $releaseDir"
}

$existingItems = Get-ChildItem -LiteralPath $updatesRoot -Force | Where-Object { $_.Name -ne '.git' }
foreach ($item in $existingItems) {
    if ($DryRun) {
        Write-Host "Будет удалено: $($item.FullName)"
        continue
    }

    Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop
}

$copyPlan = @(
    @{ Source = $versionSource; Destination = Join-Path -Path $updatesRoot -ChildPath $VersionFileName },
    @{ Source = $setupSource; Destination = Join-Path -Path $updatesRoot -ChildPath $SetupName }
)

foreach ($step in $copyPlan) {
    if ($DryRun) {
        Write-Host "Будет скопировано: $($step.Source) -> $($step.Destination)"
        continue
    }

    Copy-Item -LiteralPath $step.Source -Destination $step.Destination -Force -ErrorAction Stop
}

if ($DryRun) {
    Write-Host 'DryRun завершён, изменений нет.'
    return
}

$gitArgs = @('-C', $updatesRoot)
try {
    & git @gitArgs add -A | Out-Null
    $status = & git @gitArgs status -sb
    if ($status -match 'working tree clean') {
        Write-Host 'Изменений для коммита нет.'
        return
    }

    $commitMessage = "chore(release): refresh updates repo for $SetupName"
    & git @gitArgs commit -m $commitMessage
    & git @gitArgs push
    Write-Host 'Обновления отправлены в репозиторий обновлений.'
} catch {
    Write-Host "Git-команды завершились ошибкой: $($_.Exception.Message)"
    throw
}