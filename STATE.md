# Project state

Updated: 2026-08-16

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
- Current task branch: `codex/feature-updates-diagnostics`
- Latest feature commits: `1426e0c` (diagnostic journal), `ef52a9f`
  (licensed updater), and `4a70fe7` (bounded/non-blocking hardening)
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

The licensed V3 updater and diagnostic journal are implemented and covered by
the desktop tests. Migration 006 and the matching license-service branch were
deployed on 2026-08-16 after a fresh database backup; the public health endpoint,
artifact-upload UI, and signed update-key delegation passed live checks. The
next step is the authorized Windows `3.0.1` build from
`codex/feature-updates-diagnostics`, followed by artifact verification and
manual Windows acceptance.

## Blockers and risks

- The deployed license service and signed online desktop contract are active;
  availability of VDS, DNS, TLS, and PostgreSQL is therefore a direct
  application-availability dependency.
- The tracked `licenses.db` is potentially sensitive and requires a separately
  approved migration out of source control without exposing its contents.
- Automated packaged checks passed, but final installation, production-license
  activation, Windows visual behavior, and SmartScreen behavior still require a
  manual check on the target Windows computer.
- VDS access to the private GitHub repository and Codex authentication must be configured outside Git; no credentials are stored here.
- Linux cannot replace Windows visual and packaged-client verification.
- The installer from run `31909510317` predates the new updater and diagnostic
  journal. It must not be presented as containing these changes.
- Secure update delivery is deployed but has no published `3.0.1` revision yet;
  update download cannot be exercised end to end until the new Windows artifact
  exists and a controlled test revision is created.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
