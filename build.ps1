param(
    [string]$AppVersion = "",
    [switch]$AcceptanceBuild
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
if ($AcceptanceBuild -ne (Test-Path -LiteralPath "_acceptance_build.py")) {
    throw "Acceptance build flag must match the generated profile; production cannot bundle test trust."
}
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = "python"
}

Write-Host "==> Validate release version"
$releaseDir = Join-Path $projectRoot "release"
$versionFile = Join-Path $releaseDir "VERSION.txt"
if ([string]::IsNullOrWhiteSpace($AppVersion)) {
    if (-not (Test-Path -LiteralPath $versionFile)) {
        throw "Release version source is missing: $versionFile"
    }
    $AppVersion = (Get-Content -Raw $versionFile).Trim()
}
if ($AppVersion -notmatch '^\d+\.\d+(\.\d+)?$') {
    throw "AppVersion must be a semantic version such as 3.0 or 3.0.1"
}

Write-Host "==> Install build dependencies"
& $pythonExe -m pip install -c constraints-build.txt -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "Runtime dependency installation failed with exit code $LASTEXITCODE" }
& $pythonExe -m pip install -c constraints-build.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Build dependency installation failed with exit code $LASTEXITCODE" }

Write-Host "==> Clean previous build artifacts"
if (Test-Path "build") { Remove-Item "build" -Recurse -Force }
if (Test-Path "dist") { Remove-Item "dist" -Recurse -Force }

Write-Host "==> Prepare release version"
if (-not (Test-Path $releaseDir)) {
    New-Item -ItemType Directory -Path $releaseDir | Out-Null
}
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
    --add-data "assets/mode-clipart.png;assets" `
    --add-data "assets/mode-pinterest.png;assets" `
    --add-data "assets/mode-processing.png;assets" `
    --add-data "assets/studio-generation-cover.png;assets" `
    --add-data "assets/studio-patterns-cover.png;assets" `
    --add-data "assets/studio-mockups-cover.png;assets" `
    --add-data "assets/style_previews;assets/style_previews" `
    --add-data "assets/vibix-images.svg;assets" `
    --add-data "studio_builtin_workflows;studio_builtin_workflows" `
    --add-data "release/VERSION.txt;release" `
    --add-data "third_party/remove_ai_watermarks_gemini/assets;third_party/remove_ai_watermarks_gemini/assets" `
    --add-data "third_party/remove_ai_watermarks_gemini/LICENSE;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/remove_ai_watermarks_gemini/NOTICE.md;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/migan/migan.onnx;third_party/migan" `
    --add-data "third_party/migan/LICENSE;third_party/migan" `
    --add-data "third_party/migan/NOTICE.md;third_party/migan" `
    --add-data "realesrgan-ncnn-vulkan-20211212-windows;realesrgan-ncnn-vulkan-20211212-windows" `
    --collect-submodules "studio_builtin_workflows" `
    --collect-submodules "scipy._external.array_api_compat" `
    --collect-submodules "rembg.sessions" `
    --copy-metadata "rembg" `
    --copy-metadata "pymatting" `
    main.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

$distAppDir = Join-Path $projectRoot "dist\Vibix Images"
$AppExeName = "Vibix Images.exe"
if (-not (Test-Path -LiteralPath $distAppDir)) {
    throw "PyInstaller output is missing: $distAppDir"
}
& (Join-Path $projectRoot "scripts\remove_bundled_vc_runtime.ps1") -AppDir $distAppDir
if (-not (Test-Path -LiteralPath (Join-Path $distAppDir $AppExeName))) {
    throw "Packaged executable is missing: $(Join-Path $distAppDir $AppExeName)"
}

Write-Host "Done: dist\\Vibix Images\\$AppExeName"
