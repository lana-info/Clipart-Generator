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
