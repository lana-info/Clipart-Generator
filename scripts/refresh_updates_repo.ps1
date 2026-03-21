# Release automation helper for Clipart Generator.
param(
    [Parameter(Mandatory)][string]$PrivateRepoPath,
    [Parameter(Mandatory)][string]$UpdatesRepoPath,
    [string]$AppVersion,
    [ValidateSet('full','copy','post-build')][string]$Mode = 'full'
)

Set-StrictMode -Version Latest
$projectRoot = (Get-Location).ProviderPath

function Normalize-Path([string]$relativePath) {
    if ([string]::IsNullOrWhiteSpace($relativePath)) {
        throw 'Не задан путь.'
    }
    if ([System.IO.Path]::IsPathRooted($relativePath)) {
        return $relativePath
    }
    return Join-Path -Path $projectRoot -ChildPath $relativePath
}

$ghCommand = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghCommand) {
    throw 'GitHub CLI (gh) не найден. Установите его с https://cli.github.com/ и повторите запуск.'
}

$privateRoot = Normalize-Path $PrivateRepoPath
$updatesRoot = Normalize-Path $UpdatesRepoPath

$versionFileDefault = Join-Path -Path $projectRoot -ChildPath 'release\VERSION.txt'
if (-not $AppVersion) {
    if (-not (Test-Path -LiteralPath $versionFileDefault)) {
        throw "Невозможно определить версию: $versionFileDefault отсутствует и -AppVersion не задан."
    }
    $AppVersion = (Get-Content -Raw $versionFileDefault).Trim()
}

function Start-Workflow([string]$version) {
    Write-Host "Dispatching workflow release-multi-platform.yml for $version..."
    & gh workflow run release-multi-platform.yml --ref main --field "app_version=$version"
    $deadline = (Get-Date).AddMinutes(30)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 6
        $runsJson = & gh run list --workflow release-multi-platform.yml --branch main --limit 5 --json databaseId,event,status,createdAt
        if ([string]::IsNullOrWhiteSpace($runsJson)) { continue }
        $runs = $runsJson | ConvertFrom-Json
        foreach ($run in $runs) {
            if ($run.event -ne 'workflow_dispatch') { continue }
            $createdAt = [datetime]::Parse($run.createdAt).ToUniversalTime()
            if ($createdAt -lt (Get-Date).ToUniversalTime().AddMinutes(-5)) { continue }
            Write-Host "Waiting for workflow run #$($run.databaseId)..."
            & gh run watch $run.databaseId --exit-status
            return
        }
    }
    throw 'Превышено время ожидания завершения workflow.'
}

function Download-Artifacts([string]$version) {
    Write-Host "Downloading artifacts for v$version into release/..."
    try {
        & gh release download "v$version" --pattern "ClipartGenerator-Setup-$version.exe" -D "${projectRoot}\release"
        & gh release download "v$version" --pattern "ClipartGenerator-macOS-$version.zip" -D "${projectRoot}\release"
    } catch {
        throw "Не удалось скачать артефакты v$version: $_"
    }
}

Write-Host "Режим выполнения: $Mode (версия $AppVersion)."
switch ($Mode) {
    'full' {
        Write-Host 'Mode=full: обновляю version.json, отправляю workflow и загружаю артефакты.'
        & powershell -ExecutionPolicy Bypass -File "${projectRoot}\update_version.ps1" -AppVersion $AppVersion
        Start-Workflow $AppVersion
        Download-Artifacts $AppVersion
    }
    'copy' {
        Write-Host 'Mode=copy: скачиваем только артефакты из релиза.'
        Download-Artifacts $AppVersion
    }
    'post-build' {
        Write-Host 'Mode=post-build: артефакты уже в release/, пропускаем сборку/загрузку.'
    }
}

$versionJsonSrc = Join-Path -Path $projectRoot -ChildPath 'version.json'
$exeSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-Setup-$AppVersion.exe"
$macSrc = Join-Path -Path $projectRoot -ChildPath "release\ClipartGenerator-macOS-$AppVersion.zip"
foreach ($path in @($versionJsonSrc, $exeSrc, $macSrc)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Отсутствует нужный файл: $path"
    }
}

Write-Host 'Копирую version.json и установщики в `_updates_repo_tmp`...'
Copy-Item -LiteralPath $versionJsonSrc -Destination (Join-Path $updatesRoot 'version.json') -Force
Copy-Item -LiteralPath $exeSrc -Destination (Join-Path $updatesRoot "ClipartGenerator-Setup-$AppVersion.exe") -Force
Copy-Item -LiteralPath $macSrc -Destination (Join-Path $updatesRoot "ClipartGenerator-macOS-$AppVersion.zip") -Force

Write-Host 'Готово. Что дальше:'
Write-Host " 1. cd $updatesRoot"
Write-Host ' 2. git status'
Write-Host " 3. git add version.json ClipartGenerator-Setup-$AppVersion.exe ClipartGenerator-macOS-$AppVersion.zip"
Write-Host ' 4. git commit / git push в _updates_repo_tmp, затем обновите релиз.'