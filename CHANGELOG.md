# CHANGELOG

## [3.0.0-rc1] - 2026-07-31

- Source release candidate for the Clipart, Pinterest, and Processing V3
  workflows; see [RELEASE_NOTES_3.0.md](RELEASE_NOTES_3.0.md).
- Processing acceptance, Results UX, source preservation, output-folder
  routing, collision handling, and provider-boundary regression evidence are
  recorded in the 3.0 documents.
- Public packaging is not claimed: `APP_VERSION`, `version.json`, installer
  defaults, and existing artifacts still identify `2.0`.

## Unreleased

- Добавлен общий network security guard для credential-bearing provider и
  legacy calls: HTTPS-only redirects, same-host/port policy, protected auth
  headers, bounded JSON responses и typed safe transport errors.

- Windows release теперь фиксирует production dependency constraints, проверяет
  SHA-256 официального Real-ESRGAN archive до распаковки и публикует
  machine-readable secret-free build provenance.

- Из legacy `MainWindow` вынесен автономный `VisibleMarkSettingsWidget` с
  сохранёнными alias-ами, object names, UX-размером и offscreen contract test.

- Добавлен pure processing contract: immutable context/step plan, provider и
  cancellation/event seams, secret-safe failure classification, output-adjacent
  run workspace и единая atomic publication primitive.

- Добавлен pure schema boundary для V3 preferences: version/migration table,
  safe defaults, nested secret stripping, atomic save и проверка валидного
  `output_dir` с fallback из `work_dir`.

- Вынесен единый immutable-каталог generation-моделей: capabilities, visible
  options, estimates, reference compatibility и GPT Image 2 endpoint routing;
  legacy `main`/V3 имена сохранены как compatibility exports, неизвестные
  модели отклоняются явно.

- Закрыт release contract: `release/VERSION.txt` стал строгим source of truth,
  packaging и workflow используют имя `Vibix Images.exe`, а stale/invalid
  version manifest отклоняется тестами и release-contract валидатором.
- Добавлен единый offline pytest baseline с отдельными `network`/`paid`
  markers, offscreen smoke и обычным push/PR CI; Windows packaged smoke остаётся
  manual release-проверкой.
- V3 controllers теперь используют явный runtime adapter protocol; legacy
  `WorkerThread` и перевод его progress-сообщений остаются одной заменяемой
  реализацией без изменения пользовательского потока.
- Added the licensed V3 Windows update flow backed by the self-hosted license
  service. It checks once after successful startup licensing, asks before any
  download, treats `Не сейчас` as no download, verifies the signed manifest,
  exact size, and SHA-256, and launches the installer only after verification.
- Added `Журнал диагностики` before mode selection and in the shared wizard.
  It retains three bounded launch sessions, records safe operational/license/
  update events, lets support copy one sanitized record, and exports a ZIP with
  TXT, JSON, safe system details, and a README.
- Replaced the V3 entrypoint's legacy GitHub update scheduling with the licensed
  server channel; revision publication remains a separate post-acceptance step.
- Made the bundled `release/VERSION.txt` authoritative for the packaged
  application as well as the installer, and made the Windows smoke test reject
  a build whose internal version differs from its installer version.
- Built and verified the Windows-only `3.0.1` installer in Actions run
  `31924194111`. The packaged V3 smoke passed before Inno Setup, and the
  downloaded installer matched SHA-256
  `e095a018a0dd44d7f9d99c7d4bba7e35a7519974894f0428d957c51c40beb973`.
- Fixed the Windows release entrypoint so the main interface opens only after
  fresh online license validation or successful key activation; cancellation,
  offline validation, and missing license configuration now fail closed.
- Added a license/API control card to the first mode-selection screen, including
  safe online-verification status and direct license replacement without ever
  displaying or persisting the reusable key.
- New projects now default to the user's `Pictures/Clipart Generator` folder,
  remember the last selected work and processing-result folders, and no longer
  derive the folder-dialog default from the installed process directory.
- Built the replacement Windows 3.0 installer from commit `43682ac`; the packaged
  executable passed mandatory startup-license, first-screen license/API control,
  connected-action, and Pictures-default checks before installer creation.
- Added a shared persistent processing editor to Pinterest, structured progress
  events with indeterminate long-stage activity, and a global high-contrast dark
  palette independent of the Windows system theme.

- The former startup auto-application behavior remains legacy-only and is not
  connected to the V3 release entrypoint.
- Simplified the cleanup workflow into one safe preset, removed the ordinary processing rights gate, preserved ICC/DPI automatically, and added cleanup-only pixel-parity coverage for PNG and JPEG inputs.
- Locked clipart defaults to upscale-before, remove-background, trim, and 300 DPI export; added an alpha-safe guard so post-background upscale must preserve transparency.
- Added per-file deletion, a visible processing output-folder selector, and safe output-path routing so processed files keep their source intact.
- Added a user-data `.env` credential store for KIE, PhotoRoom, and license secrets, with atomic migration from legacy `config.json` keys and a fail-closed network block if secret persistence cannot be written.
- Fixed result preview rejection when a custom processing output folder is selected; the queue now validates the actual request output directory.
- Simplified the evidence cleanup UI to one “Очистить все служебные данные” checkbox and switched the visible AI-image check handoff to ZeroGPT (manual upload only; no automatic file transfer).
- Separated text-generation and reference-generation settings into distinct visible sections, kept processing on its own wizard step, enlarged reference previews, and clarified visible-marker cleanup wording.
- Expanded the Clipart text-generation model list to include GPT Image 2, Nano Banana 2, Qwen Image 2.0, FLUX.2 Flex/Pro, and GPT Image 1.5 with their supported aspect ratios.
- Unified the Clipart and Pinterest model selectors and aspect-ratio catalogs, including Nano Banana Pro and its reference pairing.



### Added

- Completed the local research-only M1 reverse-SynthID pilot with pinned
  source/model hashes, two profiles on three user-owned inputs,
  reproducibility and fidelity/resource reports; official Gemini evidence
  remains pending and no removal claim or production integration was made.
- Prepared the application for the next multi-platform release as `2.0`;
  hidden SynthID/neural-marker removal remains outside this release pending
  further research.
- Reorganized processing settings into logical operation groups, clarified the
  BEN2 and visible-watermark labels, and added a full metadata cleanup option
  that preserves ICC and DPI while retaining legacy config compatibility.
- Configured Local Real-ESRGAN as a bundled application resource in the source
  runtime and existing PyInstaller recipe; no build or release was run.
- Reduced the initial window height, added scrolling to the processing and
  settings tabs, moved provider settings to the processing tab, simplified
  metadata cleanup to one checkbox, and kept model prices beside their fields.
- Aligned Local rembg and BEN2 controls with the shared processing-settings
  column so fixed-width fields no longer drift to the right.
- Added a trustworthy test matrix and focused feature contracts for KIE
  generation, polling, CSV/reference preparation, license cache lifecycle, and
  verified updater downloads. These tests do not publish, release, or spend
  provider credits.
- Strengthened the trustworthy test set with a network-free generation-to-PNG
  integration flow, public license activation/cache coverage, updater checksum-
  mismatch cleanup, and corrupt-input rejection; runtime-dependent tests were
  then verified in the project's full local environment.
- Verified the complete test suite in the project `.venv`: `198/198` tests pass;
  also stabilized the concurrent budget-reservation test against transient lock
  timing without changing production behavior.
- Completed Task 50 cleanup acceptance across independent metadata choices,
  combined local processing, mixed KIE, and PhotoRoom Standard routes.
- Added offline light/dark comparison evidence for photo, face, illustration,
  transparent clipart, and text-heavy content; decoded RGBA, alpha, dimensions,
  ICC, and DPI were preserved through metadata-only cleanup.
- Added regression coverage for PhotoRoom plus shared cleanup, mixed KIE plus
  cleanup, exact KIE credential hosts and redirects, fully decodable provider
  PNGs, non-blocking Stop, cancellation-before-publication, secret-safe provider
  errors, bounded provider uploads/responses, and non-retried POST requests.
- Fixed Stop so it remains responsive while an in-flight request finishes and
  never publishes the current item after cancellation.
- Restricted KIE credentials to exact `kie.ai`/`redpandaai.co` domains and their
  subdomains; sensitive headers are not inherited by redirects.
- Stopped logging provider response bodies, validated PNG payloads by decoding,
  and retry only idempotent GET/HEAD/OPTIONS requests automatically.
- Hardened KIE, PhotoRoom, update, and license transports against HTTPS downgrade
  redirects; remote license URLs require HTTPS, authenticated redirects cannot
  inherit secrets, and provider response/upload sizes are bounded.
- Added bounded update manifest/installer responses and HTTPS-only update URLs;
  local Real-ESRGAN, rembg, and BEN2 inputs now reject animated or oversized
  images before model execution.
- Added focused security-boundary regression tests and consolidated repeated
  HTTPS URL validation without changing provider or updater behavior.
- Kept model preflight fail-closed for transport failures while allowing only a
  bounded, classified reference-schema error without exposing provider bodies.
- Changed user-confirmed visible-mark wording to report bounded area processing
  that requires visual verification instead of claiming proven removal.
- Verified Task 50 with 176 offline tests and no paid request, build, tag,
  workflow, or release.
- Completed Task 42 with a pinned, isolated, no-download production-hardware
  feasibility preflight for `remove-ai-watermarks` SDXL, ControlNet, and Qwen
  pipelines.
- Recorded the current Windows machine's local production no-go: no CUDA/XPU/MPS
  device or upstream DirectML path, `17.95 GiB` total RAM, and audited selected
  weights of `12.92 GiB` for SDXL, `15.25 GiB` with ControlNet, and `53.74 GiB`
  for Qwen before its CPU FP32 expansion.
- Added a bounded official Hugging Face metadata audit plus Task 42 preflight
  and 13 focused tests that verify source/model revisions, card licenses,
  selected weight filenames/sizes, upstream constants, clean source checkout,
  zero model downloads, and `not_verified` detector status.
- Skipped conditional Tasks 43-49 because Task 42 produced no approved pipeline;
  no model weights, GPU resources, desktop controls, release, or paid requests
  were created.
- Verified Task 42 with 26 pinned-upstream focused tests, 13 local focused tests,
  all 149 project tests, Python compilation, and offscreen `SMOKE_OK`; `main.py`
  and application requirement files remain unchanged.
- Completed the isolated Task 41 managed-editor fidelity benchmark for
  Seedream 4.5 and Riverflow 2.5 Pro with a strict preservation prompt,
  one-shot per-candidate reservations, and the existing multi-class RGBA rubric.
- Excluded FLUX.2 Max from paid execution because its per-megapixel endpoint
  does not expose a bounded output size, so the request could not prove a hard
  maximum inside the approved test budget.
- Added layered paid-request controls: endpoint capabilities/prices and an exact
  provider tag are checked before reservation; local state uses one-shot locked
  reservations; pinned HTTPS rejects redirects; byte/pixel/decompression limits
  cover inputs/results; and secret-safe error parsing never stores raw responses.
- Added 28 focused Task 41 tests for closed/no-key gates, concurrent one-shot and
  total-budget behavior, tampered state, actual-cost violations, ambiguous
  endpoints, key limits, redirect protection, bounded image decoding, Windows
  lock errors, secret-safe reports, RGB fallback input, and `not_verified`
  pixel-marker claims.
- Recorded the paid Task 41 evidence. Seedream RGB cost `$0.040`, lost alpha,
  changed face/photo detail, added C2PA, and remained `not_verified`. Riverflow
  preserved the visible image best but lost alpha, remained `not_verified`, and
  reported `$0.264885` against a `$0.130` endpoint snapshot.
- Rejected all managed whole-image providers and activated Task 42. Successful
  Task 41 responses total `$0.304885`; including Task 40, known billed test spend
  is `$0.339885`. Paid testing stopped and the final authorization list is empty.
- Verified the final closed-gate state with 28 focused Task 41 tests and all 136
  project tests; the existing offscreen application main flow remains unchanged.
- Added the isolated Task 40 OpenRouter benchmark preparation for
  `recraft/recraft-v4.1-utility`, reusing the Task 39 RGBA fixture and quality
  rubric while keeping the production application unchanged.
- Added a globally closed paid-request gate, process-independent one-shot
  reservation, base64 reference transport, strict provider-image validation,
  allowlisted cost/media parsing, and secret-safe failure reports. The benchmark
  remains outside the production application.
- Added bounded WebP container inspection for the OpenRouter benchmark. It
  records the presence of Recraft's signed `CRFT` provenance block without
  serializing its signature, identifier, or other provider values.
- Added the isolated Task 39 KIE whole-image regeneration harness, a globally closed live-request gate after the five authorized attempts, one multi-class RGBA fixture, provider-byte preservation, per-tile quality/alpha/dimension metrics, metadata/C2PA inspection, and Task 38 `not_verified` status output.
- Added the Task 39 comparison report for GPT Image 2 and FLUX 2 Pro at `1K`; generated artifacts remain outside git and no production UI or pipeline behavior changed.
- Added the provider-neutral hidden pixel-watermark status contract with separate processing/evidence/file-hint/handoff branches, explicit input/output evidence stage, controlled `detected`/`not_detected`/`not_verified`/`unsupported` evidence, official Gemini SynthID handoff, safe logs, and no false `removed` state.
- Added 6 focused status-contract tests covering scoped negative evidence, successful-but-unverified processing, metadata/C2PA separation, unknown markers, invalid detector claims, JSON serialization, and secret-safe formatting.
- Added the pinned MIT-licensed MI-GAN ONNX model for bounded user-confirmed visible-mark filling, with a local integrity check, attribution, and Windows/macOS PyInstaller data entries; no build or release was run.
- Added Task 37 acceptance evidence for 3 marked and 6 unmarked general-image fixtures: source hashes, dimensions, modes, and alpha were preserved, no pixels changed outside approved masks, clean files produced no output, normal/200% comparisons passed, and no KIE/API request was made.
- Added local visible-mark processing before the first upscale: automatic Gemini detection at confidence `>= 0.5` and a per-file user-confirmed rectangle for other small service marks.
- Added atomic `raw/*_visible_mark_*.png` output validation, alpha preservation, cancellation/rollback handling, and runtime-only confirmed coordinates; this step never requires or calls KIE.
- Vendored the pinned Apache-2.0 Gemini detector and its two required templates from `remove-ai-watermarks` commit `190dc89d234fd7e3a61ff755f01251c9c0b87ef0`, including attribution and packaging data.
- Added the detector templates, license, and notice to the tracked Windows/macOS PyInstaller commands without running a build or release.
- Added disabled-by-default visible-mark settings at the top of the processing order with only `Gemini automatically` and `User-confirmed area` modes, compact right-side parameters, and no KIE/provider selector.
- Added the isolated Task 31 visible-mark detector evaluation harness and documented the pinned `remove-ai-watermarks` revision, Apache-2.0 attribution requirement, reproducible command, confidence/location/timing results, and temporary binary-mask output.
- Added a separate visible-mark inpainting benchmark harness for automatic versus user-confirmed rectangular masks; it reports runtime, changed pixels inside/outside the mask, alpha presence, and optional-backend failures without overwriting sources.
- Added the Task 33 KIE mask-edit benchmark preparation note with the documented API contract, mask semantics, supported aspect ratios, and a minimal no-key paid-test protocol.
- Added an isolated KIE benchmark harness with a five-request hard cap, secret-safe progress capture, output metadata inspection, resize-normalization baseline, and request-free reanalysis of an existing result.

- Added metadata-cleanup acceptance coverage for every independent removal choice and one combined local pipeline with before/after pixel and alpha invariants.
- Documented the implemented Tasks 24-30 contract, exact PNG/JPEG limits, ICC/DPI behavior, atomic final-save order, and unsupported C2PA/pixel-watermark claims.
- Added one atomic final-save path for optional metadata/C2PA cleanup across generate-only, generate-and-process, process-only, local, and mixed workflows.
- Added value-safe cleanup progress summaries for found, removed, preserved, unsupported, and failed categories without logging metadata values.
- Added 10 final-save integration tests covering disabled compatibility, cleanup-only runs, local/mixed routes, trim order, ICC/DPI preservation, 300 DPI precedence, palette alpha, C2PA preflight, safe logs, and rollback.
- Added a compact final-file cleanup section with independent EXIF, XMP, IPTC, comments/text, embedded-thumbnail, known-generator, and embedded-C2PA choices plus ICC/DPI preservation settings.
- Added offscreen UI coverage for independent cleanup choices, legacy-safe defaults, persistence, restoration, and non-overlapping layout.
- Added explicit C2PA export cleanup for bounded PNG `caBX`, JPEG APP11/JUMBF, valid embedded XMP pointers, and supported external manifest references in a new PNG.
- Added 11 C2PA cleanup tests covering PNG/JPEG containers, remote and `self#jumbf` references, post-`IDAT` XMP, packet/comment/PI preservation, unknown and mixed provenance, duplicate XMP, sidecars, value-safe results, and atomic rollback.
- Added a selective metadata cleanup core for new PNG exports with independent EXIF, XMP, IPTC, comments/text, embedded-thumbnail, known-generator, ICC, and DPI options.
- Added a shared exact-match generator metadata policy plus bounded PNG/JPEG preflight, UTF-8/UTF-16 XMP handling, EXIF overlap protection, stripe-based pixel/alpha verification, value-safe metadata digests, and atomic publication.
- Added 15 cleanup tests covering category independence, ICC/DPI, palette/RGB transparency, localized iTXt, C2PA rejection, malformed/overlapping EXIF, UTF-16 XMP declarations, duplicate text, multiple JPEG comments, input limits, and failure rollback.
- Added bounded read-only C2PA presence inspection for PNG `caBX` and JPEG APP11/JUMBF containers without signature validation or remote-manifest access.
- Added adversarial C2PA fixtures for truncated/oversized chunks, nested and extended lengths, malformed toggles, APP11 sequence gaps, extra continuations, and scan limits.
- Added a standalone read-only PNG/JPEG metadata inspector with structured summaries for EXIF, XMP, IPTC, comments/text, embedded thumbnails, ICC, DPI, and known generator fields.
- Added synthetic metadata fixtures covering transparent PNG, JPEG, content-based format detection, animation rejection, invalid inputs, and value-safe JSON serialization.
- Added PhotoRoom Standard background removal with a separate masked API key, provider selection, PNG/RGBA validation, and process-only routing without KIE.
- Added network-free PhotoRoom tests for multipart requests, alpha output, failures, provider routing, key locking, validation, and settings persistence.
- Added independent upscale passes before and after background removal, each with its own provider and scale/model settings plus a combined multiplier indicator.
- Added focused tests for before-only, after-only, and two-pass upscale order, dimensions, alpha preservation, and legacy config behavior.
- Added `CLEANUP_CAPABILITY_MATRIX.md` with source-backed decisions for EXIF/XMP/IPTC, generator metadata, C2PA manifests, SynthID, unknown pixel-level markers, and visible marks.
- Evaluated `lana-info/remove-ai-watermarks` as an Apache-2.0 prototype candidate and separated its metadata, visible-inpainting, and whole-image diffusion modes.
- Added ordered prototype and conditional integration tasks for pixel-watermark regeneration across general images, with local, KIE, and OpenRouter comparisons.
- Expanded the remaining cleanup roadmap into focused Tasks 24-50 with separate gates for metadata/C2PA, visible marks, KIE-first hidden-marker regeneration, optional OpenRouter evaluation, and conditional GPU serverless/VPS gateway work.
- Added isolated offscreen UI acceptance tests for the window title, work-folder setup, API-key lock, processing-setting persistence, validation, and completion/Stop dialog rules.
- Added network-free KIE routing tests for worker and UI key validation, generate-only output, mixed local/KIE processing, error reporting, and secret-safe logs.
- Added focused local-processing acceptance tests covering Real-ESRGAN, PNG/JPG process-only flows, alpha controls, Unsharp Mask, edge shrink, trim, and pipeline order.
- Added a post-MVP export cleanup plan for selective metadata cleanup, visible generator marks, and supported hidden provenance data.
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
- Added a standalone BEN2 evaluation script for testing background removal quality outside the app runtime.
- Added Local BEN2 as an experimental background removal provider with hard alpha, softness, and corner radius controls.

### Changed

- Completed the separately authorized Task 40 OpenRouter comparison and closed
  its live-request gate again. Recraft V4.1 Utility is rejected for production;
  Task 41 is now the next decision gate.
- Changed the multi-platform release workflow to manual-only `workflow_dispatch`; ordinary pushes to `main` no longer start builds or releases.
- Replaced visible-mark `cv2.inpaint` after its 200% quality check exposed rectangular patches: the Gemini mode now reconstructs the known alpha overlay, while confirmed small service labels use bounded local MI-GAN with an internally feathered edge.
- The fixed processing order now starts with optional local visible-mark cleanup; all existing upscale, Unsharp Mask, background, edge, trim, metadata, and final-save ordering remains unchanged after it.
- Task 34 approved a disabled-by-default local visible-mark path: automatic detection only for Gemini, a user-confirmed bounded mask for other small service marks, and no KIE key or KIE selector. Task 37 retained those product limits while improving the local fill method.
- Rejected KIE GPT Image 1.5 as the precise visible-mark fallback; bounded local processing remains selected, while whole-image managed regeneration stays separate for future hidden-marker evaluation.
- Closed the metadata/C2PA acceptance gate and moved visible generator-mark work behind its separate prototype and go/no-go tasks.
- Process-only runs can now perform metadata cleanup without another image-processing step or a KIE API key.
- Selected cleanup carries supported metadata through trim and print-export staging; the existing 300 DPI export setting remains the final DPI authority.
- Advanced the metadata-inspector schema to v3 with separate embedded-container, embedded-XMP-reference, supported-external-reference, and unclassified-provenance states.
- PNG text inspection now uses a bounded raw chunk scan so metadata after `IDAT` is included without decoding image pixels.
- Selective XMP cleanup now preserves packet wrappers, comments, processing instructions, and unrelated fields; ambiguous provenance aborts unless full XMP removal is explicitly selected.
- Known generator fields now use one shared exact allowlist; substring matches and ordinary EXIF camera `Model` fields are no longer classified as generator metadata.
- Metadata-only cleanup rejects C2PA-bearing or indeterminate inputs until explicit C2PA export cleanup is implemented in Task 27.
- Advanced the metadata-inspector schema to v2 with a separate C2PA presence, scan-status, and always-`not_validated` result.
- Closed the non-release MVP acceptance gate and moved the ordered task plan to the post-MVP cleanup capability research task.
- Isolated startup update timers and pending windows in UI tests so the full suite cannot trigger background update checks or write outside temporary test folders.
- Reworked the open task plan into ordered MVP verification, metadata cleanup, hidden provenance, and conditional visible-mark stages; build and release work remain excluded unless requested separately.
- Ignored local `realesrgan-ncnn-vulkan-20211212-windows/` binaries and models so they do not get committed.
- KIE API key validation now depends on the selected processing providers instead of any enabled processing step.
- Changed the rembg requirement to `rembg[cpu]` so fresh installs include the CPU backend.
- Extended the processing order to `optional upscale before -> Unsharp Mask -> remove background -> optional upscale after -> edge shrink -> trim`.
- Limited the planned first cleanup implementation to single-frame PNG/JPEG inspection and new-PNG export; experimental whole-image regeneration is kept separate from metadata cleanup and cannot claim success without detector evidence.
- Prioritized KIE before new infrastructure; RunPod/Modal and the ordinary VPS gateway are now conditional fallbacks instead of mandatory application dependencies.
- Removed the trim timing selector from the UI; trim now always runs at the end.
- Reordered the processing controls vertically to match the actual processing order, with each step's parameters on the right.
- Made Unsharp Mask an independent processing step that can run without upscale.
- Compacted the edge contour pixel selector and adjusted processing provider settings to prevent price/model field overlap.
- Moved KIE processing cost labels back next to their model selectors while keeping the provider settings grid compact.
- Placed KIE processing cost labels in the same inline row as their model selectors.
- Local BEN2 background removal now defaults to hard alpha output so it does not introduce semi-transparent edges unless softness is enabled.
- Local Real-ESRGAN `Clipart 2x` now uses the matching `RealESRGANv2-animevideo-xsx2` model instead of forcing the x4 anime model to 2x.
- Removed unsupported Local Real-ESRGAN `3x` from the scale selector; local scale choices are now `2x` and `4x`.
- Local Real-ESRGAN now preserves the alpha channel when upscaling already-trimmed transparent PNG files.

### Fixed

- Fixed packaged Local Real-ESRGAN resource lookup so the bundled binary is
  found inside PyInstaller's `_internal` resource directory.
- Fixed the Windows build script to use the project `.venv` Python when
  available, matching the tested local environment.
- Fixed GPT Image 2 generation by routing text prompts to `gpt-image-2-text-to-image` and reference prompts to `gpt-image-2-image-to-image`, while preserving the existing `gpt-image-2` UI/config id.

### Verified

- Completed one OpenRouter Recraft V4.1 Utility generation: the API response
  reported `$0.035` and `12.588 s`. It returned `1024x1024` RGB WebP, lost alpha,
  changed the photo/face/clipart/text content, scored global SSIM `0.177527`, and
  added a signed `CRFT` provenance block. Pixel-marker status remains
  `not_verified`, so removal is not claimed.
- Verified the completed Task 40 state with 10 focused tests and all 108 project
  tests. The code-level live gate is back at zero, the persistent state records
  the single attempt as used, oversized WebP files are rejected before reading,
  bytes outside the declared RIFF boundary are rejected, and provider
  signature/identifier values are not serialized.
- Completed three Task 40 review passes and fixed every reported important
  issue: bounded reads, consistent verification counts, and strict RIFF
  boundaries. No blocking or important finding remains open.
- Verified the Task 40 preparation command without network access and 6 focused
  tests: the live gate remains closed at zero, no state/output is created by a
  denied call, one future authorization cannot be reused from another process,
  a missing key does not consume an attempt, and analysis cannot claim pixel
  watermark removal without detector evidence. All 104 project tests pass.
- Completed the two remaining user-authorized provider attempts: GPT Image 2 task polling took `99.497` seconds at a listed `6 credits / $0.030` and returned `1254x1254` RGB; FLUX 2 Pro task polling took `67.568` seconds at a listed `5 credits / $0.025` and returned `1024x1024` RGB. Upload time is excluded. Both flattened alpha and added embedded C2PA; FLUX also contaminated the board with the control grid. Neither output has detector evidence, so both remain `not_verified` and KIE is rejected as the universal regeneration path.
- Verified Task 39 with 5 focused tests and all 98 project tests; the fixture has real alpha, the exhausted budget blocks live generation independently of output directory, credit snapshots are recorded, the FLUX fallback keeps its safety checker enabled, and report analysis cannot claim pixel-marker removal without detector evidence.
- Verified Task 38 with 6 focused tests and all 93 project tests: processing success remains separate from detector evidence, negative evidence is scoped, metadata/C2PA hints cannot imply pixel results, unknown markers cannot report `removed`, and safe logs ignore arbitrary provider values.
- Verified Task 37 with 8 focused tests and all 87 project tests on two marked Gemini images, one user-confirmed Doubao label, five clean upstream images, and one clean user-owned clipart. The final local path changed `0` pixels outside approved masks, preserved sources/dimensions/modes/alpha, left all clean fixtures unchanged, passed normal/200% visual inspection, and made `0` KIE/API requests.
- Verified Task 36 with 6 focused tests and all 85 project tests: visible cleanup runs only when enabled and before upscale, process-only works without KIE, confirmed coordinates are not persisted, alpha is preserved, zero pixels change outside the approved mask, and failure/cancellation preserve source and prior output.
- Verified the real owned Gemini fixture at confidence `0.694789`: the source hash remained unchanged, `3,237` pixels changed inside the removal mask, and `0` outside. An unmarked UI screenshot scored `0.184643`, stayed unchanged, and created no raw output. No API request or credit was used.
- Verified the Windows build script parses, the GitHub workflow YAML parses, and every declared detector data path exists; packaging itself was intentionally not run.
- Verified the Task 35 controls use safe defaults for legacy configs, enable parameters only with the action, show confirmation only for the manual-area mode, persist independently, stay inside the existing processing layout, and expose no unsupported automatic/KIE option; 2 focused offscreen tests pass.
- Verified the isolated detector against one Gemini marked fixture, one Doubao marked fixture, and five unmarked upstream fixtures: 2/2 marked detections and 0/5 false positives. Jimeng, Samsung, and user-owned marked fixtures remain unverified.
- Verified bounded `cv2` inpainting as the Task 32 safety baseline; Task 37 later rejected its visible production quality and replaced it with reverse-alpha Gemini recovery plus bounded local MI-GAN. LaMa remains unselected.
- Completed the Task 32 owned-fixture gate with a Gemini-marked image and an unmarked clipart: detector confidence `0.694789`, no unmarked detection, zero changed pixels outside both automatic and rectangular masks, and opaque RGBA preserved.
- Completed one successful KIE GPT Image 1.5 mask-reference generation at a listed `$0.02` in `102.485` seconds after two native 4o payloads were rejected before generation. The output removed the mark but changed `817,034` pixels (`78.3491%`) outside the mask versus a `2.5936%` resize-normalization baseline and `0%` for local `cv2`; no API key appeared in the saved report or progress capture.
- Closed the Task 34 provider gate from two reproducible marked fixtures, five reproducible unmarked fixtures, and the user-owned Gemini marked/unmarked pair. Gemini is the only approved automatic mark; Doubao and unmeasured marks remain user-confirmed-only.

- Verified every cleanup checkbox independently and all choices together in a local pipeline; 2 focused acceptance tests and all 77 project tests pass with identical final-stage pixels/alpha.
- Verified 10 focused final-save cleanup tests and all 75 project tests pass after review of byte-equivalent disabled behavior, atomic rollback, trim ordering, metadata preservation, palette alpha, and C2PA conversion safety.
- Verified the cleanup UI keeps all removals disabled for legacy configs, preserves ICC/DPI by default, restores every choice independently, and passes 2 focused plus all 65 project tests.
- Verified 11 focused C2PA cleanup tests and all 63 project tests pass; three review passes closed URI prefix collisions, mixed valid/unknown provenance, post-`IDAT` metadata, XMP structure preservation, and duplicate-key concerns.
- Verified the cleanup result states that remote manifests, sidecars, signature validity, and pixel soft bindings were not deleted, accessed, removed, or validated.
- Verified 15 focused metadata-cleanup tests and all 52 project tests pass; the third review pass returned `PASS` after C2PA, alpha, EXIF-overlap, XMP, allowlist, preservation, JPEG-comment, and memory-bound findings were fixed.
- Verified cleanup preserves source files and prior outputs on failure, preserves selected ICC/300 DPI and unchecked supported metadata values, and publishes only after decoded pixels, dimensions, alpha, and metadata match expectations.
- Verified 8 focused C2PA tests and all 37 project tests pass after enforcing PNG/JPEG bounds, nested/extended JPEG JUMBF lengths, contiguous APP11 sequence, and required description toggles.
- Verified the detector against 54 embedded C2PA PNG/JPEG fixtures from the official `contentauth/c2pa-rs` checkout, including a 30-segment JPEG; all detected fixtures returned an OK bounded scan.
- Review reproduced and fixed incomplete-JUMBF and invalid-toggle false positives before Task 25 was closed.
- Verified metadata inspection preserves source hashes, sizes, and modification timestamps; no fixture metadata values appear in serialized results.
- Verified 5 focused metadata-inspector tests and all 29 project tests pass after bounded decompression-bomb error handling.
- Verified Tasks 24-50 are contiguous and include Goal/Steps/Acceptance/Verification/Notes; Task 25 is now the next safe implementation task.
- Verified the planning-only change leaves `main.py` compiling and all 24 existing tests passing.
- Verified all 24 tests pass in one process, including PhotoRoom Standard, both upscale positions, GPT Image 2 routing, real local Real-ESRGAN checks, and isolated main-window acceptance checks.
- Verified `2x + 2x` produces `4x`, `4x + 4x` reports `16x`, and post-removal upscale preserves a valid alpha channel.
- Verified the cleanup matrix links every factual capability claim to official Google, C2PA, W3C, IPTC, Pillow, Adobe, or c2patool documentation.
- Verified current `remove-ai-watermarks`, KIE, and OpenRouter documentation before assigning local and cloud candidates to separate prototype tasks.
- Verified PhotoRoom process-only does not require or call KIE, validates PNG alpha before saving, and never writes its API key to progress logs.
- PhotoRoom verification used mocked network responses only; no paid live request or credits were used.
- Verified GPT Image 2 generation and availability probes use the same documented task-model routing without making a live KIE request.
- Verified non-GPT generation model ids remain unchanged by the new resolver.
- Verified sections 1-9 of `TEST_CHECKLIST.md` through automated UI/worker tests plus the previously recorded real local pipeline and dark-background inspection.
- Verified generate-only writes `raw/` and `output/`, background removal produces PNG alpha, and processing settings restore from an isolated saved config.
- Reviewed `README_AUTHOR_SHORT.md`, `PRD.md`, `TASKS.md`, `CHANGELOG.md`, and `TEST_CHECKLIST.md`; their MVP flow and fixed processing order agree with the current application.
- Live KIE generation, manual visual UI inspection, build, tag, release, and update-repository actions were not performed.
- Verified 5 focused KIE routing tests pass without network calls.
- Verified UI and worker routing across local-only, KIE-only, local-to-KIE, and KIE-to-local provider combinations.
- Verified simulated generate-only and mixed local/KIE workflows save `raw/` intermediates and final `output/` PNG files.
- Verified provider failures remain visible while the API key stays absent from progress and completion logs.
- Did not run a live KIE smoke request to avoid consuming credits; external provider availability remains intentionally unverified in this task.
- Verified 7 local-processing acceptance tests pass without KIE or network calls.
- Verified real Local Real-ESRGAN `2x` and `4x` runs produce exact dimensions, preserve binary alpha, and retain the expected quadrant layout without tile artifacts.
- Verified local process-only accepts RGBA PNG and RGB JPEG inputs, writes diagnostic intermediates to `raw/`, and saves final PNG output.
- Verified the local order is `upscale -> unsharp -> remove background -> edge shrink -> trim -> save`.
- Verified BEN2 hard alpha, optional softness, rembg edge softness, RGB-preserving edge shrink, and transparent-border trim with deterministic image fixtures.
- Inspected the real `4x` transparent result on a dark background; the alpha boundary was clean and no tiled layout defect was visible.
- Verified the current `main.py` compiles and constructs `MainWindow` in Qt offscreen mode without errors.
- Verified an isolated legacy config preserves existing values and receives safe defaults for missing processing settings without accessing the user's real config.
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
- Verified provider cost labels construct next to model selectors in an offscreen UI smoke test.
- Verified inline processing cost labels share the same row widget as their model selectors.
- Verified the BEN2 evaluation script compiles and exposes CLI help without requiring BEN2 dependencies.
- Verified BEN2 can run on the watercolor bird sample and save PNG plus dark preview output for visual comparison.
- Verified Local BEN2 UI settings save/load and hard-alpha post-processing with targeted smoke tests.
- Verified Local Real-ESRGAN model selection maps `Clipart 2x` to the x2 model and `Clipart 4x` to the x4 model.
- Verified Local Real-ESRGAN preserves alpha on the affected trimmed bird PNG during a real `2x` run.

## 3.0 final stabilization

- Verified Windows x64 installation, V3 startup and all three client modes.
- Fixed Processing intermediate path handling; selected output folders and source files are safe.
- Verified persistence of API settings, output folders, recipes and Processing preferences.
- Deferred RunPod SynthID and automatic updates; documented macOS arm64 limitations.
