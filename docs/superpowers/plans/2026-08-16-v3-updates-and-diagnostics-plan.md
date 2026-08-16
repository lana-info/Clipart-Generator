# Implementation plan: V3 updates and diagnostics

## Overview

Implement the approved Windows-only update channel across the separate license
service and desktop repositories, then add a bounded cross-launch diagnostic
journal and expose it throughout V3. No deployment, release publication,
installer build, or GitHub Actions run belongs to this implementation pass.

## Architecture decisions

- The license service remains the update authority and issues signed manifests
  plus short-lived artifact download tokens.
- The desktop uses a dedicated update client and update public key; legacy
  `version.json` code is not reused by V3.
- Diagnostics use bounded per-launch JSON Lines files with sanitized structured
  events and a derived TXT/JSON ZIP export.
- Diagnostics are installed before updater integration so update behavior is
  observable from its first implementation.

## Task 1: Server artifact and token persistence

**Description:** Add the database and store boundary for server-owned release
artifacts and short-lived bounded-use download tokens.

**Acceptance criteria:**

- Release artifacts have safe names, contained storage paths, computed size and
  SHA-256 metadata.
- Download tokens are stored as hashes and bound to license, activation,
  artifact, expiry, and bounded use.
- Withdrawn/deleted releases and ineligible licenses cannot resolve a token.

**Verification:** Focused store and migration tests pass.

**Dependencies:** None.

**Files likely touched:** server migration, `postgres_store.py`, focused tests.

## Task 2: Server upload, signed manifest, and download HTTP slice

**Description:** Complete the administrator artifact attachment, manifest token
issuance, and public token download flow.

**Acceptance criteria:**

- The administrator can attach a bounded Windows installer to a draft release;
  metadata is computed server-side.
- The signed manifest contains only published eligible stable releases and a
  short-lived HTTPS service download URL.
- A valid token streams the expected bounded artifact with safe headers; invalid
  or expired tokens fail closed.

**Verification:** API, HTTP, admin, tampering, and download tests pass.

**Dependencies:** Task 1.

**Files likely touched:** `api.py`, `http_server.py`, `admin.py`, `web/admin.html`,
focused tests.

## Checkpoint A: Server channel

- Server test suite passes.
- No artifact, token, private path, or secret is committed or logged.
- Existing activation, validation, and administrator behavior remains green.

## Task 3: Desktop diagnostic storage and sanitization

**Description:** Implement the bounded structured journal, retention, recovery,
safe event model, and support-package export.

**Acceptance criteria:**

- Three launch sessions and the 10 MiB/4 MiB/16 KiB limits are enforced.
- Corrupt tails recover and concurrent writes remain valid.
- Secrets, prompts, images, full paths, and raw provider responses cannot enter
  stored or exported events.

**Verification:** Focused retention, corruption, redaction, copy-text, and ZIP
tests pass.

**Dependencies:** None.

**Files likely touched:** new diagnostic module and focused tests.

## Task 4: Desktop diagnostic UI and event wiring

**Description:** Add the journal window and connect high-value V3 application,
license, settings, project, and run events.

**Acceptance criteria:**

- `Журнал диагностики` is available before mode selection and in the wizard.
- The journal shows safe readable entries and supports only copy-record and ZIP
  export as primary support actions.
- Startup, license, settings, project, operation/item results, retry,
  cancellation, export, exit, and unhandled failures are represented without
  progress spam.

**Verification:** UI connection, minimum-size smoke, event coverage, and secret
absence tests pass.

**Dependencies:** Task 3.

**Files likely touched:** diagnostic UI, `v3_mode_selection.py`, `v3_wizard.py`,
`v3_run_queue.py`, focused tests.

## Checkpoint B: Diagnostic journal

- Focused and existing V3 tests pass.
- A synthetic 100-item operation stays within bounds and remains readable.
- Exported ZIP is complete and sanitized.

## Task 5: Desktop signed update client

**Description:** Extend the activated-device client boundary with a dedicated
signed-manifest verifier and atomic artifact downloader.

**Acceptance criteria:**

- Manifest requests use fresh device proof and the separate update key.
- Claims, semantic versions, platform/channel, HTTPS URL, filename, size,
  SHA-256, and response/download bounds are enforced.
- Atomic download, cancellation, cleanup, and verified-file handoff work
  without starting an installer in tests.

**Verification:** Network-free valid/tampered/error/cancel/checksum tests pass.

**Dependencies:** Task 2 and Task 3.

**Files likely touched:** new update module, `license_client.py`, focused tests.

## Task 6: V3 update prompt and startup integration

**Description:** Schedule one asynchronous licensed startup check and implement
the explicit prompt, progress, cancellation, verified installer launch, and
diagnostic events.

**Acceptance criteria:**

- V3 checks once per eligible launch without freezing the UI.
- `Не сейчас` performs no download; `Обновить` alone starts it.
- A verified installer launches and the app exits; every failure keeps the
  current app usable and produces a safe event.

**Verification:** UI/controller tests and packaged-entrypoint smoke pass.

**Dependencies:** Task 4 and Task 5.

**Files likely touched:** updater controller/UI, `main.py`,
`v3_mode_selection.py`, focused tests.

## Checkpoint C: Integrated implementation

- Both repository test suites pass.
- Desktop compile and offscreen packaged smoke pass.
- Static inspection confirms final V3, not legacy `MainWindow`, owns the update
  schedule.
- `TASKS.md`, `STATE.md`, and change documentation match actual status.
- No build, deployment, publication, push-triggered action, or paid operation
  has run.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Server and desktop branches are not yet integrated into their base branches | High | Keep repository commits separate and report merge/deployment order explicitly |
| A leaked permanent artifact URL bypasses entitlement | High | Return only short-lived service tokens and keep storage paths private |
| Diagnostic data leaks credentials or personal paths | High | Allowlist fields, central sanitizer, adversarial regression fixtures |
| A large batch grows logs indefinitely | Medium | No progress ticks, per-item terminal events, three-session and byte caps |
| Update launch behavior differs on Windows | Medium | Mock automated tests plus required manual Windows acceptance before publication |

## Open questions

None. Product behavior and scope are fixed by the approved design.
