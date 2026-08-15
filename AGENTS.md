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
- After showing the completed diff and verification results, the main agent may
  commit and push the current task branch without requesting separate approval.
- Merge, branch deletion, tag deletion, and worktree removal still require
  explicit user approval.
- Never dispatch GitHub Actions or start local/GitHub builds without a separate
  explicit user command. An ordinary push must not trigger a build workflow.
- Merge completed task branches into `develop/3.0` one at a time and verify after each merge.
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
