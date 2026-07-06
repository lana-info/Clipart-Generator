# Release Checklist

Use this checklist before every release. The goal is to avoid publishing an installer whose filename, internal app version, update manifest, SHA, or public assets disagree.

## 1. Choose the Release Source

- [ ] Decide whether this release comes from `main` or from a hotfix branch.
- [ ] Do not switch to `main` automatically for a hotfix. Release from the branch that contains the intended fix.
- [ ] Confirm remotes:
  - [ ] `origin` is `lana-info/Clipart-Generator` private source/build repo.
  - [ ] `updates` or `_updates_repo_tmp` points to `lana-info/Clipart-Generator-Updates` public updates repo.
- [ ] Run `git status --short --branch` and stop if unrelated local changes are present.

## 2. Update Every Version Source

For version `X.Y.Z`, all of these must match:

- [ ] `main.py`: `APP_VERSION = "X.Y.Z"`.
- [ ] `release/VERSION.txt`: exactly `X.Y.Z`.
- [ ] GitHub Actions input: `app_version=X.Y.Z`.
- [ ] `version.json`: `latest_version` must be `X.Y.Z` after final artifacts are built.
- [ ] Installer output filename must be `ClipartGenerator-Setup-X.Y.Z.exe`.
- [ ] macOS output filename must be exactly `ClipartGenerator-macOS-X.Y.Z.zip`.

Never publish if `APP_VERSION` is still the previous version. That causes the installed app to show the same update again.

## 3. Pre-Build Checks

- [ ] Run `python -m py_compile main.py`.
- [ ] Run `git diff --check`.
- [ ] Check release workflow shape:
  - [ ] Windows job produces `ClipartGenerator-Setup-X.Y.Z.exe`.
  - [ ] macOS job produces one file only: `ClipartGenerator-macOS-X.Y.Z.zip`.
  - [ ] No `apple-silicon` or `intel` suffixes unless the product decision changes.
- [ ] Commit and push the source branch before running the workflow.

## 4. Build in Private Repo

- [ ] Run workflow manually when releasing a branch:
  `gh workflow run release-multi-platform.yml --repo lana-info/Clipart-Generator --ref <branch> --field app_version=X.Y.Z`
- [ ] Watch it:
  `gh run watch <run_id> --repo lana-info/Clipart-Generator --exit-status`
- [ ] Confirm the private release `vX.Y.Z` has exactly:
  - [ ] `ClipartGenerator-Setup-X.Y.Z.exe`
  - [ ] `ClipartGenerator-macOS-X.Y.Z.zip`
  - [ ] `VERSION.txt`
- [ ] Delete and recreate the release if wrong assets were uploaded.

## 5. Refresh Local Artifacts and Manifest

- [ ] Download private release assets into `release/` with `--clobber`.
- [ ] Run:
  `powershell -ExecutionPolicy Bypass -File .\update_version.ps1 -AppVersion X.Y.Z`
- [ ] Confirm `version.json` points to the public updates repo, not private source repo:
  `https://github.com/lana-info/Clipart-Generator-Updates/releases/download/vX.Y.Z/ClipartGenerator-Setup-X.Y.Z.exe`
- [ ] Confirm `version.json.sha256` equals:
  `Get-FileHash release\ClipartGenerator-Setup-X.Y.Z.exe -Algorithm SHA256`
- [ ] Commit changed `version.json` in the private repo.
- [ ] If GitHub download added a BOM to `release/VERSION.txt`, restore it before finishing.

## 6. Publish Public Updates Repo

- [ ] Copy these three files into `_updates_repo_tmp`:
  - [ ] `version.json`
  - [ ] `ClipartGenerator-Setup-X.Y.Z.exe`
  - [ ] `ClipartGenerator-macOS-X.Y.Z.zip`
- [ ] In `_updates_repo_tmp`, run `git status --short --branch`.
- [ ] Make sure no unrelated old files are deleted.
- [ ] Commit and push to public `main`.
- [ ] Create or replace public release `vX.Y.Z` in `Clipart-Generator-Updates` with exactly:
  - [ ] `ClipartGenerator-Setup-X.Y.Z.exe`
  - [ ] `ClipartGenerator-macOS-X.Y.Z.zip`
  - [ ] `version.json`

## 7. Final Verification

- [ ] Compare private and public asset SHA values:
  - [ ] Windows SHA matches.
  - [ ] macOS SHA matches.
- [ ] Confirm public `version.json` contains the final Windows SHA.
- [ ] Confirm local `git status --short --branch` is clean in:
  - [ ] private repo
  - [ ] `_updates_repo_tmp`
- [ ] Install/update from the previous app version.
- [ ] Relaunch the app.
- [ ] Confirm the window title or app diagnostics show `X.Y.Z`.
- [ ] Confirm the app does not offer the same update again.

## 8. If Something Goes Wrong

- [ ] If a wrong asset was uploaded, delete the affected GitHub release and recreate it.
- [ ] If `APP_VERSION` was wrong, rebuild and republish the same version with refreshed assets and a new SHA.
- [ ] If public `version.json` SHA does not match the public `.exe`, update `version.json`, commit, push, and replace the public release asset.
- [ ] If a workflow run starts from the wrong branch, cancel it immediately and delete any partial release it created.
