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
    --add-data "assets/studio-prompt-composer-cover.png;assets" `
    --add-data "assets/studio-patterns-cover.png;assets" `
    --add-data "assets/studio-mockups-cover.png;assets" `
    --add-data "assets/style_previews;assets/style_previews" `
    --add-data "assets/vibix-images.svg;assets" `
    --add-data "release/VERSION.txt;release" `
    --add-data "third_party/remove_ai_watermarks_gemini/assets;third_party/remove_ai_watermarks_gemini/assets" `
    --add-data "third_party/remove_ai_watermarks_gemini/LICENSE;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/remove_ai_watermarks_gemini/NOTICE.md;third_party/remove_ai_watermarks_gemini" `
    --add-data "third_party/migan/migan.onnx;third_party/migan" `
    --add-data "third_party/migan/LICENSE;third_party/migan" `
    --add-data "third_party/migan/NOTICE.md;third_party/migan" `
    --add-data "realesrgan-ncnn-vulkan-20211212-windows;realesrgan-ncnn-vulkan-20211212-windows" `
    --exclude-module "studio_builtin_workflows" `
    --exclude-module "v3_clipart_flow" `
    --exclude-module "v3_processing_flow" `
    --exclude-module "v3_pinterest_flow" `
    --exclude-module "studio_auto_clipart_flow" `
    --exclude-module "prompt_composer" `
    --hidden-import "chroma_key" `
    --hidden-import "chroma_key_selection" `
    --hidden-import "clipart_run_results" `
    --hidden-import "config_schema" `
    --hidden-import "fal_model_catalog" `
    --hidden-import "license_client" `
    --hidden-import "model_catalog" `
    --hidden-import "output_naming" `
    --hidden-import "processing_contract" `
    --hidden-import "prompt_translation" `
    --hidden-import "provider_error_messages" `
    --hidden-import "security_redaction" `
    --hidden-import "studio_bundle_planner" `
    --hidden-import "studio_object_editor" `
    --hidden-import "studio_prompt_composer_host" `
    --hidden-import "studio_text_errors" `
    --hidden-import "studio_text_models" `
    --hidden-import "studio_text_pricing" `
    --hidden-import "studio_workflow_host" `
    --hidden-import "v3_api_settings" `
    --hidden-import "v3_components" `
    --hidden-import "v3_evidence_center" `
    --hidden-import "v3_flow_runtime" `
    --hidden-import "v3_flow_ui" `
    --hidden-import "v3_image_generation_runtime" `
    --hidden-import "v3_image_generation_ui" `
    --hidden-import "v3_image_processing_ui" `
    --hidden-import "v3_image_review_ui" `
    --hidden-import "v3_image_worker_settings" `
    --hidden-import "v3_lazy_loading" `
    --hidden-import "v3_localization" `
    --hidden-import "v3_processing_editor" `
    --hidden-import "v3_project_state" `
    --hidden-import "v3_prompt_csv_import" `
    --hidden-import "v3_prompt_editor_ui" `
    --hidden-import "v3_prompt_generator" `
    --hidden-import "v3_provider_registry" `
    --hidden-import "v3_run_queue" `
    --hidden-import "v3_transparency_preview" `
    --hidden-import "workflow_definitions" `
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
