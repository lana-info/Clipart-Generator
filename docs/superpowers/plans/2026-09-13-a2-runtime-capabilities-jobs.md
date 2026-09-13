# A2 Runtime Capabilities and Job Leases Implementation Plan

**Goal:** Scope negotiated module capabilities and make runtime lifecycle honor real long-running jobs without adding a second scheduler/provider stack.

**Architecture:** Keep ModuleRuntimeHost and ModuleStore. Registration remains declaration-only; after exact capability negotiation, a host-side CapabilityBroker creates module-scoped contracts and an optional bind phase receives only those declared bindings. Separately, host-owned job leases extend the existing page/callback lifetime rules, and ModuleStore exposes a rollback-safe activation transaction instead of runtime calling private state writers.

**Constraints:** baseline 8ff2c54; branch codex/refactor-studio-module-api-3.2; no UI change, build, deploy, paid call, merge, release/version metadata change, `.env` read, or new provider/scheduler system.

## A2.1 Scoped capability binding
- RED: text probe declares providers.text.v1 but cannot receive a contract yet.
- Add immutable public ModuleCapabilities/ModuleCapabilityContext, not Mapping and no string lookup.
- Add host-side CapabilityProvider/CapabilityBroker with exact requirement + module-scoped factory.
- Runtime order: register -> validate identity -> negotiate exact requirements -> scope bindings -> optional bind -> publish.
- Bind failure must fail activation and preserve previous registration/store pointer.
- Extend text probe so its command uses the scoped fake text contract.
- Contract tests prove undeclared capability access fails and provider factory receives module_id.

## A2.2 Lifecycle leases and activation transaction
- RED: external long-running job can currently outlive command callback without blocking unload/update.
- Add host-owned job lease; active lease blocks activate/unload until closed.
- Lease release must be safe for worker completion without exposing host internals to modules.
- Add public ModuleStore activation transaction that restores exact prior pointer/state on exception.
- Runtime stops calling ModuleStore._write_state directly.
- Existing package integrity, authorization, page leases, and synchronous command behavior stay unchanged.

## Verification
- Focused module/runtime/store/Pinterest/dependency tests.
- py_compile and git diff --check.
- Full isolated pytest suite.
- Separate [skip ci] commit for A2.1 and A2.2; push feature branch only.
