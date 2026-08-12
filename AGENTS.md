# Clipart Generator project workflow

## Branches

- `develop/3.0` is the development and integration branch.
- `release/3.x` is the stabilization branch for release preparation.
- `main` is not part of routine 3.0 development.
- Create task branches from the current `develop/3.0`:
  - `codex/fix-*` for bug fixes;
  - `codex/ui-*` for visual or usability changes;
  - `codex/license-*` for licensing and registration;
  - `codex/feature-*` for other features.

## Safe task flow

- Before work, verify the branch is current and the working tree is clean or clearly document existing changes.
- Keep unrelated tasks in separate branches.
- Do not modify `release/3.x` during routine development.
- Before commit, show the diff and test results.
- Commit, push, merge, branch deletion, tag deletion, and worktree removal require explicit user approval.
- Merge completed task branches into `develop/3.0` one at a time and verify after each merge.
- Update `release/3.x` only after the candidate is stable and explicitly approved.

## Important project boundaries

- Do not expose secrets or read `.env` contents.
- Preserve releases, tags, version files, workflow files, and user data unless the task explicitly includes them.
- The updates repository is private and is not the active update delivery channel until a new delivery design is approved.
