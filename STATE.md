# Project state

Updated: 2026-08-24

## Operating model

- VDS is the primary development environment.
- Windows is the environment for Windows-specific behavior and visual verification.
- GitHub is the handoff point between environments.
- Only one side edits the active branch at a time.
- Before changing sides, the active side runs relevant checks, commits, and pushes.
- The receiving side uses `git fetch` and `git pull --ff-only`.
- Windows-only tasks do not block independent Linux-safe work.

## Current branch and handoff

- Base branch: `develop/3.0`
- Current task branch: `codex/tech-debt-11`
- Latest completed audit commit: `e64ee12` (cross-component audit, lifecycle fixes, and
  sensitive-artifact cleanup)
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

The current product priority is to finish the existing interface and close the
remaining UX findings before adding new product modes. The immediate plan is
recorded in `TASKS_3.0.ru.md`: complete the remaining rendered/Windows smoke
checks around `CG3-TASK-034` and validate `CG3-TASK-035` from the packaged
runtime. Vectorization and Patterns remain deferred.

## Current implementation checkpoint — 2026-08-24

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
- A controlled live KIE smoke run completed on 2026-08-25: three GPT Image 2
  1K tasks were accepted and downloaded successfully, with an estimated cost
  of $0.09. Exact packaged-app execution and Windows rendered smoke remain
  pending. The Ubuntu project environment does run the application runtime;
  a second app-level run completed 2/2 generations successfully. Local rembg
  dependencies are installed, but its model is not cached; BEN2 and the
  Windows Real-ESRGAN bundle are not installed on this Linux server.

The Windows 3.0.1 smoke test covered installation, startup licensing, folder
persistence, diagnostics, local processing, cancellation, and basic lifecycle.
Unchecked acceptance items are `SKIP / NOT TESTED`, not proven passes. Do not
upload or publish an update revision until the current source and focused
acceptance are approved.

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
