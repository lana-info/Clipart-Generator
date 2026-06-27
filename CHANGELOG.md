# CHANGELOG

## Unreleased

### Added

- Added `PROCESSING_PIPELINE_TZ.md` with the final processing pipeline specification.
- Added `TASKS.md` with the ordered implementation checklist for local Real-ESRGAN, local rembg, edge shrink, and verification.
- Added default config keys for future local Real-ESRGAN, local rembg, and edge shrink settings.
- Added an upscale provider selector for `KIE` and `Local Real-ESRGAN` in processing settings.
- Added Local Real-ESRGAN settings for folder path, profile, and scale.
- Added a background removal provider selector for `KIE` and `Local rembg`.
- Added Local rembg settings for profile and model selection.
- Added a separate edge contour removal checkbox with a `1/2/3 px` selector.
- Added Local Real-ESRGAN executable path validation before runs that use local upscale.
- Added the Local Real-ESRGAN subprocess runner with profile and scale command arguments.
- Added a Local Real-ESRGAN pipeline step that writes intermediate upscale output into `raw/`.
- Added concise Local Real-ESRGAN progress logs without dumping full commands.
- Added Local Real-ESRGAN error handling for missing `models/`, failed subprocess runs, and missing output files.
- Added lazy Local rembg imports so app startup does not require rembg/backend readiness.
- Added per-batch Local rembg session caching.
- Added Local rembg background removal for a single file.
- Added Local rembg PNG/RGBA output saving.
- Added a Local rembg first-run progress message before model session initialization.
- Added alpha edge shrinking for PNG outputs.
- Added edge shrink after background removal with intermediate output saved in `raw/`.
- Added edge-only processing for images that already have an alpha channel.
- Added clamping for edge shrink strength to `1..3`.
- Added local-only and mixed local/KIE processing pipeline routing.
- Added `LOCAL_PROCESSING_PROJECT_PAGE.md` with links to the processing spec and author setup instructions.
- Added an early `onnxruntime` preload to avoid a Windows DLL import-order conflict between PyQt6 and rembg.
- Added a local rembg edge quality setting with `Soft`, `Normal`, and `Sharp` presets.
- Added optional Unsharp Mask after upscale with custom amount, radius, and threshold settings.

### Changed

- Ignored local `realesrgan-ncnn-vulkan-20211212-windows/` binaries and models so they do not get committed.
- KIE API key validation now depends on the selected processing providers instead of any enabled processing step.
- Changed the rembg requirement to `rembg[cpu]` so fresh installs include the CPU backend.
- Fixed the processing order to `upscale -> Unsharp Mask -> remove background -> edge shrink -> trim`.
- Removed the trim timing selector from the UI; trim now always runs at the end.
- Reordered the processing controls vertically to match the actual processing order, with each step's parameters on the right.
- Made Unsharp Mask an independent processing step that can run without upscale.
- Compacted the edge contour pixel selector and adjusted processing provider settings to prevent price/model field overlap.

### Verified

- Verified legacy config files load successfully and receive the new local processing defaults without changing existing values.
- Verified new processing UI settings save to config and load back correctly in an isolated headless smoke test.
- Verified Local Real-ESRGAN path validation for missing paths, missing exe, valid folders, direct exe paths, and KIE/generate-only bypass cases.
- Verified the Local Real-ESRGAN subprocess command, working directory, default profile/scale normalization, and non-zero exit handling with a monkeypatched smoke test.
- Verified Local Real-ESRGAN intermediate output path generation under `raw/`.
- Verified Local Real-ESRGAN progress logs include profile, scale, and output path without command dumps.
- Verified Local Real-ESRGAN error handling for missing exe, missing models, failed process, missing output, and successful output creation.
- Verified `main.py` imports without importing rembg and that rembg/backend failures are reported only when the lazy helper is called.
- Verified Local rembg `new_session()` is called once and reused for repeated worker calls.
- Verified Local rembg reads input bytes, passes the cached session to `remove`, and writes PNG output.
- Verified Local rembg output is saved as PNG with an alpha channel.
- Verified the Local rembg first-run message placement with AST parsing and targeted source search.
- Verified alpha edge shrinking on a synthetic RGBA PNG preserves RGB and erodes only alpha.
- Verified edge shrink runs after background removal and the resulting local file can be saved as the final output.
- Verified edge-only processing shrinks transparent PNG inputs and skips RGB inputs without alpha.
- Verified edge shrink pixel normalization for invalid, too-low, valid, and too-high values.
- Verified Phase 6 routing for local-only processing without KIE key, local -> KIE, KIE -> local, and KIE-only URL behavior with a smoke test.
- Verified `python -m py_compile .\main.py`.
- Verified a real local-only image through Local Real-ESRGAN, Local rembg, edge shrink, trim, and PNG output.
- Verified a mixed local Real-ESRGAN -> KIE remove-background pipeline with a network-free smoke test.
- Verified the local-only output composites on a dark background and keeps an alpha channel.
- Verified Real-ESRGAN binaries/models are ignored and not tracked by git.
- Verified local rembg edge quality normalization and alpha-channel post-processing with a targeted smoke test.
- Verified the local rembg edge quality UI setting saves into config in an offscreen smoke test.
- Verified Unsharp Mask normalization and output with a targeted smoke test.
- Verified the Unsharp Mask UI settings save into config and the trim timing selector is absent.
- Verified mixed KIE/local order with Unsharp Mask before background removal.
- Verified the reordered processing controls construct and save settings in an offscreen UI smoke test.
- Verified Unsharp Mask can run as the only processing step without upscale.
- Verified compact edge contour and provider settings UI construction in an offscreen smoke test.
