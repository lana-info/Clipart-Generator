"""Lazy V3 page registry and determinate initialization progress UI."""

from __future__ import annotations

from collections.abc import Callable, Iterator, MutableMapping
from dataclasses import dataclass
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QProgressDialog, QWidget

from v3_project_state import ProjectMode, StepId, route_for_mode


@dataclass(frozen=True, slots=True)
class InitializationStage:
    label: str
    completed: int
    total: int

    def __post_init__(self) -> None:
        if self.total < 1 or self.completed < 0 or self.completed > self.total:
            raise ValueError("Invalid initialization progress")

    @property
    def percent(self) -> int:
        return round(self.completed * 100 / self.total)


class InitializationProgressOverlay(QProgressDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Открываем режим…", "", 0, 100, parent)
        self.setWindowTitle("Загрузка")
        self.setCancelButton(None)
        self.setMinimumDuration(150)
        self.setAutoClose(True)
        self.setAutoReset(False)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setWindowFlag(Qt.WindowType.WindowDoesNotAcceptFocus, True)

    def update_stage(self, stage: InitializationStage) -> None:
        self.setLabelText(stage.label[:160])
        self.setValue(stage.percent)


class LazyPageRegistry(MutableMapping[StepId, QWidget]):
    """Mapping-compatible page registry that materializes each page once."""

    def __init__(self, shell: Any, mode: ProjectMode) -> None:
        self.shell = shell
        self.mode = mode
        self._factories: dict[StepId, Callable[[], QWidget]] = {}
        self._materialized: dict[StepId, QWidget] = {}

    @property
    def materialized_steps(self) -> set[StepId]:
        return set(self._materialized)

    def register(self, step: StepId, factory: Callable[[], QWidget]) -> None:
        if step in self._factories or step in self._materialized:
            raise ValueError(f"Page already registered: {step.value}")

        def materialize() -> QWidget:
            page = factory()
            self._materialized[step] = page
            return page

        self._factories[step] = materialize
        if step in route_for_mode(self.mode):
            self.shell.set_step_factory(self.mode, step, materialize)

    def register_instance(self, step: StepId, page: QWidget) -> None:
        if step in self._factories or step in self._materialized:
            raise ValueError(f"Page already registered: {step.value}")
        self._materialized[step] = page
        self.shell.set_step_page(self.mode, step, page)

    def __getitem__(self, step: StepId) -> QWidget:
        if step not in self._materialized:
            if step in route_for_mode(self.mode):
                self.shell.ensure_step_page(self.mode, step)
            else:
                self._factories[step]()
        return self._materialized[step]

    def __setitem__(self, step: StepId, page: QWidget) -> None:
        self.register_instance(step, page)

    def __delitem__(self, step: StepId) -> None:
        if step in self._materialized:
            del self._materialized[step]
        elif step in self._factories:
            del self._factories[step]
        else:
            raise KeyError(step)

    def __iter__(self) -> Iterator[StepId]:
        return iter(dict.fromkeys((*self._factories, *self._materialized)))

    def __len__(self) -> int:
        return len(set(self._factories) | set(self._materialized))
