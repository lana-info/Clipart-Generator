# Clipart Style Profiles Implementation Plan

> **For agentic workers:** implement task-by-task with TDD and verify each increment before commit.

**Goal:** Add a local, deterministic Style Profile library for coherent Clipart collections without paid/provider calls.

**Architecture:** `studio_style_profiles.py` owns validated base styles, generic modifiers, alias resolution and theme/context recommendations. Existing `ClipartRecipe.visual['technique']` remains the persisted user choice; planning derives bounded style hints from it, so no recipe migration is required. UI integration followed the required owner-approved visual gate.

**Tech Stack:** Python 3.12, PyQt6 existing builder, pytest/unittest.

**Spec:** `PRD_VIBIX_STUDIO_3.2_V2.ru.md`

## Global Constraints
- No network/provider call for style recommendations.
- One coherent base style across a collection unless the user explicitly changes it.
- Do not expose/copy brand-specific style names; use generic visual language.
- Preserve custom style text and existing project roundtrip.
- Production UI changes require approved 1120x780 mockup first.

### Task 1: Local Style Profile library
- [x] Add failing tests for validation, aliases, recommendations and brand-neutral names.
- [x] Implement `studio_style_profiles.py` with generic base profiles and modifiers.
- [x] Verify style-profile tests.

### Task 2: Planning integration
- [x] Add failing test that `planning_request()` contains bounded local style guidance.
- [x] Add `style_planning_hints()` to planning request without extra provider calls.
- [x] Verify planner/text-client regressions.

### Task 3: Documentation and UI design gate
- [x] Update PRD/TASKS/STATE/PROJECT with Style Profile architecture and source rationale.
- [x] Create dark-theme 1120x780 style-selector mockup with recommendations, base styles, modifiers and custom style; owner approved it.
- [x] Do not modify production builder UI until owner approves the mockup.

### Task 4: Approved production UI and verification
- [x] Implement recommendations, featured-six library view, category filtering and modifier chips.
- [x] Preserve custom style and existing line/material/detail fields without recipe migration.
- [x] Capture real 1120x780 Qt proof under `docs/ui/3.2/style-profiles/`.
- [x] Run full isolated suite and read-only diff review; commit/push is the final handoff action.
