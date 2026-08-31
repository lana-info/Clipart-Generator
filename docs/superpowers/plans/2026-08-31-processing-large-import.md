# Processing Large Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Keep the Processing files page responsive when 81 large upscaled images are added at once.

**Architecture:** Split fast header validation from full pixel decoding, cache immutable file metadata across page refreshes, and defer thumbnail decoding for large batches through the Qt event queue. Full pixel decoding remains at the worker boundary where failures are reported per file.

**Tech Stack:** Python, Pillow, PyQt6, unittest/pytest.

**Spec:** Owner report and diagnostics from the 2026-08-31 81-file Processing import.

## Constraints

- Keep the existing page layout and controls.
- Preserve file size, dimension, frame-count, and format limits.
- Do not silently discard files; worker failures remain per-item.
- Small batches retain immediate thumbnails.

### Task 1: Prove duplicate decoding and large-batch blocking

**Files:** `tests/test_v3_processing_flow.py`

1. Add a test proving one newly added file is inspected once, not again during refresh.
2. Add an 81-file test that fails if Pillow pixel decoding occurs inside `add_files`.
3. Assert that large-batch thumbnail labels exist immediately while their decoding is deferred.

### Task 2: Add fast inspection and metadata caching

**Files:** `v3_processing_flow.py`

1. Add an explicit `decode_pixels` option to `inspect_local_image`, defaulting to strict behavior.
2. Use header-only inspection during file selection and run-request construction.
3. Cache `LocalImageInfo` by normalized path plus file stat signature.
4. Invalidate cache entries on removal, clear, or file replacement.

### Task 3: Defer thumbnails for large batches

**Files:** `v3_processing_flow.py`, `tests/test_v3_processing_flow.py`

1. Keep synchronous thumbnails for small batches.
2. For larger batches, create cards immediately and schedule one scaled thumbnail read per timer callback.
3. Safely ignore callbacks for cards removed before their turn.

### Task 4: Verify and document

**Files:** `ERROR_LOG.md`, `STATE.md`

1. Run Processing flow, navigation, project-state, and request-building suites.
2. Run the full offline suite and compile check.
3. Record root cause, limits, test evidence, and Windows residual risk.
4. Commit and push a checkpoint without merging or building.
