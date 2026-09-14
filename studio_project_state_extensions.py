"""Generic extension hooks for legacy monolithic V3 project-state compatibility."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class ProjectStateExtension(Protocol):
    def normalize_state(self, state: dict[str, Any]) -> dict[str, Any]: ...
    def before_replace(self, destination: Path, state: dict[str, Any], *, max_bytes: int) -> None: ...


def _extension_tuple(extensions) -> tuple[ProjectStateExtension, ...]:
    result = tuple(extensions or ())
    for extension in result:
        if not callable(getattr(extension, "normalize_state", None)):
            raise TypeError("Project state extension must define normalize_state")
        if not callable(getattr(extension, "before_replace", None)):
            raise TypeError("Project state extension must define before_replace")
    return result


def normalize_project_state(
    state: dict[str, Any],
    extensions=(),
) -> dict[str, Any]:
    if not isinstance(state, dict):
        raise TypeError("Project state must be an object")
    try:
        current = json.loads(json.dumps(state, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ValueError("Project state must contain JSON values only") from exc
    for extension in _extension_tuple(extensions):
        current = extension.normalize_state(current)
        if not isinstance(current, dict):
            raise ValueError("Project state extension returned invalid state")
    return current


def before_project_state_replace(
    destination: Path,
    state: dict[str, Any],
    *,
    max_bytes: int,
    extensions=(),
) -> None:
    for extension in _extension_tuple(extensions):
        extension.before_replace(Path(destination), state, max_bytes=max_bytes)


__all__ = [
    "ProjectStateExtension", "before_project_state_replace", "normalize_project_state",
]
