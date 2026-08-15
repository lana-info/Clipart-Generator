# Start-screen License and API Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show safe license state and license/API actions before the user selects a work mode.

**Architecture:** Keep the latest signed authorization in memory in `OnlineLicenseGate`. Render a compact control card in `ModeSelectionScreen`, connect it through `V3ApplicationView` to the existing dialogs, and refresh it after startup authorization and license changes.

**Tech Stack:** Python 3, PyQt6, unittest, existing V3 design tokens and license client.

## Global Constraints

- Windows is the only release target.
- Internet is required; do not add offline authorization.
- Never display or persist the reusable license key.
- Do not label the five-minute authorization-envelope expiry as the commercial license term.
- Do not add dependencies.

---

### Task 1: License status model

**Files:**
- Modify: `v3_license.py`
- Test: `tests/test_v3_license_gate.py`

**Interfaces:**
- Consumes: `LicenseAuthorization` returned by `LicenseClientProtocol.activate()` and `.validate()`.
- Produces: `OnlineLicenseGate.current_authorization: LicenseAuthorization | None` and `verification_text: str`.

- [x] **Step 1: Write a failing test** proving successful activate/validate retains the latest authorization while a failed check clears it and cannot report online verification.
- [x] **Step 2: Run** `.venv/bin/python -m unittest tests.test_v3_license_gate -v` and confirm failure on the missing state API.
- [x] **Step 3: Implement** in-memory authorization tracking and a bounded Russian verification label based on signed `issued_at`.
- [x] **Step 4: Run the test** and confirm it passes.

### Task 2: First-screen control card

**Files:**
- Modify: `v3_mode_selection.py`
- Test: `tests/test_v3_mode_selection.py`

**Interfaces:**
- Consumes: safe strings from `OnlineLicenseGate.status_text` and `.verification_text`.
- Produces: `ModeSelectionScreen.license_requested`, `.api_settings_requested`, and `set_license_status(status: str, verification: str) -> None`.

- [x] **Step 1: Write failing UI tests** asserting the card and both buttons are visible at 980×700, labels are accessible, and clicks emit their signals.
- [x] **Step 2: Run** `.venv/bin/python -m unittest tests.test_v3_mode_selection -v` and confirm failure on missing controls.
- [x] **Step 3: Add** the compact top card, connect its signals in `V3ApplicationView`, and add one refresh method used after dialogs.
- [x] **Step 4: Run the UI tests** and confirm layout, keyboard, and action tests pass.

### Task 3: Startup synchronization and regression verification

**Files:**
- Modify: `main.py`
- Modify: `v3_license.py`
- Test: `tests/test_release_entrypoint.py`
- Modify: `CHANGELOG.md`, `STATE.md`, `TASKS.md`

**Interfaces:**
- Consumes: `V3ApplicationView.refresh_license_status()`.
- Produces: a packaged startup screen synchronized with the fresh online authorization result.

- [x] **Step 1: Write a failing startup test** asserting successful authorization refreshes the first-screen license card.
- [x] **Step 2: Run** `.venv/bin/python -m unittest tests.test_release_entrypoint -v` and confirm the refresh assertion fails.
- [x] **Step 3: Call** `refresh_license_status()` after successful startup validation and replace misleading authorization-expiry copy with online-verification copy.
- [x] **Step 4: Update project status documents** to record that the first-screen controls are complete while the replacement Windows installer remains pending.
- [x] **Step 5: Verify** targeted tests, `QT_QPA_PLATFORM=offscreen .venv/bin/python main.py --release-entrypoint-smoke`, `git diff --check`, and the full unittest suite.

No commit or push is part of this plan until the user approves the completed diff and verification results.
