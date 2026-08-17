# Repository artifact inventory

This is a classification policy, not an automatic deletion list.

| Scope | Decision | Owner / lifecycle |
|---|---|---|
| `main.py`, V3 modules, `tests/`, `third_party/` | KEEP | Runtime and regression source |
| `main_restored.py` | REMOVED FROM WORKTREE | Historical copy remains available in Git history; do not restore into the source tree |
| `benchmark_*.json`, `TASK*_BENCHMARK.md`, `*_BENCHMARK.*` | HISTORICAL | Research evidence; retain with date/context |
| `release/*.exe`, `release/*.zip`, `*.sha256` | RELEASE ARTIFACT | Keep only when referenced by release evidence; do not treat as source |
| `release/ClipartGenerator-Setup-3.0.exe` and matching `.sha256` | HISTORICAL LOCAL ARTIFACT | Legacy filename; current workflow artifact is `VibixImages-Setup-<version>.exe`; do not publish the legacy pair |
| `release/ClipartGenerator-macOS-1.0.0.zip`, `-1.0.1.zip`, `-2.0.zip` | HISTORICAL INTERNAL | Retain for rollback/evidence only; macOS is not a supported 3.0 delivery target |
| `README_processed.png`, `source_processed.png`, `sibling_processed.png` | GENERATED LOCAL OUTPUT | Do not commit or package; preserve only as local evidence if needed |
| `.superpowers/` | LOCAL AGENT STATE | Never package or commit; ownership belongs to the local workspace |
| `PROJECT_CLEANUP_REPORT.md`, `STATE.md`, `TASKS*.md` | PROJECT HISTORY / CONTROL DOCS | Keep; `tech_debt/README.md` is the current debt index |
| `run_error.log`, generated PNGs, caches, `.pytest_cache/`, `__pycache__/` | GENERATED / LOCAL | Do not commit or include in release artifacts |
| `licenses.db` | LOCAL SENSITIVE STATE | Ignored and not tracked; keep backups and server data outside Git |
| `TECHNICAL_DEBT.md` | POINTER | Canonical task status lives in `tech_debt/` |

Historical files are not deleted automatically. `main_restored.py` is the
explicit exception: it was removed from the worktree after confirming that it
is not imported or packaged; Git history remains the rollback source.
