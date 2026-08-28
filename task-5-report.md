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
