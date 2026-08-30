# Clipart Generator project workflow

## Branches

- `develop/3.1` is the current development and integration branch for 3.1.0.
- `develop/3.0` and `codex/fix-pinterest-prompt-only` remain frozen historical
  3.0.x lines and are not implementation bases for current work.
- All 3.1 implementation branches start from synchronized `develop/3.1`, not
  from an older 3.0 task or release-candidate branch.
- `release/3.x` is the stabilization branch for release preparation.
- `main` is not part of routine development.
- Create task branches from the current development branch for the target
  release (`develop/3.1` for current 3.1 work):
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

## Mandatory visual approval gate

- Before coding any new or materially redesigned user-visible page, section,
  dialog, result view, editor or control group, first show the owner a visual
  mockup. A PRD/task approval does not approve the later UI automatically.
- Before the mockup, restate in plain language what is changing, why, what stays
  unchanged and which user action the screen must support.
- The mockup must use the actual Vibix dark visual language and show the full
  screen context rather than an isolated control when surrounding layout affects
  understanding. The supported acceptance target is 1120×780 at 100% Windows
  display scaling. Smaller windows and scaling above 100% are best-effort and
  may use internal scrolling; they do not block release while all controls stay
  reachable. Remote-desktop use is unsupported and outside acceptance. Early
  alternatives may be rough, but the version submitted for final approval must
  be visually close to the intended implementation, not only a text diagram.
- Show all materially different states before implementation: default/empty,
  enabled or populated, relevant provider/model choice, validation/error, and
  disabled/hidden behavior where applicable. For a redesign, include a clear
  current-versus-proposed comparison.
- Explain interactions and conditional visibility next to the mockup. Revise the
  visual as many times as needed. Do not edit implementation source until the
  owner explicitly says that the mockup is approved.
- If implementation discovers a visual change not present in the approved
  mockup, stop and obtain approval for the revised visual before continuing.
- After implementation, capture the real screen in the same important states
  and compare it with the approved mockup before declaring the UI task complete.
- Save the approved mockup and final comparison in the task-specific design
  artifacts under `docs/ui/3.1/<task-id>/` using only safe dummy content; link
  them from the task/spec so a later session can recover the exact approval.
- Purely internal or non-visual fixes do not require a mockup, but still require
  a short description of the intended behavior and approval before source edits.

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
