#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${PROJECT_ROOT}/.venv"
failures=()

say() { printf '\n[bootstrap] %s\n' "$*"; }
fail() { failures+=("$*"); printf '[bootstrap][FAIL] %s\n' "$*" >&2; }

say "Project: ${PROJECT_ROOT}"
if [[ "$(uname -s)" != "Linux" ]]; then fail "Linux is required; detected $(uname -s)."; fi
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  say "Distribution: ${PRETTY_NAME:-${ID:-unknown}}"
else
  fail "Cannot identify the Linux distribution (/etc/os-release is missing)."
fi

for command_name in git python3 curl tmux; do
  if command -v "${command_name}" >/dev/null 2>&1; then
    printf '[bootstrap][OK] %s: %s\n' "${command_name}" "$(command -v "${command_name}")"
  else
    fail "Required command is missing: ${command_name}"
  fi
done

if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
  say "Creating or reusing the project virtual environment"
  if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
    python3 -m venv "${VENV_DIR}" || fail "Could not create ${VENV_DIR}; install the Python venv package."
  fi
  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    "${VENV_DIR}/bin/python" -m pip install --upgrade pip
    "${VENV_DIR}/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements.txt"
  fi
else
  fail "requirements.txt is missing."
fi

if command -v codex >/dev/null 2>&1; then
  printf '[bootstrap][OK] codex: %s\n' "$(codex --version 2>&1 || true)"
else
  fail "Codex CLI is not available in PATH; install/authenticate it outside the repository."
fi

if [[ -d "${PROJECT_ROOT}/.codex/agents" ]]; then
  agent_count="$(find "${PROJECT_ROOT}/.codex/agents" -maxdepth 1 -type f -name '*.toml' | wc -l | tr -d ' ')"
  printf '[bootstrap][OK] project custom agents: %s\n' "${agent_count}"
else
  fail "Project custom-agent directory is missing."
fi

say "Running safe baseline checks"
(
  cd "${PROJECT_ROOT}"
  "${VENV_DIR}/bin/python" -m py_compile main.py
  QT_QPA_PLATFORM=offscreen "${VENV_DIR}/bin/python" -m unittest discover -s tests -v
)

say "Bootstrap summary"
if ((${#failures[@]})); then
  printf '[bootstrap][FAIL] %s issue(s):\n' "${#failures[@]}" >&2
  printf ' - %s\n' "${failures[@]}" >&2
  exit 1
fi
printf '%s\n' '[bootstrap][OK] Environment, project agents, dependencies, and baseline tests are ready.'
