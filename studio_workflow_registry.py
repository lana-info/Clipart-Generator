"""Generic discovery for trusted built-in workflow compatibility adapters."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

_MODULE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
MAX_ENTRY_BYTES = 128 * 1024


class WorkflowRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowRegistration:
    module_id: str
    install: Callable[..., object]

    def __post_init__(self) -> None:
        if not isinstance(self.module_id, str) or not _MODULE_ID.fullmatch(self.module_id):
            raise WorkflowRegistryError("Invalid workflow module id")
        if not callable(self.install):
            raise WorkflowRegistryError("Workflow installer must be callable")


class WorkflowRegistry:
    __slots__ = ("_registrations",)

    def __init__(self, registrations=()) -> None:
        result: dict[str, WorkflowRegistration] = {}
        for registration in tuple(registrations):
            if not isinstance(registration, WorkflowRegistration):
                raise WorkflowRegistryError("Invalid workflow registration")
            if registration.module_id in result:
                raise WorkflowRegistryError("Duplicate workflow module id")
            result[registration.module_id] = registration
        self._registrations: Mapping[str, WorkflowRegistration] = MappingProxyType(result)

    @property
    def module_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._registrations))

    def require(self, module_id: str) -> WorkflowRegistration:
        try:
            return self._registrations[module_id]
        except (KeyError, TypeError) as exc:
            raise WorkflowRegistryError("Workflow module is not registered") from exc


def _load_entry(path: Path) -> WorkflowRegistration:
    if path.is_symlink() or not path.is_file():
        raise WorkflowRegistryError("Workflow entry must be a regular file")
    try:
        if path.stat().st_size > MAX_ENTRY_BYTES:
            raise WorkflowRegistryError("Workflow entry exceeds size limit")
        source = path.read_text(encoding="utf-8")
        namespace = {
            "__name__": f"_studio_builtin_{path.parent.name}",
            "__file__": str(path),
        }
        exec(compile(source, str(path), "exec"), namespace, namespace)
        return WorkflowRegistration(namespace.get("MODULE_ID"), namespace.get("install"))
    except WorkflowRegistryError:
        raise
    except Exception as exc:
        raise WorkflowRegistryError("Workflow entry could not be loaded") from exc


def discover_workflows(root: str | Path) -> WorkflowRegistry:
    base = Path(root)
    if base.is_symlink() or not base.is_dir():
        raise WorkflowRegistryError("Workflow registry root is unavailable")
    registrations = []
    try:
        children = sorted(base.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        raise WorkflowRegistryError("Workflow registry root cannot be read") from exc
    for child in children:
        if child.name.startswith(".") or child.is_symlink() or not child.is_dir():
            continue
        entry = child / "entry.py"
        if entry.exists() or entry.is_symlink():
            registrations.append(_load_entry(entry))
    return WorkflowRegistry(registrations)


__all__ = [
    "WorkflowRegistration", "WorkflowRegistry", "WorkflowRegistryError", "discover_workflows",
]
