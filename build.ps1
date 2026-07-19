param(
    [string]$AppVersion = "1.0.2"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "==> Install build dependencies"
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt

Write-Host "==> Clean previous build artifacts"
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }

Write-Host "==> Build app with PyInstaller"
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "Clipart Generator" `
    --add-data ".env.example;." `
    --add-data "third_party/remove_ai_watermarks_gemini/assets;third_party/remove_ai_watermarks_gemini/assets" `
    --add-data "third_party/remove_ai_watermarks_gemini/LICENSE;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/remove_ai_watermarks_gemini/NOTICE.md;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/migan/migan.onnx;third_party/migan" `
    --add-data "third_party/migan/LICENSE;third_party/migan" `
    --add-data "third_party/migan/NOTICE.md;third_party/migan" `
    --add-data "realesrgan-ncnn-vulkan-20211212-windows;realesrgan-ncnn-vulkan-20211212-windows" `
    main.py

Write-Host "==> Prepare release directory"
$releaseDir = Join-Path $projectRoot "release"
if (-not (Test-Path $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}

$versionFile = Join-Path $releaseDir "VERSION.txt"
"$AppVersion" | Out-File -FilePath $versionFile -Encoding utf8

Write-Host "Done: dist\\Clipart Generator"
