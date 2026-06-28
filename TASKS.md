# TASKS

Source spec: `PROCESSING_PIPELINE_TZ.md`.

Rule: take the next open task in order. Keep code changes narrow and do not refactor working code unless it directly makes the current task safer.

## Phase 1 - Preparation

- [x] Add `realesrgan-ncnn-vulkan-20211212-windows/` to `.gitignore`.
- [x] Add new default config keys in `main.py`.
- [x] Verify old config files still open without errors.

## Phase 2 - UI

- [x] Add upscale provider selection: `KIE` / `Local Real-ESRGAN`.
- [x] Add Local Real-ESRGAN settings: folder path, profile, scale.
- [x] Add background removal provider selection: `KIE` / `Local rembg`.
- [x] Add Local rembg settings: profile/model.
- [x] Add separate `Удалять контур` checkbox and `1/2/3 px` selector.
- [x] Wire new UI fields into settings save/load.

## Phase 3 - Local Real-ESRGAN

- [x] Validate path to `realesrgan-ncnn-vulkan.exe`.
- [x] Run Real-ESRGAN through `subprocess.run`.
- [x] Save Real-ESRGAN output into `raw/`.
- [x] Log the local upscale step without secrets or noisy command dumps.
- [x] Handle errors: missing exe, missing models, failed process, missing output file.

## Phase 4 - Local rembg

- [x] Import `rembg` lazily so the app can still start if model setup is not ready.
- [x] Create `new_session()` once per batch.
- [x] Implement local background removal for one file.
- [x] Save local rembg output as PNG with alpha.
- [x] Log clearly that the first model run can take longer.

## Phase 5 - Edge Shrink

- [x] Implement `shrink_alpha_edges`.
- [x] Run edge shrink after background removal.
- [x] Allow edge shrink without background removal when input already has alpha.
- [x] Clamp edge shrink pixels to `1..3`.

## Phase 6 - Pipeline Integration

- [x] Preserve current KIE-only behavior.
- [x] Support local-only processing without requiring KIE API Key.
- [x] Support mixed local -> KIE and KIE -> local flows.
- [x] Update `needs_kie_api` so KIE API Key is required only when a selected step actually uses KIE.

## Phase 7 - Documentation

- [x] Link `PROJECT_KNOWLEDGE_BASE.md` or a project page to `PROCESSING_PIPELINE_TZ.md`.
- [x] Add a short author instruction for Real-ESRGAN + rembg + edge shrink settings.

## Phase 8 - Verification

- [x] Run `python -m py_compile .\main.py`.
- [x] Test one image through local-only pipeline.
- [x] Test one image through mixed pipeline.
- [x] Inspect output on a dark background.
- [x] Verify Real-ESRGAN binaries/models are not tracked by git.

## Phase 9 - Local rembg Settings

- [x] Add a local rembg edge quality setting with `Soft`, `Normal`, and `Sharp` presets.
- [x] Save and load the local rembg edge quality setting with the rest of the UI config.
- [x] Apply local rembg edge quality only after local rembg output, without changing KIE behavior.
- [x] Verify the new setting with a targeted smoke test.

## Phase 10 - Fixed Processing Order and Unsharp Mask

- [x] Add optional Unsharp Mask settings after upscale.
- [x] Allow custom Unsharp Mask amount, radius, and threshold values.
- [x] Fix processing order to `upscale -> unsharp -> remove background -> edge shrink -> trim`.
- [x] Remove the trim timing selector from the UI and config writes.
- [x] Verify compile, Unsharp Mask output, and a mixed pipeline smoke test.

## Phase 11 - Processing UI Order

- [x] Reorder the processing controls vertically to match the actual processing order.
- [x] Move each action's parameters to the right of that action.
- [x] Verify UI construction and settings save/load.

## Phase 12 - Processing UI Polish

- [x] Make Unsharp Mask independent from the upscale checkbox.
- [x] Keep the edge contour pixel selector compact.
- [x] Fix processing provider settings layout so price labels and rembg model fields do not overlap.
- [x] Verify UI construction, settings save/load, and Unsharp Mask without upscale.

## Phase 13 - Provider Settings UI Cost Labels

- [x] Move KIE processing cost labels next to their model selectors.
- [x] Keep the provider settings grid compact without overlapping rembg fields.
- [x] Verify UI construction and settings save/load.

## Phase 14 - Inline Processing Cost Labels

- [x] Put each KIE processing cost label in the same row widget as its model selector.
- [x] Verify UI construction and settings save/load.

## Phase 15 - BEN2 Evaluation Script

- [x] Add a standalone BEN2 background removal test script.
- [x] Document the exact command to install and run BEN2 testing.
- [x] Verify the script compiles and exposes help without requiring BEN2 to be installed.

## Phase 16 - Local BEN2 Provider

- [x] Add Local BEN2 as an experimental background removal provider.
- [x] Add BEN2 hard alpha threshold, edge softness, and corner radius settings.
- [x] Keep BEN2 default output hard-edged with no semi-transparent alpha.
- [x] Save and load BEN2 settings with the rest of the processing config.
- [x] Let local BEN2 processing run without requiring a KIE API key.
- [x] Verify compile, UI settings save/load, and hard-alpha post-processing.
