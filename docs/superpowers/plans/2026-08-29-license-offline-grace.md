# License Offline Grace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow a previously verified Vibix Images license to keep working for seven calendar days when the license server is temporarily unreachable, without granting offline access to new, rejected, expired, damaged, or rolled-back state.

**Architecture:** Persist the last server-signed authorization envelope together with its device/nonce binding and a device-signed local time record in the existing atomic license state. Online authorization remains the primary path. Only `LicenseUnavailableError` may fall back to the cached record; explicit server denials and all validation failures remain fail-closed.

**Tech Stack:** Python 3.12, Ed25519 via `cryptography`, RFC 8785 canonical JSON, PyQt6, `unittest`/`pytest`.

**Spec:** `PRD_3.1.ru.md` (`CG31-FR-060`–`062`) and `TASKS_3.1.ru.md` Task 14.

## Global Constraints

- Grace period is exactly seven calendar days after the most recent successful online authorization.
- First activation always requires the server.
- HTTP 401/403 or another explicit denial never uses grace.
- No license key is persisted, displayed, logged, or included in diagnostics.
- Clock rollback, cache tampering, an invalid server signature, device mismatch, product mismatch, expiry, and grace expiry fail closed.
- The visible state must match `docs/ui/3.1/task-14-license-grace/approved-main.png` and `approved-expired.png`.

---

### Task 1: Persist a verifiable offline authorization record

**Files:**
- Modify: `license_client.py`
- Test: `tests/test_license_client_security.py`

**Interfaces:**
- Consumes: the existing signed server envelope returned by activation/validation.
- Produces: `LicenseClient.authorize_offline_grace(now: datetime | None = None) -> LicenseAuthorization` and offline metadata on `LicenseAuthorization`.

- [x] **Step 1: Write failing security tests**

Add literal-behavior tests proving that activation creates no license-key copy, timeout within seven days succeeds, HTTP 401/403 does not fall back, and expired/tampered/rolled-back cache fails.

- [x] **Step 2: Run the focused tests and confirm RED**

Run: `python -m unittest tests.test_license_client_security -v`

Expected: new offline-grace tests fail because no cached authorization API exists.

- [x] **Step 3: Implement the minimal signed cache**

Store the original signed envelope, expected nonce/device, last successful online time, and highest observed local time. Canonicalize the record with RFC 8785 and sign it with the existing device Ed25519 key. Verify both server and device signatures before returning an offline authorization.

- [x] **Step 4: Run focused security tests and confirm GREEN**

Run: `python -m unittest tests.test_license_client_security -v`

Expected: all license-client security tests pass.

### Task 2: Route temporary outages through grace and expose safe UI status

**Files:**
- Modify: `v3_license.py`
- Test: `tests/test_v3_license_gate.py`
- Test: `tests/test_v3_license_flow_gate.py`

**Interfaces:**
- Consumes: `LicenseClient.authorize_offline_grace()` only after `validate()` raises `LicenseUnavailableError`.
- Produces: the approved `Временный автономный доступ` status and last-check/grace-end text.

- [x] **Step 1: Write failing gate/UI tests**

Cover temporary outage success, explicit denial failure, unexpected exception sanitization, approved status copy, and grace-expired retry dialog copy.

- [x] **Step 2: Run focused tests and confirm RED**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_v3_license_gate tests.test_v3_license_flow_gate -v`

- [x] **Step 3: Implement outage-only fallback**

Catch only `LicenseUnavailableError`, ask the client for the cached authorization, and keep all other failures on the existing blocking path. Update the saved-license dialog and activation description without adding new controls.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run: `QT_QPA_PLATFORM=offscreen python -m unittest tests.test_v3_license_gate tests.test_v3_license_flow_gate -v`

### Task 3: Acceptance, documentation, and checkpoint

**Files:**
- Modify: `TASKS_3.1.ru.md`
- Modify: `STATE.md`
- Modify: `CHANGELOG.md`
- Create: `docs/ui/3.1/task-14-license-grace/approved-main.png`
- Create: `docs/ui/3.1/task-14-license-grace/approved-expired.png`
- Create: `docs/ui/3.1/task-14-license-grace/README.md`

**Interfaces:**
- Consumes: the implemented gate and approved screenshots.
- Produces: auditable Task 14 evidence and a verified feature checkpoint.

- [x] **Step 1: Render the implemented UI**

Capture the real main-screen grace state and expired dialog at 1120×780/compact dialog size, then compare them with the approved mockups.

- [x] **Step 2: Run complete verification**

Run: `python -m py_compile license_client.py v3_license.py main.py`

Run: `QT_QPA_PLATFORM=offscreen python -m pytest -q`

Run: `git diff --check`

- [x] **Step 3: Perform the security review**

Confirm that only transport/server unavailability enters grace, no secret is persisted or rendered, both signatures are verified, and time rollback/cache corruption fail closed.

- [x] **Step 4: Commit and push the verified checkpoint**

Commit message: `feat: allow bounded offline license grace`
