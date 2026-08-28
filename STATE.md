# Project state

Updated: 2026-08-27

## Operating model

- VDS is the primary development environment.
- Windows is the environment for Windows-specific behavior and visual verification.
- GitHub is the source-code handoff point between environments. The current
  Windows 3.0.5 installer must be built by the manual GitHub Actions workflow;
  Azure remains historical/fallback infrastructure and is not queued here.
- Only one side edits the active branch at a time.
- Before changing sides, the active side runs relevant checks, commits, and pushes.
- The receiving side uses `git fetch` and `git pull --ff-only`.
- Windows-only tasks do not block independent Linux-safe work.
- Release pipelines are manual. Start a build only after a separate,
  explicit owner request and only for the platform named in that request;
  ordinary fixes, commits, and pushes must not start Windows or macOS builds.

## Current branch and handoff

- Base branch: `develop/3.0`
- Provider-contract checkpoint branch: `fix/provider-api-contracts`
- Verified provider-aware source: `08648e2a623291b8ba90684e37d947b1db427a0f`
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

Подготовить эталонный набор изображений и после пополнения Fal.ai провести
контролируемое сравнение BiRefNet v2, BEN v2, Ideogram, Bria и rembg. До этого
зафиксировать endpoint `fal-ai/birefnet/v2` и режимы Matting/Portrait/Heavy.

Предварительная стоимость Fal.ai теперь запрашивается вручную с экрана
проверки запуска по текущему набору вызовов. Фактический Usage API после
запуска пока не подключён, чтобы не выдавать расходы всего аккаунта за один
конкретный запуск.

Добавить и проверить Fal.ai background-removal profiles в рабочем UI. До
появления ключа и средств ограничиться локальными тестами; после этого
выполнить небольшой controlled live smoke с подтверждением стоимости.

Run owner acceptance on the replacement Windows 3.0.5 installer from GitHub
Actions run `33032049521`. Do not publish it as an update before this
target-machine acceptance.

## Pinterest Pins Task 6 checkpoint — 2026-08-28

- Feature branch `codex/feature-generation-fal-localization` implements
  selective one-slot regeneration and accepted-pin folder export; it is not
  merged into `develop/3.0` yet.
- Regeneration uses the original immutable `ProductLayer` when it is available,
  keeps its digest, and submits only the selected template or AI-scene slot to
  the existing Pinterest queue. No Fal client or live provider was added.
- Accepted successful variants export to the selected folder as JPG or PNG with
  collision-safe names such as `product_template_01.jpg` and
  `product_ai-scene_01.jpg`; a failed export preserves earlier files and shows
  the saved count and folder.

## Pinterest Pins Task 7 checkpoint — 2026-08-28

- The unmerged feature branch now declares an explicit Pinterest-only route:
  product photo, copy/layout, generation, six-slot preview, and export.
  Clipart prompt-review, cleanup and processing pages are no longer reachable
  in this workflow, and their operations are not allowed by its definition.
- New Pinterest visible strings, errors, statuses and accessibility names use
  the shared RU/EN message registry. Missing product, unavailable output folder,
  failed scene and partial export are covered for both locales.
- Provider capability rejection takes the no-network safe-template fallback;
  the source product remains protected. No Fal client, live API request, paid
  call or release build was added.
- Focused offscreen tests (68) and Python compilation pass locally; the branch
  remains unmerged into `develop/3.0`.

## Replacement Windows 3.0.5 build — 2026-08-27

- All approved owner-acceptance source branches were integrated into
  `develop/3.0` and pushed as commit `02e03d0d666f58fe924c638ad994a8ba0700915a`.
- The combined source passes 738 tests, 1 expected Linux skip, 2 deselected and
  87 subtests; compilation, tracked sensitive-artifact scan and diff integrity
  pass.
- GitHub Actions run `33032049521` built only Windows 3.0.5, installed the
  resulting setup in a clean location, passed packaged startup, artwork,
  prompt-screen and release-contract checks, and uploaded the artifact.
- `VibixImages-Setup-3.0.5.exe` is 191,623,601 bytes. SHA-256:
  `5ab70b1df4eeab98f394b6a1bedde6f1915ae6a0d10325f8777b51327a4eda77`.
- macOS, Azure and update-service publication were not started.

## Generation settings clarity checkpoint — 2026-08-27

- Generation settings identify how many prompts have no references.
- Reference-model settings are hidden when the current prompt table has no
  references. When present, the section is clearly named and displays its
  prompt count.
- Clipart and Pinterest focused tests pass (67 tests). Full offscreen pytest
  passes: 733 tests, 1 expected Linux skip, 2 deselected and 87 subtests.
  Python compilation passes. No paid API request or build was started.

## Reference preflight and Review layout checkpoint — 2026-08-27

- New local references over 10 MB are rejected at selection time with file
  name, actual size and corrective action. Saved projects receive the same
  preflight before worker creation.
- HTTPS references are not silently downloaded merely to inspect their size;
  KIE responses for an oversized reference and official `402 Insufficient
  Credits` are converted to actionable user messages while bounded technical
  details remain available in diagnostics.
- The Clipart/Pinterest Review summary starts directly below its description,
  uses a common left edge and no longer distributes rows vertically.
- Focused Clipart/Pinterest/Results verification passes: 118 tests and 5
  subtests. Full offscreen pytest passes: 736 tests, 1 expected Linux skip,
  2 deselected and 87 subtests. Python compilation passes. No paid request or
  build was started.

## Provider-aware parallel stabilization checkpoint — 2026-08-26

- KIE and PhotoRoom now have independent 1/2/3 settings, each defaulting to
  3, behind a fixed six-task network cap. KIE's limit is shared by generation,
  Topaz, KIE background removal, and other existing KIE operations.
- Generation-only, processing-only and generate-then-process runs preserve
  per-image stage order while independent provider work can overlap. Local
  processing remains sequential.
- PhotoRoom uses its own launch guard: an initial burst of at most its selected
  provider limit, followed by a 60-images-per-minute pace. Bounded HTTP 429
  handling remains in force.
- Recraft payload, availability and no-silent-fallback behavior are unchanged;
  fal.ai remains excluded. Topaz remains limited to 2x/4x.
- Worker lifecycle events retain the exact item index. Results can show several
  active rows and route out-of-order output, failure and cancellation to the
  correct prompt/file. User-facing diagnostics exclude prompts, credentials,
  raw provider responses and full private paths.
- Focused offscreen regressions pass: 292 tests and 24 subtests. Full offline
  pytest passes: 724 tests, 1 expected Linux skip, 2 deselected and 87 subtests.
  Python compilation, tracked sensitive-artifact scan and `git diff --check`
  pass. No paid request, build, merge, push or server publication ran.

## Final concurrency audit — 2026-08-27

- Stop atomically closes admission at every paid provider POST boundary,
  including nested KIE work and PhotoRoom 429 retries. Already admitted tasks
  may settle; no new paid submission is admitted afterward.
- Mode switching and starts in another mode are blocked while any application
  controller owns an active run, preserving the application-wide remote cap.
- Structured cancellation closes every active/pending Results row; legacy
  aggregate progress no longer overwrites indexed progress, and retry
  diagnostics map back to the original item.
- Drive, UNC and POSIX paths with spaces share one redaction implementation in
  item errors, provider events and exported diagnostic archives.
- Full source verification: 731 passed, 1 expected Linux skip, 2 deselected,
  87 subtests; compile and diff checks passed. No paid call or build was made.
- The audited branch was fast-forwarded into `develop/3.0` and the exact merged
  commit `8aae4801718d1a33a427c886ded02a73fb284af6` passed the same full suite.
- GitHub Actions run `33026433664` built only Windows 3.0.5, installed the setup
  in a clean location, passed packaged startup/artwork and release-contract
  checks, and uploaded `VibixImages-Setup-3.0.5.exe` (191,609,853 bytes).
  SHA-256: `3e2efe15b4c35ab2163957715021297c3234e44ec613c989cc941f3e6242c7a7`.
  macOS, Azure and update-service publication were not started.

## Windows acceptance UX checkpoint — 2026-08-26

- Starting a mode, including the same mode from Results, now always opens a
  clean first step. Results exposes one same-mode restart action; mode switching
  remains in the shared header.
- CSV import has a primary top-of-page button, drag-and-drop, bounded mapping
  controls and a live three-row prompt/reference preview.
- Clipart and Pinterest can generate without processing. The Generation step
  no longer displays a partial estimate; Review separates images, generation
  calls, processing calls and their cost components from one calculation.
- Review no longer highlights API-key storage or a generic ready message.
  Processing Review also removes the duplicate external-transfer checkbox;
  choosing a network provider remains explicit on the preceding pipeline step,
  while missing-key and provider errors stay blocking and visible.
  Result hover previews close on pointer leave, app deactivation and Escape;
  terminal runs show a compact count/time/folder summary.
- Full offline pytest passes: 688 tests, 1 expected Linux skip, 2 deselected
  and 83 subtests. Syntax, sensitive-artifact and diff checks pass. No Windows
  build, paid API call or server publication was run for this checkpoint.

## Branded Windows installer checkpoint — 2026-08-26

- The installer source now uses Inno Setup's built-in high-DPI Polar dark style
  with the approved `#101827` surface and coordinated installer artwork.
- The visible flow is grouped into three stages: welcome, installation and
  completion. Destination and desktop-shortcut choices remain available while
  redundant Start Menu and Ready pages are hidden.
- GitHub and Azure Windows workflows pin Inno Setup 6.7.1, the minimum project
  compiler version supporting the selected style and background directives.
- GitHub Actions run `33002277766` built Windows version `3.0.5` from merged
  commit `631219f1b2494857d82f07a380e2f6cf538a4f02`. The workflow installed the
  finished package and verified the approved mode artwork and both prompt
  screens from the installed executable. The installer is `191583836` bytes
  with SHA-256
  `fceb6abfb44c2feb93ce8f2e2142987dc551fa47b0ddf1d7667341b6f12e8fef`.
  macOS and server publication were not run; the visible installer wizard still
  requires owner review on the target Windows computer.

## Provider contract checkpoint — 2026-08-26

- Ordinary generation no longer creates paid KIE availability probes; live
  model checks remain explicit user actions only.
- GPT Image 2, Qwen Image 2 and FLUX.2 use mode-specific documented ratios,
  resolutions, prompt limits, and reference limits before upload.
- Recraft Crisp, Recraft Remove Background and PhotoRoom preflight now match
  their documented file and image constraints.
- The deployed license service is recorded accurately: service URL approved,
  license and update terms implemented, and the admin panel uses username and
  password with TOTP as an additional second factor.
- Full offline pytest passes: 669 tests, 1 expected Linux skip, 2 deselected
  and 83 subtests; syntax, sensitive-artifact, startup-smoke and diff checks pass.
- No live/paid API request or release build is part of this checkpoint.

## Detailed diagnostics checkpoint — 2026-08-26

- Diagnostic schema v2 records a correlated timeline for each image: safe file
  metadata, stage/provider/model, parameters, duration, HTTP status, task ID,
  polling state, result count and bounded provider error.
- KIE generation/processing, PhotoRoom, RunPod and principal local processing
  stages emit structured events without additional network requests. Legacy
  progress parsing remains as a compatibility fallback.
- The journal can filter by severity, provider and image and displays Russian
  labels at the supported 980 x 700 minimum. Session storage remains bounded at
  8 MiB and 24 MiB total across the newest three launches.
- Exact prompts, API/licence keys, headers, full paths, URLs, raw responses and
  image contents are excluded from memory logs, persistent files and ZIP
  exports. Provider messages that echo the current prompt are redacted.
- `docs/API_CONTRACTS.md` records official links, current calls, diagnostic
  events and confirmed discrepancies; diagnostics does not claim those
  discrepancies are fixed.
- Full offline pytest passes: 653 tests, 1 expected Linux skip, 2 deselected and
  83 subtests. No live/paid API request, build or release was run.

## KIE Topaz checkpoint — 2026-08-26

- Root cause confirmed without a paid call: the application still sent the
  retired `topaz/upscale` model and silently replaced configured 4× with 8×.
- The worker, V3 state, provider registry and legacy config now migrate to
  `topaz/image-upscale`; the shared editor exposes only 2× and 4×, while old
  saved 1× values migrate safely to 2×.
- Local inputs are rejected before upload when they are not JPEG/PNG/WEBP,
  exceed 10 MB or would exceed 20,000 px on the longest output side. The error
  states that no KIE task was created.
- Full local pytest passes: 634 tests, 1 expected Linux skip, 2 deselected and
  83 subtests. No network or paid KIE request was made.

## Prompt flow checkpoint — 2026-08-25

- Clipart and Pinterest now use two explicit steps: prompt source/input, then
  series and reference review. The approved mode-selection screen is unchanged.
- The input step presents three visible source choices: generated series, one
  ready multiline prompt with up to five references, and CSV import. Sources
  only add; replace-all actions and the duplicate first-step table are removed.
- The generator combines objects × variations and joins only visible,
  user-entered fields. It adds no hidden mode text, numbering or requirements;
  the first two exact results and total count are shown before creation.
- CSV mapping has one import action, a brief count/error summary and automatic
  navigation to review; there is no duplicate preview table.
- The review step gives the prompt text two thirds of a larger table, supports
  search across hundreds of rows, and keeps compact prompt/reference actions.
- Offscreen screenshots were reviewed at 1400×900 and the supported 980×700
  minimum. The variable text fields are aligned and the 200-row review table
  uses internal scrolling.
- The whole V3 application now starts at 1120×780, cannot shrink below 980×700,
  preserves a user-resized window across menu and every route step, and gives
  large pages internal vertical/horizontal scrolling instead of resizing the
  top-level window.
- Full local pytest passes: 629 tests, 1 expected Linux skip, 2 deselected and
  78 subtests. No paid request or release build was started.
- GitHub and Azure Windows pipelines are configured to capture both prompt
  steps in addition to mode selection from the installed copy. Execution of
  the updated gate awaits a separately approved installer build.

## Current implementation checkpoint — 2026-08-24

The current product priority is to finish the existing interface and close the
remaining UX findings before adding new product modes. The immediate plan is
recorded in `TASKS_3.0.ru.md`: complete `CG3-TASK-034` (rendered UI smoke and
the remaining Windows smoke findings), then implement `CG3-TASK-035`
(controlled parallel KIE generation, initially up to three tasks with one new
task per second). Vectorization and Patterns remain deferred.

- Files and Results UX changes from `CG3-TASK-034` are implemented and covered
  by offscreen tests: file metadata is name/pixels/DPI/MB, overwrite is one
  safe-by-default checkbox, the drop zone is visible, Results uses a larger
  queue with hover/click preview, human duration, and one Diagnostics dialog.
- Local Real-ESRGAN subprocesses request hidden Windows console creation; the
  source registry still exposes both local background-removal providers
  (`rembg` and `BEN2`) and Local Real-ESRGAN for upscale.
- `CG3-TASK-035` has a first implementation: generation-only work uses at most
  three workers, launches new KIE tasks at no more than one per second, retries
  HTTP 429 with bounded backoff, and preserves per-item output/error handling.
- The release branch now also contains the previously divergent Files/Results
  UX work and controlled parallel-generation implementation. The packaged
  smoke can save 1366×900 screenshots of mode selection and Clipart prompts;
  GitHub produces them from the application after Inno Setup installation and
  uploads them beside the installer for visual review.
- Full local pytest passes: 613 tests, 1 expected Linux skip, 2 deselected and
  73 subtests. No paid KIE request was made. Windows installed-copy rendered
  smoke and a small real KIE speed/credit run remain pending.
- GitHub Windows run `32906900417` succeeded from source commit `9222eea`.
  Inno Setup installed the application into a clean directory; the installed
  executable passed version, startup, artwork and native-Windows rendered UI
  checks. The downloaded installer is `191310485` bytes with SHA-256
  `1a93d54e4c555ef6a0f70523b0ff9126ff7b636dd148c75b9c3a80aaf5b7fd7f`.
  Its two readable screenshots confirm the three approved raster illustrations
  and the current Clipart prompt workspace. Server publication was not run.

The Windows 3.0.1 smoke test covered installation, startup licensing, folder
persistence, diagnostics, local processing, cancellation, and basic lifecycle.
Unchecked acceptance items are `SKIP / NOT TESTED`, not proven passes. Do not
upload or publish an update revision until the current source and focused
acceptance are approved.

## Blockers and risks

- Azure Windows run `141` was requested from the merged `develop/3.0` commit
  `5732eedd` on 2026-08-26 but Azure rejected the job before checkout because
  the organization had no free hosted minutes. GitHub Actions run
  `32977293110` replaced it, built Windows only from the exact same commit,
  installed the finished package, and passed the installed-copy artwork and UI
  evidence gates. The downloaded `VibixImages-Setup-3.0.5.exe` is `191362608`
  bytes with SHA-256
  `6c3f4837b381f2da44cd0d54fa4b8fce8ec03b047227efc9e3b57c226d8daba6`.
- The deployed license service and signed online desktop contract are active;
  availability of VDS, DNS, TLS, and PostgreSQL is therefore a direct
  application-availability dependency.
- The local legacy `licenses.db` is ignored and no longer tracked in source
  control; server-side license state must use the configured external database.
- Automated packaged checks passed, but final installation, production-license
  activation, Windows visual behavior, and SmartScreen behavior still require a
  manual check on the target Windows computer.
- Owner testing of the superseded GitHub `3.0.5` showed the pre-artwork card
  layout even though the downloaded installer hash matched run `32900235313`.
  The old gate checked only that three cards existed. The replacement source
  now rejects null card pixmaps and verifies the application again after Inno
  Setup installs it.
- The same owner test exposed visible helper-process console windows. Root cause:
  the `CREATE_NO_WINDOW` change existed only in divergent commit `82fe6ff` and
  was absent from the artwork release branch. The focused fix is now applied to
  Local Real-ESRGAN and all optional local watermark subprocesses. That
  superseded artifact is not a publication candidate; replacement run
  `32977293110` contains the fixes and awaits owner target testing.
- VDS access to the private GitHub repository and Codex authentication must be configured outside Git; no credentials are stored here.
- Linux cannot replace Windows visual and packaged-client verification.
- Azure Windows run `81` proved KIE balance and KIE processing on the owner's
  Windows machine, but its bundled Real-ESRGAN runtime is incomplete and Local
  rembg packaging was not covered by the packaged smoke gate. Source fixes are
  verified locally; a new Windows build remains `WINDOWS_REQUIRED` and may run
  only after explicit owner approval.
- Do not start an Azure Windows or macOS release build unless the owner
  explicitly requests that platform's build after the desired fixes are ready.
- Source now keeps successful worker completion on Results and records an
  ordered privacy-safe technical trail. The exact packaged Windows focus,
  layout, and exported-ZIP behavior still require the next approved build.
- The verified 3.0.1 installer and Azure run `77` artifact are historical
  evidence only; neither contains the current fix pack.
- The current source candidate passes 557 unittest tests and 584 pytest tests
  plus 73 subtests. The expected Linux skip remains because the Windows
  Real-ESRGAN binary is unavailable there. Windows/macOS packaging and manual
  target-machine acceptance remain the final platform-specific checks.
- Final Azure Windows run `102` and macOS run `103` both succeeded from commit
  `a085167e0e311856a4cacedf0c85a6b7147bdc47`. The downloaded Windows installer
  is `204556261` bytes with SHA-256
  `66b011747948f57065ce5a2b3004a74e3a7df55702694f08060d18d195f49db7`.
  The downloaded macOS ZIP is `245668325` bytes with SHA-256
  `ba8d0cc134f0ad8b75dfd419889d942cf5e202ef4db307320a8a771c4b3c6887`;
  its sidecar matches and `unzip -t` reports no errors.
- Windows target testing invalidated run `102` for publication: Local rembg
  cannot initialize `onnxruntime_pybind11_state`, and Local BEN2 is absent from
  its release UI. The source repair now bundles the Microsoft Visual C++ x64
  prerequisite, removes stale native runtime files during upgrade, verifies an
  installed copy in Azure, restores BEN2 through the pinned official 223 MB
  ONNX model, and performs real rembg/BEN2 packaged inference. A replacement
  Windows build was replaced by verified run `116`.
- Final 3.0.3 Azure Windows run `116` and macOS run `117` both succeeded from
  commit `6ed15376d74753078aab6c82a7ae29b673e40fbe`. The downloaded Windows
  installer is `222630658` bytes with SHA-256
  `d9acd80fe1c87aa10e2294b5456ccb67709e6fa9effe9acefa3b023b552eadfd`.
  The downloaded macOS ZIP is `245716567` bytes with SHA-256
  `ae18022315b459b37906f2c0f8ced34b07f26bfb7af97eb2c0a9a6bd6e3b62f9`;
  both sidecars match and the macOS archive passes `unzip -t`.
- KIE documentation still lists `recraft/crisp-upscale`, but that does not
  prove account/region availability; the implementation does not silently
  switch a failed Recraft task to another paid model. Topaz remains the safe
  default.
- The Windows smoke test found a misleading offline saved-license key prompt,
  an enabled SynthID consent control for an unavailable capability, stale file
  UI after `process more`, a clipped/incorrect wizard header, and slow eager
  first-mode initialization. These are tracked in Task 65.
- Do not start Azure/GitHub Actions Windows packaging for the current version
  until all known source issues are resolved and the owner explicitly approves
  the final build run.
- The installer from run `31909510317` predates the new updater and diagnostic
  journal. Use the verified `3.0.1` installer from run `31924194111` for current
  acceptance.
- Secure update delivery is deployed and the Windows artifact exists, but no
  `3.0.1` revision is published yet. Manual Windows installation should precede
  a controlled draft upload and end-to-end update test.
- The macOS build is intentionally unsigned and not notarized. Gatekeeper will
  warn on first launch; the application must not automate bypassing that warning.
- The mode-selection screen now uses packaged 1774×887 PNG illustrations for
  the three primary workflows (clipart, Pinterest pins, and image processing),
  matching the public download page. Windows Inno Setup uses the coordinated
  `assets/installer-wizard-hq.png` artwork and retains the workflow/license
  messaging. Replacement GitHub run `32977293110` verified these assets from an
  installed copy; final visual acceptance remains pending on the owner's
  Windows computer.
- Azure's hosted macOS ARM64 preview is paused. The Azure artifact is x86_64 and
  requires Apple's free Rosetta 2 on Apple Silicon; a native ARM64 build would
  require a self-hosted Apple Silicon agent or a different CI provider.
- Azure run `91` succeeded from source commit `6b41682`; artifact `macos-x64`
  contains `VibixImages-macOS-3.0.2-x64.zip` (`245630259` bytes) with SHA-256
  `04d4bf58f085f5239a7a6a5c46c3b6470d32ee6d116828ee383d29708399f6d9`.

## Approved brand direction

- Product name: `Vibix Images`.
- Subtitle: `AI Image Generation & Processing`.
- Shared family mark: a solid white `V` plus one separate dark pixel at the
  lower right, aligned to the same lower baseline.
- The canonical geometry and portable SVG are recorded under `docs/brand/` and
  in `docs/superpowers/specs/2026-08-17-vibix-shared-mark-design.md`.
- Branding is integrated into the application runtime, Windows icon set, and
  Inno Setup configuration. The current Windows installer naming convention is
  `VibixImages-Setup-<version>.exe`; GitHub run `32977293110` is the current
  verified Windows 3.0.5 acceptance candidate.
- Previous license keys did not exist, so no license-key migration is required;
  the first Vibix Images installation activates a new key through the existing
  online license flow.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
