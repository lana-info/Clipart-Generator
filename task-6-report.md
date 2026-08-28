# Task 6 report — selective Pinterest regeneration and folder export

## Implemented

- `PinterestPinOrchestrator` caches its immutable `ProductLayer` by product
  path and accepts the cached layer in a selective request. A regeneration
  builds only the requested slot, retains the original source path and digest,
  and does not recreate the six-slot series.
- The Results preview delegates `regenerate_variant()` to the Pinterest
  controller. The controller creates a one-item request through the existing
  queue and worker adapter, preserves unrelated preview slots, and reuses the
  cached protected product layer when the selected product has not changed.
- `export_accepted()` writes only accepted successful variants to the selected
  Pinterest output folder. It preserves JPG/PNG format, creates safe names such
  as `product_template_01.jpg` and `product_ai-scene_01.png`, avoids existing
  names with a numeric suffix, and leaves files already written intact if a
  later export fails.
- The preview displays an export summary with the saved count and destination
  folder. No Fal client, live provider request, or Clipart/queue retry contract
  was added or changed.

## TDD evidence

- RED: focused tests failed as expected before implementation: a second
  regeneration reloaded `ProductLayer`, preview did not start a one-slot
  worker, and export returned source paths rather than saving files.
- GREEN: regression coverage verifies cached ProductLayer/digest reuse,
  selected-slot queue requests, preservation of an unrelated accepted slot,
  JPG/PNG export names, collision avoidance, and preservation of successful
  files after a partial failure.

## Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_pinterest_pin_templates.py tests/test_pinterest_pin_composer.py tests/test_v3_pinterest_flow.py tests/test_v3_run_queue.py tests/test_v3_clipart_flow.py -q` — 172 passed, 8 subtests passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_v3_pinterest_flow.py -q` — 44 passed.
- `python -m py_compile v3_pinterest_flow.py` — passed.
- `git diff --check` — passed.

## Remaining boundary

AI-scene regeneration remains provider-neutral. Without a separately approved
background provider, it produces the existing safe retryable scene failure;
template regeneration and local export continue to work without a live call.

## Review findings follow-up

- Selective regeneration now keeps the previous successful slot intact until
  preflight, authorization, and worker creation have all succeeded. A rejected
  preflight, authorization, or worker construction therefore preserves the
  prior output path, protected-layer digest, acceptance, and export status.
- Export target selection atomically reserves a new file with exclusive
  creation before image writing. Parallel exports receive distinct suffixes;
  a reservation is removed if the export itself fails.
- Regeneration controller messages now use the existing Pinterest RU/EN
  registry, including the active-run, already-running, and started statuses.

### TDD and verification

- RED: `tests/test_v3_pinterest_flow.py` exposed the premature state reset in
  all three pre-start failure paths, duplicate names from parallel export
  reservations, and a Russian regeneration status in the English flow.
- GREEN: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
  tests/test_v3_pinterest_flow.py -q` — 48 passed.
- Related Task 5 and Clipart boundary: `QT_QPA_PLATFORM=offscreen .venv/bin/python
  -m pytest tests/test_pinterest_pin_templates.py tests/test_pinterest_pin_composer.py
  tests/test_v3_clipart_flow.py tests/test_v3_pinterest_flow.py
  tests/test_v3_run_queue.py -q` — 176 passed, 8 subtests passed.
- `.venv/bin/python -m py_compile v3_pinterest_flow.py v3_run_queue.py` — passed.
