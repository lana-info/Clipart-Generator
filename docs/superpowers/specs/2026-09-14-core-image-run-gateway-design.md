# Core Image Run Gateway Design

Status: Proposed for implementation — 2026-09-14

## Goal

Remove raw provider credentials and the full runtime-settings mapping from built-in workflows while preserving the existing WorkerThread, journal/recovery, paid-call admission, retry semantics, UI behavior, and project-save guarantees.

## Product boundary

Built-in Vibix modules are trusted first-party code under ADR-004. This change is therefore about ownership and modularity, not a hostile-code sandbox. Provider credentials, provider-account configuration, paid-call policy, and authoritative run admission belong to Studio Core. Modules own workflow choices and user-facing configuration, but do not receive API-key values.

## Non-goals

- No new scheduler, provider transport, task journal, or retry engine.
- No change to credential storage or API Settings UI.
- No visual UI redesign.
- No migration to third-party plugin sandboxing.
- No provider/network calls in tests.
## Chosen approach

Introduce one Core-owned `CoreImageRunGateway` used by Clipart, Processing, and the active prompt-only Pinterest flow through narrow `WorkflowHost` operations.

A built-in module creates a secret-free `FlowRunRequest`. Its `settings` may contain workflow choices such as model IDs, provider IDs, timeouts, output/workspace paths, and operation parameters, but must never contain `kie_api_key`, `fal_api_key`, `photoroom_api_key`, `runpod_api_key`, or other credentials.

The gateway performs three operations:

1. `preflight(request)` — inspect the secret-free plan plus Core-owned runtime settings and return only safe missing-requirement labels.
2. `estimate_fal_cost(endpoint_quantities)` — use the Core-owned Fal credential and return a typed amount/currency quote; the key never leaves Core.
3. `launch(request)` — re-run Core preflight, authorize the run, save the project, enrich an internal WorkerThread settings snapshot with credentials/local runtime config, create the existing worker/handle, and return that handle.

Retry calls the same `launch(request)` operation, so retry cannot bypass authorization, save-before-worker, or credential injection.
## Public contracts

Create `studio_image_run_api.py` as a secret-free public/shared boundary with immutable result types:

- `ImageRunPreflight(ready: bool, missing_requirements: tuple[str, ...])`
- `ImageRunCostQuote(amount: float, currency: str)`

`FlowRunRequest` remains the shared run-plan type for the first migration. The architecture test will require that requests produced by built-in image workflows contain no known credential keys. This avoids introducing a second request model while still separating plan data from Core-only worker configuration.

No public contract exposes provider clients, credential values, a generic settings mapping from Core, or arbitrary service lookup.

## Core service

Create `studio_image_run_services.py` with `CoreImageRunGateway`. It owns callbacks/ports for current runtime settings, authorization, project preparation/save, and legacy worker creation. The service may call existing helpers for provider requirements and Fal pricing, but it must not perform the paid image operation itself; existing WorkerThread/provider code remains the source of truth for journal/resume/idempotency and `_admit_paid_submission`.
## Request construction

`v3_image_worker_settings.build_image_worker_settings()` becomes a secret-free builder. It receives project/runtime data and operation choices only. Credential/local-runtime enrichment moves to Core.

`build_image_generation_run_request()` and `build_processing_run_request()` no longer need a raw `runtime_settings` argument for built-in production use. Their output continues to include all non-secret fields needed by RunQueue and WorkerThread: run mode, model/provider IDs, bounded timeout/retry fields, output/workspace paths, prompts/files, and processing parameters.

Core creates an internal worker settings copy immediately before worker construction. It adds only the legacy fields the existing WorkerThread actually needs from application configuration, initially the provider credentials and `local_realesrgan_dir`. No Core settings object is returned to the module.

## Preflight

Preflight derives required providers from the secret-free request. It checks Core-owned credentials and local runtime availability, returning user-facing labels such as `KIE API Key`, `Fal.ai API Key`, `PhotoRoom API Key`, or the existing Real-ESRGAN availability message.

Module-local validation stays module-local: invalid model/ratio combinations, missing prompts/files, unsupported processing combinations, path/image validation, and external-transfer consent are validated before Core preflight.
## Launch ordering and retry

For every initial image run and retry, the Core gateway enforces this order:

1. Validate the request type and Core runtime requirements.
2. Call the existing license/run authorization.
3. Persist the authoritative project state with the existing fail-closed save path.
4. Build an internal worker settings snapshot and inject Core-owned credentials/runtime configuration.
5. Create the existing legacy worker and wrap it in the existing `CoreWorkerJobHandle`.
6. Return the handle to the controller; the controller keeps the existing `RunQueueSupport.start_new/connect_worker/start` sequence.

No paid provider POST occurs in the gateway. WorkerThread retains `_paid_submission_open`, provider lease scopes, journal/resume/idempotency, uncertain-submission handling, and the exact pre-send `_admit_paid_submission` checks.

RunQueue retry stops calling authorization and worker creation as separate module-visible operations. It submits the retry `FlowRunRequest` through the same gateway launch operation, preserving one admission path.
## Workflow migration

Clipart, Processing, and prompt-only Pinterest stop calling `WorkflowHost.runtime_settings()`, stop reading credential keys, and stop calling `estimate_fal_cost()` directly with a key.

Their controllers instead:

- build a secret-free request;
- call `image_run_preflight(request)` for review-page readiness;
- call `image_run_estimate_fal_cost(endpoint_quantities)` when the user explicitly requests Fal pricing;
- call `image_run_launch(request)` after module-local validation;
- keep the returned handle in the existing `worker` field and keep existing RunQueue/UI signal wiring.

The deferred six-slot Pinterest local worker remains module-owned and uses the separate `prepare_run()` path from ADR-004 remediation because it does not require provider credentials. It must not be forced through the legacy image WorkerThread gateway.

## Error and secrecy behavior

Gateway exceptions exposed to modules must contain only safe messages. Existing `safe_runtime_error()` continues to sanitize worker/provider failures, but built-in controllers should no longer retain `_runtime_settings` containing secrets because those secrets are never returned to them.
## Architecture guards and tests

Add tests that fail if built-in flow sources contain known credential-key strings or call `runtime_settings()` for image-run execution. Request-construction tests must assert that secret keys are absent from `FlowRunRequest.settings` even when Core runtime settings contain secrets.

Gateway tests cover provider-key preflight without exposing values, Fal cost estimation through a fake Core pricing port, secret enrichment only inside the worker factory call, authorization/save-before-worker ordering, save/authorization failure with zero worker creation, and retry using the same launch path.

Existing suites must continue to cover RunQueue recovery, paid-call protections, mode switching, lazy pages, Evidence Center, transparency editing, packaged smoke, exact dependency allowlist, `Core→module = 0`, and `module→module = 0`.

## Alternatives considered

1. **Expose a sanitized runtime profile to modules.** Rejected as the primary design because modules would still own credential-availability logic and Core Fal pricing would remain a special escape path.
2. **Have modules call `CoreProviderFacade` for every provider operation.** Rejected for this migration because it would duplicate/replace the mature WorkerThread orchestration, journal and retry stack.
3. **Create a second image scheduler.** Rejected because it adds lifecycle and paid-call risk without product benefit.

The chosen gateway is a compatibility boundary: it centralizes secret ownership now while preserving the proven execution engine underneath.