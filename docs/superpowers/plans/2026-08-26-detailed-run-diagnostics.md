# Detailed Run Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record and display a complete privacy-safe timeline for every image and provider operation without changing processing behavior or making additional network requests.

**Architecture:** Add a provider-neutral sanitizer/event builder, emit structured events at worker and provider boundaries, correlate them in `RunQueueSession`, and render the resulting allowlisted events in the existing diagnostic dialog. Keep legacy progress-string parsing as a fallback and retain bounded local storage/export.

**Tech Stack:** Python 3.11+, PyQt6, Pillow, standard-library JSON/ZIP/network clients, unittest/pytest.

**Spec:** `docs/superpowers/specs/2026-08-26-detailed-run-diagnostics-design.md`

## Global Constraints

- Do not store prompt text, API/licence keys, authorization headers, private paths, URLs, image bytes or raw HTTP response bodies.
- Do not add dependencies, network requests, paid probes, build steps or release actions.
- Diagnostics are best-effort and must never make a generation or processing job fail.
- Preserve existing generation, processing, retry, licensing and update behavior.
- Keep the application usable at the existing 980 x 700 minimum size.

---

### Task 1: Safe structured event builder

**Files:**
- Create: `provider_diagnostics.py`
- Create: `tests/test_provider_diagnostics.py`

**Interfaces:**
- Produces: `inspect_image_metadata(path: str | Path) -> dict[str, object]`
- Produces: `build_provider_event(event: str, **values: object) -> dict[str, object]`
- Produces: `safe_provider_message(value: object) -> str`
- Produces: `count_provider_results(value: object) -> int`

- [ ] **Step 1: Write failing metadata and privacy tests**

  Add tests using temporary RGB/RGBA images and hostile values containing a
  secret, local path, prompt and signed URL. Assert that allowed metadata is
  preserved and prohibited content is absent from serialized events.

- [ ] **Step 2: Run the focused test and verify RED**

  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest -v tests.test_provider_diagnostics`

  Expected: import failure because `provider_diagnostics` does not exist.

- [ ] **Step 3: Implement the allowlisted builder**

  Implement immutable allowlists for event names and scalar fields. Read only
  image metadata with Pillow, reduce filenames to basenames, bound all strings,
  reuse `security_redaction.redact_text`, and reject mappings/lists except for
  explicitly normalized parameter summaries.

- [ ] **Step 4: Verify GREEN and security properties**

  Re-run the focused test. Search the module for accidental serialization of
  `headers`, `prompt`, `url`, `raw_response`, `body` or binary content.

- [ ] **Step 5: Commit the component**

  Commit message: `feat: add safe provider diagnostic events`

### Task 2: Journal schema and run correlation

**Files:**
- Modify: `diagnostics.py`
- Modify: `v3_run_queue.py`
- Modify: `tests/test_v3_diagnostics.py`
- Modify: `tests/test_v3_run_queue.py`

**Interfaces:**
- Produces: `DiagnosticJournal.record_structured(event: Mapping[str, object]) -> dict[str, object]`
- Produces: `RunQueueSession.handle_diagnostic(event: Mapping[str, object]) -> None`

- [ ] **Step 1: Write failing schema and ordering tests**

  Assert schema version 2, expanded scalar metadata, operation/item
  correlation, ordered technical-log lines, 8 MiB session and 24 MiB total
  defaults, and secret-safe ZIP export. Include malformed input and disk-write
  failure cases that do not raise into the run.

- [ ] **Step 2: Run the focused tests and verify RED**

  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest -v tests.test_v3_diagnostics tests.test_v3_run_queue`

  Expected: failures for missing structured-recording interfaces and old
  storage limits.

- [ ] **Step 3: Extend journal and session minimally**

  Add the new allowlisted fields, schema migration-compatible reads for v1/v2,
  `record_structured`, and `handle_diagnostic`. Attach authoritative
  `operation_id`, item number, totals and retry attempt in the session instead
  of trusting worker-supplied identifiers. Keep legacy progress parsing.

- [ ] **Step 4: Verify GREEN and existing exports**

  Re-run both modules and confirm existing diagnostic/run-report tests still
  pass without changing their public behavior.

- [ ] **Step 5: Commit the integration**

  Commit message: `feat: correlate detailed run diagnostics`

### Task 3: Worker, KIE and PhotoRoom instrumentation

**Files:**
- Modify: `main.py`
- Modify: `v3_run_queue.py`
- Modify: `tests/test_kie_routing.py`
- Modify: `tests/test_photoroom_provider.py`
- Modify: `tests/test_v3_run_queue.py`

**Interfaces:**
- Produces: `WorkerThread.diagnostic = pyqtSignal(object)`
- Produces: `WorkerThread._emit_diagnostic(event: str, **values: object) -> None`
- Consumes: `RunQueueSession.handle_diagnostic(event)`

- [ ] **Step 1: Write failing signal and provider-boundary tests**

  Cover input inspection, upload start/finish, task submission, every status
  poll, provider success/failure, result download, local-stage completion and
  item completion. Assert exact task/error identifiers remain while prompts,
  keys, headers, paths, URLs and response bodies do not reach emitted events.

- [ ] **Step 2: Run focused provider tests and verify RED**

  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest -v tests.test_kie_routing tests.test_photoroom_provider tests.test_v3_run_queue`

  Expected: failures because the worker has no structured diagnostic signal.

- [ ] **Step 3: Emit events without changing request flow**

  Add the signal and best-effort emitter. Instrument existing network calls
  immediately before and after upload/create/poll/download operations and
  existing local stage boundaries. Parse KIE `resultJson` only for result
  count. Never emit request dictionaries or provider URLs.

- [ ] **Step 4: Connect the signal to the active run session**

  Update `RunQueueCoordinator.connect_worker` with the same active-worker
  generation guard used for progress/error signals so late events from an old
  worker cannot contaminate a retry.

- [ ] **Step 5: Verify GREEN and no extra requests**

  Re-run the focused tests. Assert mocked network-call counts are unchanged by
  diagnostics.

- [ ] **Step 6: Commit provider instrumentation**

  Commit message: `feat: trace image provider operations`

### Task 4: RunPod instrumentation

**Files:**
- Modify: `cloud_gpu_backend.py`
- Modify: `tests/test_cloud_gpu_backend.py`

**Interfaces:**
- Produces: optional `diagnostic_callback: Callable[[dict[str, object]], None] | None` on `RunPodClient`

- [ ] **Step 1: Write failing submit/status/error callback tests**

  Assert callbacks receive HTTP status, job identifier, provider state and safe
  errors while API key, endpoint URL and worker payload are absent. Assert the
  callback cannot break the RunPod request if it raises.

- [ ] **Step 2: Run focused tests and verify RED**

  Run: `.venv/bin/python -m pytest -q tests/test_cloud_gpu_backend.py`

- [ ] **Step 3: Add best-effort callback instrumentation**

  Keep the public `submit` and `status` return values unchanged. Capture HTTP
  status before parsing, emit only allowlisted summaries and make callback
  failures non-fatal.

- [ ] **Step 4: Verify GREEN and unchanged request bodies**

  Re-run the focused module and confirm existing payload assertions pass.

- [ ] **Step 5: Commit RunPod instrumentation**

  Commit message: `feat: trace runpod operations safely`

### Task 5: Diagnostic filtering and detail UI

**Files:**
- Modify: `v3_diagnostics.py`
- Modify: `tests/test_v3_diagnostics.py`

**Interfaces:**
- Produces: severity/source/item filter controls and Russian detail labels in `DiagnosticJournalDialog`

- [ ] **Step 1: Write failing UI filtering tests**

  Build a journal with local, KIE, PhotoRoom and error events. Assert each
  filter changes the visible event set, item selection is based on safe names,
  detail text includes stage/model/status/duration, and no prohibited values
  appear. Render at 1400 x 900 and 980 x 700 offscreen.

- [ ] **Step 2: Run focused UI tests and verify RED**

  Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest -v tests.test_v3_diagnostics`

- [ ] **Step 3: Implement compact filter row and translated details**

  Add three `QComboBox` controls, rebuild the list from the original event
  collection on changes, retain selected-event behavior and keep vertical
  splitter scrolling. Translate stable field names with a fixed label map.

- [ ] **Step 4: Verify GREEN and screenshots**

  Re-run the focused test and save offscreen screenshots in the existing test
  artifact location without committing generated images.

- [ ] **Step 5: Commit the UI**

  Commit message: `feat: add diagnostic journal filters`

### Task 6: Contract documentation and complete verification

**Files:**
- Create: `docs/API_CONTRACTS.md`
- Modify: `README_AUTHOR_SHORT.md`
- Modify: `CHANGELOG.md`
- Modify: `TASKS.md`
- Modify: `STATE.md`

**Interfaces:**
- Documents each provider endpoint/model, official documentation link, request fields, limits, response fields, implementation location, diagnostic events and last verification date.

- [ ] **Step 1: Write the API contract register**

  Cover KIE common endpoints and every visible KIE model, PhotoRoom, RunPod and
  the internal licence/update service. Mark dormant GPT-4o compatibility code
  as inactive and list each confirmed contract discrepancy separately rather
  than claiming it is fixed by diagnostics.

- [ ] **Step 2: Document journal usage and privacy boundary**

  Explain how to filter by image/provider/error, identify the last successful
  stage and export a support package. State explicitly that prompts, secrets,
  URLs and images are excluded.

- [ ] **Step 3: Run focused and full verification**

  Run:

  ```bash
  .venv/bin/python -m py_compile main.py diagnostics.py provider_diagnostics.py v3_diagnostics.py v3_run_queue.py cloud_gpu_backend.py
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest -v tests.test_provider_diagnostics tests.test_v3_diagnostics tests.test_v3_run_queue tests.test_kie_routing tests.test_photoroom_provider
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
  ```

  Expected: all tests pass; only the documented Linux skip/deselection remains.

- [ ] **Step 4: Run security review**

  Search changed files and exported fixtures for test secrets, prompt text,
  `Authorization`, URLs, private paths and raw response fragments. Confirm no
  new dependency, external write, paid call or build occurred.

- [ ] **Step 5: Update project state and commit**

  Record exact test counts and remaining provider-contract discrepancies.
  Commit message: `docs: record api and diagnostic contracts`

- [ ] **Step 6: Push the verified feature branch**

  Push `feature/detailed-diagnostics` without starting a build or release.
