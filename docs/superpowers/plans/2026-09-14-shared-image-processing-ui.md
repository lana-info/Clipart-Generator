# Shared Image Processing UI

Goal: remove Clipart/Pinterest dependencies on the Processing module while preserving the existing image-processing editor behavior.

- Extract `ProcessingPipelineEditor`, operation-step helpers, SynthID-disabled UI, and shared cleanup metadata into `v3_image_processing_ui.py`.
- Keep Processing recipes and `ProjectState.processing` mutation in `v3_processing_editor.py`.
- Preserve old imports through compatibility re-exports.
- Clipart, Pinterest, and Processing consume the same shared Core UI contract.
- No UI layout/copy changes, paid calls, migrations, builds, or deploys.
- Rollback boundary: this commit only.
