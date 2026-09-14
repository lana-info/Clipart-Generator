# Module-owned run results checkpoint

Goal: remove the final Core-to-Clipart dependencies from `v3_run_queue`.

- Core owns queue/session/lifecycle, trusted output paths, and result-page signals.
- Optional `RunResultsExtension` receives only state, session, export paths, and narrow callbacks.
- Clipart owns membership migration, bundle planning, alpha QC, and Set Export UI.
- Generic/Processing/Pinterest result pages do not receive the Clipart extension.
- Explicit edited-output adoption remains Core-owned; module hook only migrates module metadata.
- Existing alpha-QC and bundle semantics remain unchanged.
- No paid-call, job-recovery, build, deploy, release, or visual behavior changes.

Rollback boundary: this commit only.