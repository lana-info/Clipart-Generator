# Vibix Images

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

Development is VDS-first. `develop/3.1` is the current integration line for
3.1.0; frozen 3.0.x and old release-candidate branches are historical and must
not be used as implementation bases. Windows remains the clean clone for
Windows-specific behavior and visual checks. GitHub is the only handoff point;
do not edit the same branch from both machines simultaneously.

## Sensitive data and artifacts

API keys, credentials, `.env` files, user configs, generated images, build outputs, model binaries, and release installers are local-only and must not be committed. See `VDS_WORKFLOW.md` for the transfer procedure.

## Current product state

The ordered MVP and cleanup acceptance work is complete. The product is branded
as `Vibix Images` with the subtitle `AI Image Generation & Processing`; the
approved shared mark is integrated into the runtime and Windows packaging
configuration. The self-hosted license
service is deployed, and the desktop client uses signed online validation with
a bounded seven-calendar-day offline grace for a previously verified license
during transport or server outage. First activation, explicit denial,
revocation, expiry, tampering and clock rollback remain fail-closed. The main
interface stays closed until online validation/new activation or a valid signed
local proof within that grace.
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
channel. A licensed V3 update client and a bounded user-facing diagnostic
journal are implemented on `codex/feature-updates-diagnostics`. The client asks
before downloading, downloads only after consent, verifies the signed manifest,
size, and SHA-256, and then launches the Windows installer. The corresponding
private-artifact delivery is implemented in the license-service repository on
`codex/feature-secure-updates`. Migration 006 and that server branch were
deployed to the existing public staging-like service on 2026-08-16; its health,
artifact-upload UI, and license-signed update-key delegation were verified.
The Windows-only `3.0.1` build completed successfully in GitHub Actions run
`31924194111` on 2026-08-16. The packaged entrypoint verified the internal
`3.0.1` version plus the license, diagnostic, and update wiring before Inno
Setup created the installer. The downloaded installer SHA-256 is
`e095a018a0dd44d7f9d99c7d4bba7e35a7519974894f0428d957c51c40beb973`.
The current Windows installer naming convention is
`VibixImages-Setup-<version>.exe`. GitHub Actions run `33002277766` built the
approved three-stage Polar dark installer for version `3.0.5` from merged
`develop/3.0` commit `631219f1b2494857d82f07a380e2f6cf538a4f02`. The workflow
installed the finished package and verified the application artwork and prompt
screens from the installed copy. The installer SHA-256 is
`fceb6abfb44c2feb93ce8f2e2142987dc551fa47b0ddf1d7667341b6f12e8fef`.

## Next product phase — generation quality and provider expansion

Version 3.0.7 is the frozen baseline for the next product phase; new owner
feedback does not expand that release. The authoritative 3.1.0 delta is
`PRD_3.1.ru.md`, and its ordered implementation source is `TASKS_3.1.ru.md`.
The `Next Product Phase` section in `PRD.md` and `NEXT-TASK-*` history in
`TASKS_3.0.ru.md` remain architectural background only where they do not
conflict with those 3.1 documents. The phase is a focused improvement of the
existing generation and processing workflows:

1. establish workflow composition and a structured clipart prompt contract;
2. prepare localization infrastructure for Russian and English versions
   without coupling UI language to prompt language;
3. choose the translation backend and make the clipart prompt generator produce
   coherent prompts from structured Russian fields;
4. establish a provider-neutral generation/lifecycle contract before adding a
   new provider;
5. add Fal.ai through the provider abstraction for confirmed operations;
6. validate the complete clipart workflow before designing the Pinterest prompt
   generator.

The default policy is to build prompts deterministically from structured fields
(`Object`, `Scene`, `Style`, `Color palette`, `Composition`, `Background`,
`Details`, `Restrictions`, and technical requirements). Optional AI prompt
rewriting may be added later, but it must be explicit, previewable, bounded by
cost and length, and must not silently change the user's intent.

The application should store clipart prompt data structurally and render it
separately for the UI and for providers. Free-form Russian-to-English
translation is an explicit architecture decision and must not be faked by
merely adding English section labels around Russian text. An English UI will
reuse the same data model and provider contracts. Patterns, mockups,
invitations/Canva, and module-based licensing are intentionally deferred until
the core clipart and Pinterest workflows are stable.

The phase also introduces a workflow-definition layer before new page-specific
features are added. A workflow can reuse shared pages, provide its own prompt
builder, and decide which processing operations and provider controls are
relevant. A capability with no user value must be omitted from that workflow,
not shown as a disabled checkbox. This is internal product architecture; it is
not yet commercial module licensing.

Workflow definitions may also add ordered post-processing and delivery steps.
One workflow may end with a PNG, while another may create a PDF, prepare a
Canva-compatible package, or upload an approved result to Google Drive. Local
file creation and external delivery are separate step types; external actions
require an explicit confirmation and a visible destination before execution.
