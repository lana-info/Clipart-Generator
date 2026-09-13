# A0 Dependency Guardrails Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven development for every guardrail behavior change.

**Goal:** Freeze the current Studio/Core/module dependency debt as an exact baseline so new boundary violations cannot be added silently.

**Architecture:** Parse production Python imports with `ast`, assign existing legacy sources to explicit module layers, treat all other root production modules as Core/shared, and compare every cross-layer edge against one exact allowlist. Official packages under `studio_official_modules/<module_id>/` are treated as distinct module layers so future packages cannot import Core internals or another module without an explicit reviewed contract.

**Tech Stack:** Python 3.12, stdlib `ast`/`pathlib`, pytest.

**Spec:** `PRD_VIBIX_STUDIO_3.2_V2.ru.md`, `AGENTS.md`, and the owner-approved Option A boundary-migration architecture with the 2026-09-13 refinements.

## Global Constraints

- Baseline commit is exactly `8ff2c54f256ae35392e9374c9ba91619493764ff`.
- Work only in `/root/projects/Clipart Generator/studio-module-api-worktree` on `codex/refactor-studio-module-api-3.2`.
- Do not modify `/root/projects/Clipart Generator/studio-3.2-worktree`.
- No build, deploy, paid API call, workflow dispatch, merge, release/version change, or `.env` read.
- Allowlist entries are exact source/target module pairs; wildcard or prefix permissions are forbidden.
- No user-visible behavior or UI change in A0.
- A0 is rollbackable as one checkpoint commit with `[skip ci]`.

---
### Task 1: RED — expose all current cross-layer imports

**Files:**
- Create: `tests/test_studio_dependency_architecture.py`

**Interfaces:**
- Consumes: current repository Python sources only.
- Produces: deterministic `set[tuple[str, str]]` of cross-layer import edges.

- [ ] Define explicit legacy layer membership for Clipart, Pinterest, Patterns, and Processing.
- [ ] Treat other top-level production `.py` modules as Core/shared.
- [ ] Treat `studio_official_modules/<module_id>/` as distinct official-module layers.
- [ ] Start with an empty legacy allowlist.
- [ ] Run `pytest tests/test_studio_dependency_architecture.py -q` and verify failure lists the real existing edges.

### Task 2: GREEN — freeze the exact dependency baseline

**Files:**
- Modify: `tests/test_studio_dependency_architecture.py`

**Interfaces:**
- Consumes: the RED failure's exact edges.
- Produces: `LEGACY_ALLOWED_EDGES` containing only exact `(source_module, target_module)` pairs.

- [ ] Add each existing edge explicitly; do not use glob, regex, prefix or layer-wide permissions.
- [ ] Assert allowlist entries themselves contain no wildcard characters.
- [ ] Assert current cross-layer edges equal the allowlist, so both new edges and stale removed edges fail review.
- [ ] Run the focused test and verify GREEN.
### Task 3: Verification and checkpoint

**Files:**
- Test: `tests/test_studio_dependency_architecture.py`
- Plan: `docs/superpowers/plans/2026-09-13-a0-dependency-guardrails.md`

- [ ] Run focused architecture tests.
- [ ] Run `python -m py_compile tests/test_studio_dependency_architecture.py`.
- [ ] Run the full isolated pytest suite with `scripts/run_isolated_tests.py -q`.
- [ ] Run `git diff --check` and inspect the complete diff.
- [ ] Recheck source `studio-3.2-worktree` remains clean at baseline.
- [ ] Commit the verified A0 checkpoint with `[skip ci]` and push only the refactor branch.

**Completion criterion:** a new cross-layer import in the protected production surface fails unless its exact edge is explicitly reviewed into the allowlist; existing behavior and production code remain unchanged.

**Rollback boundary:** revert the single A0 checkpoint commit.

**Visual approval:** not required.

**Separate owner decision:** none for A0. License-service and UI remain out of scope.
