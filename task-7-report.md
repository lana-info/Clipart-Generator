# Task 7 report — Pinterest workflow, localization and capabilities

Date: 2026-08-28

Implemented:

- Explicit Pinterest workflow pages and no Pinterest processing operations.
- Dedicated Pinterest review page; legacy Clipart prompt-review and processing
  pages are excluded from the route.
- Shared RU/EN registry for Pinterest labels, validation errors, statuses and
  accessibility names.
- Local capability fallback from unavailable/unsafe AI scenes to protected
  template composition; no network provider was added.
- Localized handling and regression tests for missing product, output-folder
  failure, scene failure, partial export and accessibility.

Verification:

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest tests.test_workflow_definitions tests.test_v3_pinterest_flow -v` — 68 passed.
- `.venv/bin/python -m py_compile workflow_definitions.py v3_localization.py v3_pinterest_flow.py` — passed.

No live or paid API call, release build, merge or deploy was performed.

## Findings follow-up — 2026-08-28

Fixed:

- A clean Pinterest project now has the canonical route `product → copy/layout
  → generation → preview → export` and does not require or serialize legacy
  `pinterest.prompts`, prompt-generator, or processing-plan state.
- Older Pinterest drafts move that source data into the isolated
  `pinterest_legacy` migration archive; it is preserved on save but is not
  routed into a Pinterest request or queue diagnostics.
- Product/folder and copy/layout are separate UI slices. The controller now
  consumes its capability source, selects the safe local template fallback when
  no AI-scene provider is installed, and shows its localized fallback status.
- Pinterest UI/status/error/accessibility messages, including worker and
  inherited generation-page status, use the RU/EN message registry.

Verification:

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m unittest
  tests.test_workflow_definitions tests.test_v3_project_state
  tests.test_v3_pinterest_flow -q` — passed (only expected Qt offscreen
  `propagateSizeHints` warnings).
- `.venv/bin/python -m py_compile workflow_definitions.py v3_project_state.py
  v3_localization.py v3_pinterest_flow.py` — passed.
- `git diff --check` — passed.

No live or paid API call, release build, merge, or deploy was performed.
