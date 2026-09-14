# A6 Provider and Job Facades Implementation Plan

**Goal:** Expose scoped provider/job capabilities without exposing secrets, transports, WorkerThread, or bypasses around paid-call protections.

**Architecture:** Public DTO/protocol modules contain no provider implementations. Core facades own preflight and literal authorization and delegate exactly once to a protected executor whose contract explicitly owns credentials, task journal/idempotency, resume semantics, and no-silent-retry. Jobs reuse ModuleRuntimeHost job leases and Core-registered launchers rather than adding a scheduler.

**Constraints:** no network/paid calls, no provider_v2/jobs_v2, no raw API keys in public contracts, no module-provided launch callbacks, no UI change.

## A6.1 Provider/jobs contracts
- RED public provider request contains no credential/approval fields.
- RED paid facade refuses submission before literal Core authorization.
- RED facade performs one protected execution attempt and never retries uncertain submission.
- RED job service accepts operation IDs only, owns runtime lease, and releases on Core completion callback.
- Add dependency guards for public API modules.

## A6.2 Extended text probe
- Add projects.v1 scoped capability over ProjectDocumentService.
- Text fixture declares projects.v1/providers.text.v1/jobs.v1 and a non-Qt page declaration.
- End-to-end test: signed module binds all three scoped capabilities, creates/opens its own note document, runs fake protected text operation, and uses a Core-owned job launcher.
- Verify the fixture imports only public API modules and no image/provider implementation stack.

## Verification
- Focused contract/runtime/project tests, py_compile, git diff --check, full isolated pytest.
- Separate [skip ci] commits for A6.1 and A6.2.
