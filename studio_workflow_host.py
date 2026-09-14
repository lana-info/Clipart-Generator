"""Explicit, mode-scoped host surface for built-in Studio workflows."""
from __future__ import annotations

import weakref
from typing import Any

from v3_project_state import ProjectMode, StepId


class WorkflowCommonView:
    __slots__ = ("__state_ref", "_scope")

    def __init__(self, state: Any, scope: ProjectMode) -> None:
        self.__state_ref = weakref.ref(state)
        self._scope = scope

    def __state(self):
        state = self.__state_ref()
        if state is None:
            raise RuntimeError("Workflow state is unavailable")
        return state

    @property
    def project_name(self) -> str:
        return self.__state().common.project_name

    @project_name.setter
    def project_name(self, value: str) -> None:
        self.__state().common.project_name = value

    @property
    def work_dir(self) -> str:
        return self.__state().common.work_dir

    @work_dir.setter
    def work_dir(self, value: str) -> None:
        self.__state().common.work_dir = value

    @property
    def output_dir(self) -> str:
        return self.__state().output_dir_for_mode(self._scope)

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self.__state().set_output_dir_for_mode(value, self._scope)


class WorkflowStateView:
    __slots__ = ("__state_ref", "_scope", "common")

    def __init__(self, state: Any, module_id: str) -> None:
        self.__state_ref = weakref.ref(state)
        try:
            self._scope = ProjectMode(module_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Workflow state scope is invalid") from exc
        self.common = WorkflowCommonView(state, self._scope)

    def __state(self):
        state = self.__state_ref()
        if state is None:
            raise RuntimeError("Workflow state is unavailable")
        return state

    @property
    def scope(self) -> ProjectMode:
        return self._scope

    @property
    def mode(self) -> ProjectMode:
        return self._scope

    @property
    def is_active(self) -> bool:
        return self.__state().mode is self._scope

    @property
    def current_step(self) -> StepId:
        return self.__state().current_step_by_mode[self._scope]

    @property
    def runtime(self):
        return self.__state().runtime

    @property
    def data(self):
        return getattr(self.__state(), self._scope.value)

    def _require_scope(self, mode: ProjectMode | str) -> ProjectMode:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        if normalized is not self._scope:
            raise ValueError("Workflow state operation is outside module scope")
        return normalized

    def output_dir_for_mode(self, mode: ProjectMode | str) -> str:
        return self.__state().output_dir_for_mode(self._require_scope(mode))

    def set_output_dir_for_mode(self, value: str, mode: ProjectMode | str) -> None:
        self.__state().set_output_dir_for_mode(value, self._require_scope(mode))

    def set_step(self, step: StepId | str) -> None:
        state = self.__state()
        if state.mode is not self._scope:
            raise ValueError("Workflow state operation is outside active module scope")
        state.set_step(step)


class WorkflowHost:
    """Narrow shell facade. It deliberately is not a QObject or generic proxy."""
    __slots__ = ("__shell_ref", "module_id", "state", "tokens", "__weakref__")

    def __init__(self, shell: Any, module_id: str) -> None:
        if not isinstance(module_id, str) or not module_id:
            raise ValueError("Workflow module id is invalid")
        required = (
            "state", "tokens", "step_changed", "run_requested", "state_changed",
            "finish_requested", "workflow_definition", "set_step_page",
            "ensure_step_page", "register_workflow_controller", "workflow_controller",
        )
        if any(not hasattr(shell, name) for name in required):
            raise TypeError("Workflow host source does not expose the required shell contract")
        try:
            self.__shell_ref = weakref.ref(shell)
        except TypeError as exc:
            raise TypeError("Workflow host source must support weak references") from exc
        self.module_id = module_id
        self.state = WorkflowStateView(shell.state, module_id)
        self.tokens = shell.tokens

    def __shell(self):
        shell = self.__shell_ref()
        if shell is None:
            raise RuntimeError("Workflow shell is unavailable")
        return shell

    @property
    def step_changed(self):
        return self.__shell().step_changed

    @property
    def run_requested(self):
        return self.__shell().run_requested

    @property
    def state_changed(self):
        return self.__shell().state_changed

    @property
    def finish_requested(self):
        return self.__shell().finish_requested

    @property
    def diagnostic_journal(self):
        return getattr(self.__shell(), "diagnostic_journal", None)

    def mark_dirty(self) -> None:
        self.__shell().mark_dirty()

    def refresh(self) -> None:
        self.__shell().refresh()

    def go_next(self) -> None:
        self.__shell().go_next()

    def show_results(self) -> None:
        self.__shell().show_results()

    def set_canvas_focus_mode(self, enabled: bool) -> None:
        self.__shell().set_canvas_focus_mode(enabled)

    def another_run_is_active(self, controller: object) -> bool:
        return bool(self.__shell().another_run_is_active(controller))

    def workflow_definition(self, mode=None):
        normalized = self.state._require_scope(mode or self.state.scope)
        return self.__shell().workflow_definition(normalized)

    def set_workflow_factory(self, mode, step, factory) -> None:
        self.__shell().set_workflow_factory(self.state._require_scope(mode), step, factory)

    def set_step_factory(self, mode, step, factory) -> None:
        self.__shell().set_step_factory(self.state._require_scope(mode), step, factory)

    def set_step_page(self, mode, step, page) -> None:
        self.__shell().set_step_page(self.state._require_scope(mode), step, page)

    def ensure_step_page(self, mode, step):
        return self.__shell().ensure_step_page(self.state._require_scope(mode), step)

    def workflow_controller(self, module_id: str):
        if module_id != self.module_id:
            raise ValueError("Workflow controller lookup is outside module scope")
        return self.__shell().workflow_controller(module_id)

    def register_workflow_controller(self, module_id: str, controller: object) -> None:
        if module_id != self.module_id:
            raise ValueError("Workflow controller registration is outside module scope")
        self.__shell().register_workflow_controller(module_id, controller)


def workflow_host_for(value: Any, module_id: str) -> WorkflowHost:
    if not isinstance(value, WorkflowHost):
        raise TypeError("built-in workflow installer requires WorkflowHost")
    if value.module_id != module_id:
        raise ValueError("Workflow host scope does not match module")
    return value


__all__ = ["WorkflowCommonView", "WorkflowHost", "WorkflowStateView", "workflow_host_for"]
