# Project state

Updated: 2026-08-14

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
- Current desktop integration branch: `codex/license-server-client-integration`
- Handoff commit at preparation start: `b4648042e3d0ed41416c6055216bbe73de128825`
- Recommended VDS path: `~/projects/clipart-generator`
- Bootstrap: `bash scripts/bootstrap_vds.sh`
- Baseline: `python -m py_compile main.py` and `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v`

## Next task

Build and manually verify a bootstrap Windows installer containing the VDS
license/update client, then publish only that tested installer as the first
portal revision.

## Blockers and risks

- The first bootstrap installer has not yet been built and tested on Windows.
- A real end-to-end test still needs an owner-created temporary license and a
  real installer URL/checksum.
- The tracked `licenses.db` is potentially sensitive and requires a separately
  approved migration out of source control without exposing its contents.
- Mandatory online validation makes VDS, DNS, TLS, and database availability a
  direct application-availability dependency.
- Update/license commercial duration policies remain owner decisions.
- VDS access to the private GitHub repository and Codex authentication must be configured outside Git; no credentials are stored here.
- Linux cannot replace Windows visual and packaged-client verification.

## Prohibited without explicit approval

- Secrets, credentials, `.env` files, and user data in Git.
- Force push, destructive cleanup, automatic rebase, or deletion of uncertain branches/worktrees.
- Production workers, paid API operations, deployment, release/build publication, or account actions.
