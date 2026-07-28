# Traceability 3.0

PRD Key: `CG3-PRD-001`

| PRD area | Task keys | Evidence |
|---|---|---|
| Routes, drafts, prompt/reference workspace | `CG3-TASK-001`–`CG3-TASK-005`, `CG3-TASK-016`–`CG3-TASK-020` | `tests.test_v3_project_state`, `tests.test_v3_wizard_navigation`, `tests.test_v3_prompt_workspace`, `tests.test_v3_csv_import` |
| Clipart, Pinterest and processing flows | `CG3-TASK-006`–`CG3-TASK-010`, `CG3-TASK-021`–`CG3-TASK-026` | corresponding `tests.test_v3_*_flow`, processing and pipeline tests |
| Provider settings and secret handling | `CG3-TASK-022`, `CG3-TASK-027` | `tests.test_v3_provider_settings`, `tests.test_v3_credential_store`, security regression |
| Observable execution and cancellation | `CG3-TASK-010`, `CG3-TASK-028` | `tests.test_v3_run_queue`, `tests.test_v3_progress_events` |
| Contrast and accessible states | `CG3-TASK-002`, `CG3-TASK-029` | `tests.test_v3_components`, offscreen wizard smoke |
| SynthID provenance | `CG3-TASK-011`–`CG3-TASK-014` | `SYNTHID_3_METHOD_BENCHMARK.ru.md`, ADR-001; research-only/no production claim |

Research-only items are explicitly not release blockers for ordinary generation,
processing or export. No secrets, user files or benchmark inputs are included in
the release source set.
