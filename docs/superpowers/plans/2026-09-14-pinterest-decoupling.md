# Pinterest Decoupling Implementation Plan

**Goal:** Remove Pinterest dependencies on Clipart implementation internals while preserving the current prompt-only workflow and Clipart compatibility API.

**Architecture:** Extract genuinely shared prompt-image runtime and UI primitives into neutral Core-owned modules with two consumers: Clipart and Pinterest. Keep Clipart public symbols as thin wrappers/aliases so existing callers and saved-project behavior remain unchanged.

## Boundaries
- `v3_image_generation_runtime.py`: shared model options, request validation/building, cost/preflight helpers and Fal quantities.
- `v3_image_generation_ui.py`: data-oriented generation settings page.
- `v3_prompt_editor_ui.py`: data-oriented prompt input/review and helper dialogs.
- `v3_image_review_ui.py`: shared review/run presentation.
- `v3_flow_ui.ProjectDirectoryPage`: shared work-directory page.
- Pinterest imports none of `v3_clipart_flow`; Clipart wrappers preserve existing names and behavior.

## Safety
- No UI redesign, build, deploy, paid API calls, merge, release/version mutation or `.env` reads.
- Existing cost/preflight/provider protections remain in existing runtime paths.
- Exact dependency allowlist removes Pinterest→Clipart and adds only reviewed module→shared-Core edges.
- Rollback boundary is the single Pinterest-decoupling checkpoint commit.