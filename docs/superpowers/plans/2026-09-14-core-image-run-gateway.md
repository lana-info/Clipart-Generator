# Core Image Run Gateway Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove raw provider credentials/full runtime settings from built-in image workflows while preserving existing WorkerThread, paid-call, journal/recovery, retry and UI behavior.

**Architecture:** Built-in workflows create secret-free `FlowRunRequest` plans. `CoreImageRunGateway` owns runtime credentials/config, safe preflight/Fal pricing, authorization, project-save admission, legacy worker enrichment and creation. RunQueue retry goes through the same gateway launch path.

**Tech Stack:** Python 3.12, PyQt6, pytest, existing WorkerThread/runtime adapter, existing Studio capability host.

**Spec:** `docs/superpowers/specs/2026-09-14-core-image-run-gateway-design.md`

## Global Constraints

- Built-in modules are trusted first-party code under ADR-004; this is an ownership/modularity boundary, not a hostile-code sandbox.
- No new scheduler, provider transport, retry engine, task journal or paid-call stack.
- Do not read `.env`, credentials, or call paid/live provider APIs in tests or implementation validation.
- Keep existing UI behavior/layout unchanged.
- Every commit includes `[skip ci]`; keep stable source worktree untouched at `8ff2c54f256ae35392e9374c9ba91619493764ff`.
- Core→module and module→module dependency counts must remain zero.
### Task 1: Secret-free run-plan settings

**Files:**
- Modify: `v3_image_worker_settings.py`
- Modify: `v3_image_generation_runtime.py`
- Modify: `v3_processing_flow.py`
- Test: `tests/test_v3_clipart_flow.py`, `tests/test_v3_processing_flow.py`

**Interfaces:**
- Produces `build_image_run_settings(runtime, generation, operations, *, run_mode) -> dict[str, Any]` with no credential/local-Core keys.
- Produces `enrich_image_worker_settings(plan_settings, runtime_settings) -> dict[str, Any]` for Core-only enrichment.
- Keeps `build_image_worker_settings(...)` as a compatibility composition of the two helpers.

- [ ] Add RED tests asserting built-in request builders never include `kie_api_key`, `fal_api_key`, `photoroom_api_key`, `runpod_api_key`, or `local_realesrgan_dir` even when secret runtime settings are supplied to compatibility call sites.
- [ ] Run focused tests and verify the new assertions fail on current code.
- [ ] Implement the two split helpers; switch image-generation and processing request builders to `build_image_run_settings`.
- [ ] Keep compatibility `build_image_worker_settings` behavior for legacy/direct WorkerThread tests.
- [ ] Run focused request-construction/output-path tests GREEN; run `py_compile` and `git diff --check`.
- [ ] Commit checkpoint: `refactor: separate image run plan from secrets [skip ci]`.
### Task 2: Core image run gateway

**Files:**
- Create: `studio_image_run_services.py`
- Test: `tests/test_studio_image_run_services.py`

**Interfaces:**
- Produces `CoreImageRunGateway.preflight(request) -> tuple[str, ...]`.
- Produces `CoreImageRunGateway.estimate_fal_cost(endpoint_quantities) -> tuple[float, str]`.
- Produces `CoreImageRunGateway.launch(request) -> CoreWorkerJobHandle`.
- Gateway dependencies are callbacks/ports for runtime settings, authorization, project preparation and prepared worker creation; callbacks are stored weakly where possible.

- [ ] Add RED unit tests for missing KIE/Fal/PhotoRoom credentials, local Real-ESRGAN validation, safe Fal pricing with fake estimator, and no secret values in returned data/errors.
- [ ] Add RED launch-order tests recording `preflight → authorize → prepare/save → worker factory`; verify authorization/save failure creates zero workers.
- [ ] Implement gateway using `enrich_image_worker_settings`; use existing `missing_runtime_requirements` on an internal enriched request copy only.
- [ ] Sanitize exceptions using Core-owned runtime secrets before returning errors to modules.
- [ ] Ensure `launch()` wraps the existing worker in `CoreWorkerJobHandle` and performs exactly one worker-factory attempt.
- [ ] Run gateway tests GREEN plus existing worker-handle tests; commit `refactor: add core image run gateway [skip ci]`.
### Task 3: Wire gateway through WorkflowHost/Core composition

**Files:**
- Modify: `_studio_workflow_core.py`
- Modify: `studio_workflow_host.py`
- Modify: `v3_mode_selection.py`
- Test: `tests/test_studio_workflow_host.py`, `tests/test_v3_mode_selection.py`

**Interfaces:**
- `WorkflowHost.image_run_preflight(request)` delegates to the Core gateway.
- `WorkflowHost.image_run_estimate_fal_cost(endpoint_quantities)` delegates to Core.
- `WorkflowHost.image_run_launch(request)` delegates to Core.
- Existing `runtime_settings()`, `create_worker_job()` and `authorize_run()` remain temporarily for non-migrated compatibility but built-in image controllers must stop using them by the final task.

- [ ] Add RED host/composition tests showing the gateway is scoped per module and module code receives only safe results/handles.
- [ ] Split `V3ApplicationView` prepared-worker creation so gateway launch can save exactly once and then create the existing legacy worker with injected `project_id`.
- [ ] Construct one `CoreImageRunGateway` per built-in workflow host using weak/lifecycle-safe callbacks.
- [ ] Run host/mode-selection/license/save-before-worker tests GREEN.
- [ ] Verify no duplicate project save and no second worker/scheduler path.
- [ ] Commit `refactor: expose core image run gateway to workflows [skip ci]`.
### Task 4: Migrate Clipart to the gateway

**Files:**
- Modify: `v3_clipart_flow.py`
- Test: `tests/test_v3_clipart_flow.py`, `tests/test_v3_run_queue.py`

**Interfaces:**
- Clipart request construction uses no raw runtime settings.
- Review preflight uses `shell.image_run_preflight(request)`.
- Fal quote uses `shell.image_run_estimate_fal_cost(fal_endpoint_quantities(...))`.
- Initial launch/retry use `shell.image_run_launch(request)` via `create_worker_for_request`.

- [ ] Add RED architecture/behavior tests that Clipart controller never calls `runtime_settings()` and its `FlowRunRequest.settings` contains no credentials.
- [ ] Remove direct `estimate_fal_cost`/credential reads and `_runtime_settings` secret snapshot from controller paths.
- [ ] Add `create_worker_for_request()` delegating FlowRunRequest to Core gateway.
- [ ] Preserve review status, Fal cost UI, authorization failure behavior, save-before-worker and error rendering.
- [ ] Run Clipart + RunQueue retry tests GREEN.
- [ ] Commit `refactor: route clipart runs through core gateway [skip ci]`.
### Task 5: Migrate Processing to the gateway

**Files:**
- Modify: `v3_processing_flow.py`
- Test: `tests/test_v3_processing_flow.py`, `tests/test_v3_run_queue.py`

**Interfaces:**
- `build_processing_run_request()` creates secret-free settings.
- Processing preflight/launch use the same Core gateway as Clipart.
- Local-only processing remains launchable without provider credentials.

- [ ] Add RED tests for secret-free Processing requests and safe provider-missing labels from Core preflight.
- [ ] Remove controller use of `runtime_settings()` and module-side credential checks.
- [ ] Add `create_worker_for_request()` delegating FlowRunRequest to `image_run_launch()`.
- [ ] Preserve external-transfer consent, local Real-ESRGAN checks, output path rules and Evidence Center behavior.
- [ ] Run Processing/RunQueue tests GREEN.
- [ ] Commit `refactor: route processing runs through core gateway [skip ci]`.

### Task 6: Migrate prompt-only Pinterest and retry admission

**Files:**
- Modify: `v3_pinterest_flow.py`
- Modify: `v3_run_queue.py`
- Test: `tests/test_v3_pinterest_flow.py`, `tests/test_v3_run_queue.py`, `tests/test_v3_license_flow_gate.py`

**Interfaces:**
- Prompt-only Pinterest FlowRunRequest uses Core gateway for preflight/Fal quote/launch.
- `PinterestPinRunRequest` six-slot local worker keeps its separate `prepare_run()` path.
- RunQueue retry asks the owning controller to `create_worker_for_request(request)` and does not separately authorize/create a legacy worker.

- [ ] Add RED tests proving retry reaches gateway launch exactly once and still authorizes/saves before worker creation.
- [ ] Remove prompt-only Pinterest raw runtime-settings/Fal-key reads.
- [ ] Route FlowRunRequest through `image_run_launch()` while keeping PinterestPinRunRequest local-worker behavior unchanged.
- [ ] Remove separate retry authorization/create-worker fallback from RunQueueSupport.
- [ ] Run Pinterest/RunQueue/license tests GREEN, including selective six-slot regression.
- [ ] Commit `refactor: unify image retry admission through core [skip ci]`.
### Task 7: Architecture guards and final convergence

**Files:**
- Modify: `tests/test_studio_dependency_architecture.py`
- Modify/create focused gateway architecture tests as needed
- Update: `docs/superpowers/specs/2026-09-14-core-image-run-gateway-design.md` only if implementation reveals a material mismatch

**Interfaces:**
- Built-in image workflows contain no image-run `runtime_settings()` calls and no known credential-key reads.
- Secret enrichment exists only in Core/compatibility worker-setting code.

- [ ] Add static guards scanning `v3_clipart_flow.py`, `v3_processing_flow.py`, and `v3_pinterest_flow.py` for credential-key strings and image-run `runtime_settings()` usage.
- [ ] Verify exact dependency allowlist, Core→module=0, module→module=0 and no wildcard.
- [ ] Run affected suites: gateway, host, Clipart, Processing, Pinterest, RunQueue, license gate, mode selection, packaged/release smoke.
- [ ] Run full isolated suite and record exact pass/skip/subtest counts and exit code.
- [ ] Run `python -m py_compile` on changed production files and `git diff --check`.
- [ ] Confirm stable source worktree still clean at baseline.
- [ ] Commit final guard/convergence checkpoint with `[skip ci]`, push feature branch, and prepare exact independent READ-ONLY review range.