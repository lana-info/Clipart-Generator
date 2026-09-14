# A5 Dynamic Workflow Registry and Shell Bridge Plan

**Goal:** Remove direct Core imports and controller-name switches for existing workflows while preserving current UI/behavior.

**Architecture:** Discover trusted built-in workflow adapters generically from `studio_builtin_workflows/<module>/entry.py`. Entry modules expose only `MODULE_ID` and a uniform `install(...)` callable; they lazily import their own implementation. Core registry knows no Clipart/Pinterest/Processing names. AppShell tracks installed controllers by module ID instead of hard-coded attributes.

**Constraints:** compatibility bridge only; no new UI, no ProjectMode schema change, no module_runtime_v2, no build/deploy/paid calls.

## Tasks
- RED: arbitrary temp fixture workflow must discover without Core changes.
- RED: `v3_mode_selection.py` must not import concrete flow modules.
- Add strict WorkflowRegistry/discovery with duplicate/invalid entry rejection.
- Add built-in compatibility entries for current three flows; lazy implementation imports stay in module layer.
- Replace Core installer/attribute mappings with registry lookup.
- Make AppShell controller tracking generic by module ID.
- Preserve existing controllers, routes, locale behavior, autosave, and worker lifecycle.
- Extend dependency guard to scan built-in adapter package and remove obsolete Core->module allowlist edges.
