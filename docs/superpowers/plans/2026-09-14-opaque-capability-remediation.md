# Opaque Capability Remediation

Baseline checkpoint: `87e22a505ce97a91de520814083144eefc2fcbf8`.

This increment closes the second workflow-boundary review findings without using
Python name-mangling as an isolation mechanism.

- Raw AppShell/ProjectState stay in Core-owned capability storage.
- WorkflowHost/state/common objects carry only opaque ids plus allowed mode data.
- Raw legacy workers stay in Core-owned worker storage.
- CoreWorkerJobHandle carries only an opaque id and narrow lifecycle/events.
- Built-in installers receive no Core bound callbacks or closures.
- Retry uses the same Core authorization/save/worker path as initial launch.
- Capability entries release when their shell/worker lifecycle ends.

Rollback boundary: revert this commit to restore the prior in-process facades;
project documents, assets, provider journals and user data are not migrated.
