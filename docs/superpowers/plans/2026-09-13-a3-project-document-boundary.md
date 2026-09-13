# A3 Project and Document Boundary Implementation Plan

**Goal:** Make ProjectStore a generic Core persistence boundary with explicit document metadata and opaque module-owned state.

**Architecture:** Core owns only a bounded envelope: project_id, module_id, document_type, document_version, name, timestamp, and opaque JSON state. Envelope migration is Core-owned; document validation/migration is adapter-owned. Loading never imports a module or starts work. Missing modules leave data untouched; unsupported newer document versions are not silently overwritten.

**Constraints:** preserve existing projects, no paid calls, no UI redesign, no build/deploy/merge, no `.env` read. Existing V3 reopen must not start provider work.

## A3.1 Generic envelope
- Add envelope schema v2 with `document_type` and `document_version`.
- Keep `create/save` legacy-compatible through explicit default `project`/v1 metadata.
- Read schema-v1 files as legacy project/v1 without rewriting on load/recent.
- Preserve opaque state bytes semantically; Core validates only bounded JSON and generic secret exclusions.
- Prevent module/document identity changes and document-version downgrade on save.
- Keep unknown outer envelope schemas fail-closed.

## A3.2 Module adapter ownership
- Define a narrow document adapter contract outside ProjectStore storage mechanics.
- Move Clipart export-membership validation/migration backup out of generic ProjectStore.
- Legacy V3 adapter owns current ProjectState validation/migration behavior.
- Missing adapter permits Core metadata/result access but no opaque-state mutation.
- Newer unsupported document version opens fail-closed/read-only at adapter boundary.
- Preserve exact migration backup and old project compatibility tests.

## Verification
- Focused ProjectStore/ProjectState/export-membership/reopen tests.
- Dependency guard must remove `studio_projects -> studio_export_membership` rather than allow new debt.
- Full isolated pytest, py_compile, diff check.
- Separate [skip ci] commits for A3.1 and A3.2.
