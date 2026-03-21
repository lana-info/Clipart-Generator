<#
Скрипт действует одного шага: копирует артефакты release/ → локальный клон `_updates_repo_tmp` и информирует пользователя.
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

    [Parameter(Mandatory)]
    [string]
    $MacZipName,

    [string]
    $VersionFileName = 'version.json'
)

Set-StrictMode -Version Latest

$projectRoot = (Get-Item '.').FullName

function Resolve-PathFromRoot([string]$relativePath) {
    if ([System.IO.Path]::IsPathRooted($relativePath)) {
        return $relativePath
    }

    return Join-Path -Path $projectRoot -ChildPath $relativePath
}

$privateRoot = Resolve-PathFromRoot $PrivateRepoPath
$updatesRoot = Resolve-PathFromRoot $UpdatesRepoPath

$releaseDir = Join-Path -Path $privateRoot -ChildPath 'release'
$versionSource = Join-Path -Path $privateRoot -ChildPath $VersionFileName
$setupSource = Join-Path -Path $releaseDir -ChildPath $SetupName
$macSource = Join-Path -Path $releaseDir -ChildPath $MacZipName

foreach ($artifact in @{
    version = $versionSource;
    windows = $setupSource;
    macos = $macSource
}) {
    if (-not (Test-Path -LiteralPath $artifact.Value)) {
        throw "Скачайте артефакт $($artifact.Value) и разместите в release/."
    }
}

[array]$copyPlan = @(
    @{ Source = $versionSource; Destination = Join-Path -Path $updatesRoot -ChildPath $VersionFileName; Label = 'описание версии' },
    @{ Source = $setupSource; Destination = Join-Path -Path $updatesRoot -ChildPath $SetupName; Label = 'Windows-установщик' },
    @{ Source = $macSource; Destination = Join-Path -Path $updatesRoot -ChildPath $MacZipName; Label = 'macOS-архив' }
)

Write-Host 'Скрипт выполняет единственный шаг — копирует артефакты в `_updates_repo_tmp`.'

foreach ($step in $copyPlan) {
    Write-Host "Копирую $($step.Label) из $($step.Source) → $($step.Destination)..."
    Copy-Item -LiteralPath $step.Source -Destination $step.Destination -Force -ErrorAction Stop
}

Write-Host 'Готово: файлы лежат в `_updates_repo_tmp`.'
Write-Host 'Дальше вам нужно:'
Write-Host " 1. Перейти в каталог $updatesRoot и проверить `git status`."
Write-Host " 2. Добавить version.json, $SetupName и $MacZipName, затем сделать git commit и git push в Clipart-Generator-Updates."
Write-Host ' 3. Создать или обновить релиз на GitHub и загрузить туда указанные артефакты.'