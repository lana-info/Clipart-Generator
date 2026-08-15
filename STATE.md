# Project state

Updated: 2026-08-15

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
- Current documentation branch: `codex/license-server`
- Current remote commit: `453ef4e35683fecc85a549ea1f8fffbb73482fbe`
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

Review the completed startup-license hotfix, first-screen license/API controls,
remembered output folders, and test evidence; then obtain explicit approval to
commit and push. After that, build a new Windows installer and verify the
packaged client displays the license dialog before the main UI. Do not distribute
the 2026-08-14 installer because it predates these fixes.

## Blockers and risks

- The deployed license service and signed online desktop contract are active;
  availability of VDS, DNS, TLS, and PostgreSQL is therefore a direct
  application-availability dependency.
- The tracked `licenses.db` is potentially sensitive and requires a separately
  approved migration out of source control without exposing its contents.
- The existing Windows installer does not contain the startup-license hotfix and
  first-screen/folder improvements and must be replaced before distribution.
- VDS access to the private GitHub repository and Codex authentication must be configured outside Git; no credentials are stored here.
- Linux cannot replace Windows visual and packaged-client verification.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
