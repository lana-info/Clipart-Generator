# Project state

Updated: 2026-08-20

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
- Current task branch: `codex/fix-windows-acceptance-3-0-2`
- Current local implementation head: `2604e57` (review findings fixed; final
  documentation and verification still in progress)
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

The Windows 3.0.1 smoke-test findings are implemented in the 3.0.2 candidate.
Manual Azure run `77` succeeded from commit `92046e0` and published the
`windows-installer` artifact. Download and verify the exact installer SHA-256,
then repeat focused Windows acceptance. Do not upload or publish an update
revision until the build is approved.

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
- The Windows smoke-test findings are fixed in source and covered by local
  regressions; Azure packaging is `CLOUD_OK`, but installation and visible
  behavior remain `WINDOWS_REQUIRED` at real Windows DPI values.
- Do not start Azure/GitHub Actions Windows packaging for the current version
  until all known source issues are resolved and the owner explicitly approves
  the final build run.
- Full pytest has two pre-existing baseline inconsistencies outside Task 65: the
  configured-output-path expectation differs from the current implementation,
  and `TECHNICAL_DEBT.md` links to an untracked local `tech_debt/README.md`.
  The 3.0.2 change set passes when those two baseline tests are deselected.
- The verified 3.0.1 installer remains historical evidence only. The 3.0.2
  acceptance artifact is Azure run `77`, size `164809973` bytes, SHA-256
  `46366a1a655e3f272e7bff54674e14c66036d468bdd93e46f2cceaa9fd21fc14`.
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
