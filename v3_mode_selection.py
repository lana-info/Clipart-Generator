from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from v3_components import (
    DEFAULT_TOKENS,
    ButtonVariant,
    ModeCard,
    V3Button,
    V3DesignTokens,
    apply_v3_theme,
)
from v3_project_state import ProjectMode, ProjectState
from v3_project_state import ProjectStateError, load_project_draft, save_project_draft
from v3_clipart_flow import install_clipart_flow
from v3_pinterest_flow import install_pinterest_flow
from v3_processing_flow import install_processing_flow
from v3_wizard import AppShell, MODE_TITLES, STEP_TITLES


@dataclass(frozen=True)
class ModeCardSpec:
    title: str
    description: str
    result: str


MODE_CARD_SPECS: dict[ProjectMode, ModeCardSpec] = {
    ProjectMode.CLIPART: ModeCardSpec(
        title="Создать клипарт",
        description=(
            "Создайте согласованную серию изолированных объектов "
            "с настройкой генерации и обработки."
        ),
        result="набор готовых PNG-клипартов",
    ),
    ProjectMode.PINTEREST: ModeCardSpec(
        title="Создать Pinterest-пины",
        description=(
            "Создавайте только готовые вертикальные изображения по промптам — "
            "без публикации, редактора макетов и обязательного текста поверх."
        ),
        result="пакет изображений Pinterest-пинов",
    ),
    ProjectMode.PROCESSING: ModeCardSpec(
        title="Обработать изображения",
        description=(
            "Улучшите собственные или лицензированные файлы: фон, качество, "
            "края, метаданные и проверка."
        ),
        result="новые обработанные файлы и отчёт",
    ),
}


class SelectionIntent(str, Enum):
    NEW_PROJECT = "new_project"
    SWITCH_MODE = "switch_mode"


class ModeSelectionScreen(QWidget):
    mode_selected = pyqtSignal(str)
    continue_last_project_requested = pyqtSignal()
    cancel_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        self.tokens = tokens
        self.mode_cards: dict[ProjectMode, ModeCard] = {}

        self.setMinimumSize(980, 700)
        self.setAccessibleName("Выбор задачи")
        apply_v3_theme(self, tokens)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            tokens.space_6,
            tokens.space_6,
            tokens.space_6,
            tokens.space_6,
        )
        layout.setSpacing(tokens.space_4)

        title = QLabel("Что вы хотите сделать?")
        title.setProperty("v3Title", True)
        title.setAccessibleName(title.text())
        layout.addWidget(title)

        description = QLabel(
            "Выберите задачу — дальше будут показаны только нужные шаги и настройки."
        )
        description.setProperty("v3Description", True)
        description.setWordWrap(True)
        layout.addWidget(description)

        self.cards_container = QWidget()
        cards_layout = QHBoxLayout(self.cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(tokens.space_4)
        for mode in ProjectMode:
            spec = MODE_CARD_SPECS[mode]
            card = ModeCard(
                mode.value,
                spec.title,
                spec.description,
                spec.result,
                tokens=tokens,
            )
            card.selected.connect(self._select_mode)
            card.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Expanding,
            )
            self.mode_cards[mode] = card
            cards_layout.addWidget(card, 1)
        layout.addWidget(self.cards_container, 1)

        self.recent_project_card = QFrame()
        self.recent_project_card.setProperty("v3Card", True)
        recent_layout = QHBoxLayout(self.recent_project_card)
        recent_layout.setContentsMargins(
            tokens.space_4,
            tokens.space_3,
            tokens.space_4,
            tokens.space_3,
        )
        recent_layout.setSpacing(tokens.space_3)

        self.recent_project_label = QLabel()
        self.recent_project_label.setProperty("v3Description", True)
        self.recent_project_label.setWordWrap(True)
        recent_layout.addWidget(self.recent_project_label, 1)

        self.continue_button = V3Button(
            "Продолжить черновик",
            ButtonVariant.SECONDARY,
        )
        self.continue_button.clicked.connect(
            self.continue_last_project_requested.emit
        )
        recent_layout.addWidget(self.continue_button)
        self.recent_project_card.hide()
        layout.addWidget(self.recent_project_card)

        self.cancel_button = V3Button(
            "Вернуться",
            ButtonVariant.SECONDARY,
        )
        self.cancel_button.clicked.connect(self.cancel_requested.emit)
        self.cancel_button.hide()
        layout.addWidget(self.cancel_button, 0)

    def _select_mode(self, mode_value: str) -> None:
        selected_mode = ProjectMode(mode_value)
        for mode, card in self.mode_cards.items():
            card.set_selected(mode is selected_mode)
        self.mode_selected.emit(selected_mode.value)

    def reset_selection(self) -> None:
        for card in self.mode_cards.values():
            card.set_selected(False)

    def set_recent_project_summary(self, state: ProjectState | None) -> None:
        if state is None:
            self.recent_project_label.clear()
            self.recent_project_label.setAccessibleName("")
            self.continue_button.setAccessibleDescription("")
            self.recent_project_card.hide()
            return

        project_name = state.common.project_name.strip() or "Без названия"
        summary = (
            f"Последний черновик: {project_name} · "
            f"{MODE_TITLES[state.mode]} · "
            f"шаг «{STEP_TITLES[state.current_step]}»"
        )
        self.recent_project_label.setText(summary)
        self.recent_project_label.setAccessibleName(summary)
        self.continue_button.setAccessibleDescription(summary)
        self.recent_project_card.show()


    def set_mode_switch_context(self, enabled: bool) -> None:
        self.cancel_button.setVisible(bool(enabled))


class V3ApplicationView(QWidget):
    screen_changed = pyqtSignal(str)
    new_project_started = pyqtSignal(str)
    project_continued = pyqtSignal(str)

    def __init__(
        self,
        recent_project: ProjectState | None = None,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        runtime_settings_provider: Callable[[], Mapping[str, Any]] | None = None,
        worker_factory: Callable[..., Any] | None = None,
        draft_path: str | Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.tokens = tokens
        self._selection_intent = SelectionIntent.NEW_PROJECT
        self._recent_project: ProjectState | None = None
        self._runtime_settings_provider = runtime_settings_provider
        self._v3_runtime_settings: dict[str, str] = {}
        self._worker_factory = worker_factory
        self._draft_path = Path(draft_path) if draft_path is not None else None
        self.shell: AppShell | None = None

        self.setMinimumSize(980, 700)
        self.setAccessibleName("Clipart Generator 3.0")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)

        self.mode_selection = ModeSelectionScreen(tokens=tokens)
        self.mode_selection.mode_selected.connect(self._handle_mode_selected)
        self.mode_selection.continue_last_project_requested.connect(
            self.continue_last_project
        )
        self.mode_selection.cancel_requested.connect(self.cancel_mode_switch)
        self.stack.addWidget(self.mode_selection)

        if recent_project is None and self._draft_path is not None:
            recent_project = self._load_recent_project()
        if recent_project is not None:
            self.set_recent_project(recent_project)
        self.show_new_project()

    def _runtime_settings(self) -> Mapping[str, Any]:
        base = dict(self._runtime_settings_provider() or {}) if self._runtime_settings_provider else {}
        base.update(self._v3_runtime_settings)
        return base

    def _show_api_settings(self) -> None:
        from v3_api_settings import ApiSettingsDialog
        dialog = ApiSettingsDialog(initial=self._runtime_settings(), parent=self.shell or self)
        if dialog.exec():
            self._v3_runtime_settings.update(dialog.settings)
            if self.shell is not None:
                self.shell.state_changed.emit()

    @property
    def project_state(self) -> ProjectState | None:
        return self.shell.state if self.shell is not None else None

    @property
    def selection_intent(self) -> SelectionIntent:
        return self._selection_intent

    def set_recent_project(self, state: ProjectState) -> None:
        if not isinstance(state, ProjectState):
            raise TypeError("recent project must be a ProjectState")
        self._recent_project = ProjectState.from_dict(state.to_dict())
        if self._selection_intent is SelectionIntent.NEW_PROJECT:
            self.mode_selection.set_recent_project_summary(self._recent_project)

    def clear_recent_project(self) -> None:
        self._recent_project = None
        self.mode_selection.set_recent_project_summary(None)

    def show_new_project(self) -> None:
        self._selection_intent = SelectionIntent.NEW_PROJECT
        self.mode_selection.reset_selection()
        self.mode_selection.set_mode_switch_context(False)
        self.mode_selection.set_recent_project_summary(self._recent_project)
        self.stack.setCurrentWidget(self.mode_selection)
        self.screen_changed.emit("mode_selection")

    def show_mode_switcher(self) -> None:
        if self.shell is None:
            self.show_new_project()
            return
        self._selection_intent = SelectionIntent.SWITCH_MODE
        self.mode_selection.reset_selection()
        self.mode_selection.set_mode_switch_context(True)
        self.mode_selection.set_recent_project_summary(None)
        self.stack.setCurrentWidget(self.mode_selection)
        self.screen_changed.emit("mode_selection")

    def cancel_mode_switch(self) -> bool:
        if self.shell is None:
            return False
        self.mode_selection.set_mode_switch_context(False)
        self.stack.setCurrentWidget(self.shell)
        self.screen_changed.emit("wizard")
        return True

    def _handle_mode_selected(self, mode_value: str) -> None:
        mode = ProjectMode(mode_value)
        if (
            self._selection_intent is SelectionIntent.SWITCH_MODE
            and self.shell is not None
        ):
            self.shell.request_mode_switch(mode)
            self.stack.setCurrentWidget(self.shell)
            self.screen_changed.emit("wizard")
            return

        state = ProjectState(mode=mode)
        self._replace_shell(state)
        self.new_project_started.emit(mode.value)

    def continue_last_project(self) -> bool:
        if self._recent_project is None:
            return False
        state = ProjectState.from_dict(self._recent_project.to_dict())
        self._replace_shell(state)
        self.project_continued.emit(state.mode.value)
        return True

    def _load_recent_project(self) -> ProjectState | None:
        path = self._draft_path
        if path is None or not path.is_file():
            return None
        try:
            return load_project_draft(path)
        except ProjectStateError:
            return None

    def _save_draft(self) -> None:
        path = self._draft_path
        if path is None or self.shell is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            save_project_draft(self.shell.state, path)
        except ProjectStateError:
            return

    def _replace_shell(self, state: ProjectState) -> None:
        previous = self.shell
        if previous is not None:
            previous.state_changed.disconnect(self._save_draft)
            self.stack.removeWidget(previous)
            previous.deleteLater()

        shell = AppShell(state, tokens=self.tokens)

        install_clipart_flow(
            shell,
            runtime_settings_provider=self._runtime_settings,
            worker_factory=self._worker_factory,
        )
        install_pinterest_flow(
            shell,
            runtime_settings_provider=self._runtime_settings,
            worker_factory=self._worker_factory,
        )
        install_processing_flow(
            shell,
            runtime_settings_provider=self._runtime_settings,
            worker_factory=self._worker_factory,
        )
        shell.state_changed.connect(self._save_draft)
        shell.mode_picker_requested.connect(self.show_mode_switcher)
        shell.api_settings_requested.connect(self._show_api_settings)
        shell.finish_requested.connect(self._finish_workflow)
        self.shell = shell
        self.stack.addWidget(shell)
        self.stack.setCurrentWidget(shell)
        self.screen_changed.emit("wizard")
        self._save_draft()

    def _finish_workflow(self, _mode: str) -> None:
        """Return to mode selection without reusing the completed shell."""
        self.show_new_project()
