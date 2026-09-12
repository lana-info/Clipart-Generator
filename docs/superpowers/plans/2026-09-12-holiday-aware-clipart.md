# Holiday-Aware Clipart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local holiday profiles that drive canonical five-color palette recommendations and holiday-aware object/decor suggestions in Clipart without paid calls.

**Architecture:** `studio_holiday_profiles.py` owns validated immutable holiday data and lookup/recommendation helpers. The Clipart builder consumes those helpers for palette cards and context-aware recommendations; the planning request includes bounded holiday hints so existing text assistants can enrich objects while preserving the main theme. Project state continues to store only the user-selected context/palette/objects, not duplicated profile data.

**Tech Stack:** Python 3, PyQt6, existing Clipart recipe/planning pipeline, pytest/unittest.

**Spec:** `PRD_VIBIX_STUDIO_3.2_V2.ru.md`

## Global Constraints

- First wave: Christmas, Halloween, Easter, Valentine’s Day, Thanksgiving, 4th of July / Independence Day, St. Patrick’s Day, Baby Shower, Birthday, First Birthday.
- Mother’s Day and Father’s Day are not first-wave holiday profiles.
- Palette cards show exactly 5 visible colors.
- Holiday palettes are canonical/theme-linked, not arbitrary aesthetic labels.
- Holiday context influences accessories, props, decor, compositions, mood and background hints while preserving the main theme.
- No provider call, paid request, build, deployment or workflow dispatch is introduced by this increment.
- User-selected custom/reference palettes remain supported.

---

### Task 1: Holiday profile data contract

**Files:**
- Create: `studio_holiday_profiles.py`
- Test: `tests/test_studio_holiday_profiles.py`

**Interfaces:**
- Produces: `HolidayProfile`, `get_holiday_profile(context)`, `holiday_palette_presets(context)`, `holiday_planning_hints(context)`.

- [ ] Write failing tests for first-wave lookup, aliases, exact five-color palettes, Christmas/Halloween canonical colors, exclusions, and unknown context.
- [ ] Run the focused test and verify RED.
- [ ] Implement validated frozen profile data and helpers.
- [ ] Run focused tests and verify GREEN.

### Task 2: Planning integration

**Files:**
- Modify: `studio_clipart_planner.py`
- Modify: `studio_text_client.py`
- Test: `tests/test_studio_clipart_planner.py`
- Test: `tests/test_studio_text_client.py`

**Interfaces:**
- Consumes: `holiday_planning_hints(context)`.
- Produces: bounded `holiday` context in planning request; existing provider prompt instructs assistants to use it as enrichment, not replacement.

- [ ] Write failing tests proving Christmas hints reach planning requests and non-holiday contexts do not gain a fake profile.
- [ ] Verify RED.
- [ ] Add local holiday hints to request/prompt serialization without secrets or provider changes.
- [ ] Verify GREEN and compatibility with existing request staleness checks.

### Task 3: Palette library UI

**Files:**
- Modify: `studio_clipart_builder_ui.py`
- Test: `tests/test_studio_clipart_builder_ui.py`
- Add final visual proof: `docs/ui/3.2/holiday-palettes/`

**Interfaces:**
- Consumes: holiday palette presets plus general curated five-color presets.
- Produces: theme/context recommendations, five-color cards, custom palette field, existing reference-palette action.

- [ ] Write failing UI tests for five swatches, Christmas recommendation when context is Christmas, no Mother/Father first-wave card, and persistence of selected/custom palette.
- [ ] Verify RED.
- [ ] Implement approved summary-first palette library layout with five swatches per card and plain-language labels.
- [ ] Verify GREEN and render at 1120×780.

### Task 4: Documentation and verification

**Files:**
- Modify: `PRD_VIBIX_STUDIO_3.2_V2.ru.md`
- Modify: `TASKS_VIBIX_STUDIO_3.2.ru.md`
- Modify: `STATE.md`
- Modify: `PROJECT.md`

- [ ] Record Holiday Profile architecture, first-wave list, five-color rule and reviewed Excel as structural inspiration only.
- [ ] Run focused tests.
- [ ] Run full isolated pytest.
- [ ] Run `py_compile` and `git diff --check`.
- [ ] Perform read-only diff review in this ChatGPT workflow; do not consume Codex CLI quota.
- [ ] Commit with `[skip ci]` and push; do not trigger Actions/builds.
