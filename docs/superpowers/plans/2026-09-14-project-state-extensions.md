# Project state extension checkpoint

Goal: remove Core imports of Clipart recipe/export-membership persistence while preserving legacy V3 project compatibility.

- Core stores Clipart recipe/membership as opaque JSON.
- Built-in workflow registry exposes optional generic project-state extensions.
- Clipart owns semantic validation, migration, and pre-replace backup hooks.
- Production V3 project store and legacy draft paths use the same registry-provided extensions.
- Missing extension leaves opaque module data generic; Core does not mutate it.
- Unknown/newer project document behavior remains fail-closed in ProjectDocumentService.
- No UI, paid-call, build, deploy, or release behavior changes.

Rollback boundary: this commit only; no data-format version bump.