# Clipart Generator

## Purpose

Windows desktop application for generating and processing clipart images. The project supports KIE-backed generation and local or remote processing providers, including Real-ESRGAN, rembg, BEN2, PhotoRoom, metadata cleanup, and bounded provenance inspection.

## Runtime

- Python 3.11+; the current Windows environment uses Python 3.12.
- Runtime dependencies are in `requirements.txt`; development checks are in `requirements-dev.txt`.
- The application is PyQt6-based. Linux GUI checks should use Qt offscreen mode.
- Node.js is not a project runtime requirement.

## Standard commands

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m py_compile main.py
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

Windows activation is `.venv\\Scripts\\Activate.ps1`.

## Workflow boundary

Development is VDS-first on `develop/3.0`. Windows remains the clean clone for Windows-specific behavior and visual checks. GitHub is the only handoff point; do not edit the same branch from both machines simultaneously.

## Sensitive data and artifacts

API keys, credentials, `.env` files, user configs, generated images, build outputs, model binaries, and release installers are local-only and must not be committed. See `VDS_WORKFLOW.md` for the transfer procedure.

## Current product state

The ordered MVP and cleanup acceptance work is complete. The self-hosted license
service is deployed, and the desktop client uses its signed online-only license
contract. Protected operations and retries require fresh authorization. A
startup-gate hotfix is implemented so the main interface also remains closed
until a saved license is validated online or a new key is activated.
The first screen exposes safe license status, license replacement, and API
settings. New projects use a Pictures-based default and retain the last selected
work and result folders in user-data preferences.

A replacement Windows installer was built successfully on 2026-08-15 from
implementation commit `43682ac` in GitHub Actions run `31909510317`. The packaged
executable passed startup-license, first-screen license/API control, signal
connection, and Pictures-default smoke checks before Inno Setup created the
installer. Its SHA-256 is
`b228999e36029bf91f3a5cbf307422f557cfb28ed2b4c86b6b3848c7a0d1ea6d`.
The legacy GitHub updates flow remains superseded and is not an active delivery
channel.
