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
