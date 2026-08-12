# VDS workflow

## Fixed project facts

- Repository: `https://github.com/lana-info/Clipart-Generator.git`
- Working branch: `develop/3.0`
- Recommended path: `~/projects/clipart-generator`
- Development authority: Ubuntu VDS
- Windows role: Windows-specific and visual verification
- Handoff authority: GitHub

## First clone and bootstrap

Private-repository access must already be configured through the user's SSH agent or an approved GitHub credential helper. Never put a token in a command, file, or prompt.

```bash
mkdir -p ~/projects
git clone --branch develop/3.0 git@github.com:lana-info/Clipart-Generator.git ~/projects/clipart-generator
cd ~/projects/clipart-generator
bash scripts/bootstrap_vds.sh
```

The bootstrap creates or reuses `.venv`, installs `requirements.txt`, checks Git/Python/curl/tmux/Codex/custom agents, and runs only compile plus network-free baseline tests. It does not configure SSH/firewall, install secrets, start workers, deploy, or make paid API calls.

## Start Codex

```bash
cd ~/projects/clipart-generator
codex
```

For a persistent session:

```bash
tmux new -s clipart-codex
cd ~/projects/clipart-generator
codex
# detach: Ctrl-b, then d
tmux attach -t clipart-codex
```

Use the repository `AGENTS.md`, `PROJECT.md`, `STATE.md`, and `.codex/agents/`. The main agent owns planning, integration, tests, review, commit, and push.

## Synchronize from GitHub

Only do this when Windows has handed the branch back and the VDS working tree is clean:

```bash
git fetch origin
git pull --ff-only origin develop/3.0
```

Never use reset, force push, automatic rebase, or `git clean` as a synchronization shortcut.

## Checkpoint and handoff VDS -> Windows

```bash
git status --short
python -m py_compile main.py
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
git add <reviewed-files>
git commit -m "Describe the completed checkpoint"
git push origin develop/3.0
```

After push, Windows updates only through `git fetch` and `git pull --ff-only`. Do not copy the working directory or edit the branch on both machines.

## Handoff Windows -> VDS

Windows runs the relevant Windows-specific or visual checks, then commits and pushes the reviewed result. VDS then runs:

```bash
cd ~/projects/clipart-generator
git fetch origin
git pull --ff-only origin develop/3.0
bash scripts/bootstrap_vds.sh
```

## Operating rules

- One active editor and one active worktree for the branch at a time.
- Keep `.env`, API keys, credentials, user configs, generated images, model files, build outputs, and release installers outside Git.
- Windows-only failures are recorded as platform-specific blockers; they do not justify weakening Linux-safe tests.
- Do not start release/build/publication work or paid provider calls without separate explicit approval.
