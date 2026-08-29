# Clipart Generator project workflow

## Branches

- `develop/3.0` is the development and integration branch.
- `codex/fix-pinterest-prompt-only` at the verified 3.0.7 checkpoint remains
  the frozen source candidate until it is explicitly integrated/released.
- After 3.0.7 is frozen and the owner approves the transition, create
  `develop/3.1` from the exact published 3.0.7 commit. All 3.1 implementation
  branches must start from current `develop/3.1`, not from an older 3.0 task
  branch. The 3.1 PRD/docs alone do not authorize this branch creation.
- `release/3.x` is the stabilization branch for release preparation.
- `main` is not part of routine 3.0 development.
- Create task branches from the current development branch for the target
  release (`develop/3.0` now; `develop/3.1` only after the approved transition):
  - `codex/fix-*` for bug fixes;
  - `codex/ui-*` for visual or usability changes;
  - `codex/license-*` for licensing and registration;
  - `codex/feature-*` for other features.

## Safe task flow

- Before work, verify the branch is current and the working tree is clean or clearly document existing changes.
- Keep unrelated tasks in separate branches.
- Do not modify `release/3.x` during routine development.
- Before commit, show the diff and test results.
- After showing the completed diff and verification results, the main agent may
  commit and push the current task branch without requesting separate approval.
- Merge, branch deletion, tag deletion, and worktree removal still require
  explicit user approval.
- Never dispatch GitHub Actions or start local/GitHub builds without a separate
  explicit user command. An ordinary push must not trigger a build workflow.
- Merge completed task branches into the active target development branch one
  at a time and verify after each merge.
- Update `release/3.x` only after the candidate is stable and explicitly approved.

## Important project boundaries

- Do not expose secrets or read `.env` contents.
- Preserve releases, tags, version files, workflow files, and user data unless the task explicitly includes them.
- The updates repository is private and is not the active update delivery channel until a new delivery design is approved.

## VDS-first workflow

- Ubuntu VDS is the primary development environment; Windows is reserved for Windows-specific and visual verification.
- GitHub is the handoff point. Only one machine may edit the active branch at a time.
- Before handing work to the other machine, run the relevant checks, commit, and push. The receiving machine must use `git fetch` and `git pull --ff-only`.
- Never copy working files directly between machines and never run two independent editing sessions on the same branch.
- Use `scripts/bootstrap_vds.sh` only for environment setup and safe baseline checks. It must not install secrets, alter SSH/firewall settings, start production workers, or deploy.
- The main agent owns planning, integration, final tests, review, commit, and push. Subagents must not edit the same files in parallel.
