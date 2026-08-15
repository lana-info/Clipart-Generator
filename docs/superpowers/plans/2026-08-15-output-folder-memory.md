# Output-folder Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Default new projects to Pictures/Clipart Generator and remember the last selected work and result folders.

**Architecture:** Resolve the default through Qt platform paths in `v3_mode_selection.py`. Extend the existing user-data `preferences.json` schema with global last-folder values while preserving per-mode output and operation settings.

**Tech Stack:** Python 3, PyQt6 `QStandardPaths`, pathlib, unittest.

## Global Constraints

- Never use the process/install directory as a new-project folder default.
- Keep source images intact and preserve existing per-mode output routing.
- Do not add dependencies.

---

### Task 1: Default and persisted folders

**Files:**
- Modify: `v3_mode_selection.py`
- Test: `tests/test_v3_mode_selection.py`
- Modify: `CHANGELOG.md`, `ERROR_LOG.md`, `STATE.md`, `TASKS.md`

**Interfaces:**
- Produces: `default_work_directory() -> pathlib.Path`.
- Persists: `preferences.json` keys `last_work_dir: str` and `last_output_dir: str`.

- [x] **Step 1: Write failing tests** for a Pictures-based default and restoration of both selected paths after reopening.
- [x] **Step 2: Run the focused tests** and confirm failure because `default_work_directory` is absent.
- [x] **Step 3: Implement** the Qt Pictures fallback, safe directory creation, preference load, and preference save behavior.
- [x] **Step 4: Run** `.venv/bin/python -m unittest tests.test_v3_mode_selection -v` and confirm the folder regressions pass.
- [x] **Step 5: Run** output-path and full-suite regressions, then update project status documents with the verified totals.

No commit or push is authorized by this plan.
