# Task 1 — Pinterest Pins draft contract

## Scope completed

- Added `PinterestPinData` with the required fixed MVP canvas and series defaults.
- Added serializable `PinterestPinResultData` metadata without an image or byte field.
- Added strict persisted-draft validation, while Pinterest drafts saved before these
  fields existed still load with defaults.
- Extended the Pinterest prompt schema with localized `scene`, `layout`, and
  `text` fields; the existing `restrictions` field and language-aware renderer
  remain in use.

## Changed files

- `v3_project_state.py`
  - Added `PinterestPinData` and `PinterestPinResultData`.
  - Added bounded in-memory normalization, selected-product index normalization,
    metadata status validation, JSON serialization, and old-draft defaults.
  - Rejects persisted canvas/count values outside the fixed 1000×1500 / 3+3 MVP
    contract.
- `pinterest_prompt_schema.py`
  - Added `scene`, `layout`, and `text` data/rendering fields with English and
    Russian labels.
- `tests/test_v3_project_state.py`
  - Added tests for defaults, normalization, metadata round-trip, old-project
    compatibility, and persisted invalid dimensions/counts.
- `tests/test_pinterest_prompt_schema.py`
  - Added renderer and localized-label coverage for the new prompt fields.
- `.superpowers/sdd/2026-08-28-pinterest-pins-implementation/task-1-report.md`
  - Records this task's scope, TDD evidence, verification, and remaining risks.

## TDD evidence

1. RED tests were added before production code.
2. Requested command attempted:

   ```text
   pytest tests/test_v3_project_state.py tests/test_pinterest_prompt_schema.py -q
   /bin/bash: pytest: command not found
   ```

3. Equivalent focused run using the available standard-library runner failed for
   the intended missing contract:

   ```text
   ImportError: cannot import name 'PinterestPinData'
   TypeError: PinterestPromptFields.__init__() got an unexpected keyword argument 'scene'
   FAILED (failures=1, errors=2)
   ```

4. After the minimal implementation and a validator correction, the focused run
   passed:

   ```text
   python3 -m unittest tests.test_v3_project_state tests.test_pinterest_prompt_schema -v
   Ran 27 tests in 0.022s
   OK
   ```

5. Final static checks passed:

   ```text
   python3 -m py_compile v3_project_state.py pinterest_prompt_schema.py
   git diff --check
   ```

## Concerns

- `pytest` is not installed in this worktree and the expected project `.venv`
  executable is absent, so the required pytest invocation could not run here.
  The focused test modules are `unittest` suites and were run successfully with
  `python3 -m unittest`.
- This task defines only the persisted contract. Later Pinterest flow, rendering,
  generation, and UI tasks must consume `PinterestModeData.pin` and `results`.
- Error metadata deliberately stores only `error_code` and a bounded
  `error_message`; creating localized messages from provider failures belongs to
  the later flow/localization task.

## Review follow-up — safe Pinterest error metadata

- Added a fixed Pinterest error-code table. `background_generation_failed` and
  `pin_generation_failed` map to canonical localized safe messages; an empty
  code maps to an empty message.
- Unknown in-memory codes normalize to `pin_generation_failed`, replacing any
  provider response text. Persisted JSON rejects unknown codes and messages
  that are not the canonical message for their code.
- Regression coverage:
  - `test_pinterest_result_replaces_raw_provider_error_with_safe_fallback`
    proves a provider-like message containing `api_key=demo-provider-token` is
    not retained in serialized metadata.
  - `test_project_draft_rejects_unknown_pinterest_error_code_and_raw_message`
    proves an externally mutated persisted result cannot inject an unknown code
    or raw provider message.

Verification command and output:

```text
python3 -m unittest tests.test_v3_project_state tests.test_pinterest_prompt_schema -v
Ran 29 tests
OK

python3 -m py_compile v3_project_state.py pinterest_prompt_schema.py
git diff --check
```

## Re-review follow-up — safe write boundary

- Root cause: `save_project_draft()` serialized `state.to_dict()` directly and
  did not call `_validate_project_draft_shape()`. Direct post-construction
  mutation of a `PinterestPinResultData` instance could therefore bypass the
  safe error-metadata validation applied on load.
- Fix: the write path now validates the complete serialized draft before JSON
  encoding or temporary-file creation. This reuses the existing strict contract
  for all modes, while old Pinterest drafts remain load-compatible because
  missing `pin` and `results` fields are still handled by the read path.
- Regression test:
  `test_save_project_draft_rejects_mutated_unsafe_pinterest_error` mutates a
  result after construction with a provider-like error and secret-like token,
  asserts `save_project_draft()` raises `ProjectStateError`, and confirms no
  project JSON file is created.

Verification command and output:

```text
python3 -m unittest tests.test_v3_project_state.ProjectSerializationTests.test_save_project_draft_rejects_mutated_unsafe_pinterest_error -v
Ran 1 test
OK

python3 -m unittest tests.test_v3_project_state tests.test_pinterest_prompt_schema -v
Ran 30 tests
OK

python3 -m py_compile v3_project_state.py pinterest_prompt_schema.py
git diff --check
```
