# Workflow Boundary Review Remediation

**Review base:** `35ff5f729b8413a335a5b393b9fee6799024dbb7`

## Goal
Close the independent-review P1/P2 findings without changing user-visible workflow behavior.

## Boundary fixes
- Make `WorkflowHost` a plain narrow facade with only a weak shell reference; no QObject parent chain.
- Scope common output path and current step to the owning workflow mode.
- Require `WorkflowHost` at built-in installers; raw `AppShell` fails closed.
- Make Processing recipe and Clipart Builder consume mode-owned data.
- Keep raw legacy `WorkerThread` inside Core behind `CoreWorkerJobHandle`.
- Remove built-in access to `runtime_adapter.create_worker` and raw worker creation.

## Rollback and verification
No UI layout/copy change, build, deploy, paid call, release, or merge is part of this checkpoint.
Rollback is the single remediation commit. Verify architecture guards, packaged smoke, focused workflow tests, and the full isolated suite before commit.
