"""Narrow compatibility host for built-in Studio workflows."""
from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QObject

from v3_project_state import ProjectMode, StepId


class WorkflowStateView:
    __slots__ = ("__state", "_scope")

    def __init__(self, state: Any, module_id: str) -> None:
        self.__state = state
        try:
            self._scope = ProjectMode(module_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Workflow state scope is invalid") from exc

    @property
    def scope(self) -> ProjectMode:
        return self._scope

    @property
    def mode(self) -> ProjectMode:
        return self.__state.mode

    @property
    def current_step(self) -> StepId:
        return self.__state.current_step
    @property
    def common(self):
        return self.__state.common

    @property
    def runtime(self):
        return self.__state.runtime

    @property
    def data(self):
        return getattr(self.__state, self._scope.value)

    def _require_scope(self, mode: ProjectMode | str) -> ProjectMode:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        if normalized is not self._scope:
            raise ValueError("Workflow state operation is outside module scope")
        return normalized

    def output_dir_for_mode(self, mode: ProjectMode | str) -> str:
        return self.__state.output_dir_for_mode(self._require_scope(mode))

    def set_output_dir_for_mode(self, value: str, mode: ProjectMode | str) -> None:
        self.__state.set_output_dir_for_mode(value, self._require_scope(mode))

    def set_step(self, step: StepId | str) -> None:
        if self.__state.mode is not self._scope:
            raise ValueError("Workflow state operation is outside active module scope")
        self.__state.set_step(step)


class WorkflowHost(QObject):
    """Explicit shell surface used only by built-in compatibility workflows."""
    __slots__ = ("__shell", "module_id", "state", "tokens")

    def __init__(self, shell: QObject, module_id: str) -> None:
        if not isinstance(module_id, str) or not module_id:
            raise ValueError("Workflow module id is invalid")
        if not isinstance(shell, QObject):
            raise TypeError("Workflow host parent must be a QObject")
        super().__init__(shell)
        required = (
            "state", "tokens", "step_changed", "run_requested", "state_changed",
            "finish_requested", "workflow_definition", "set_step_page",
            "ensure_step_page", "register_workflow_controller", "workflow_controller",
        )
        if any(not hasattr(shell, name) for name in required):
            raise TypeError("Workflow host parent does not expose the required shell contract")
        self.__shell = shell
        self.module_id = module_id
        self.state = WorkflowStateView(shell.state, module_id)
        self.tokens = shell.tokens

    @property
    def step_changed(self):
        return self.__shell.step_changed

    @property
    def run_requested(self):
        return self.__shell.run_requested

    @property
    def state_changed(self):
        return self.__shell.state_changed
    @property
    def finish_requested(self):
        return self.__shell.finish_requested

    @property
    def diagnostic_journal(self):
        return getattr(self.__shell, "diagnostic_journal", None)

    def mark_dirty(self) -> None:
        self.__shell.mark_dirty()

    def refresh(self) -> None:
        self.__shell.refresh()

    def go_next(self) -> None:
        self.__shell.go_next()

    def show_results(self) -> None:
        self.__shell.show_results()

    def set_canvas_focus_mode(self, enabled: bool) -> None:
        self.__shell.set_canvas_focus_mode(enabled)

    def another_run_is_active(self, controller: object) -> bool:
        return bool(self.__shell.another_run_is_active(controller))

    def workflow_definition(self, mode=None):
        normalized = self.state._require_scope(mode or self.state.scope)
        return self.__shell.workflow_definition(normalized)
    def set_workflow_factory(self, mode, step, factory) -> None:
        self.__shell.set_workflow_factory(self.state._require_scope(mode), step, factory)

    def set_step_factory(self, mode, step, factory) -> None:
        self.__shell.set_step_factory(self.state._require_scope(mode), step, factory)

    def set_step_page(self, mode, step, page) -> None:
        self.__shell.set_step_page(self.state._require_scope(mode), step, page)

    def ensure_step_page(self, mode, step):
        return self.__shell.ensure_step_page(self.state._require_scope(mode), step)

    def workflow_controller(self, module_id: str):
        if module_id != self.module_id:
            raise ValueError("Workflow controller lookup is outside module scope")
        return self.__shell.workflow_controller(module_id)

    def register_workflow_controller(self, module_id: str, controller: object) -> None:
        if module_id != self.module_id:
            raise ValueError("Workflow controller registration is outside module scope")
        self.__shell.register_workflow_controller(module_id, controller)


def workflow_host_for(value: Any, module_id: str) -> WorkflowHost:
    if isinstance(value, WorkflowHost):
        if value.module_id != module_id:
            raise ValueError("Workflow host scope does not match module")
        return value
    return WorkflowHost(value, module_id)


__all__ = ["WorkflowHost", "WorkflowStateView", "workflow_host_for"]