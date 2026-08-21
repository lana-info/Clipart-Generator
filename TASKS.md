# TASKS

Source specs: `PRD.md` and `PROCESSING_PIPELINE_TZ.md`.

Rule: take the next open task in order. Keep code changes narrow and do not refactor working code unless it directly makes the current task safer.

For each task: explain the plan, implement only that task, verify it, update `TASKS.md` and `CHANGELOG.md`, then commit and push. Ordinary pushes must not start a build or release workflow. Build, tag, publish, release, and manual GitHub Actions runs are allowed only after an explicit user command that the application is ready.

Current next task: **Download the installer from Azure run `77`, verify its
SHA-256, then repeat focused Windows acceptance. Do not upload a revision before
that exact artifact is approved.**

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

Status: Done

Goal:
Inspect ordinary PNG/JPEG metadata without modifying the source file.

Steps:
- Add a focused inspector module outside `main.py`.
- Detect PNG/JPEG by file content and reject unsupported or animated inputs clearly.
- Return structured presence/size summaries for EXIF, XMP, IPTC, comments/text, thumbnails, ICC, DPI, and known generator fields.
- Never emit full metadata values to normal logs.
- Add synthetic PNG, transparent PNG, JPEG, and unsupported-format fixtures.

Acceptance:
- [x] The source hash, size, and modification timestamp remain unchanged after inspection.
- [x] Present, absent, and unsupported categories are reported deterministically.
- [x] Results are serializable and usable by tests, logs, and future UI.

Verification:
- [x] `python -m unittest tests.test_metadata_inspector -v`

Notes:
- Prefer Pillow and standard-library parsing already available in the project.
- Implemented in `metadata_inspector.py` without changing `main.py`; 5 focused tests and all 29 tests pass.
- Review hardened decompression-bomb handling and confirmed that returned/loggable data contains only category counts, sizes, and allowlisted field names.

## Task 25 - Bounded C2PA Presence Inspector

Status: Done

Goal:
Detect embedded C2PA structures locally without validating signatures or using the network.

Steps:
- Detect PNG `caBX` and JPEG APP11/JUMBF structures with strict length bounds.
- Return `present`, `not present`, or `not validated` separately from ordinary metadata.
- Add malformed, truncated, and oversized-segment fixtures.
- Integrate the result into the Task 24 inspector schema.

Acceptance:
- [x] Detection never claims a manifest is valid.
- [x] Corrupt inputs fail safely without unbounded reads or memory allocation.
- [x] No remote manifest is fetched automatically.

Verification:
- [x] `python -m unittest tests.test_c2pa_inspector -v`

Notes:
- Do not add `c2pa-python` until its packaging and build impact are explicitly justified.
- Implemented as a standard-library bounded scan in `metadata_inspector.py`; schema v2 keeps C2PA presence and `not_validated` separate from ordinary metadata categories.
- Review added exact JPEG JUMBF/description `LBox`, extended-`LBox`, contiguous APP11 `En/Z`, description-toggle, overrun, and sequence-gap checks instead of treating marker presence as a complete container.
- Eight focused tests and all 37 project tests pass; 54 embedded fixtures from the official `contentauth/c2pa-rs` checkout were detected with no non-OK present result.

## Task 26 - Selective Metadata Cleanup Core

Status: Done

Goal:
Remove selected ordinary and AI/service metadata while preserving selected export data and image pixels.

Steps:
- Add a cleanup module with independent EXIF, XMP, IPTC, comments/text, thumbnail, and known-generator options.
- Use a documented allowlist for AI/service fields instead of deleting unknown fields by guess.
- Preserve ICC and DPI independently when selected.
- Write to a temporary PNG, validate it, then atomically publish the new output.
- Compare decoded pixels, dimensions, and alpha before and after metadata-only cleanup.

Acceptance:
- [x] Checked categories are removed and unchecked categories remain where the output format supports them.
- [x] ICC and 300 DPI are preserved when selected.
- [x] Pixel values, dimensions, and alpha are unchanged.
- [x] A failure leaves the source and previous output intact.

Verification:
- [x] `python -m unittest tests.test_metadata_cleanup -v`

Notes:
- This task contains no C2PA or visible/pixel watermark handling.
- Implemented a shared exact-match allowlist in `metadata_policy.py`: EXIF `Software`; normalized exact PNG/JPEG text names for software, prompt, model, digital-source, and generator identifiers; and exact XMP `CreatorTool`/`DigitalSourceType` properties. Unknown fields and EXIF camera `Model` are not guessed.
- C2PA-bearing or indeterminate inputs are rejected until Task 27 can make removal explicit; multiple JPEG comments and duplicate PNG text keys are rejected unless their selected category is removed.
- Added bounded file/pixel/dimension/metadata preflight, stripe-based pixel/alpha hashing, EXIF overlap validation, value-safe metadata digests, and atomic same-directory publication.
- Fifteen focused cleanup tests and all 52 project tests pass; three review passes closed C2PA, transparency, EXIF overlap, UTF-16 XMP, allowlist consistency, metadata preservation, JPEG comment, and memory-bound findings.

## Task 27 - C2PA Export Cleanup

Status: Done

Goal:
Remove supported embedded C2PA data or references from the new PNG export when explicitly selected.

Steps:
- Add owned PNG/JPEG fixtures containing embedded-manifest and remote-reference structures.
- Ensure the new PNG does not carry selected embedded C2PA structures or selected external-manifest references.
- Re-run the inspector after export and distinguish removed file structures from remote records and soft bindings.
- Abort publication if post-save validation does not match the selected action.

Acceptance:
- [x] Embedded structures selected for cleanup are absent from the new PNG.
- [x] The source file remains unchanged.
- [x] Logs never claim that remote manifests or pixel soft bindings were deleted.

Verification:
- [x] `python -m unittest tests.test_c2pa_cleanup -v`

Notes:
- This task validates the limited `REMOVE` claim in `CLEANUP_CAPABILITY_MATRIX.md`.
- Added explicit `remove_embedded_c2pa` cleanup for bounded PNG `caBX`, JPEG APP11/JUMBF, valid XMP `self#jumbf=c2pa/...`, and supported HTTP(S) `.c2pa`/JUMBF references in the new PNG only.
- Inspector schema v3 separates embedded containers, embedded XMP pointers, supported external references, and unclassified provenance values; no remote fetch or signature validation is performed.
- Unknown or mixed provenance values abort selective cleanup unless the whole XMP category is explicitly removed. Duplicate PNG XMP keys abort before any `dict` conversion.
- Selective XMP filtering preserves packet wrappers, comments, processing instructions, and unrelated XMP fields; a bounded raw PNG text scan includes metadata placed after `IDAT`.
- Sidecar files, remote manifests, and pixel soft bindings are never touched. Eleven focused C2PA cleanup tests and all 63 project tests pass after three review passes.

## Task 28 - Metadata Cleanup UI And Settings

Status: Done

Goal:
Expose independent metadata/C2PA cleanup choices without changing current defaults.

Steps:
- Add a compact `Очистка файла` section near final export.
- Add independent controls for supported metadata categories and embedded C2PA.
- Add `Сохранить ICC-профиль` and `Сохранить DPI` choices to the right of the related action.
- Save and restore settings; cleanup remains disabled for legacy configs while preservation options default to enabled.

Acceptance:
- [x] Every supported category can be enabled independently.
- [x] Old config files preserve current processing behavior.
- [x] Controls do not overlap at the supported offscreen viewport.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_cleanup_ui -v`

Notes:
- Do not rearrange unrelated controls.
- Added seven independent removal choices plus ICC/DPI preservation choices. Cleanup remains disabled for legacy configs, ICC/DPI preservation defaults to enabled, and all 65 project tests pass.

## Task 29 - Shared Final-Save Cleanup Integration

Status: Done

Goal:
Run selected metadata cleanup once through the shared final-save path.

Steps:
- Integrate inspection and cleanup after trim and before final completion is reported.
- Use the same path for generate-only, generate-and-process, process-only, local, and mixed runs.
- Keep `raw/` intermediates unchanged for diagnostics.
- Log found, removed, preserved, unsupported, and failed categories without metadata values or secrets.

Acceptance:
- [x] Disabled cleanup is behaviorally equivalent to the current application.
- [x] Every final workflow uses the same cleanup decision and validation path.
- [x] A cleanup failure does not publish a corrupt or partial output.

Verification:
- [x] `python -m unittest tests.test_final_save_cleanup -v`
- [x] `python -m unittest discover -s tests -v`

Notes:
- This is the first user-complete cleanup slice.
- All final workflows now publish through one same-directory staging path. Cleanup-only process runs need no KIE key, trim precedes cleanup, raw intermediates stay unchanged, C2PA cannot be hidden by trim/DPI conversion, and cleanup failures leave prior outputs untouched.
- Ten focused final-save tests and all 75 project tests pass after three review passes.

## Task 30 - Metadata Cleanup Acceptance And Documentation

Status: Done

Goal:
Close the metadata/C2PA slice before starting pixel-changing watermark work.

Steps:
- Review PRD, capability matrix, task results, changelog, and author instructions.
- Verify every cleanup checkbox separately and in one combined local pipeline.
- Record exact supported formats, preservation behavior, and unsupported claims.
- Fix only blocking issues discovered by this review.

Acceptance:
- [x] Documentation matches tested behavior.
- [x] Metadata cleanup never changes visible pixels or alpha.
- [x] Existing processing remains usable with cleanup disabled.

Verification:
- [x] `python -m py_compile .\main.py`
- [x] `python -m unittest discover -s tests -v`

Notes:
- Do not start visible-mark work until this gate passes.
- Every removal choice passes an independent PNG/JPEG fixture, and one combined local pipeline verifies one cleanup call plus identical decoded pixels/alpha before and after metadata cleanup.
- `CLEANUP_CAPABILITY_MATRIX.md` now records implemented formats, bounds, preservation behavior, C2PA scope, unsupported claims, and the 300 DPI precedence rule. Two focused acceptance tests and all 77 project tests pass.

## Phase 20 - Visible Generator Marks

## Task 31 - Local Visible-Mark Detector Prototype

Status: Done - prototype evidence completed; production scope decided in Task 34

Goal:
Measure whether `lana-info/remove-ai-watermarks` reliably localizes supported visible generator marks.

Steps:
- Pin and record the evaluated repository commit and Apache-2.0 attribution requirements.
- Run detection outside the application on owned marked and unmarked fixtures.
- Save only masks, confidence, location, and timing results; do not change production code.
- Measure false positives across clipart, photos, illustrations, and textured corners.

Acceptance:
- [x] Gemini and Doubao detection rates are documented for the available reproducible marked fixtures.
- [x] False positives are measured on five unmarked image fixtures.
- [x] No heavy dependency is added to the main application.

Verification:
- [x] Prototype command and results are recorded in `VISIBLE_MARK_DETECTOR_EVAL.md`.

Notes:
- Detection approval does not approve an inpainting backend.
- Jimeng/Samsung remain an explicit evidence gap. The user-owned Gemini marked and
  unmarked fixture gate was completed in Task 32; Task 34 limits automatic
  integration to Gemini.

## Task 32 - Local Visible-Mark Inpainting Benchmark

Status: Done - cv2 established as the bounded baseline; superseded by Task 37 quality acceptance

Goal:
Choose a local fill method for confirmed masks without unacceptable damage outside the marked region.

Steps:
- Compare cv2, MI-GAN, and LaMa where available using the same masks.
- Compare automatic masks with a user-confirmed rectangular/mask fallback.
- Measure changed pixels outside the requested mask and inspect texture continuity.
- Record runtime, RAM, model downloads, and supported image classes.

Acceptance:
- [x] Provisional local default/fallback selected: cv2 with automatic or user-confirmed mask.
- [x] The bounded benchmark changed zero pixels outside the supplied mask.
- [x] Benchmark never overwrites originals; backend failures are reported without publishing output.

Verification:
- [x] Before/after/mask comparisons are inspected on owned fixtures; decoded pixels and alpha were verified.

Notes:
- Keep benchmark assets outside git unless small and redistributable.
- MI-GAN/LaMa were unavailable during this bounded baseline. Task 37 later evaluated and bundled the official MIT MI-GAN ONNX model after the `cv2` production result failed the 200% visual quality gate; LaMa remains unselected.

## Task 33 - KIE Mask-Edit Benchmark

Status: Done - KIE rejected for precise visible-mark cleanup

Goal:
Determine whether KIE 4o mask editing is a better fallback for visible marks than local inpainting.

Steps:
- Use the smallest useful paid sample set with the existing KIE key.
- Send explicit masks and prompts; preserve original aspect ratio and request PNG.
- Compare changes inside and outside the mask, output metadata, cost, and latency.
- Record provider errors and invalid-output handling.

Acceptance:
- [x] KIE is compared against the selected local method on identical fixtures.
- [x] Cost and visible changes outside the mask are recorded.
- [x] No KIE key appears in logs or saved artifacts.

Verification:
- [x] Manual comparison and request-cost evidence are recorded.

Notes:
- This task spends credits and must remain a minimal benchmark.
- API ratio constraints and the safe paid-test protocol are recorded in `TASK33_KIE_MASK_BENCHMARK.md`.
- Two native 4o mask payloads were rejected before generation; one GPT Image 1.5
  mask-reference task succeeded at a listed `$0.02` and took `102.485` seconds.
- The KIE output changed `78.3491%` of content pixels outside the mask versus `0%`
  for local `cv2`, so no additional request from the authorized five was justified.

## Task 34 - Visible-Mark Provider Decision Gate

Status: Done - local-only go decision with Gemini-only automation

Goal:
Choose local, KIE, user-confirmed-only, or no automatic visible-mark removal.

Steps:
- Compare Tasks 31-33 against one quality rubric.
- Select supported marks, image classes, default provider, and fallback.
- Update the capability matrix and mark Tasks 35-37 active or skipped.

Acceptance:
- [x] The decision is based on saved evidence rather than a single image.
- [x] Automatic processing is rejected for any class with unsafe false positives.
- [x] User-confirmed mask fallback remains available when automatic detection is not approved.

Verification:
- [x] Decision and rationale are recorded in PRD/project documentation and changelog.

Notes:
- No production integration belongs to this gate.
- Automatic local detection/removal is approved only for the small Gemini corner
  mark on owned/licensed PNG/JPEG. Doubao and unmeasured/unknown small service marks
  require a user-confirmed bounded mask; unsupported images remain unchanged.
- At this gate, local `cv2` was the only evaluated precise provider. Task 37 later
  retained the same local-only UI and bounded-mask rules but replaced `cv2` after
  production visual acceptance with reverse-alpha Gemini recovery and bundled MI-GAN.
  KIE and LaMa are not selectable. The feature remains disabled by default.

## Task 35 - Visible-Mark UI And Settings

Status: Done - local-only controls added with legacy-safe defaults

Goal:
Expose only the approved visible-mark controls.

Steps:
- Add an independent visible-mark checkbox with `Gemini automatically` and
  `User-confirmed area` modes; do not add a KIE/provider selector.
- Place parameters to the right of the action and keep the step disabled by default.
- Save/load settings without affecting legacy configs.
- Show when user confirmation is required.

Acceptance:
- [x] Controls match the Task 34 decision exactly.
- [x] Existing UI remains unchanged while the feature is disabled.
- [x] Unsupported automatic modes are not selectable.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_ui -v`

Notes:
- Automatic modes for Doubao, Jimeng, Samsung, and unknown marks are intentionally unavailable.
- Added one disabled-by-default row before upscale with only `Gemini automatically`
  and `User-confirmed area`. The confirmation status appears only for the second
  mode; no KIE/provider control was added.
- Task 35 introduced config/UI only; Worker integration was completed separately in Task 36.

## Task 36 - Visible-Mark Pipeline Integration

Status: Done - local-only step integrated before the first upscale

Goal:
Run approved visible-mark cleanup before upscale without changing unrelated processing.

Steps:
- Insert the step before the first upscale pass.
- Save the result into `raw/` and validate dimensions, mode, and non-empty pixels.
- Leave unmarked images unchanged when no mark is confidently found.
- Handle cancellation, provider failure, and user-confirmation requirements safely.

Acceptance:
- [x] The step runs only when enabled.
- [x] Existing processing order after the step remains unchanged.
- [x] Failed cleanup does not overwrite the source or previous final output.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_pipeline -v`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v`

Notes:
- Metadata cleanup still runs only at final save.
- Visible-mark cleanup is local-only and must never require or call KIE.
- Vendored only the pinned Apache-2.0 Gemini detector and two required templates
  from `remove-ai-watermarks` commit `190dc89d234fd7e3a61ff755f01251c9c0b87ef0`;
  no upstream model weights or removal engines were added.
- Automatic Gemini removal requires confidence `>= 0.5`; a lower score leaves the
  source unchanged and creates no visible-mark `raw/` file.
- User-confirmed mode opens a local rectangle selector for each process-only file,
  limits the area to 15% of the image, and keeps coordinates only in current-run memory.
- Successful output is validated and atomically saved as
  `raw/*_visible_mark_*.png`; source pixels and prior outputs remain intact on failure
  or cancellation.
- Tracked Windows/macOS PyInstaller commands include the two templates, Apache
  license, and attribution notice; no application build or release was run.
- Six focused tests and all 85 project tests pass. A real owned Gemini fixture scored
  `0.694789`, changed `0` pixels outside the mask, and preserved the source hash; an
  unmarked screenshot scored `0.184643` and produced no raw output. No API request was made.
- Task 37 subsequently replaced the initial `cv2.inpaint` fill after its 200% visual
  acceptance exposed rectangular patches; the step order, UI modes, and local-only
  routing remain unchanged.

## Task 37 - Visible-Mark Acceptance

Status: Done - local-only quality acceptance passed

Goal:
Verify the complete visible-mark slice on marked and unmarked general images.

Steps:
- Test automatic Gemini and user-confirmed flows on approved general-image fixtures.
- Verify local-only routing and that visible-mark cleanup never requires a KIE key.
- Compare results at normal view and 200% zoom.
- Update supported/unsupported documentation.

Acceptance:
- [x] Approved fixtures meet the recorded quality rubric.
- [x] Unmarked fixtures remain unchanged.
- [x] Logs and UI describe detection and removal accurately.

Verification:
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest tests.test_visible_mark_pipeline -v`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v`
- [x] Manual comparison is recorded in `CHANGELOG.md`.

Notes:
- Acceptance included two marked Gemini fixtures, one user-confirmed Doubao fixture,
  five clean upstream fixtures, and one clean user-owned clipart fixture.
- Reverse-alpha Gemini recovery and bounded local MI-GAN passed normal-size and 200%
  visual inspection. All three marked files changed `0` pixels outside the mask;
  all six unmarked files remained unchanged and produced no visible-mark output.
- Source hashes, dimensions, modes, and alpha were preserved. The run made `0`
  KIE/API requests. Evidence is stored outside git in
  `C:\Users\belou\Downloads\output\task37-visible-mark-acceptance-fixed`.
- The pinned MI-GAN model, MIT license, notice, and Windows/macOS packaging entries
  are tracked. No application build, release, tag, or workflow run was performed.
- Eight focused visible-mark tests and all 87 project tests pass.

## Phase 21 - Hidden Pixel Markers: Managed API First

## Task 38 - Pixel-Watermark Status Contract

Status: Done - provider-neutral claim-safe contract added

Goal:
Represent hidden-marker evidence without turning metadata proxies into false removal claims.

Steps:
- Define structured statuses: `detected`, `not detected`, `not verified`, and `unsupported`.
- Keep metadata/C2PA hints separate from pixel-level detector evidence.
- Define the manual or official verification handoff for SynthID.
- Add safe log formatting and tests.

Acceptance:
- [x] `not detected` never means proven human-made.
- [x] Processing success is separate from detector result.
- [x] Unknown markers never receive a false `removed` result.

Verification:
- [x] `python -m unittest tests.test_watermark_status -v`

Notes:
- This contract is shared by KIE, OpenRouter, and any GPU worker.
- `watermark_status.py` returns separate `processing`, `pixel_evidence`,
  `file_hints`, and `verification_handoff` branches. Metadata/C2PA hints cannot
  change pixel evidence, detector evidence identifies the checked input/output
  stage, and the schema has no `removed` status.
- Unverified SynthID uses the official Gemini handoff; unknown markers use manual
  or external verification. The formatter emits only allowlisted labels and never
  echoes provider/user values.
- Six focused tests and all 93 project tests pass. Task 38 adds no UI, API call,
  or pipeline behavior.

## Task 39 - KIE Whole-Image Regeneration Prototype

Status: Done

Goal:
Test whether the existing KIE integration is sufficient for whole-image regeneration before adding infrastructure.

Steps:
- Test GPT Image 2 image-to-image first and FLUX image-to-image as fallback.
- Do not use Google/Nano Banana models for SynthID removal because their outputs receive SynthID.
- Use owned photos, illustrations, text-heavy images, faces, and clipart.
- Record quality, dimensions, alpha behavior, latency, credits, and metadata/provenance added to outputs.
- Re-check a known SynthID sample through the available official verification flow.

Acceptance:
- [x] KIE results are evaluated on all required image classes.
- [x] Cost and quality are recorded per model/resolution.
- [x] Results report `not verified` unless detector evidence exists.

Verification:
- [x] Minimal paid benchmark results are recorded outside production code.

Notes:
- `TASK39_KIE_REGENERATION_BENCHMARK.md` records one GPT Image 2 and one FLUX 2
  Pro `1K` generation. GPT returned `1254x1254` RGB and FLUX returned
  `1024x1024` RGB; both lost alpha and added embedded C2PA. GPT preserved the
  fixture better, while FLUX spread the fine grid across the board and changed
  layout/text.
- The known Gemini-origin fixture and both outputs remain `not_verified` because
  no authenticated official Gemini detector session was available. Processing
  success is not reported as watermark removal.
- The five-attempt authorization is exhausted: Task 33 used three attempts and
  Task 39 used two. The reusable harness now blocks live generation globally,
  independent of output directory; the recorded model snapshots total
  `11 credits / $0.055` without claiming actual billing.
- KIE does not pass the universal quality gate, so Task 40 is activated. No
  production UI or pipeline behavior was changed.
- Five focused benchmark tests and all 98 project tests pass. They cover the
  closed global budget, credit snapshots, real alpha, safe status claims, and the
  enabled FLUX safety checker.

## Task 40 - OpenRouter Managed-API Fallback Prototype

Status: Done

Goal:
Test one current OpenRouter image-to-image candidate only if KIE is insufficient.

Steps:
- Re-check current image-model capabilities, pricing, and provider watermark policy.
- Select one non-Google candidate and run the same fixtures/rubric as Task 39.
- Record output metadata, cost, latency, quality, and detector status.
- Keep the prototype outside the main application.

Acceptance:
- [x] OpenRouter is compared directly with the failed or partial KIE cases.
- [x] No OpenRouter key appears in logs or fixtures.
- [x] The result does not receive production approval without detector and quality evidence.

Verification:
- [x] Preparation command and pending comparison table are recorded.
- [x] One live result and the completed comparison table are recorded.

Notes:
- `recraft/recraft-v4.1-utility` was selected from the current dedicated Image
  API records as the single non-Google candidate. Its endpoint snapshot is
  `$0.035` per output image and accepts one reference image.
- The provider has no documented hidden pixel-watermark removal guarantee or
  checked pixel-watermark policy. The result must remain `not_verified` without
  detector evidence.
- `scripts/run_openrouter_regeneration_benchmark.py` reuses the Task 39 fixture,
  prompt, metrics, metadata/C2PA inspection, and Task 38 status contract. It is
  outside the application and does not change `main.py` or the UI.
- One separately authorized request completed in `12.588 s`; the API response
  reported `$0.035`. Recraft returned `1024x1024` RGB WebP, lost alpha, changed
  `99.9579%` of RGB pixels beyond tolerance, and scored global SSIM `0.177527`.
- Manual review failed: photo subject, face identity, clipart, exact text, and
  fine-grid content were changed. The raw WebP also contains a signed `CRFT`
  provenance chunk. SynthID remains `not_verified`; removal is not claimed.
- Live generation is globally closed again at zero authorized attempts, while
  the local state records the authorized attempt as `1/1` used. The key does not
  appear in the report, fixtures, diff, or git history.
- Ten focused tests cover the real-alpha fixture, closed network gate, global
  one-shot reservation, missing-key behavior, validated response allowlisting,
  signed WebP evidence without provider values, and safe `not_verified`
  analysis, including malformed WebP padding, pre-read size rejection, and RIFF
  boundary enforcement; all 108 project tests pass.
- Three review passes found and fixed bounded-read, test-count, and RIFF-boundary
  issues. No blocking or important finding remains open.
- Decision: OpenRouter/Recraft is not approved for production. Task 41 is active.

## Task 41 - Managed-API Decision Gate

Status: Done - managed APIs rejected; isolated local/GPU feasibility path activated

Goal:
Decide whether KIE alone, KIE plus OpenRouter, or a custom GPU path is justified.

Steps:
- Compare quality, detector evidence, cost, latency, alpha/dimension behavior, and operational complexity.
- Record the user-approved quality threshold and acceptable per-image cost.
- Select a managed provider or explicitly activate Tasks 42-47.
- Update PRD, capability matrix, and later task statuses.

Acceptance:
- [x] No managed API was chosen because none met the complete quality and detector gate.
- [x] KIE was proven insufficient before the conditional local/GPU path was activated.
- [x] The decision names supported image classes and known failure modes.

Verification:
- [x] Decision evidence and activated/skipped tasks are recorded in `TASKS.md` and `CHANGELOG.md`.

Notes:
- This is the required cost-control gate.
- User-approved total OpenRouter test ceiling: `$0.300`; Task 40 consumed
  `$0.035`, leaving at most `$0.265` for Task 41.
- FLUX.2 Max was removed before paid execution because its per-megapixel
  endpoint did not expose a bounded output size.
- The first Seedream request failed with HTTP 400 and was not billed. The RGB
  defaults attempt cost `$0.040`, returned `2048x2048` RGB JPEG, changed the
  face/photo style, lost alpha, added C2PA, and remained `not_verified`.
- Riverflow produced the best visual fidelity and preserved exact text, but it
  lost alpha and remained `not_verified`. Its response reported `$0.264885`
  against the immediately preceding `$0.130` endpoint snapshot.
- Successful Task 41 responses total `$0.304885`; including Task 40, known
  response-reported spend is `$0.339885`. Testing stopped immediately and the
  final live authorization list is empty.
- No managed API is added to production. Task 42 is activated. Exact evidence,
  artifacts, safety controls, and commands are in
  `TASK41_MANAGED_API_DECISION.md`.
- The final state passes 28 focused Task 41 tests and all 136 project tests.

## Phase 22 - Conditional GPU Fallback

## Task 42 - Local remove-ai-watermarks Feasibility

Status: Done - clear local production hardware no-go documented without model downloads

Goal:
Measure the local repository's diffusion pipelines without affecting the application environment.

Steps:
- Pin the evaluated commit and create an isolated Python environment.
- Audit code and downloaded model-weight licenses before execution.
- Compare ControlNet, SDXL, and Qwen where current hardware permits.
- Record model downloads, runtime, VRAM/RAM, quality, dimensions, alpha, and detector result.

Acceptance:
- [x] The main application environment and requirements remain unchanged.
- [x] At least one feasible pipeline or a clear hardware no-go is documented.
- [x] Apache-2.0 and model-weight obligations are recorded.

Verification:
- [x] Exact isolated install/run commands and benchmark results are recorded.

Notes:
- CPU-only execution may be measured but is not a production deployment candidate.
- Evaluated upstream commit `190dc89d234fd7e3a61ff755f01251c9c0b87ef0`
  in `D:\WorkOS\Clipart Generator-task42\.venv-locked` via `uv sync --locked`;
  the application environment,
  `requirements.txt`, `requirements-dev.txt`, `main.py`, and UI were unchanged.
- The machine has `17.95 GiB` physical RAM, an AMD integrated adapter reporting
  `2 GiB`, and no CUDA/XPU/MPS device. The upstream accepts only
  `cpu`/`cuda`/`xpu`/`mps`; AMD DirectML is not supported.
- The CPU path selects FP32. Audited selected weights are `12.92 GiB` for SDXL,
  `15.25 GiB` for SDXL + ControlNet, and `53.74 GiB` serialized BF16 for Qwen.
  Model-weight downloads and inference were therefore stopped at preflight.
- No output exists, so runtime/VRAM/quality/dimensions/alpha are explicitly not
  measured and detector evidence remains `not_verified`. Details and exact
  commands are in `TASK42_LOCAL_WATERMARK_FEASIBILITY.md`.
- Upstream model IDs are not loaded with pinned `revision=` values. The report
  pins the audited snapshots, and the final preflight verified their SHA,
  card-license metadata, and selected file sizes through the official Hugging
  Face metadata API. Any future worker must enforce those revisions and must
  remain isolated from the desktop environment.
- The ControlNet component is Apache-2.0 but its combined pipeline retains
  SDXL Open RAIL++-M obligations. The MIT-marked FP16 VAE is derived from
  SDXL-VAE, so inherited terms require review before any future distribution.
- Upstream supports a slow CPU route, but Task 42 excludes CPU-only production;
  plain-SDXL CPU impossibility is not claimed because inference was not run.
- Verification passed: 13 focused Task 42 tests, 26 pinned-upstream focused
  tests, all 149 application tests, Python compilation, and offscreen
  `SMOKE_OK`. No release/build/workflow was run.

## Task 43 - GPU Serverless Provider Spike

Status: Skipped - Task 42 produced no approved feasible pipeline

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
- No GPU resource, account, payment, worker, or live job was created.

## Task 44 - GPU Worker Endpoint

Status: Skipped - Task 43 prerequisite was not activated

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

Status: Skipped - no distributed GPU service was approved

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

Status: Skipped - no GPU endpoint or gateway was approved

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

Status: Skipped - no custom GPU path reached acceptance

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

Status: Skipped - both managed and custom regeneration paths are no-go

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

Status: Skipped - no approved regeneration provider exists

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

Status: Done

Goal:
Verify the complete post-MVP cleanup goal without building or publishing a release.

Steps:
- Review PRD, TASKS, changelog, capability matrix, knowledge base, and author documentation.
- Verify every enabled checkbox independently and in combined local/KIE/approved-provider flows.
- Test old config compatibility, key routing, cancellation, raw/final outputs, and unsupported claims.
- Fix only blocking issues and record later improvements separately.

Acceptance:
- [x] Metadata cleanup preserves pixels/alpha and selected ICC/DPI.
- [x] Visible and hidden mark claims match saved evidence.
- [x] Existing generation and processing remain usable with all cleanup features disabled.
- [x] Conditional GPU tasks are either verified or explicitly marked `Skipped` with rationale.

Verification:
- [x] `python -m py_compile .\main.py .\license_client.py .\tests\test_license_client_security.py .\tests\test_kie_routing.py .\tests\test_main_ui_acceptance.py .\tests\test_photoroom_provider.py .\tests\test_visible_mark_pipeline.py .\tests\test_security_boundaries.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -v` (`176/176` passed)
- [x] Manual comparisons on light/dark backgrounds and multiple image classes are recorded.

Notes:
- Finish with documentation, commit, and push only. Do not build, tag, publish, or create a release.
- The first acceptance pass was reopened after independent review reproduced redirect/header leaks, provider-body logging, final-publication cancellation races, ambiguous upload POST fallback, and insufficient provider-image limits.
- The fixes were covered by regressions and a fresh independent review returned `PASS`, including HTTPS redirect handling and real HTTP 400/422 reference-schema classification.
- The follow-up review added bounded updater responses, HTTPS-only update URL validation, and local-image preflight limits; a second fresh review and a post-refactor fresh review returned `PASS`.
- The current session's bundled Python lacked project runtime dependencies (`PyQt6` and `cv2`), so the new focused runtime tests were syntax-checked but not executed here; the previously recorded 176-test acceptance run remains unchanged.
- Final evidence is recorded in [`TASK50_CLEANUP_ACCEPTANCE.md`](./TASK50_CLEANUP_ACCEPTANCE.md).
- No paid request, model download, build, tag, workflow, or release was run.

## Task 51 - Trustworthy Feature Test Coverage

Status: Done - verified in the project's local `.venv`

Goal:
Cover the application's real user-facing features with deterministic tests that
assert business outcomes and safe failure behavior rather than only code paths.

Scope:
- Image generation: KIE model payloads, reference routing, polling, and result extraction.
- Data validation: supported image boundaries and invalid-input rejection before processing.
- Information preparation: CSV/BOM/delimiter/quotes, prompt normalization, and reference limits.
- Publication boundaries: final-output contracts, license cache lifecycle, and verified updater downloads.

Acceptance:
- [x] A feature matrix is recorded in [`TRUSTWORTHY_TEST_MATRIX.md`](./TRUSTWORTHY_TEST_MATRIX.md).
- [x] Focused generation/preparation/result tests are in `tests/test_trustworthy_feature_contracts.py`.
- [x] A network-free generation integration test verifies request payload, polling,
  download, and publication of one PNG output.
- [x] Positive license lifecycle tests are in `tests/test_license_client_security.py`.
- [x] Positive and negative updater/image-boundary tests are in `tests/test_security_boundaries.py`.
- [x] Negative scenarios cover failed generation, expired license cache, checksum
  mismatch cleanup, corrupt input, and unsupported result shapes.
- [x] Existing final-output, cleanup, UI, provider, and local-processing suites remain part of the required regression set.
- [x] No test performs a paid request, release, publication, commit, or push.

Verification:
- [x] `python -m py_compile .\main.py .\license_client.py .\tests\test_license_client_security.py .\tests\test_security_boundaries.py .\tests\test_trustworthy_feature_contracts.py`
- [x] Bundled runtime: `python -m unittest tests.test_license_client_security -v` (`7/7` passed).
- [x] `git diff --check`.
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\.venv\Scripts\python.exe -m unittest discover -s tests -v` (`198/198` passed).

Notes:
- The bundled Codex runtime lacked `PyQt6` and `cv2`; the project's local
  `.venv` was created and populated from `requirements.txt` for verification.
- Independent review rated the first pass `5/10`; the follow-up added the
  missing generation integration, public activation/cache flow, checksum
  mismatch cleanup, and corrupt-input regressions. Those import-dependent
  tests still require the project's normal environment.
- No production behavior was changed for this testing task.

## Task 52 - Processing Settings Clarity And Bundled Local Upscaler

Status: Done - verified without build or release

Goal:
Make the processing settings understandable and stable for everyday use while
preserving existing configuration keys and processing behavior.

Scope:
- Group processing controls by operation: upscale before background removal,
  upscale after background removal, background removal, Local rembg, and BEN2.
- Rename visible-watermark and BEN2 controls in user-facing text.
- Add one full metadata cleanup checkbox that removes all supported metadata
  while preserving ICC and DPI; retain old config keys only for migration.
- Treat Real-ESRGAN as an application-bundled resource and add it to the
  existing PyInstaller build recipe; do not run the build in this task.

Acceptance:
- [x] Existing provider data values, config keys, and processing order remain
  compatible with the prior UI.
- [x] BEN2 is described as a local experimental background-mask model, not a
  neural watermark remover.
- [x] Full cleanup preserves ICC/DPI and leaves image pixels/alpha untouched.
- [x] The bundled Real-ESRGAN path is used for source and packaged runs, and
  the build recipe includes its folder.
- [x] No generic hidden neural watermark/SynthID removal claim was added.

Verification:
- [x] `python -m py_compile .\\main.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest tests.test_cleanup_ui tests.test_main_ui_acceptance tests.test_visible_mark_ui tests.test_local_processing_acceptance -v` (`20/20` passed)
- [x] `git diff --check`

Notes:
- `README.md` is not present in this repository; the review used `README_AUTHOR_SHORT.md`, `PRD.md`, `TASKS.md`, and `CHANGELOG.md`.
- The executable and installer were not rebuilt, released, committed, or pushed.

## Task 53 - Compact Processing And Cleanup UI

Status: Done - verified without build or release

Goal:
Keep the application usable on a normal laptop screen while making cleanup
and processing settings easier to understand.

Scope:
- Replace the visible metadata sub-checkboxes with one full-cleanup checkbox;
  preserve ICC and DPI automatically and keep legacy config keys synchronized.
- Move provider/model processing settings to the `Обработка` tab.
- Add scrollable content to the processing and settings tabs and reduce the
  initial window height.
- Explain in the BEN2 block when local mask refinement runs.
- Keep generation, PhotoRoom, and processing prices beside their own fields.

Acceptance:
- [x] One cleanup checkbox enables all supported metadata/C2PA cleanup and
  always preserves ICC/DPI.
- [x] BEN2 timing is visible: it runs as the selected background-removal step
  after the first upscale and before edge shrink/trim.
- [x] Settings pages can be scrolled instead of forcing a tall main window.
- [x] Price labels are contained in the same row as their corresponding model
  or provider field.
- [x] Existing processing order, provider data values, and API behavior remain
  unchanged.

Verification:
- [x] `python -m py_compile .\\main.py .\\tests\\test_cleanup_ui.py`
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest tests.test_cleanup_ui tests.test_main_ui_acceptance tests.test_visible_mark_ui tests.test_local_processing_acceptance tests.test_photoroom_provider -v` (`25/25` passed)
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v` (`198/198` passed)
- [x] `git diff --check`

Notes:
- No build, release, commit, or push was performed.

## Task 54 - Align Local Background Settings

Status: Done - verified and pushed

Goal:
Align Local rembg and BEN2 controls with the other processing settings.

Acceptance:
- [x] Fixed-width controls are left-aligned within a shared settings column.
- [x] Local rembg and BEN2 fields start on the same vertical line as the
  upscale/background provider fields.
- [x] Generation, processing, cleanup, and provider behavior is unchanged.

Verification:
- [x] Qt geometry smoke check reports the same `x=377` start for the upper
  provider, Local rembg, and BEN2 controls.
- [x] `$env:QT_QPA_PLATFORM='offscreen'; .\\.venv\\Scripts\\python.exe -m unittest discover -s tests -v` (`198/198` passed)
- [x] `git diff --check`

## Task 55 - Silent Auto-Update to 2.0

Status: Superseded - legacy public update channel is inactive

Goal:
Enable legacy 1.x installs to auto-upgrade to `2.0` during startup without requiring
manual click, using the existing manifest and installer flow.

Scope:
- Keep update manifest parsing and HTTPS validation unchanged.
- Keep checksum validation and download limits in place.
- Add auto-apply behavior when `check_for_updates` is triggered at app startup.
- Download large installers in chunks with bounded retries to avoid partial files.

Acceptance:
- [x] Update manifest check uses `latest_version` from public `version.json` and respects `APP_VERSION` comparison.
- [x] Auto-apply path skips the interactive confirmation on startup update checks.
- [x] Installer download is bounded, streamed, and cleaned up on checksum/failure errors.
- [ ] Historical acceptance not pursued: manual/offline validation of the old
  `1.3` -> `2.0` public-channel flow on real clients.

Notes:
- The private GitHub updates repository is no longer an active delivery channel.
- Do not continue this flow or modify its public Release/manifest without a
  separate migration decision.
- No release/build workflow is started by this task.

## Phase 24 - Shared License And Update Service

Reference: `LICENSE_UPDATE_SERVICE_PRD.md`

### Task 56 - Approve License And Update Service Architecture

Status: In Review

Goal:
Approve the business rules, security boundaries, API surface, database model,
and free VDS-first infrastructure before implementation.

Acceptance:
- [x] One license is limited to one active device.
- [x] Device reset is administrator-only; there is no customer self-service reset.
- [x] The administrator can generate keys in a protected panel.
- [x] Offline use is prohibited and cannot be authorized by a local cache.
- [x] Multiple products and separate update entitlements are represented.
- [x] The first stage requires no new paid service.
- [ ] Exact subdomain is approved.
- [ ] License duration policy is approved.
- [ ] Update entitlement policy is approved.
- [x] Independent architecture/security review findings are reflected in the PRD.

### Task 57 - Create Separate Private Server Repository

Status: Local foundation prepared - private remote still required

Scope:
- Create the server repository only after architecture approval.
- A local repository foundation now exists at
  `/root/projects/Clipart Generator/license-service`, with environment-only
  staging configuration and tests. It has no API, database, secrets, or
  deployment behavior.
- Add server-specific instructions, secret exclusions, migrations, tests, and
  deployment boundaries.
- Do not copy `licenses.db`, desktop secrets, or release artifacts.

### Task 58 - Implement Core License API And Database

Status: Planned - requires architecture approval

Scope:
- Implement products, high-entropy keys, HMAC lookup and protected key
  verification, one-device activation, per-install asymmetric device proof,
  nonce-based validation, signed responses, administrative release,
  revocation, audit events, and transactional concurrency protection.
- Use isolated PostgreSQL roles and migrations.
- Enforce one active device with a PostgreSQL partial unique index and a
  transaction; enforce unique product/version/channel/platform releases.
- Use separate license/update signing keys with `kid`, rollover, backup,
  rotation, and revocation procedures.
- Use the approved v1 Ed25519/RFC 8785 signed envelope with explicit schema and
  algorithm versions.
- Do not implement offline authorization.

Verification:
- Unit and integration tests for all license states and product isolation.
- Concurrent activation test proves that two devices cannot both activate.
- Signature, secret-redaction, response-bound, rate-limit, and migration tests.

### Task 59 - Implement Protected Administrative Panel

Status: Planned - requires architecture approval

Scope:
- Create the first administrator locally; expose no public registration.
- Administrator login with secure sessions, free TOTP two-factor
  authentication, recovery codes, and rate limiting.
- Generate one or multiple keys and show full values only on creation/export.
- Search, suspend, revoke, extend, and manually reset a device binding.
- Display safe device/license identifiers and an immutable audit history.
- Require recent re-authentication for exports, resets, revocation, release
  publication, and signing-key operations.
- No public customer reset route or UI.

### Task 60 - Prepare Free Staging Deployment On VDS

Status: Planned - deployment requires separate approval

Scope:
- Configure the approved subdomain, free TLS, reverse proxy, isolated service,
  isolated PostgreSQL database, private artifact directory, health checks,
  logging, rate limits, and backup/restore procedure.
- Select an existing no-new-cost off-VDS backup target controlled by the owner;
  complete a restore test before production.
- Do not alter existing VDS projects or reuse their database credentials.
- Do not start production service or publish releases in this task.

### Task 61 - Integrate Mandatory Online License Gate

Status: Planned - separate desktop task

Branch: `codex/license-server`

Scope:
- Replace the prototype client contract with the approved signed API.
- Generate a per-install Ed25519 device key and protect its serialized private
  key for the current Windows user with DPAPI; use challenge/response proof and
  fresh nonces without claiming hardware-backed non-exportability.
- Require a fresh server round-trip at startup and immediately before every
  protected operation; periodic checks are additional only.
- Preserve completed outputs and avoid destructive shutdown.
- Remove prototype authorization: the three-day/offline cache and
  `use_offline=True`, client/public `/deactivate`, plaintext license-key
  response/storage, repeated license-key validation, and static admin token.

Verification:
- Offline and invalid-license states fail closed without starting providers.
- Disconnect immediately after validation; the next protected operation is
  blocked.
- Every generation, processing, batch, and mixed-workflow entry point is gated.
- No desktop or public route can reset/release a device binding.
- Valid license permits existing generation and processing unchanged.
- Administrator reset invalidates the old device and permits one replacement.
- Windows packaged-client behavior is checked in an isolated environment.

### Task 61A - Mandatory Startup License Gate Hotfix

Status: Windows installer built - manual Windows acceptance pending

Root cause:
- The signed license gate protected worker starts and retries, but the release
  entrypoint opened the main V3 interface before invoking it.

Implemented:
- Require a fresh online validation before the main window can open.
- If no valid saved activation exists, show the license-key dialog immediately.
- Close startup on cancellation, offline validation, server rejection, or a
  missing license gate.
- Revalidate online after a newly entered key is activated.
- Show license status, the fresh online-check time, `Сменить лицензию`, and
  `Настройки API` before a work mode is selected; never display the full key.
- Default new work to `Pictures/Clipart Generator` and persist the last selected
  work and processing-result folders outside the install directory.

Verification:
- [x] `python -m unittest tests.test_release_entrypoint -v`
- [x] Critical license suite: 41 tests passed.
- [x] Current full desktop suite: 420 tests passed, 1 expected skip.
- [x] Source packaged-entrypoint smoke verifies the masked key field and
  fail-closed startup behavior.
- [x] First-screen license/API controls pass offscreen layout and action tests.
- [x] Pictures default and last-folder restoration pass restart regressions.
- [x] Rebuild the Windows installer from implementation commit `43682ac` in run
  `31909510317` (Windows success; macOS skipped).
- [x] Verify the packaged Windows `.exe` passes `--release-entrypoint-smoke`,
  including startup licensing, visible license/API controls, their signal
  connections, and the Pictures-based default.
- [ ] Manually confirm on Windows that the key dialog appears before the main UI.

### Task 62 - Design And Implement Private Update Delivery

Status: Server deployed - Windows build and acceptance pending

Branches: desktop `codex/feature-updates-diagnostics`; server
`codex/feature-secure-updates`

Scope:
- Add product/platform release records, signed manifests bound to the licensed
  device request, short-lived download tokens, local VDS artifact retention,
  and explicit installer confirmation.
- Keep free Ed25519 service/artifact signatures separate from optional Windows
  Authenticode, which is not required by the free first stage.
- Replace the old client channel with one asynchronous licensed V3 check after
  startup. `Не сейчас` downloads nothing and asks again on the next launch.
- Do not modify existing public releases or publish a new build automatically.

Verification:
- [x] License and update entitlement gates are independent and fail closed.
- [x] Manifest delegation/signature, request binding, HTTPS, size, SHA-256,
  token expiry/use bounds, and interrupted-download cleanup are tested.
- [x] The V3 entrypoint no longer invokes the legacy updater.
- [x] Apply server migration 006 after a fresh backup, deploy with a prepared
  rollback image, and verify public health, artifact upload, and signed update
  key delegation.
- [ ] Validate the manifest/download path with a draft revision after the new
  Windows artifact exists.
- [x] Build Windows `3.0.1` in run `31924194111`; verify the packaged V3
  entrypoint, exact internal version, installer creation, and downloaded SHA-256.
- [ ] Windows upgrade, cancellation, UAC, and rollback safety receive manual
  isolated checks after the separately authorized build.

### Task 62A - Add User-Facing Diagnostic Journal

Status: Implementation complete - packaged Windows visual acceptance pending

Implemented:
- Keep at most three launch sessions and 10 MiB total, with bounded events and
  a non-blocking in-memory fallback if application-data storage is unavailable.
- Show `Журнал диагностики` before mode selection and in the shared wizard.
- Record startup, license, update, configuration, project, processing, retry,
  cancellation, and terminal outcomes without keys, prompts, images, raw
  provider responses, environment values, or full personal paths.
- Allow copying one sanitized record and exporting a ZIP with readable TXT,
  structured JSON, safe system/application information, and a README.

Verification:
- [x] Retention, corruption recovery, event bounds, redaction, copy, export,
  first-screen/wizard visibility, processing events, and packaged-entrypoint
  wiring have automated coverage.
- [x] Package the journal and its connected initial-screen/wizard actions in the
  verified Windows `3.0.1` build.
- [ ] Confirm the journal layout and exported ZIP manually in the packaged
  Windows application.

### Task 63 - Security Review And Production Readiness

Status: Planned

Scope:
- Review authentication, key storage, signing, database access, rate limiting,
  audit privacy, backup restore, incident response, and dependency risk.
- Resolve all high-severity findings before production deployment.
- Production deployment, credential creation, and DNS changes require explicit
  owner approval.

### Task 64 - Proactive Cross-Component Contract Audit

Status: Local audit complete - Windows and live-account acceptance pending

Implemented:
- Align V3 generated-path validation with the worker's `output/.run` run workspace.
- Make native stop-after-current terminal even when the stop marker follows a
  successful output event; pending items are cancelled instead of left running.
- Keep incomplete evidence fields as `unknown`/`None` instead of converting them
  to clean/zero results.
- Remove the legacy sensitive `licenses.db` from Git tracking while preserving
  the ignored local copy for the configured local/server workflow.
- Synchronize offline fixtures with the protected opener and run-workspace
  contracts without making real provider requests.

Verification:
- [x] Focused regressions cover output-path trust, stop-after-current, incomplete
  evidence, provider routing, and metadata-preserving outputs.
- [x] Full local pytest and full `compileall .` checks.
- [ ] Windows packaged, DPI, installer/UAC, real-account, live provider, and
  native teardown checks; these remain `WINDOWS_REQUIRED` or `BLOCKED`.

### Task 65 - Windows 3.0.1 Acceptance Fix Pack

Status: Azure 3.0.2 installer built; Windows acceptance pending

Source of truth:
- `docs/testing/windows-3.0.1-acceptance-checklist.ru.md`

Required for the next Windows build:
- Replace the misleading offline saved-license key prompt with a fail-closed
  server-unavailable state and retry action.
- Disable and explicitly mark the remaining SynthID consent control as
  unavailable.
- Keep the processing file list and model synchronized after `process more`;
  preserve selected inputs until the user removes them.
- Simplify and make the wizard header responsive; remove the false dirty label
  and surface only real autosave failures.
- Lazy-load and cache wizard pages, keep hardware probes off the UI path, and
  show determinate progress for initialization that is visibly slow.
- Use one consistent processing editor presentation across modes and replace
  avoidable user-facing technical English.

Deferred follow-up:
- Simplify the prompt-generation workflow without changing it in the 3.0.1 fix
  pack.

Required regressions:
- Saved activation plus network/server outage never reopens key entry and never
  grants access.
- SynthID remains disabled and labelled unavailable in every mode.
- `process more` has matching visible/model file state and supports reprocessing
  the same input.
- Header actions fit the minimum window at supported Windows DPI values.
- Autosave failure is visible; successful autosave has no false dirty status.
- Initial mode selection creates only required pages and hardware probes cannot
  block the GUI thread.
- Shared processing labels and capability states match across all three modes.

Implemented for candidate `3.0.2`:
- Route only typed temporary license-service failures to Retry/Close; rejected,
  expired, revoked, or otherwise invalid saved activations can open the safe
  replacement-key flow without granting access.
- Keep selected processing inputs synchronized for `process more`; disable and
  label SynthID consistently; localize shared cleanup copy.
- Simplify the work header and show only real autosave failures.
- Construct only the selected mode and requested pages, cache successful pages,
  show determinate initialization progress, and retain failed factories for a
  bounded user-visible retry.
- Synchronize `release/VERSION.txt` and the manual Azure pipeline default at
  `3.0.2`; the pipeline remains build-only with `trigger: none` and `pr: none`.

Verification:
- [x] Focused acceptance regressions: 81 passed, 14 subtests passed.
- [x] Azure offline release-gate command: 49 tests passed, 1 expected skip.
- [x] Supported source tree passes `compileall`, sensitive-artifact scan, and
  `git diff --check`.
- [x] Full suite excluding two documented pre-existing baseline inconsistencies:
  517 passed, 1 expected skip, 4 deselected, 73 subtests passed.
- [x] Manual Azure run `77` (`20260820.1`) succeeded from source commit
  `92046e0`; artifact `windows-installer` contains
  `VibixImages-Setup-3.0.2.exe` (`164809973` bytes) and matching SHA-256
  `46366a1a655e3f272e7bff54674e14c66036d468bdd93e46f2cceaa9fd21fc14`.
- [ ] Repeat focused Windows installation, licensing, DPI, retry, and update
  acceptance against the exact Azure artifact and its SHA-256.

### Task 66 - macOS Azure Release

Status: Azure artifact verified; Mac acceptance pending

Implemented:
- Add a separate manual Azure pipeline for an unsigned `macos-x64` `.app`
  distributed as a ZIP archive with a SHA-256 sidecar. It runs natively on
  Intel Mac and through Rosetta 2 on Apple Silicon because Azure's hosted
  ARM64 preview is currently paused.
- Bundle the verified universal Real-ESRGAN macOS runtime and select its native
  executable name at runtime.
- Request platform-specific update manifests; accept only ZIP updates on macOS,
  verify their signed metadata and SHA-256, and reveal the archive in Finder for
  manual replacement.
- Use `~/Library/Application Support/Vibix Images` consistently for macOS config,
  API credentials, license state, diagnostics, and update downloads.

Verification:
- [x] Full Linux-safe suite: 534 passed, 1 expected platform skip, 2 deselected,
  plus 73 unittest subtests.
- [x] Real-ESRGAN macOS archive SHA-256 and universal arm64 slice verified.
- [x] Azure run `91` succeeded from source commit `6b41682`; artifact
  `macos-x64` contains `VibixImages-macOS-3.0.2-x64.zip` (`245630259` bytes)
  and a matching SHA-256 sidecar:
  `04d4bf58f085f5239a7a6a5c46c3b6470d32ee6d116828ee383d29708399f6d9`.
- [x] The downloaded ZIP passed `unzip -t`; the application launcher and bundled
  Real-ESRGAN executable are Mach-O x86_64 binaries with executable permissions.
- [ ] Manual Gatekeeper acknowledgement, launch, licensing, provider, and update
  acceptance on Apple Silicon hardware.

### Task 67 - Windows Local Processing Repair

Status: Source fix verified; Windows Azure rebuild requires explicit owner approval

Implemented:
- Replace the incomplete Windows Real-ESRGAN `v0.2.0` archive with the official
  pinned `20220424` archive containing the executable, DLLs, and model files.
- Validate the archive SHA-256 and required 2x/4x model files before packaging;
  reject incomplete or unsafe ZIP content.
- Correct the 2x clipart model name to the model actually included in the
  runtime: `realesr-animevideov3-x2`.
- Collect rembg sessions and metadata in PyInstaller and add a packaged local
  runtime smoke gate that checks both Real-ESRGAN resources and rembg imports.
- Keep safe local/provider failure details in diagnostics, including bounded
  task ID, provider error code, and sanitized error message.
- Remove the non-functional BEN2 choice from release UI. Existing BEN2 settings
  migrate to Local rembg rather than KIE; the standalone BEN2 research script
  remains available for a separately managed test environment.

Verification:
- [x] TDD regressions observed failing before each implementation and passing
  afterward.
- [x] Official Windows Real-ESRGAN archive SHA-256 verified as
  `abc02804e17982a3be33675e4d471e91ea374e65b70167abc09e31acb412802d`;
  the preparation script staged all required runtime files.
- [x] Real Local rembg IS-Net inference produced a valid RGBA output with an
  alpha range of `(0, 255)` using a temporary model cache.
- [x] Full Linux-safe suite: 545 passed, 1 expected platform skip, 2 deselected,
  plus 73 unittest subtests.
- [x] Expanded manual Azure release-gate equivalent: 94 tests passed, with the
  expected Linux Real-ESRGAN and absent sibling-service skips.
- [x] `compileall`, sensitive-artifact scan, PowerShell syntax, and
  `git diff --check` passed.
- [ ] Run a new manual Windows Azure build only after explicit owner approval,
  then retest Local Real-ESRGAN and Local rembg in the packaged application.
