"""Core-owned storage and dispatch for same-process workflow capabilities."""
from __future__ import annotations

import uuid
import weakref
from dataclasses import dataclass
from typing import Any

from v3_project_state import ProjectMode, StepId


_SIGNAL_NAMES = frozenset({
    "step_changed", "run_requested", "state_changed", "finish_requested",
})
_COMMON_FIELDS = frozenset({"project_name", "work_dir"})


@dataclass(slots=True)
class _WorkflowCapability:
    shell_ref: weakref.ReferenceType[Any]
    scope: ProjectMode
    runtime_settings_provider: Any = None
    worker_factory: Any = None
    authorization_provider: Any = None


_CAPABILITIES: dict[str, _WorkflowCapability] = {}


def _store_callback(callback):
    if callback is None:
        return None
    try:
        return weakref.WeakMethod(callback)
    except TypeError:
        return callback


def _load_callback(value, label: str):
    if isinstance(value, weakref.WeakMethod):
        callback = value()
        if callback is None:
            raise RuntimeError(f"Core {label} service is unavailable")
        return callback
    return value


def register_workflow_capability(
    shell: Any,
    module_id: str,
    *,
    runtime_settings_provider=None,
    worker_factory=None,
    authorization_provider=None,
) -> str:
    try:
        scope = ProjectMode(module_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Workflow capability scope is invalid") from exc
    token = uuid.uuid4().hex

    def release(_ref, *, capability_id=token) -> None:
        _CAPABILITIES.pop(capability_id, None)

    try:
        shell_ref = weakref.ref(shell, release)
    except TypeError as exc:
        raise TypeError("Workflow capability source must support weak references") from exc
    _CAPABILITIES[token] = _WorkflowCapability(
        shell_ref,
        scope,
        _store_callback(runtime_settings_provider),
        _store_callback(worker_factory),
        _store_callback(authorization_provider),
    )
    return token


def _resolve(capability_id: str) -> tuple[Any, ProjectMode]:
    entry = _CAPABILITIES.get(str(capability_id))
    if entry is None:
        raise RuntimeError("Workflow capability is unavailable")
    shell = entry.shell_ref()
    if shell is None:
        _CAPABILITIES.pop(str(capability_id), None)
        raise RuntimeError("Workflow capability is unavailable")
    return shell, entry.scope


def capability_scope(capability_id: str) -> ProjectMode:
    return _resolve(capability_id)[1]


def capability_tokens(capability_id: str):
    shell, _scope = _resolve(capability_id)
    return shell.tokens


def capability_mode_data(capability_id: str):
    shell, scope = _resolve(capability_id)
    return getattr(shell.state, scope.value)


def capability_runtime_data(capability_id: str):
    shell, _scope = _resolve(capability_id)
    return shell.state.runtime


def state_is_active(capability_id: str) -> bool:
    shell, scope = _resolve(capability_id)
    return shell.state.mode is scope


def state_current_step(capability_id: str) -> StepId:
    shell, scope = _resolve(capability_id)
    return shell.state.current_step_by_mode[scope]


def common_get(capability_id: str, field: str) -> str:
    if field not in _COMMON_FIELDS:
        raise ValueError("Workflow common field is not exposed")
    shell, _scope = _resolve(capability_id)
    return str(getattr(shell.state.common, field))


def common_set(capability_id: str, field: str, value: str) -> None:
    if field not in _COMMON_FIELDS:
        raise ValueError("Workflow common field is not exposed")
    shell, _scope = _resolve(capability_id)
    setattr(shell.state.common, field, str(value))


def state_output_dir(capability_id: str) -> str:
    shell, scope = _resolve(capability_id)
    return shell.state.output_dir_for_mode(scope)


def state_set_output_dir(capability_id: str, value: str) -> None:
    shell, scope = _resolve(capability_id)
    shell.state.set_output_dir_for_mode(str(value), scope)


def state_set_step(capability_id: str, step: StepId | str) -> None:
    shell, scope = _resolve(capability_id)
    if shell.state.mode is not scope:
        raise ValueError("Workflow state operation is outside active module scope")
    shell.state.set_step(step)


def signal_connect(capability_id: str, name: str, callback) -> None:
    if name not in _SIGNAL_NAMES:
        raise ValueError("Workflow signal is not exposed")
    shell, _scope = _resolve(capability_id)
    getattr(shell, name).connect(callback)


def signal_disconnect(capability_id: str, name: str, callback=None) -> None:
    if name not in _SIGNAL_NAMES:
        raise ValueError("Workflow signal is not exposed")
    shell, _scope = _resolve(capability_id)
    signal = getattr(shell, name)
    if callback is None:
        signal.disconnect()
    else:
        signal.disconnect(callback)


def signal_emit(capability_id: str, name: str, *args) -> None:
    if name not in _SIGNAL_NAMES:
        raise ValueError("Workflow signal is not exposed")
    shell, _scope = _resolve(capability_id)
    getattr(shell, name).emit(*args)


def host_mark_dirty(capability_id: str) -> None:
    shell, _scope = _resolve(capability_id)
    shell.mark_dirty()


def host_refresh(capability_id: str) -> None:
    shell, _scope = _resolve(capability_id)
    shell.refresh()


def host_go_next(capability_id: str) -> None:
    shell, _scope = _resolve(capability_id)
    shell.go_next()


def host_show_results(capability_id: str) -> None:
    shell, _scope = _resolve(capability_id)
    shell.show_results()


def host_set_canvas_focus_mode(capability_id: str, enabled: bool) -> None:
    shell, _scope = _resolve(capability_id)
    shell.set_canvas_focus_mode(bool(enabled))


def host_another_run_is_active(capability_id: str, controller: object) -> bool:
    shell, _scope = _resolve(capability_id)
    return bool(shell.another_run_is_active(controller))


def host_workflow_definition(capability_id: str):
    shell, scope = _resolve(capability_id)
    return shell.workflow_definition(scope)


def host_set_workflow_factory(capability_id: str, step, factory) -> None:
    shell, scope = _resolve(capability_id)
    shell.set_workflow_factory(scope, step, factory)


def host_set_step_factory(capability_id: str, step, factory) -> None:
    shell, scope = _resolve(capability_id)
    shell.set_step_factory(scope, step, factory)


def host_set_step_page(capability_id: str, step, page) -> None:
    shell, scope = _resolve(capability_id)
    shell.set_step_page(scope, step, page)


def host_ensure_step_page(capability_id: str, step):
    shell, scope = _resolve(capability_id)
    return shell.ensure_step_page(scope, step)


def host_workflow_controller(capability_id: str):
    shell, scope = _resolve(capability_id)
    return shell.workflow_controller(scope.value)


def host_register_workflow_controller(capability_id: str, controller: object) -> None:
    shell, scope = _resolve(capability_id)
    shell.register_workflow_controller(scope.value, controller)


def has_diagnostic_journal(capability_id: str) -> bool:
    shell, _scope = _resolve(capability_id)
    return getattr(shell, "diagnostic_journal", None) is not None


def diagnostic_record(capability_id: str, *args, **kwargs):
    shell, _scope = _resolve(capability_id)
    journal = getattr(shell, "diagnostic_journal", None)
    if journal is None:
        return None
    return journal.record(*args, **kwargs)


def diagnostic_record_structured(capability_id: str, *args, **kwargs):
    shell, _scope = _resolve(capability_id)
    journal = getattr(shell, "diagnostic_journal", None)
    if journal is None:
        return None
    recorder = getattr(journal, "record_structured", None)
    return recorder(*args, **kwargs) if callable(recorder) else None


def host_runtime_settings(capability_id: str) -> dict[str, Any]:
    entry = _CAPABILITIES.get(str(capability_id))
    if entry is None:
        raise RuntimeError("Workflow capability is unavailable")
    provider = _load_callback(entry.runtime_settings_provider, "runtime settings")
    if provider is None:
        return {}
    value = provider()
    if not isinstance(value, dict):
        try:
            value = dict(value)
        except (TypeError, ValueError) as exc:
            raise TypeError("Core runtime settings provider returned invalid data") from exc
    return dict(value)


def host_authorize_run(capability_id: str):
    entry = _CAPABILITIES.get(str(capability_id))
    if entry is None:
        raise RuntimeError("Workflow capability is unavailable")
    authorize = _load_callback(entry.authorization_provider, "authorization")
    if authorize is None:
        from license_client import LicenseError
        raise LicenseError("Лицензионный сервис не настроен")
    return authorize()


def host_create_worker_job(capability_id: str, **kwargs):
    entry = _CAPABILITIES.get(str(capability_id))
    if entry is None:
        raise RuntimeError("Workflow capability is unavailable")
    factory = _load_callback(entry.worker_factory, "worker")
    if factory is None:
        raise OSError("Core worker service is unavailable")
    worker = factory(**kwargs)
    from studio_job_services import CoreWorkerJobHandle
    return worker if isinstance(worker, CoreWorkerJobHandle) else CoreWorkerJobHandle(worker)
