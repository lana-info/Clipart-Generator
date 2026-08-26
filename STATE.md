# Project state

Updated: 2026-08-26

## Operating model

- VDS is the primary development environment.
- Windows is the environment for Windows-specific behavior and visual verification.
- GitHub is the source-code handoff point between environments; release
  artifacts are built and published by Azure Pipelines.
- Only one side edits the active branch at a time.
- Before changing sides, the active side runs relevant checks, commits, and pushes.
- The receiving side uses `git fetch` and `git pull --ff-only`.
- Windows-only tasks do not block independent Linux-safe work.
- Azure release pipelines are manual. Start a build only after a separate,
  explicit owner request and only for the platform named in that request;
  ordinary fixes, commits, and pushes must not start Windows or macOS builds.

## Current branch and handoff

- Base branch: `develop/3.0`
- Current task branch: `fix/kie-topaz-image-upscale`
- Verified release source: `6ed15376d74753078aab6c82a7ae29b673e40fbe`
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

Owner visual approval of the revised prompt flow, stable window behavior and
Topaz scale control. Do not start a new Windows build or publish `3.0.5` until
the source screenshots are approved.

## KIE Topaz checkpoint — 2026-08-26

- Root cause confirmed without a paid call: the application still sent the
  retired `topaz/upscale` model and silently replaced configured 4× with 8×.
- The worker, V3 state, provider registry and legacy config now migrate to
  `topaz/image-upscale`; the shared editor exposes only 1×, 2× and 4×.
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

- Azure Windows run `139` reached the offline release gate on 2026-08-25 and
  exposed a legacy `QSvgWidget` aspect-ratio API error, fixed in commit
  `631eb43`; replacement run `140` could not start because Azure had no hosted
  minutes. GitHub Actions run `32900235313` replaced that blocked build and
  produced the verified Windows `3.0.5` artifact from commit `44ec8a7`.
- The deployed license service and signed online desktop contract are active;
  availability of VDS, DNS, TLS, and PostgreSQL is therefore a direct
  application-availability dependency.
- The local legacy `licenses.db` is ignored and no longer tracked in source
  control; server-side license state must use the configured external database.
- Automated packaged checks passed, but final installation, production-license
  activation, Windows visual behavior, and SmartScreen behavior still require a
  manual check on the target Windows computer.
- Owner testing of GitHub `3.0.5` showed the pre-artwork card layout even though
  the downloaded installer hash matched run `32900235313`. The old gate checked
  only that three cards existed. The replacement source now rejects null card
  pixmaps and verifies the application again after Inno Setup installs it.
- The same owner test exposed visible helper-process console windows. Root cause:
  the `CREATE_NO_WINDOW` change existed only in divergent commit `82fe6ff` and
  was absent from the artwork release branch. The focused fix is now applied to
  Local Real-ESRGAN and all optional local watermark subprocesses. The `3.0.5`
  artifact is not a publication candidate.
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
  messaging. Source and packaging checks are complete; packaged Windows visual
  acceptance remains pending the explicitly approved Azure build.
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
  `VibixImages-Setup-<version>.exe`; a new Windows build is pending the manual
  Azure pipeline run.
- Previous license keys did not exist, so no license-key migration is required;
  the first Vibix Images installation activates a new key through the existing
  online license flow.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
