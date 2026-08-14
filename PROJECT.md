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

The legacy GitHub updates flow is retired and is not an active delivery channel.
The shared self-hosted service is implemented in the separate private
`Clipart-License-Service` repository. The desktop integration is on branch
`codex/license-server-client-integration`; it uses the VDS license endpoint,
signed update manifests, and Google Drive share-link normalization. A new
bootstrap installer containing this integration still must be built and tested
on Windows before the first real release is published.
