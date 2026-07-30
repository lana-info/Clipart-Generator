"""Pure, UI-independent launch input validation."""

from __future__ import annotations


def validate_inputs(run_mode: str, *, files: list[str], prompts: list[dict]) -> tuple[str, ...]:
    issues: list[str] = []
    if run_mode in {"process_only", "both"} and not files:
        issues.append("files_required")
    if run_mode in {"generate_only", "both"} and not prompts:
        issues.append("prompts_required")
    return tuple(issues)
