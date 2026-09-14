# Workflow host boundary checkpoint

- Goal: built-in workflows no longer receive or import raw `AppShell`.
- Add explicit `WorkflowHost` with a mode-scoped `WorkflowStateView`.
- Keep controller discovery/registration generic through `workflow_controller(module_id)`.
- Do not expose MainWindow, WorkerThread, credentials, or a generic service locator.
- Preserve existing navigation, run queue, evidence center, and UI behavior.
- Dependency graph remains Core→module = 0 and module→module = 0.
- Rollback boundary: this commit only; no data/schema migration.
- Verification: architecture guard, focused flow/evidence tests, full isolated suite.
