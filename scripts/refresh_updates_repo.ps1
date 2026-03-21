<#
Скрипт охватывает полный релиз: запускает workflow "Release Multi Platform", ожидает сборок, скачивает Windows и macOS артефакты и копирует их вместе с version.json в локальный `_updates_repo_tmp`.
После выполнения он описывает, что какому репозиторию нужно закоммитить и опубликовать.
#>
param(
    [Parameter(Mandatory)]
    [string]
    $PrivateRepoPath,

    [Parameter(Mandatory)]
    [string]
    $UpdatesRepoPath,

    [string]
    $AppVersion
)

Set-StrictMode -Version Latest

$projectRoot = (Get-Item '.').FullName

function Resolve-PathFromRoot([string]$relativePath) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        throw "Не задан путь."
    }

    return if ([System.IO.Path]::IsPathRooted($relativePath)) {
        $relativePath
    } else {
        Join-Path -Path $projectRoot -ChildPath $relativePath
    }
}

$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghCommand) {
    throw 'Не найден GitHub CLI (gh). Установите его: https://cli.github.com/ и повторите запуск скрипта.'
}

$privateRoot = Resolve-PathFromRoot $PrivateRepoPath
$updatesRoot = Resolve-PathFromRoot $UpdatesRepoPath

$versionFileDefault = Join-Path -Path $projectRoot -ChildPath 'release\VERSION.txt'
if (-not $AppVersion) {
    if (-not (Test-Path -LiteralPath $versionFileDefault)) {
        throw "Не удалось определить версию, отсутствует $versionFileDefault и параметр -AppVersion не задан."
    }

    $AppVersion = (Get-Content -Raw $versionFileDefault).Trim()
}

Write-Host "Версия релиза: $AppVersion"

Write-Host 'Обновляю version.json →'
& powershell -ExecutionPolicy Bypass -File "${projectRoot}\update_version.ps1" -AppVersion $AppVersion

Write-Host 'Запускаю GitHub Action release-multi-platform.yml ...'
& gh workflow run release-multi-platform.yml --ref main --field "app_version=$AppVersion"

$dispatchStart = Get-Date
$runId = $null
$maxWait = 30
$attempt = 0

while (-not $runId -and $attempt -lt $maxWait) {
    Start-Sleep -Seconds 6
    $attempt++
    $runsJson = & gh run list --workflow release-multi-platform.yml --branch main --limit 5 --json databaseId,event,status,createdAt
    if ([string]::IsNullOrWhiteSpace($runsJson)) {
        continue
    }

    $runs = $runsJson | ConvertFrom-Json
    if (-not $runs) {
        continue
    }

    foreach ($run in $runs) {
        $createdAt = [datetime]::Parse($run.createdAt).ToUniversalTime()
        if ($createdAt -lt $dispatchStart.ToUniversalTime().AddMinutes(-1)) {
            continue
        }

        if ($run.event -ne 'workflow_dispatch') {
            continue
        }

        $runId = $run.databaseId
        break
    }
}

if (-not $runId) {
    throw 'Не удалось найти запущенный workflow. Убедитесь, что GitHub Action доступен.'
}

Write-Host "Ожидаю завершения workflow run #$runId ..."
& gh run watch $runId --exit-status

Write-Host 'Скачиваю артефакты из GitHub Release...'
try {
    & gh release download "v$AppVersion" --pattern "ClipartGenerator-Setup-$AppVersion.exe" -D "${projectRoot}\release"
    & gh release download "v$AppVersion" --pattern "ClipartGenerator-macOS-$AppVersion.zip" -D "${projectRoot}\release"
} catch {
    throw "Не удалось скачать артефакты из релиза v$AppVersion. Убедитесь, что GitHub Release существует и содержит файлы. Ошибка: $_"
}

$versionJsonSrc = Join-Path -Path $projectRoot -ChildPath 'version.json'
if (-not (Test-Path -LiteralPath $versionJsonSrc)) {
    throw 'version.json не найден после сборки.'
}

Write-Host 'Копирую файлы в `_updates_repo_tmp` ...'
Copy-Item -LiteralPath $versionJsonSrc -Destination (Join-Path -Path $updatesRoot -ChildPath 'version.json') -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "release\ClipartGenerator-Setup-$AppVersion.exe") -Destination (Join-Path $updatesRoot "ClipartGenerator-Setup-$AppVersion.exe") -Force
Copy-Item -LiteralPath (Join-Path $projectRoot "release\ClipartGenerator-macOS-$AppVersion.zip") -Destination (Join-Path $updatesRoot "ClipartGenerator-macOS-$AppVersion.zip") -Force

Write-Host 'Готово: `_updates_repo_tmp` содержит version.json, .exe и .zip.'
Write-Host 'Дальше:'
Write-Host " 1. Перейдите в каталог $updatesRoot, выполните `git status`."
Write-Host " 2. Добавьте файлы: version.json, ClipartGenerator-Setup-$AppVersion.exe, ClipartGenerator-macOS-$AppVersion.zip."
Write-Host ' 3. Создайте либо обновите GitHub Release (в Clipart-Generator-Updates) и загрузите в него эти файлы.'
Write-Host ' 4. Сделайте git commit и git push внутри _updates_repo_tmp.'