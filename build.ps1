param(
    [string]$AppVersion = "3.0"
)

$ErrorActionPreference = "Stop"

if ($AppVersion -notmatch '^\d+\.\d+(\.\d+)?$') {
    throw "AppVersion must be a semantic version such as 3.0 or 3.0.1"
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "==> Install build dependencies"
& $pythonExe -m pip install -r requirements.txt
& $pythonExe -m pip install -r requirements-dev.txt

Write-Host "==> Clean previous build artifacts"
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }

Write-Host "==> Prepare release version"
$releaseDir = Join-Path $projectRoot "release"
if (-not (Test-Path $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}
$versionFile = Join-Path $releaseDir "VERSION.txt"
[System.IO.File]::WriteAllText($versionFile, "$AppVersion`r`n", [System.Text.UTF8Encoding]::new($false))

Write-Host "==> Build app with PyInstaller"
& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "Vibix Images" `
    --icon "assets/vibix-images.ico" `
    --add-data ".env.example;." `
    --add-data "assets/vibix-images.ico;assets" `
    --add-data "release/VERSION.txt;release" `
    --add-data "third_party/remove_ai_watermarks_gemini/assets;third_party/remove_ai_watermarks_gemini/assets" `
    --add-data "third_party/remove_ai_watermarks_gemini/LICENSE;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/remove_ai_watermarks_gemini/NOTICE.md;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/migan/migan.onnx;third_party/migan" `
    --add-data "third_party/migan/LICENSE;third_party/migan" `
    --add-data "third_party/migan/NOTICE.md;third_party/migan" `
    --add-data "realesrgan-ncnn-vulkan-20211212-windows;realesrgan-ncnn-vulkan-20211212-windows" `
    main.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$distAppDir = Join-Path $projectRoot "dist\Vibix Images"
if (-not (Test-Path -LiteralPath $distAppDir)) {
    throw "PyInstaller output is missing: $distAppDir"
}

Write-Host "Done: dist\\Vibix Images"
