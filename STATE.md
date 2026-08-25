# Project state

Updated: 2026-08-22

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
- Current task branch: `codex/release-3.0.3`
- Verified release source: `6ed15376d74753078aab6c82a7ae29b673e40fbe`
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

Download Azure Windows run `116` and macOS run `117` for owner acceptance.
Repeat Local Real-ESRGAN, Local rembg, Local BEN2, Trim + 300 DPI Results, and
diagnostic-ZIP acceptance on Windows. Do not upload either 3.0.3 artifact as a
server revision until the owner explicitly requests it after focused testing.

## Blockers and risks

- The deployed license service and signed online desktop contract are active;
  availability of VDS, DNS, TLS, and PostgreSQL is therefore a direct
  application-availability dependency.
- The local legacy `licenses.db` is ignored and no longer tracked in source
  control; server-side license state must use the configured external database.
- Automated packaged checks passed, but final installation, production-license
  activation, Windows visual behavior, and SmartScreen behavior still require a
  manual check on the target Windows computer.
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
