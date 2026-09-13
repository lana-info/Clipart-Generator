# A4 Asset Handoff Implementation Plan

**Goal:** Introduce a Core-owned immutable inter-module asset handle without adding another asset store or exposing filesystem paths.

**Architecture:** Keep `AssetStore` as the single content-addressed byte store. Add a stdlib-only public `AssetHandle v1` contract containing only portable immutable metadata. Core bridges existing `AssetRecord` to/from handles and re-verifies bytes on every resolve. The handle has no source-module runtime dependency and remains usable when original files or source module packages are absent.

**Constraints:** no UI change, no new storage stack, no absolute path in public handle, no source-module class references, no paid/network calls, no build/deploy/merge.

## A4.1 Public AssetHandle v1
- RED: public asset API absent.
- Define strict immutable schema/version/id/hash/size/filename/media-type contract.
- No `path`, module implementation object, provider object, or mutable metadata.
- Add architecture guard: public asset API imports stdlib only.

## A4.2 Existing AssetStore bridge
- Convert verified AssetRecord -> AssetHandle without moving bytes.
- Resolve AssetHandle through existing store integrity checks.
- Tampered/mismatched handles fail closed.
- Original imported file may be deleted; Core stored bytes remain readable.
- Store restart preserves handle usability.

## Verification
- Existing asset tests + handoff tests + dependency guard.
- Full isolated pytest, py_compile, diff check.
- One rollbackable `[skip ci]` checkpoint commit.
