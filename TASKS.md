# TASKS

Source specs: `PRD.md` and `PROCESSING_PIPELINE_TZ.md`.

Rule: take the next open task in order. Keep code changes narrow and do not refactor working code unless it directly makes the current task safer.

For each task: explain the plan, implement only that task, verify it, update `TASKS.md` and `CHANGELOG.md`, then commit and push. Do not build, tag, publish, or create a release unless the user requests it separately.

Current next task: **Task 24 - Read-Only Metadata Inspector**.

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

## Task 22B - PhotoRoom Standard Background Removal

Status: Done

Goal:
Add PhotoRoom Standard as an independent background-removal provider without changing existing provider behavior.

Steps:
- Add a separate masked PhotoRoom API key field and lock in Settings.
- Add `PhotoRoom Standard` to the background provider selector.
- Send local image files to the documented `/v1/segment` endpoint as PNG/RGBA/full-size output.
- Validate the returned image before saving it into `raw/`.
- Require only the key for the provider actually selected and keep secrets out of logs.

Acceptance:
- [x] PhotoRoom Standard can be selected independently from KIE, rembg, and BEN2.
- [x] Process-only PhotoRoom does not require a KIE API key.
- [x] A missing PhotoRoom key or invalid response produces an actionable error.
- [x] The PhotoRoom key and provider selection save and restore safely.
- [x] Existing providers and processing order remain unchanged.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest tests.test_photoroom_provider -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Standard mode uses `https://sdk.photoroom.com/v1/segment`; no paid live request is required for automated verification.
- Verification passed with 4 focused PhotoRoom tests and 20 tests in the full suite; no live PhotoRoom credits were spent.

## Task 22C - Upscale Before And After Background Removal

Status: Done

Goal:
Allow upscale before background removal, after background removal, or at both positions.

Steps:
- Replace the single upscale step with independent before/after controls.
- Give each enabled pass its own provider and `2x/4x` scale settings.
- Preserve current behavior for old configs: before enabled, after disabled.
- Show the combined multiplier when both passes are enabled.
- Keep edge cleanup and trim after the final upscale pass.

Acceptance:
- [x] Before-only, after-only, and both-pass pipelines run in the selected order.
- [x] `2x + 2x` produces `4x`; `4x + 4x` clearly reports `16x` before processing.
- [x] Transparent PNG alpha remains valid after a post-removal upscale.
- [x] Existing configs retain their current before-upscale behavior.

Verification:
- [x] `python -m unittest tests.test_upscale_positions -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Verification passed with 4 focused tests and 24 tests in the full suite. The Settings layout was also rendered offscreen at `1100x900` without control overlap.

## Task 23 - Cleanup Capability And Safety Matrix

Status: Done

Goal:
Define exactly what can be inspected or removed reliably before adding cleanup controls.

Steps:
- Research current official documentation for Nano Banana/Gemini marks, standard image metadata, provenance manifests, and pixel-level hidden markers.
- Separate four categories: ordinary metadata, AI/service metadata, embedded provenance manifests, and pixel-level watermarks.
- Define supported input/output formats and ownership/licensing limits.
- Decide which actions can be labelled `remove`, which are only `detect/report`, and which are unsupported.

Acceptance:
- [x] A durable capability matrix lists supported, detectable-only, and unsupported items.
- [x] Every factual claim has an official or primary source.
- [x] The plan does not promise reliable removal of unknown pixel-level markers.

Verification:
- [x] The capability matrix is linked from `PRD.md` and `PROJECT_KNOWLEDGE_BASE.md`.

Notes:
- This research task must finish before implementation choices are locked.
- Decision: file metadata can be inspected and selectively removed; embedded C2PA removal is narrowly scoped to the new export and requires fixture validation; pixel-level markers may use a separate experimental whole-image regeneration mode but are not metadata-removal features.
- Candidate review: `lana-info/remove-ai-watermarks` is Apache-2.0 and suitable for a local prototype; KIE and OpenRouter expose generic image editing but no documented hidden-image-watermark remover.
- Sources were checked on 2026-07-13 against Google Gemini/SynthID, C2PA 2.4, W3C PNG, IPTC 2025.1, Pillow, Adobe Content Credentials, c2patool, `remove-ai-watermarks`, KIE, and OpenRouter documentation.

## Phase 19 - Metadata And Provenance Cleanup

## Task 24 - Read-Only Metadata Inspector Foundation

Status: Todo - next safe task

Goal:
Inspect ordinary PNG/JPEG metadata without modifying the source file.

Steps:
- Add a focused inspector module outside `main.py`.
- Detect PNG/JPEG by file content and reject unsupported or animated inputs clearly.
- Return structured presence/size summaries for EXIF, XMP, IPTC, comments/text, thumbnails, ICC, DPI, and known generator fields.
- Never emit full metadata values to normal logs.
- Add synthetic PNG, transparent PNG, JPEG, and unsupported-format fixtures.

Acceptance:
- [ ] The source hash, size, and modification timestamp remain unchanged after inspection.
- [ ] Present, absent, and unsupported categories are reported deterministically.
- [ ] Results are serializable and usable by tests, logs, and future UI.

Verification:
- [ ] `python -m unittest tests.test_metadata_inspector -v`

Notes:
- Prefer Pillow and standard-library parsing already available in the project.

## Task 25 - Bounded C2PA Presence Inspector

Status: Todo

Goal:
Detect embedded C2PA structures locally without validating signatures or using the network.

Steps:
- Detect PNG `caBX` and JPEG APP11/JUMBF structures with strict length bounds.
- Return `present`, `not present`, or `not validated` separately from ordinary metadata.
- Add malformed, truncated, and oversized-segment fixtures.
- Integrate the result into the Task 24 inspector schema.

Acceptance:
- [ ] Detection never claims a manifest is valid.
- [ ] Corrupt inputs fail safely without unbounded reads or memory allocation.
- [ ] No remote manifest is fetched automatically.

Verification:
- [ ] `python -m unittest tests.test_c2pa_inspector -v`

Notes:
- Do not add `c2pa-python` until its packaging and build impact are explicitly justified.

## Task 26 - Selective Metadata Cleanup Core

Status: Todo

Goal:
Remove selected ordinary and AI/service metadata while preserving selected export data and image pixels.

Steps:
- Add a cleanup module with independent EXIF, XMP, IPTC, comments/text, thumbnail, and known-generator options.
- Use a documented allowlist for AI/service fields instead of deleting unknown fields by guess.
- Preserve ICC and DPI independently when selected.
- Write to a temporary PNG, validate it, then atomically publish the new output.
- Compare decoded pixels, dimensions, and alpha before and after metadata-only cleanup.

Acceptance:
- [ ] Checked categories are removed and unchecked categories remain where the output format supports them.
- [ ] ICC and 300 DPI are preserved when selected.
- [ ] Pixel values, dimensions, and alpha are unchanged.
- [ ] A failure leaves the source and previous output intact.

Verification:
- [ ] `python -m unittest tests.test_metadata_cleanup -v`

Notes:
- This task contains no C2PA or visible/pixel watermark handling.

## Task 27 - C2PA Export Cleanup

Status: Todo

Goal:
Remove supported embedded C2PA data or references from the new PNG export when explicitly selected.

Steps:
- Add owned PNG/JPEG fixtures containing embedded-manifest and remote-reference structures.
- Ensure the new PNG does not carry selected embedded C2PA structures or selected external-manifest references.
- Re-run the inspector after export and distinguish removed file structures from remote records and soft bindings.
- Abort publication if post-save validation does not match the selected action.

Acceptance:
- [ ] Embedded structures selected for cleanup are absent from the new PNG.
- [ ] The source file remains unchanged.
- [ ] Logs never claim that remote manifests or pixel soft bindings were deleted.

Verification:
- [ ] `python -m unittest tests.test_c2pa_cleanup -v`

Notes:
- This task validates the limited `REMOVE` claim in `CLEANUP_CAPABILITY_MATRIX.md`.

## Task 28 - Metadata Cleanup UI And Settings

Status: Todo

Goal:
Expose independent metadata/C2PA cleanup choices without changing current defaults.

Steps:
- Add a compact `Очистка файла` section near final export.
- Add independent controls for supported metadata categories and embedded C2PA.
- Add `Сохранить ICC-профиль` and `Сохранить DPI` choices to the right of the related action.
- Save and restore settings; cleanup remains disabled for legacy configs while preservation options default to enabled.

Acceptance:
- [ ] Every supported category can be enabled independently.
- [ ] Old config files preserve current processing behavior.
- [ ] Controls do not overlap at the supported offscreen viewport.

Verification:
- [ ] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_cleanup_ui -v`

Notes:
- Do not rearrange unrelated controls.

## Task 29 - Shared Final-Save Cleanup Integration

Status: Todo

Goal:
Run selected metadata cleanup once through the shared final-save path.

Steps:
- Integrate inspection and cleanup after trim and before final completion is reported.
- Use the same path for generate-only, generate-and-process, process-only, local, and mixed runs.
- Keep `raw/` intermediates unchanged for diagnostics.
- Log found, removed, preserved, unsupported, and failed categories without metadata values or secrets.

Acceptance:
- [ ] Disabled cleanup is behaviorally equivalent to the current application.
- [ ] Every final workflow uses the same cleanup decision and validation path.
- [ ] A cleanup failure does not publish a corrupt or partial output.

Verification:
- [ ] `python -m unittest tests.test_final_save_cleanup -v`
- [ ] `python -m unittest discover -s tests -v`

Notes:
- This is the first user-complete cleanup slice.

## Task 30 - Metadata Cleanup Acceptance And Documentation

Status: Todo

Goal:
Close the metadata/C2PA slice before starting pixel-changing watermark work.

Steps:
- Review PRD, capability matrix, task results, changelog, and author instructions.
- Verify every cleanup checkbox separately and in one combined local pipeline.
- Record exact supported formats, preservation behavior, and unsupported claims.
- Fix only blocking issues discovered by this review.

Acceptance:
- [ ] Documentation matches tested behavior.
- [ ] Metadata cleanup never changes visible pixels or alpha.
- [ ] Existing processing remains usable with cleanup disabled.

Verification:
- [ ] `python -m py_compile .\main.py`
- [ ] `python -m unittest discover -s tests -v`

Notes:
- Do not start visible-mark work until this gate passes.

## Phase 20 - Visible Generator Marks

## Task 31 - Local Visible-Mark Detector Prototype

Status: Todo

Goal:
Measure whether `lana-info/remove-ai-watermarks` reliably localizes supported visible generator marks.

Steps:
- Pin and record the evaluated repository commit and Apache-2.0 attribution requirements.
- Run detection outside the application on owned marked and unmarked fixtures.
- Save only masks, confidence, location, and timing results; do not change production code.
- Measure false positives across clipart, photos, illustrations, and textured corners.

Acceptance:
- [ ] Supported marks have documented detection rates.
- [ ] False positives are measured on unmarked images.
- [ ] No heavy dependency is added to the main application.

Verification:
- [ ] Prototype command and results are recorded in the project documentation.

Notes:
- Detection approval does not approve an inpainting backend.

## Task 32 - Local Visible-Mark Inpainting Benchmark

Status: Todo

Goal:
Choose a local fill method for confirmed masks without unacceptable damage outside the marked region.

Steps:
- Compare cv2, MI-GAN, and LaMa where available using the same masks.
- Compare automatic masks with a user-confirmed rectangular/mask fallback.
- Measure changed pixels outside the requested mask and inspect texture continuity.
- Record runtime, RAM, model downloads, and supported image classes.

Acceptance:
- [ ] A local default and fallback are selected or local inpainting is rejected.
- [ ] No accepted result changes pixels outside the documented safety margin unexpectedly.
- [ ] Failures leave the original image unchanged.

Verification:
- [ ] Before/after/mask comparisons are inspected on owned fixtures.

Notes:
- Keep benchmark assets outside git unless small and redistributable.

## Task 33 - KIE Mask-Edit Benchmark

Status: Todo

Goal:
Determine whether KIE 4o mask editing is a better fallback for visible marks than local inpainting.

Steps:
- Use the smallest useful paid sample set with the existing KIE key.
- Send explicit masks and prompts; preserve original aspect ratio and request PNG.
- Compare changes inside and outside the mask, output metadata, cost, and latency.
- Record provider errors and invalid-output handling.

Acceptance:
- [ ] KIE is compared against the selected local method on identical fixtures.
- [ ] Cost and visible changes outside the mask are recorded.
- [ ] No KIE key appears in logs or saved artifacts.

Verification:
- [ ] Manual comparison and request-cost evidence are recorded.

Notes:
- This task spends credits and must remain a minimal benchmark.

## Task 34 - Visible-Mark Provider Decision Gate

Status: Todo

Goal:
Choose local, KIE, user-confirmed-only, or no automatic visible-mark removal.

Steps:
- Compare Tasks 31-33 against one quality rubric.
- Select supported marks, image classes, default provider, and fallback.
- Update the capability matrix and mark Tasks 35-37 active or skipped.

Acceptance:
- [ ] The decision is based on saved evidence rather than a single image.
- [ ] Automatic processing is rejected for any class with unsafe false positives.
- [ ] User-confirmed mask fallback remains available when automatic detection is not approved.

Verification:
- [ ] Decision and rationale are recorded in PRD/project documentation and changelog.

Notes:
- No production integration belongs to this gate.

## Task 35 - Visible-Mark UI And Settings

Status: Todo - conditional on Task 34 go decision

Goal:
Expose only the approved visible-mark controls.

Steps:
- Add an independent visible-mark checkbox and approved provider/mask controls.
- Place parameters to the right of the action and keep the step disabled by default.
- Save/load settings without affecting legacy configs.
- Show when user confirmation is required.

Acceptance:
- [ ] Controls match the Task 34 decision exactly.
- [ ] Existing UI remains unchanged while the feature is disabled.
- [ ] Unsupported automatic modes are not selectable.

Verification:
- [ ] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_ui -v`

Notes:
- If Task 34 is no-go, mark this task `Skipped`.

## Task 36 - Visible-Mark Pipeline Integration

Status: Todo - conditional on Task 34 go decision

Goal:
Run approved visible-mark cleanup before upscale without changing unrelated processing.

Steps:
- Insert the step before the first upscale pass.
- Save the result into `raw/` and validate dimensions, mode, and non-empty pixels.
- Leave unmarked images unchanged when no mark is confidently found.
- Handle cancellation, provider failure, and user-confirmation requirements safely.

Acceptance:
- [ ] The step runs only when enabled.
- [ ] Existing processing order after the step remains unchanged.
- [ ] Failed cleanup does not overwrite the source or previous final output.

Verification:
- [ ] `python -m unittest tests.test_visible_mark_pipeline -v`
- [ ] `python -m unittest discover -s tests -v`

Notes:
- Metadata cleanup still runs only at final save.

## Task 37 - Visible-Mark Acceptance

Status: Todo - conditional on Task 34 go decision

Goal:
Verify the complete visible-mark slice on marked and unmarked general images.

Steps:
- Test automatic and user-confirmed flows on approved image classes.
- Verify local-only and KIE-required key routing.
- Compare results at normal view and 200% zoom.
- Update supported/unsupported documentation.

Acceptance:
- [ ] Approved fixtures meet the recorded quality rubric.
- [ ] Unmarked fixtures remain unchanged.
- [ ] Logs and UI describe detection and removal accurately.

Verification:
- [ ] `python -m unittest tests.test_visible_mark_pipeline -v`
- [ ] Manual comparison is recorded in `CHANGELOG.md`.

Notes:
- Skip if Task 34 rejected production integration.

## Phase 21 - Hidden Pixel Markers: Managed API First

## Task 38 - Pixel-Watermark Status Contract

Status: Todo

Goal:
Represent hidden-marker evidence without turning metadata proxies into false removal claims.

Steps:
- Define structured statuses: `detected`, `not detected`, `not verified`, and `unsupported`.
- Keep metadata/C2PA hints separate from pixel-level detector evidence.
- Define the manual or official verification handoff for SynthID.
- Add safe log formatting and tests.

Acceptance:
- [ ] `not detected` never means proven human-made.
- [ ] Processing success is separate from detector result.
- [ ] Unknown markers never receive a false `removed` result.

Verification:
- [ ] `python -m unittest tests.test_watermark_status -v`

Notes:
- This contract is shared by KIE, OpenRouter, and any GPU worker.

## Task 39 - KIE Whole-Image Regeneration Prototype

Status: Todo

Goal:
Test whether the existing KIE integration is sufficient for whole-image regeneration before adding infrastructure.

Steps:
- Test GPT Image 2 image-to-image first and FLUX image-to-image as fallback.
- Do not use Google/Nano Banana models for SynthID removal because their outputs receive SynthID.
- Use owned photos, illustrations, text-heavy images, faces, and clipart.
- Record quality, dimensions, alpha behavior, latency, credits, and metadata/provenance added to outputs.
- Re-check a known SynthID sample through the available official verification flow.

Acceptance:
- [ ] KIE results are evaluated on all required image classes.
- [ ] Cost and quality are recorded per model/resolution.
- [ ] Results report `not verified` unless detector evidence exists.

Verification:
- [ ] Minimal paid benchmark results are recorded outside production code.

Notes:
- KIE is the preferred path only if it passes Task 41.

## Task 40 - OpenRouter Managed-API Fallback Prototype

Status: Todo - conditional on Task 39 no-go or partial result

Goal:
Test one current OpenRouter image-to-image candidate only if KIE is insufficient.

Steps:
- Re-check current image-model capabilities, pricing, and provider watermark policy.
- Select one non-Google candidate and run the same fixtures/rubric as Task 39.
- Record output metadata, cost, latency, quality, and detector status.
- Keep the prototype outside the main application.

Acceptance:
- [ ] OpenRouter is compared directly with the failed or partial KIE cases.
- [ ] No OpenRouter key appears in logs or fixtures.
- [ ] The result does not receive production approval without detector and quality evidence.

Verification:
- [ ] Prototype command and comparison table are recorded.

Notes:
- Mark `Skipped` if KIE passes Task 41 without a fallback need.

## Task 41 - Managed-API Decision Gate

Status: Todo

Goal:
Decide whether KIE alone, KIE plus OpenRouter, or a custom GPU path is justified.

Steps:
- Compare quality, detector evidence, cost, latency, alpha/dimension behavior, and operational complexity.
- Record the user-approved quality threshold and acceptable per-image cost.
- Select a managed provider or explicitly activate Tasks 42-47.
- Update PRD, capability matrix, and later task statuses.

Acceptance:
- [ ] A managed API is chosen only if it meets the agreed quality threshold.
- [ ] GPU infrastructure is not built when KIE is sufficient.
- [ ] The decision names supported image classes and known failure modes.

Verification:
- [ ] Decision evidence and activated/skipped tasks are recorded in `TASKS.md` and `CHANGELOG.md`.

Notes:
- This is the required cost-control gate.

## Phase 22 - Conditional GPU Fallback

## Task 42 - Local remove-ai-watermarks Feasibility

Status: Todo - conditional on Task 41 GPU decision

Goal:
Measure the local repository's diffusion pipelines without affecting the application environment.

Steps:
- Pin the evaluated commit and create an isolated Python environment.
- Audit code and downloaded model-weight licenses before execution.
- Compare ControlNet, SDXL, and Qwen where current hardware permits.
- Record model downloads, runtime, VRAM/RAM, quality, dimensions, alpha, and detector result.

Acceptance:
- [ ] The main application environment and requirements remain unchanged.
- [ ] At least one feasible pipeline or a clear hardware no-go is documented.
- [ ] Apache-2.0 and model-weight obligations are recorded.

Verification:
- [ ] Exact isolated install/run commands and benchmark results are recorded.

Notes:
- CPU-only execution may be measured but is not a production deployment candidate.

## Task 43 - GPU Serverless Provider Spike

Status: Todo - conditional on Task 42 feasible pipeline

Goal:
Choose a scale-to-zero GPU host for the approved local pipeline.

Steps:
- Compare RunPod Serverless first and Modal as fallback using current official pricing and limits.
- Measure cold start, model caching/storage, execution time, timeout limits, and per-image cost.
- Keep active workers at zero during the spike.
- Select one provider and document the rollback/stop procedure.

Acceptance:
- [ ] No always-on GPU cost is created.
- [ ] One provider is selected with an estimated cost range and hard spending limit.
- [ ] The ordinary VPS is excluded from diffusion inference.

Verification:
- [ ] One minimal GPU job completes and billing evidence is recorded.

Notes:
- Stop and remove unused workers/resources after the spike.

## Task 44 - GPU Worker Endpoint

Status: Todo - conditional on Task 43 go decision

Goal:
Expose the approved regeneration pipeline through a minimal asynchronous GPU API.

Steps:
- Build a pinned worker image with model cache and `/health` behavior.
- Accept a bounded image input, create a job, and return structured status/output.
- Validate dimensions, file type, output size, non-empty pixels, and timeout/cancellation.
- Delete temporary input/output after the documented retention window.

Acceptance:
- [ ] The worker scales from zero and processes one owned fixture successfully.
- [ ] Invalid or oversized inputs are rejected before GPU work.
- [ ] Failed jobs return actionable errors and no partial output.

Verification:
- [ ] Worker unit tests and one live serverless smoke pass.

Notes:
- Keep the worker separate from the desktop repository unless Task 43 selects a documented subdirectory contract.

## Task 45 - Ordinary VPS Gateway And Secret Boundary

Status: Todo - conditional on distributed GPU service

Goal:
Use the existing ordinary VPS only to protect GPU credentials, authorize clients, and coordinate jobs.

Steps:
- Define whether the service is personal direct-access or distributed through the license server.
- For distributed access, keep the GPU key on the VPS and authenticate the desktop request.
- Add rate limits, job ownership, maximum sizes, timeouts, retention, and secret-safe logs.
- Prefer temporary/signed transfer rather than permanent image hosting.

Acceptance:
- [ ] No GPU provider secret ships in the desktop application.
- [ ] One user cannot read another user's job or output.
- [ ] Expired files and job records follow the documented retention policy.

Verification:
- [ ] Gateway authorization, limit, expiry, and error tests pass.

Notes:
- Mark `Skipped` for a strictly personal endpoint where the user supplies their own key locally.

## Task 46 - GPU Service Desktop Adapter

Status: Todo - conditional on Tasks 44-45

Goal:
Add a tested desktop client for the selected GPU endpoint without exposing infrastructure details to the pipeline.

Steps:
- Add a narrow provider adapter for submit, status, cancel, and download.
- Route through the VPS gateway when Task 45 requires it.
- Validate downloaded output before handing it to the pipeline.
- Add network-free tests for success, timeout, cancellation, invalid output, and secret-safe errors.

Acceptance:
- [ ] The adapter is independent from KIE and OpenRouter code.
- [ ] No endpoint secret appears in logs.
- [ ] Failed downloads never replace a valid prior file.

Verification:
- [ ] `python -m unittest tests.test_gpu_watermark_provider -v`

Notes:
- Do not add UI controls in this task.

## Task 47 - GPU Cost And Reliability Acceptance

Status: Todo - conditional on Tasks 44-46

Goal:
Confirm that the custom GPU path is worth maintaining before exposing it to users.

Steps:
- Run a bounded batch across approved image classes.
- Measure cold/warm latency, failures, retries, cancellation, and actual per-image cost.
- Verify worker scale-down and temporary-file cleanup.
- Compare quality and cost against the best managed API result.

Acceptance:
- [ ] The custom path beats or materially complements the managed API decision.
- [ ] Cost limits and failure behavior are acceptable.
- [ ] Otherwise Tasks 48-49 use only the managed API path.

Verification:
- [ ] Benchmark, billing, and cleanup evidence are recorded.

Notes:
- Shut down and delete unused GPU resources after acceptance.

## Phase 23 - Pixel Regeneration Integration And Closeout

## Task 48 - Pixel-Regeneration UI And Settings

Status: Todo - conditional on Task 41 or Task 47 go decision

Goal:
Expose the approved whole-image regeneration path as a separate optional action.

Steps:
- Add `Экспериментальная перегенерация` with only approved providers and parameters.
- Explain before execution that the entire image may change.
- Keep the option disabled by default and independent from background removal and metadata cleanup.
- Save/load settings and apply existing masked-key rules for user-supplied API keys.

Acceptance:
- [ ] Unsupported or rejected providers are not selectable.
- [ ] Legacy configs preserve current behavior.
- [ ] The warning appears before a paid or pixel-changing request.

Verification:
- [ ] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_pixel_regeneration_ui -v`

Notes:
- Use the existing vertical processing-order layout.

## Task 49 - Pixel-Regeneration Pipeline And Reinspection

Status: Todo - conditional on Task 48

Goal:
Run whole-image regeneration safely and report the actual post-processing marker status.

Steps:
- Run regeneration before upscale/background removal unless the accepted provider evidence requires a narrower rule.
- Save the provider output into `raw/` and validate it before continuing.
- Apply the approved transparent-input rule from the prototype.
- Re-run metadata/provenance inspection after regeneration and again after final metadata cleanup.
- Report `detected`, `not detected`, `not verified`, or `unsupported`; never infer removal from request success.

Acceptance:
- [ ] Disabled regeneration leaves the current pipeline unchanged.
- [ ] Provider failure, cancellation, timeout, or invalid output preserves previous files.
- [ ] Final logs separate processing success from detector evidence.

Verification:
- [ ] `python -m unittest tests.test_pixel_watermark_regeneration -v`
- [ ] `python -m unittest discover -s tests -v`

Notes:
- Existing upscale/background/edge/trim order remains unchanged after this optional first step.

## Task 50 - Complete Cleanup Acceptance

Status: Todo

Goal:
Verify the complete post-MVP cleanup goal without building or publishing a release.

Steps:
- Review PRD, TASKS, changelog, capability matrix, knowledge base, and author documentation.
- Verify every enabled checkbox independently and in combined local/KIE/approved-provider flows.
- Test old config compatibility, key routing, cancellation, raw/final outputs, and unsupported claims.
- Fix only blocking issues and record later improvements separately.

Acceptance:
- [ ] Metadata cleanup preserves pixels/alpha and selected ICC/DPI.
- [ ] Visible and hidden mark claims match saved evidence.
- [ ] Existing generation and processing remain usable with all cleanup features disabled.
- [ ] Conditional GPU tasks are either verified or explicitly marked `Skipped` with rationale.

Verification:
- [ ] `python -m py_compile .\main.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] Manual comparisons on light/dark backgrounds and multiple image classes are recorded.

Notes:
- Finish with documentation, commit, and push only. Do not build, tag, publish, or create a release.
