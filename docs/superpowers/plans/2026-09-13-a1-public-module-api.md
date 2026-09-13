# A1 Public Module API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use test-driven development for each contract change.

**Goal:** Introduce a small versioned public Studio Module API and prove, with a text-oriented signed fixture module, registration plus capability negotiation without Clipart/image dependencies.

**Architecture:** Extract module-authored declarations from `studio_module_runtime.py` into `studio_module_api.py`. Modules declare exact versioned capability requirements; the runtime negotiates those requirements against an explicit typed set of supported capabilities before publishing a registration. A1 does not expose provider keys, services, jobs, UI shell objects, or a generic service locator.

**Tech Stack:** Python 3.12, dataclasses, stdlib typing/re, existing signed `ModuleStore`/`ModuleRuntimeHost`, pytest.

**Spec:** Owner-approved Option A and 2026-09-13 refinements; A0 commit `b470497fb4b1aac48afe3c844283712a35220ded`.

## Global Constraints

- Baseline ancestry remains `8ff2c54f256ae35392e9374c9ba91619493764ff`.
- Work only in `studio-module-api-worktree`; do not modify `studio-3.2-worktree`.
- No build, deploy, paid API call, workflow dispatch, merge, release/version change, or `.env` read.
- Public API must not import Clipart, Pinterest, Processing, Patterns, Qt shell, WorkerThread, provider implementations, credential stores, or image libraries.
- UI is optional: a valid module may register zero pages.
- `module_id` is the v1 entitlement identifier; no parallel licensing identity is introduced.
- Capability requirements are exact `name + version` values and fail closed when unsupported.
- `providers.text.v1` is declarative only in A1; raw provider access remains unavailable to modules.

---
### Task 1: RED — define the public API contract

**Files:**
- Create: `tests/test_studio_module_api.py`
- Create later: `studio_module_api.py`

**Interfaces:**
- Produces: `MODULE_API_VERSION`, `ModuleApiError`, `CapabilityRequirement`, `CommandDeclaration`, `PageDeclaration`, `DocumentTypeDeclaration`, `ModuleRegistration`, `ModuleContext`.
- `CapabilityRequirement(name: str, version: int)` uses names such as `providers.text` and exposes key `providers.text.v1`.
- `ModuleRegistration.module_id` is also the v1 entitlement identifier.

- [ ] Write tests that import the not-yet-existing public API and therefore fail.
- [ ] Specify strict capability-name/version validation and duplicate-name rejection.
- [ ] Specify a registration with zero pages and no image concepts.
- [ ] Specify that public `ModuleContext` exposes identity only and has no `services` mapping.
- [ ] Run focused tests and confirm RED is caused by the missing API.

### Task 2: GREEN — extract declarations without changing runtime behavior

**Files:**
- Create: `studio_module_api.py`
- Modify: `studio_module_runtime.py`
- Test: `tests/test_studio_module_api.py`
- Regression: `tests/test_studio_module_runtime.py`

- [ ] Implement only the tested public declarations and validation.
- [ ] Make runtime consume/re-export the public declarations for source compatibility.
- [ ] Keep runtime-only `ModuleInfo`, page leases, import verification, authorization, and package lifecycle private to runtime.
- [ ] Preserve current legacy runtime services internally; do not expose them through public `ModuleContext`.
- [ ] Run public API and existing runtime tests GREEN.

### Task 3: RED/GREEN — negotiate declared capabilities before registration publish

**Files:**
- Modify: `tests/test_studio_module_runtime.py`
- Modify: `studio_module_runtime.py`

**Interfaces:**
- `ModuleRuntimeHost(..., supported_capabilities: Collection[CapabilityRequirement] | None = None)`.
- Registration is rejected before publication when any required capability is absent or only another version is supported.

- [ ] Add a failing signed-package test requiring `providers.text.v1`.
- [ ] Prove no capability set and `providers.text.v2` both fail closed.
- [ ] Prove exact `providers.text.v1` succeeds.
- [ ] Implement negotiation as exact typed requirements, not `Mapping[str, Any]`.
- [ ] Verify failed negotiation leaves no published registration and does not change the active package pointer unexpectedly.

### Task 4: Text-oriented architecture probe

**Files:**
- Create: `tests/fixtures/studio_modules/text_probe/entry.py`
- Create/modify: `tests/test_studio_module_api.py`

**Interfaces:**
- Fixture declares module/entitlement id `text-probe`.
- Fixture requires only `providers.text.v1`.
- Fixture registers a text document type and synchronous text-only command; it registers no UI page.

- [ ] Package/sign the fixture in test code and load it with existing ModuleStore/ModuleRuntimeHost.
- [ ] Assert the fixture source imports only `studio_module_api` from project code.
- [ ] Assert no Clipart/image/provider-implementation/Qt imports occur.
- [ ] Assert unsupported capability fails and supported capability registers/executes.
- [ ] Do not add the fixture to the production catalog or product UI.

### Task 5: Dependency guardrail integration and checkpoint

**Files:**
- Modify: `tests/test_studio_dependency_architecture.py`
- Test: `tests/test_studio_module_api.py`
- Test: `tests/test_studio_module_runtime.py`

- [ ] Classify `studio_module_api` as the public API boundary rather than ordinary Core internals.
- [ ] Permit the intended dependency direction into the public API without adding those edges to the legacy allowlist.
- [ ] Assert the public API itself has no project-local imports and therefore cannot depend on module/image internals.
- [ ] Keep the 82-edge A0 legacy list exact except for edges actually removed by A1.
- [ ] Run focused API/runtime/dependency tests, compilation, full isolated pytest, and `git diff --check`.
- [ ] Recheck `studio-3.2-worktree` remains clean at `8ff2c54`.
- [ ] Commit/push the independently rollbackable A1 checkpoint with `[skip ci]`.

**Core API consumers:** Module registration/API: current Pinterest adapter plus text probe, later Clipart/Patterns. `providers.text.v1` requirement: Clipart AI planning and future Etsy SEO/text modules; A1 only negotiates the declaration.

**Completion criterion:** a signed text-only fixture can register through the same runtime when and only when its exact declared capability version is supported, while importing no Clipart/image stack and receiving no public service-locator object.

**Rollback boundary:** revert only the A1 checkpoint commit; A0 remains intact.

**Visual approval:** not required; no user-visible UI changes.

**Owner decision:** none in A1. Provider execution, projects, assets, and license-service remain later approved increments.
