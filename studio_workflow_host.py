"""Explicit, mode-scoped host surface for built-in Studio workflows."""
from __future__ import annotations

from typing import Any

from _studio_workflow_core import (
    capability_mode_data,
    capability_runtime_data,
    capability_tokens,
    common_get,
    common_set,
    diagnostic_record,
    diagnostic_record_structured,
    has_diagnostic_journal,
    host_another_run_is_active,
    host_ensure_step_page,
    host_go_next,
    host_runtime_settings,
    host_authorize_run,
    host_create_worker_job,
    host_prepare_run,
    host_mark_dirty,
    host_refresh,
    host_register_workflow_controller,
    host_set_canvas_focus_mode,
    host_set_step_factory,
    host_set_step_page,
    host_set_workflow_factory,
    host_show_results,
    host_workflow_controller,
    host_workflow_definition,
)
from _studio_workflow_core import (
    register_workflow_capability,
    signal_connect,
    signal_disconnect,
    signal_emit,
    state_current_step,
    state_is_active,
    state_output_dir,
    state_set_output_dir,
    state_set_step,
)
from v3_project_state import ProjectMode, StepId


class WorkflowSignal:
    __slots__ = ("_capability_id", "_name", "__weakref__")

    def __init__(self, capability_id: str, name: str) -> None:
        self._capability_id = capability_id
        self._name = name

    def connect(self, callback) -> None:
        signal_connect(self._capability_id, self._name, callback)

    def disconnect(self, callback=None) -> None:
        signal_disconnect(self._capability_id, self._name, callback)

    def emit(self, *args) -> None:
        signal_emit(self._capability_id, self._name, *args)


class WorkflowDiagnosticJournal:
    __slots__ = ("_capability_id",)

    def __init__(self, capability_id: str) -> None:
        self._capability_id = capability_id

    def record(self, *args, **kwargs):
        return diagnostic_record(self._capability_id, *args, **kwargs)

    def record_structured(self, *args, **kwargs):
        return diagnostic_record_structured(
            self._capability_id, *args, **kwargs
        )


class WorkflowCommonView:
    __slots__ = ("_capability_id",)

    def __init__(self, capability_id: str) -> None:
        self._capability_id = capability_id

    @property
    def project_name(self) -> str:
        return common_get(self._capability_id, "project_name")

    @project_name.setter
    def project_name(self, value: str) -> None:
        common_set(self._capability_id, "project_name", value)
    @property
    def work_dir(self) -> str:
        return common_get(self._capability_id, "work_dir")

    @work_dir.setter
    def work_dir(self, value: str) -> None:
        common_set(self._capability_id, "work_dir", value)

    @property
    def output_dir(self) -> str:
        return state_output_dir(self._capability_id)

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        state_set_output_dir(self._capability_id, value)


class WorkflowStateView:
    __slots__ = (
        "_capability_id", "_scope", "common", "runtime", "data",
    )

    def __init__(
        self,
        capability_id: str,
        module_id: str,
        *,
        runtime: Any,
        data: Any,
    ) -> None:
        try:
            scope = ProjectMode(module_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Workflow state scope is invalid") from exc
        self._capability_id = capability_id
        self._scope = scope
        self.common = WorkflowCommonView(capability_id)
        self.runtime = runtime
        self.data = data

    @property
    def scope(self) -> ProjectMode:
        return self._scope

    @property
    def mode(self) -> ProjectMode:
        return self._scope

    @property
    def is_active(self) -> bool:
        return state_is_active(self._capability_id)

    @property
    def current_step(self) -> StepId:
        return state_current_step(self._capability_id)

    def _require_scope(self, mode: ProjectMode | str) -> ProjectMode:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        if normalized is not self._scope:
            raise ValueError("Workflow state operation is outside module scope")
        return normalized

    def output_dir_for_mode(self, mode: ProjectMode | str) -> str:
        self._require_scope(mode)
        return state_output_dir(self._capability_id)

    def set_output_dir_for_mode(self, value: str, mode: ProjectMode | str) -> None:
        self._require_scope(mode)
        state_set_output_dir(self._capability_id, value)

    def set_step(self, step: StepId | str) -> None:
        state_set_step(self._capability_id, step)


class WorkflowHost:
    """Narrow facade containing only opaque Core capability identifiers."""
    __slots__ = (
        "_capability_id", "module_id", "state", "tokens",
        "step_changed", "run_requested", "state_changed", "finish_requested",
        "_diagnostic_journal", "__weakref__",
    )

    def __init__(
        self,
        shell: Any,
        module_id: str,
        *,
        runtime_settings_provider=None,
        worker_factory=None,
        authorization_provider=None,
        run_preparer=None,
    ) -> None:
        if not isinstance(module_id, str) or not module_id:
            raise ValueError("Workflow module id is invalid")
        required = (
            "state", "tokens", "step_changed", "run_requested", "state_changed",
            "finish_requested", "workflow_definition", "set_step_page",
            "ensure_step_page", "register_workflow_controller", "workflow_controller",
        )
        if any(not hasattr(shell, name) for name in required):
            raise TypeError("Workflow host source does not expose required shell contract")
        capability_id = register_workflow_capability(
            shell,
            module_id,
            runtime_settings_provider=runtime_settings_provider,
            worker_factory=worker_factory,
            authorization_provider=authorization_provider,
            run_preparer=run_preparer,
        )
        self._capability_id = capability_id
        self.module_id = module_id
        self.state = WorkflowStateView(
            capability_id,
            module_id,
            runtime=capability_runtime_data(capability_id),
            data=capability_mode_data(capability_id),
        )
        self.tokens = capability_tokens(capability_id)
        self.step_changed = WorkflowSignal(capability_id, "step_changed")
        self.run_requested = WorkflowSignal(capability_id, "run_requested")
        self.state_changed = WorkflowSignal(capability_id, "state_changed")
        self.finish_requested = WorkflowSignal(capability_id, "finish_requested")
        self._diagnostic_journal = (
            WorkflowDiagnosticJournal(capability_id)
            if has_diagnostic_journal(capability_id)
            else None
        )

    @property
    def diagnostic_journal(self):
        return self._diagnostic_journal

    def mark_dirty(self) -> None:
        host_mark_dirty(self._capability_id)

    def refresh(self) -> None:
        host_refresh(self._capability_id)

    def runtime_settings(self) -> dict[str, Any]:
        return host_runtime_settings(self._capability_id)

    def authorize_run(self):
        return host_authorize_run(self._capability_id)

    def create_worker_job(self, **kwargs):
        return host_create_worker_job(self._capability_id, **kwargs)

    def prepare_run(self):
        return host_prepare_run(self._capability_id)

    def go_next(self) -> None:
        host_go_next(self._capability_id)

    def show_results(self) -> None:
        host_show_results(self._capability_id)

    def set_canvas_focus_mode(self, enabled: bool) -> None:
        host_set_canvas_focus_mode(self._capability_id, enabled)

    def another_run_is_active(self, controller: object) -> bool:
        return host_another_run_is_active(self._capability_id, controller)

    def workflow_definition(self, mode=None):
        self.state._require_scope(mode or self.state.scope)
        return host_workflow_definition(self._capability_id)

    def set_workflow_factory(self, mode, step, factory) -> None:
        self.state._require_scope(mode)
        host_set_workflow_factory(self._capability_id, step, factory)

    def set_step_factory(self, mode, step, factory) -> None:
        self.state._require_scope(mode)
        host_set_step_factory(self._capability_id, step, factory)

    def set_step_page(self, mode, step, page) -> None:
        self.state._require_scope(mode)
        host_set_step_page(self._capability_id, step, page)

    def ensure_step_page(self, mode, step):
        self.state._require_scope(mode)
        return host_ensure_step_page(self._capability_id, step)

    def workflow_controller(self, module_id: str):
        if module_id != self.module_id:
            raise ValueError("Workflow controller lookup is outside module scope")
        return host_workflow_controller(self._capability_id)

    def register_workflow_controller(self, module_id: str, controller: object) -> None:
        if module_id != self.module_id:
            raise ValueError("Workflow controller registration is outside module scope")
        host_register_workflow_controller(self._capability_id, controller)


def workflow_host_for(value: Any, module_id: str) -> WorkflowHost:
    if not isinstance(value, WorkflowHost):
        raise TypeError("built-in workflow installer requires WorkflowHost")
    if value.module_id != module_id:
        raise ValueError("Workflow host scope does not match module")
    return value


__all__ = [
    "WorkflowCommonView", "WorkflowDiagnosticJournal", "WorkflowHost",
    "WorkflowSignal", "WorkflowStateView", "workflow_host_for",
]
