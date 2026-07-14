# TASKS

Source specs: `PRD.md` and `PROCESSING_PIPELINE_TZ.md`.

Rule: take the next open task in order. Keep code changes narrow and do not refactor working code unless it directly makes the current task safer.

For each task: explain the plan, implement only that task, verify it, update `TASKS.md` and `CHANGELOG.md`, then commit and push. Do not build, tag, publish, or create a release unless the user requests it separately.

Current next task: **Task 23 - Cleanup Capability And Safety Matrix**.

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

## Phase 17 - Local Real-ESRGAN Scale Fix

- [x] Diagnose square/tile artifacts in Local Real-ESRGAN `2x` output.
- [x] Use a scale-compatible Real-ESRGAN model for `Clipart 2x`.
- [x] Keep Local Real-ESRGAN `2x` and `4x` available in the UI.
- [x] Remove unsupported local `3x` from the scale selector.
- [x] Verify compile and local command/model selection smoke tests.

## Phase 18 - Local Real-ESRGAN Alpha Preservation

- [x] Diagnose fully transparent output when upscaling an already-trimmed RGBA PNG.
- [x] Run Local Real-ESRGAN on a temporary RGB composite when the input has alpha.
- [x] Restore the upscaled alpha channel after Local Real-ESRGAN finishes.
- [x] Verify compile and a real Local Real-ESRGAN run on the affected bird PNG.

## Open Tasks - Execute In Order

## Task 19 - Automated MVP Baseline

Status: Done

Goal:
Prove that the current application starts and accepts old settings before adding another processing feature.

Steps:
- Compile and import `main.py`.
- Construct `MainWindow` in Qt offscreen mode.
- Load an isolated legacy config with the newer processing keys omitted and verify safe defaults.
- Fix only blocking regressions discovered by these checks, then rerun the same checks.

Acceptance:
- [x] The module compiles and imports without errors.
- [x] The main window constructs without changing the current UI layout.
- [x] Existing config files remain compatible and missing keys receive defaults.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -c "import main; app=main.QApplication([]); w=main.MainWindow(); print('SMOKE_OK')"`
- [x] Isolated legacy-config smoke returned `LEGACY_CONFIG_OK` without reading or changing the user's real config.

Notes:
- Do not use the user's real config or print stored keys.
- No build or release work belongs to this task.

## Task 20 - Local Processing Acceptance

Status: Done

Goal:
Verify the main process-only workflow without KIE and prevent recurrence of the alpha and tiled-upscale regressions.

Steps:
- Add reusable owned RGB and RGBA test fixtures or generate synthetic fixtures during the test.
- Test Local Real-ESRGAN at `2x` and `4x`, including exact dimensions and restored alpha.
- Test Unsharp Mask, Local rembg/BEN2, hard alpha, edge shrink, trim, `raw/`, and final `output/` in pipeline order.
- Inspect one transparent result on a dark background.

Acceptance:
- [x] Process-only local mode works without a KIE key.
- [x] `2x` and `4x` outputs have correct dimensions without tile artifacts.
- [x] Transparent PNG output is non-empty and keeps a valid alpha channel.
- [x] The final order remains `upscale -> unsharp -> remove background -> edge shrink -> trim -> save`.

Verification:
- [x] `python -m unittest tests.test_local_processing_acceptance -v`
- [x] Manual dark-background comparison is recorded in `CHANGELOG.md`.

Notes:
- Use the existing local Real-ESRGAN folder; do not add its binaries or models to git.

## Task 21 - KIE And Mixed Workflow Acceptance

Status: Done

Goal:
Confirm API-key routing and the generation/mixed workflows without changing provider behavior.

Steps:
- Test key validation for local-only, KIE-only, and mixed selections without making network calls.
- Run one minimal generate-only check and one mixed processing check when a valid KIE key is available.
- Verify progress messages, `raw/`, `output/`, and error handling without logging secrets.

Acceptance:
- [x] Local-only mode never asks for a KIE key.
- [x] KIE-only and mixed modes request the key only when a selected step uses KIE.
- [x] Generate-only and mixed workflows save the expected files.
- [x] No API key or secret appears in logs.

Verification:
- [x] `python -m unittest tests.test_kie_routing -v`
- [x] Live KIE smoke was not run to avoid consuming credits; network-free generate-only and mixed-flow tests were used instead.

Notes:
- A live check can consume credits; keep it to the smallest useful sample.

## Task 22 - MVP Acceptance Closeout

Status: Done

Goal:
Close the current MVP against the product documents before starting post-MVP cleanup features.

Steps:
- Review `README_AUTHOR_SHORT.md`, `PRD.md`, `TASKS.md`, `CHANGELOG.md`, and `TEST_CHECKLIST.md` against the verified behavior.
- Complete the non-release sections of `TEST_CHECKLIST.md`.
- Fix only blocking issues; record non-blocking improvements as later tasks.
- Update PRD acceptance checkboxes only where evidence exists.

Acceptance:
- [x] Every MVP acceptance criterion is either verified or explicitly reserved for the release checklist.
- [x] Documentation matches the actual UI and processing order.
- [x] No build, release, tag, or update-repository action is performed.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest discover -s tests -v`
- [x] Manual and automated main-flow evidence is recorded in `CHANGELOG.md`.

Notes:
- Closed with 14 passing tests. Live KIE and release-only visual/build checks remain intentionally open until an explicit release request.

## Task 22A - GPT Image 2 KIE Model Routing Hotfix

Status: Done

Goal:
Restore GPT Image 2 generation in the current application without importing release-only changes from the 1.0.3 hotfix branch.

Steps:
- Keep the UI/config model id as `gpt-image-2`.
- Route KIE requests without references to `gpt-image-2-text-to-image`.
- Route KIE requests with references to `gpt-image-2-image-to-image`.
- Apply the same routing to model availability probes and normalize saved endpoint ids back to the UI id.
- Add network-free regression tests for both routes.

Acceptance:
- [x] Text-to-image and image-to-image requests use the documented KIE model ids.
- [x] The visible model name and saved config remain compatible with `gpt-image-2`.
- [x] Other generation models are unchanged.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest tests.test_kie_routing -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Live KIE generation is excluded from this task to avoid consuming credits; the same routing was previously verified live in the isolated 1.0.3 hotfix.

## Task 23 - Cleanup Capability And Safety Matrix

Status: Todo - next safe task

Goal:
Define exactly what can be inspected or removed reliably before adding cleanup controls.

Steps:
- Research current official documentation for Nano Banana/Gemini marks, standard image metadata, provenance manifests, and pixel-level hidden markers.
- Separate four categories: ordinary metadata, AI/service metadata, embedded provenance manifests, and pixel-level watermarks.
- Define supported input/output formats and ownership/licensing limits.
- Decide which actions can be labelled `remove`, which are only `detect/report`, and which are unsupported.

Acceptance:
- [ ] A durable capability matrix lists supported, detectable-only, and unsupported items.
- [ ] Every factual claim has an official or primary source.
- [ ] The plan does not promise reliable removal of unknown pixel-level markers.

Verification:
- [ ] The capability matrix is linked from `PRD.md` and `PROJECT_KNOWLEDGE_BASE.md`.

Notes:
- This research task must finish before implementation choices are locked.

## Task 24 - Read-Only Metadata Inspector

Status: Todo

Goal:
Inspect cleanup-relevant data without modifying the source image.

Steps:
- Add a small metadata inspection component outside the UI code.
- Report EXIF, XMP, IPTC, comments, embedded thumbnails, ICC profile, DPI, and supported provenance fields.
- Return structured results suitable for tests, logs, and later UI controls.
- Add fixtures for PNG, JPEG, and transparent PNG.

Acceptance:
- [ ] Inspection never modifies the source file.
- [ ] Present and absent categories are reported accurately.
- [ ] The inspector does not expose unrelated sensitive file contents in logs.

Verification:
- [ ] `python -m unittest tests.test_metadata_inspector -v`

Notes:
- Prefer Pillow and standard-library capabilities already available in the project.

## Task 25 - Selective Metadata Cleanup Engine

Status: Todo

Goal:
Remove only selected metadata categories while preserving image quality and explicitly retained export data.

Steps:
- Implement independent cleanup options for ordinary metadata, AI/service metadata, and supported embedded provenance data.
- Add separate preservation options for ICC color profile and DPI.
- Keep pixels and alpha unchanged during metadata-only cleanup.
- Save through a temporary output and replace only after successful validation.

Acceptance:
- [ ] Checked categories are removed and unchecked categories remain.
- [ ] ICC and 300 DPI are preserved when selected.
- [ ] Pixel values, dimensions, and alpha are unchanged.
- [ ] A failed cleanup leaves the source and previous output intact.

Verification:
- [ ] `python -m unittest tests.test_metadata_cleanup -v`

Notes:
- This task contains no visible-mark removal.

## Task 26 - Metadata Cleanup UI And Settings

Status: Todo

Goal:
Let the user choose cleanup actions independently without changing existing defaults.

Steps:
- Add a compact `Очистка файла` section in processing order near final export.
- Add independent checkboxes for supported cleanup categories.
- Add explicit `Сохранить ICC-профиль` and `Сохранить DPI` choices.
- Save and restore new settings with safe defaults disabled for existing users.

Acceptance:
- [ ] Each supported cleanup action can be enabled or disabled separately.
- [ ] Parameter controls are placed to the right of their action where applicable.
- [ ] Old config files load without errors and preserve current behavior.

Verification:
- [ ] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_cleanup_ui -v`

Notes:
- Do not rearrange unrelated controls.

## Task 27 - Final-Save Cleanup Integration

Status: Todo

Goal:
Run metadata cleanup once, at final save, for generated and process-only outputs.

Steps:
- Integrate the cleanup engine into the shared final PNG save path.
- Keep image processing order unchanged before final save.
- Log categories found, selected, removed, preserved, or unsupported without exposing secrets.
- Preserve `raw/` intermediates for diagnostics.

Acceptance:
- [ ] Generate-and-process, process-only, local, and mixed outputs use the same final cleanup behavior.
- [ ] Cleanup runs after trim and before the final file is reported complete.
- [ ] Disabled cleanup produces behavior equivalent to the current application.

Verification:
- [ ] `python -m unittest tests.test_final_save_cleanup -v`
- [ ] `python -m unittest discover -s tests -v`

Notes:
- This is the first user-complete metadata-cleanup slice.

## Task 28 - Hidden Provenance Handling

Status: Todo

Goal:
Handle only hidden provenance data confirmed as detectable or removable by Task 23.

Steps:
- Implement detection for supported metadata-based or manifest-based provenance markers.
- Remove them only when the matching checkbox is enabled and the capability matrix marks removal as reliable.
- Report pixel-level markers as detected, unknown, or unsupported instead of claiming success.

Acceptance:
- [ ] Supported provenance data follows the selected checkbox.
- [ ] Unsupported pixel-level markers are never reported as removed.
- [ ] Transparency, ICC, DPI, and visible pixels remain correct.

Verification:
- [ ] `python -m unittest tests.test_provenance_cleanup -v`

Notes:
- Do not add destructive image transformations merely to defeat an unknown hidden signal.

## Task 29 - Visible Generator-Mark Prototype

Status: Todo

Goal:
Determine whether visible Nano Banana/Gemini service marks can be removed locally without damaging clipart.

Steps:
- Use only owned or licensed test images with known visible marks.
- Compare automatic detection, a user-confirmed mask, and a manual fallback.
- Test the candidate step before upscale and compare edges, texture, transparency, and false positives.
- Reject automatic integration if quality is inconsistent.

Acceptance:
- [ ] Before/after samples show no unacceptable damage outside the marked region.
- [ ] False-positive behavior is measured on unmarked images.
- [ ] A clear go/no-go decision and fallback are documented.

Verification:
- [ ] Visual comparisons are saved outside git unless they are small, licensed fixtures.
- [ ] The decision is recorded in the project page and `CHANGELOG.md`.

Notes:
- This is a prototype, not automatic approval to change the production pipeline.

## Task 30 - Visible Mark Controls And Pipeline Integration

Status: Todo - conditional on Task 29 go decision

Goal:
Expose visible-mark cleanup only if the prototype meets the documented quality threshold.

Steps:
- Add a separate checkbox and only the controls required by the approved method.
- Run visible-mark cleanup before upscale; keep metadata cleanup at final save.
- Save and restore settings with the feature disabled by default.
- Log when a mark is not found or when user confirmation is required.

Acceptance:
- [ ] The feature can be enabled independently from all other cleanup actions.
- [ ] Unmarked images remain unchanged when no mark is found.
- [ ] Existing processing behavior is unchanged while the checkbox is off.

Verification:
- [ ] `python -m unittest tests.test_visible_mark_cleanup -v`
- [ ] Manual visual checks cover marked and unmarked clipart.

Notes:
- If Task 29 is no-go, mark this task `Skipped` and implement only the documented fallback.

## Task 31 - Post-MVP Cleanup Acceptance

Status: Todo

Goal:
Verify the complete cleanup feature against the PRD without performing release work.

Steps:
- Review `PRD.md`, `TASKS.md`, `CHANGELOG.md`, the capability matrix, and author documentation.
- Run all automated tests and the non-release main-flow checklist.
- Verify every checkbox independently and in a combined local pipeline.
- Fix blocking issues and record remaining optional improvements after this task.

Acceptance:
- [ ] Cleanup choices are independent, persistent, and disabled by default for old users.
- [ ] Metadata cleanup preserves selected ICC/DPI and never changes pixels or alpha.
- [ ] Hidden and visible mark claims match tested capabilities.
- [ ] The application remains usable for generation and processing with cleanup disabled.

Verification:
- [ ] `python -m py_compile .\main.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] Manual output comparison on light and dark backgrounds is recorded.

Notes:
- Finish with documentation, commit, and push only. Do not build or publish a release.
