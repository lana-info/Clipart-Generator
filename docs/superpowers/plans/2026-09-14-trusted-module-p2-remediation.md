# Trusted module P2 remediation

Checkpoint goal: close the two actionable findings from the review of `d755b3473531f142f02577fb8d915cb1746c1b9b` without turning the first-party same-process module model into a hostile-code sandbox.

## Changes

- Release Core worker capabilities on the real terminal signal. Workers with only `completed` release there; QThread-style workers with `finished` release on `finished`.
- Keep release idempotent and leave `stop()` / `isRunning()` safe after capability release.
- Repair deferred Pinterest selective regeneration with a real `PinterestPinRunRequest` and `PinterestPinWorkerAdapter` path.
- Split Core project save/admission from legacy WorkerThread construction so module-owned local workers can still fail closed on project-save failure.
- Preserve active Pinterest prompt-only behavior and existing paid-provider protections.
- Record the accepted trusted first-party module model in ADR-004 and the 3.2 PRD.