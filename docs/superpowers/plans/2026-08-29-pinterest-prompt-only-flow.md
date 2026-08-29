# Pinterest Prompt-Only Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Pinterest product/template pipeline with a simple prompt-and-reference image generation flow that saves vertical Pinterest images without post-processing.

**Architecture:** Reuse the proven Clipart prompt workspace, CSV mapping dialog, prompt review table, generation model catalog, queue and worker contracts. Pinterest gets its own localized adapter and route, but it must not expose Clipart prompt generation, product compositing, background removal or image processing.

**Tech Stack:** Python, PyQt6, existing V3 project state, shared CSV importer, existing KIE/Fal generation routing, unittest.

**Spec:** Product decision approved in chat on 2026-08-29.

## Global Constraints

- Pinterest MVP has exactly two prompt sources: manual prompt with optional references and CSV import with prompt/references columns.
- Prompt review must allow editing prompt text and adding/removing/replacing references before generation.
- Default Pinterest output is vertical `2:3`, `1000×1500`; alternative supported model ratios remain selectable.
- No product upload, product protection, fixed six-slot templates, AI scene generation, background removal, upscaling, or post-processing in this MVP.
- Results are saved to the selected output folder; source files are not overwritten.
- Fal.ai and KIE paid calls remain behind existing license/runtime gates; tests do not make live requests.

### Task 1: State and adapter contract

**Files:**
- Modify: `v3_project_state.py`
- Modify: `v3_pinterest_flow.py`
- Test: `tests/test_v3_project_state.py`, `tests/test_v3_pinterest_flow.py`

- [x] Add active Pinterest prompt entries and generation settings while preserving migration of old Pinterest pin data.
- [x] Expose an adapter compatible with the shared Clipart prompt/review/request functions.
- [x] Assert defaults, draft persistence, and old-draft migration.

### Task 2: Prompt input and CSV-only alternatives

**Files:**
- Modify: `v3_pinterest_flow.py`
- Test: `tests/test_v3_pinterest_flow.py`, `tests/test_v3_prompt_csv_import.py`

- [x] Replace the current copy/layout page with two source choices: ready prompt with optional references, or CSV import.
- [ ] Reuse `PromptCsvImportDialog` and support drag-and-drop, delimiter/header mapping, bounded errors and replacement import.
- [ ] Do not expose the Clipart prompt generator fields in Pinterest.

### Task 3: Review, generation and save route

**Files:**
- Modify: `v3_pinterest_flow.py`
- Modify: `v3_clipart_flow.py` only if a shared request contract needs a safe extension.
- Test: `tests/test_v3_pinterest_flow.py`, `tests/test_v3_run_queue.py`

- [x] Add a Pinterest prompt review page with editable prompt/reference rows and no processing controls.
- [x] Route reviewed entries to the existing generation worker and preserve cancellation/progress/error behavior.
- [ ] Save generated images directly to the Pinterest output directory with stable filenames.

### Task 4: Format and documentation

**Files:**
- Modify: `v3_pinterest_flow.py`, `v3_localization.py`
- Modify: `PRD.md`, `PRD_3.0.ru.md`, `TASKS_3.0.ru.md`, `STATE.md`
- Test: `tests/test_v3_pinterest_flow.py`, `tests/test_v3_localization.py`

- [x] Set `2:3` and `1000×1500` as the default, while retaining compatible alternative ratios/resolutions.
- [x] Remove stale Pinterest copy/template text from the active route and localize the new labels.
- [ ] Document that processing, product preservation and templates are future modules.

### Task 5: Verification and checkpoint

**Files:**
- No source changes unless verification finds a regression.

- [x] Run focused tests, full offline tests, syntax and diff checks.
- [ ] Run the Windows packaging workflow only after the source checkpoint is committed.
- [ ] Commit and push the feature branch; do not merge without explicit approval.
