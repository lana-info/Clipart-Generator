# Project state

Updated: 2026-08-17

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
- Latest task commit: `ffd407a` (cross-component audit, lifecycle fixes, and
  sensitive-artifact cleanup)
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

The cross-component audit and local sensitive-artifact cleanup are implemented
and covered by the desktop tests. The next step is manual installation and
UI/update acceptance on Windows; only after that should the verified artifact
be uploaded and published as a licensed update revision.

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
  `VibixImages-Setup-<version>.exe`; a new Windows build is still pending an
  explicit build request.
- Previous license keys did not exist, so no license-key migration is required;
  the first Vibix Images installation activates a new key through the existing
  online license flow.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
