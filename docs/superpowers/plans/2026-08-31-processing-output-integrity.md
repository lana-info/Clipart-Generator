# Processing Output Integrity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan.

**Goal:** Make Fal processing publish exactly one meaningful rough artifact per upscale, reuse the already downloaded provider result for final export, and never report an item as successful when its final PNG is missing or unreadable.

**Architecture:** Keep the provider pipeline's local downloaded PNG as the authoritative downstream artifact. Classify rough artifacts by explicit generated filename roles rather than broad substrings. Add a strict final-output validation boundary immediately after atomic publication so item success can only be emitted for an existing, non-empty, decodable PNG.

**Tech Stack:** Python 3, PyQt worker orchestration, Pillow, `unittest`/`pytest`.

**Spec:** User observations and the 2026-08-31 diagnostics bundle for the 17-file Fal Recraft Crisp run.

## Global Constraints

- Preserve current output naming and no-overwrite behavior.
- Do not add provider calls or change billing behavior.
- Preserve transparent PNGs and metadata cleanup behavior.
- Do not expose local paths or credentials in diagnostics.
- Each fix must begin with a failing regression test.

### Task 1: Restrict rough publication to actual stage results

**Files:**
- Modify: `tests/test_v3_output_paths.py`
- Modify: `main.py:2269-2318`

1. Add a regression test that creates both `file_upscaled_before_recraft_input_*.png` and `file_upscaled_before_fal_*.png`, calls `_persist_rough_outputs`, and expects only the provider result to be published as `upscaled-before`.
2. Run the focused test and confirm that it fails because the broad `"upscaled"` marker publishes both files.
3. Replace broad substring classification with explicit filename-role matching for upscale-before and upscale-after results; preparation/source artifacts must not match.
4. Run the focused test and the existing rough/output-path tests.

### Task 2: Reuse Fal's local result for final export

**Files:**
- Modify: `tests/test_kie_routing.py`
- Modify: `main.py:2910-3065`
- Modify: `main.py:2735-2765`

1. Add a regression test for Fal upscale showing one provider-result download and a local file returned from `_run_processing_pipeline`.
2. Add the equivalent assertion for Fal background removal because it has the same local-download/remote-URL state.
3. Run the tests and confirm that the pipeline currently returns the remote URL, causing `_save_final_output` to download again.
4. After a successful local download, clear `current_url`, mark the result local, and return the verified local path to downstream stages/final export.
5. Run focused Fal/routing tests and confirm one download per provider result.

### Task 3: Reject false-success final publications

**Files:**
- Modify: `tests/test_final_save_cleanup.py`
- Modify: `main.py:3823-3890`

1. Add regression tests that simulate a final destination disappearing after publication and a zero-byte/unreadable destination.
2. Confirm the tests fail because diagnostic inspection currently returns `status=unreadable` but the worker ignores it and emits item success.
3. Add strict final PNG validation after `_publish_final_output`: the destination must exist, be non-empty, decode with Pillow, and contain positive dimensions.
4. Raise a user-safe processing error when validation fails. Leave the item in failed state and do not increment the completed count.
5. Confirm valid outputs still pass for cleanup-disabled, metadata-cleanup, trim, DPI, overwrite, and no-overwrite paths.

### Task 4: Verification and project record

**Files:**
- Modify: `ERROR_LOG.md`
- Modify: `STATE.md`

1. Run focused suites: `tests/test_kie_routing.py`, `tests/test_final_save_cleanup.py`, and `tests/test_processing_contract.py`.
2. Run the broader processing/Fal test subset selected from the changed call paths.
3. Review the diff for unrelated changes and privacy regressions.
4. Record the confirmed root causes, implemented safeguards, test commands, and the residual risk: diagnostics prove the missing final file was reported as successful, but do not prove what removed it after publication.
5. Create and push a checkpoint commit on `codex/fix-processing-output-integrity` only after all checks pass.
