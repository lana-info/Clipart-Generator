# Module Install/Update Lifecycle Implementation Plan

**Goal:** Complete the existing signed-module lifecycle without creating parallel package, entitlement, or data systems.

**Architecture:** Keep `ModuleStore` as signed package inventory and `ModuleRuntimeHost` as the live-code owner. `ModuleLifecycleService` composes authorization, entitlement, staging, activation, disable, uninstall, and catalog availability while user projects/assets remain outside ModuleStore.

## Constraints
- Work only on `codex/refactor-studio-module-api-3.2` from baseline `8ff2c54f256ae35392e9374c9ba91619493764ff`.
- No build, deploy, paid API calls, workflow dispatch, merge, release/version mutation, or `.env` reads.
- Staging may happen while a module is busy; activation/disable/uninstall must respect host page/job leases.
- Entitlement, installed package state, active/enabled state, and user data remain distinct.
- Disable/uninstall never delete projects or assets.
- Package identity is reverified between inspection/authorization and staging.