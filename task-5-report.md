# Task 5 report — protected Pinterest pin series

## Implemented

- `build_pinterest_pin_series` creates six stable slots: three deterministic
  templates followed by three `ai_scene` variants.
- The provider-neutral `BackgroundGenerator` receives only a background prompt
  and slot index. Product pixels remain in the protected `ProductLayer` and
  are composed locally after background generation.
- Each successful variant passes the product-fidelity guard and stores the
  protected-layer digest. Failed scenes keep their original slot, safe retryable
  diagnostic, and do not affect template results.
- Cancellation is checked before each scene admission, so it prevents later
  background requests while preserving all six result slots.
- Template rendering now exposes an image without product pixels and its stable
  placement box, allowing the Task 5 composition path without changing the
  existing `render_template_pin` API.

## Deliberately not changed

`RunQueueSupport` currently assumes a `ClipartRunRequest` and legacy worker
progress/output protocol. A dedicated Pinterest request cannot be connected to
that queue without replacing the existing Pinterest legacy-run bridge, which is
outside Task 5 and risks Task 4. The new orchestrator is intentionally
provider-neutral and has no Fal client or live network call.

## Verification

- TDD red: the new-series tests initially failed because `PinVariant` and the
  builder did not exist.
- Green: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  tests/test_pinterest_pin_templates.py tests/test_pinterest_pin_composer.py
  tests/test_v3_pinterest_flow.py -q` — 61 passed, 3 subtests passed.
- The test doubles generate local Pillow backgrounds only; no network or paid
  provider operation is used.

## Critical Task 5 follow-up — dedicated queue runtime

- `PinterestPinRunRequest` now owns the fixed six-slot contract and is accepted
  by the existing `RunQueueSession` through its `queue_items` registry. It is
  not a `ClipartRunRequest` and carries no provider credentials.
- `PinterestPinOrchestrator` and `PinterestPinWorkerAdapter` execute the real
  Pinterest path. The adapter calls `build_pinterest_pin_series`, writes only
  protected template outputs locally, and routes all six stable slots through
  the shared queue. Until an explicitly approved background provider is added,
  the three AI-scene slots remain safe, retryable failures with no network call.
- The controller no longer creates the legacy `WorkerThread` for Pinterest;
  Clipart keeps its existing request and worker path unchanged.

### Verification

- TDD red: `tests/test_v3_pinterest_flow.py` failed at collection because the
  dedicated Pinterest request and worker adapter did not exist.
- Green: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  tests/test_v3_clipart_flow.py tests/test_v3_pinterest_flow.py
  tests/test_v3_run_queue.py -q` — 135 passed, 5 subtests passed.
- `.venv/bin/python -m py_compile v3_pinterest_flow.py v3_run_queue.py` and
  `git diff --check` pass. No Fal request, paid provider call, or build ran.

## Critical follow-up fixes — queue retry and worker lifecycle

- `RunQueueSession.prepare_retry()` now preserves the dedicated Pinterest
  request contract: it retries only failed `queue_items` and never passes
  clipart-only `generated_prompts` or `selected_files` to
  `PinterestPinRunRequest`.
- `PinterestPinOrchestrator` limits a retry to the selected variant IDs, so a
  future background generator is not asked to recreate other AI-scene slots.
  Preview synchronization now also matches variants by stable ID rather than
  their retry-local position.
- `PinterestPinWorkerAdapter` now runs on `QThread`; cancellation uses a
  thread-safe event passed into orchestration and checked before output work.
  Unexpected exceptions mark every queued Pinterest slot failed, emit a safe
  `error`, and always emit `finished`, so the shared queue reaches a terminal
  state.
- Regression tests cover retrying exactly `ai-scene-02`, unexpected
  orchestration failure (`error` plus `finished`), and off-GUI-thread
  orchestration with observable cancellation.

### Verification

- TDD red: the three new regression tests failed before implementation with
  the Pinterest `TypeError` and missing `QThread` worker API.
- Green: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  tests/test_v3_clipart_flow.py tests/test_v3_pinterest_flow.py
  tests/test_v3_run_queue.py -q` — 138 passed, 5 subtests passed.
- No Fal request, paid provider call, build, or external deployment ran.

### Remaining boundary

Cancellation prevents new scene admission and further local export work. A
future synchronous background-provider call cannot be force-interrupted after
it has started; its provider adapter must accept the existing cancellation
callback when one is introduced.

## Scoped review follow-up — retry merge and deferred stop

- Preview synchronization now changes only the Pinterest slot IDs present in
  the active request. Retrying one failed AI scene therefore merges that new
  variant into the existing six-slot series and retains successful templates
  and unrelated AI scenes.
- `PinterestPinWorkerAdapter` separates immediate cancellation from
  `request_stop_after_current()`. The deferred request allows the current
  orchestration/output variant to complete, then emits cancellation for later
  queued variants; immediate stop retains its existing interrupt behavior.
- Regression coverage verifies both that retrying `ai-scene-02` preserves all
  previous successes and that a deferred stop does not cancel the in-flight
  Pinterest variant.

### Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  tests/test_v3_clipart_flow.py tests/test_v3_pinterest_flow.py
  tests/test_v3_run_queue.py -q` — 140 passed, 5 subtests passed.
- `.venv/bin/python -m py_compile v3_pinterest_flow.py v3_run_queue.py` —
  passed.
- No Fal request, paid provider call, build, or external deployment ran.

## Important Task 5 follow-up — deferred queue stop during orchestration

- `PinterestPinWorkerAdapter` now emits an indexed `RUNNING` lifecycle event
  for the first active Pinterest slot before the potentially long
  `orchestrator.build()` call. The common `RunQueueSupport.stop_after_current()`
  therefore uses the worker's native deferred-stop boundary instead of calling
  immediate cancellation while orchestration is still running.
- A regression test exercises the actual shared queue path: the active variant
  completes after deferred stop, while all following Pinterest slots are
  cancelled. It keeps the orchestration blocked until the queue receives the
  stop request, preventing a timing-dependent false positive.
- Retry selection, unexpected-exception `error` plus `finished` lifecycle, and
  the separate Clipart worker path are unchanged.

### Verification

- TDD red: `tests/test_v3_pinterest_flow.py::V3PinterestFlowTests::test_queue_stop_after_current_keeps_active_pinterest_variant`
  failed with the first slot still `PENDING` during `orchestrator.build()`.
- Green: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  tests/test_v3_clipart_flow.py tests/test_v3_pinterest_flow.py
  tests/test_v3_run_queue.py -q` — 141 passed, 5 subtests passed.
- `.venv/bin/python -m py_compile v3_pinterest_flow.py v3_run_queue.py` and
  `git diff --check` — passed. No Fal request, paid provider call, build, or
  external deployment ran.
