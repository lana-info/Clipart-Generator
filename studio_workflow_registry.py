"""Generic discovery for trusted built-in workflow compatibility adapters."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from studio_module_api import ModuleApiError, ModuleContext, ModuleRegistration

MAX_ENTRY_BYTES = 128 * 1024
BUILTIN_WORKFLOW_VERSION = "1.0.0"


class WorkflowRegistryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowRegistration:
    module: ModuleRegistration
    install: Callable[..., object]

    def __post_init__(self) -> None:
        if not isinstance(self.module, ModuleRegistration):
            raise WorkflowRegistryError("Invalid public module registration")
        if not callable(self.install):
            raise WorkflowRegistryError("Workflow installer must be callable")

    @property
    def module_id(self) -> str:
        return self.module.module_id


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
        context = ModuleContext(path.parent.name, BUILTIN_WORKFLOW_VERSION)
        source = path.read_text(encoding="utf-8")
        namespace = {"__name__": f"_studio_builtin_{path.parent.name}", "__file__": str(path)}
        exec(compile(source, str(path), "exec"), namespace, namespace)
        register = namespace.get("register")
        install = namespace.get("install")
        if not callable(register):
            raise WorkflowRegistryError("Workflow entry must export register(context)")
        module = register(context)
        if not isinstance(module, ModuleRegistration):
            raise WorkflowRegistryError("Workflow register(context) returned invalid registration")
        if module.module_id != context.module_id or module.version != context.version:
            raise WorkflowRegistryError("Workflow registration identity mismatch")
        return WorkflowRegistration(module, install)
    except WorkflowRegistryError:
        raise
    except ModuleApiError as exc:
        raise WorkflowRegistryError("Invalid workflow module registration") from exc
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
    "BUILTIN_WORKFLOW_VERSION", "WorkflowRegistration", "WorkflowRegistry",
    "WorkflowRegistryError", "discover_workflows",
]
