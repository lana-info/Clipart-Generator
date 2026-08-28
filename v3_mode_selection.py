from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEventLoop, QStandardPaths, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
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
    V3_WINDOW_DEFAULT_SIZE,
    V3_WINDOW_MINIMUM_SIZE,
    apply_v3_theme,
)
from v3_project_state import ProjectMode, ProjectState
from v3_project_state import ProjectStateError, load_project_draft, save_project_draft
from v3_clipart_flow import install_clipart_flow
from v3_pinterest_flow import install_pinterest_flow
from v3_processing_flow import install_processing_flow
from v3_localization import app_locale_from_settings
from v3_lazy_loading import InitializationProgressOverlay, InitializationStage
from v3_license import LicenseDialog, OnlineLicenseGate
from v3_wizard import AppShell, MODE_TITLES, STEP_TITLES
from app_identity import APP_NAME
from config_schema import load_preferences, resolve_output_directory, save_preferences_atomic


@dataclass(frozen=True)
class ModeCardSpec:
    title: str
    description: str
    result: str


MODE_CARD_SPECS: dict[ProjectMode, ModeCardSpec] = {
    ProjectMode.CLIPART: ModeCardSpec(
        title="Создать клипарт",
        description=(
            "Массово создавайте изображения в нейросетях, включая "
            "согласованные серии клипартов, с гибкой генерацией и обработкой."
        ),
        result="серия готовых изображений, в том числе PNG-клипартов",
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


def default_work_directory() -> Path:
    """Return a user-owned default that never depends on the process directory."""
    pictures = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.PicturesLocation
    ).strip()
    if not pictures:
        pictures = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DocumentsLocation
        ).strip()
    if not pictures:
        pictures = str(Path.home() / "Pictures")
    return Path(pictures).expanduser() / APP_NAME


class SelectionIntent(str, Enum):
    NEW_PROJECT = "new_project"
    SWITCH_MODE = "switch_mode"


def mode_illustration_path(mode: ProjectMode) -> Path:
    """Resolve a packaged mode illustration for both source and PyInstaller runs."""
    resource_root = Path(
        getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)
    )
    return resource_root / "assets" / f"mode-{mode.value}.png"


class ModeSelectionScreen(QWidget):
    mode_selected = pyqtSignal(str)
    continue_last_project_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    license_requested = pyqtSignal()
    api_settings_requested = pyqtSignal()
    diagnostics_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        self.tokens = tokens
        self.mode_cards: dict[ProjectMode, ModeCard] = {}

        self.setMinimumSize(*V3_WINDOW_MINIMUM_SIZE)
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

        self.account_card = QFrame()
        self.account_card.setProperty("v3Card", True)
        account_layout = QHBoxLayout(self.account_card)
        account_layout.setContentsMargins(
            tokens.space_4,
            tokens.space_3,
            tokens.space_4,
            tokens.space_3,
        )
        account_layout.setSpacing(tokens.space_3)

        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(tokens.space_1)
        self.license_status_label = QLabel("Лицензия не активирована")
        self.license_status_label.setAccessibleName("Статус лицензии")
        status_layout.addWidget(self.license_status_label)
        self.license_verification_label = QLabel("Онлайн-проверка не выполнена")
        self.license_verification_label.setProperty("v3Small", True)
        self.license_verification_label.setAccessibleName("Онлайн-проверка лицензии")
        status_layout.addWidget(self.license_verification_label)
        account_layout.addLayout(status_layout, 1)

        self.license_button = V3Button("Сменить лицензию", ButtonVariant.GHOST)
        self.license_button.clicked.connect(self.license_requested.emit)
        account_layout.addWidget(self.license_button)
        self.api_settings_button = V3Button("Настройки API", ButtonVariant.GHOST)
        self.api_settings_button.clicked.connect(self.api_settings_requested.emit)
        account_layout.addWidget(self.api_settings_button)
        self.diagnostics_button = V3Button("Журнал диагностики", ButtonVariant.GHOST)
        self.diagnostics_button.clicked.connect(self.diagnostics_requested.emit)
        account_layout.addWidget(self.diagnostics_button)
        layout.addWidget(self.account_card)

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
                illustration_path=mode_illustration_path(mode),
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

    def set_license_status(self, status: str, verification: str) -> None:
        safe_status = str(status or "Лицензия не активирована")[:160]
        safe_verification = str(
            verification or "Онлайн-проверка не выполнена"
        )[:160]
        self.license_status_label.setText(safe_status)
        self.license_status_label.setAccessibleDescription(safe_status)
        self.license_verification_label.setText(safe_verification)
        self.license_verification_label.setAccessibleDescription(safe_verification)

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
        license_gate: OnlineLicenseGate | None = None,
        diagnostic_journal: Any | None = None,
        update_client: Any | None = None,
        legacy_project: ProjectState | None = None,
    ) -> None:
        super().__init__(parent)
        self.tokens = tokens
        self._selection_intent = SelectionIntent.NEW_PROJECT
        self._recent_project: ProjectState | None = None
        self._runtime_settings_provider = runtime_settings_provider
        self._v3_runtime_settings: dict[str, Any] = {}
        self._worker_factory = worker_factory
        self._license_gate = license_gate
        self._diagnostic_journal = diagnostic_journal
        self._update_client = update_client
        self._legacy_project = legacy_project
        self._update_controller = None
        self._initialization_overlay: InitializationProgressOverlay | None = None
        self._draft_path = Path(draft_path) if draft_path is not None else None
        self._preferences_path = (
            self._draft_path.with_name("preferences.json")
            if self._draft_path is not None else None
        )
        self._preferences = self._load_preferences()
        from runtime_settings import normalize_provider_concurrency

        for key in ("kie_concurrency", "photoroom_concurrency"):
            if key in self._preferences:
                self._v3_runtime_settings[key] = normalize_provider_concurrency(
                    self._preferences.get(key)
                )
        self.shell: AppShell | None = None

        self.setMinimumSize(*V3_WINDOW_MINIMUM_SIZE)
        self.resize(*V3_WINDOW_DEFAULT_SIZE)
        self.setAccessibleName(f"{APP_NAME} 3.0")

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
        self.mode_selection.license_requested.connect(self._show_license)
        self.mode_selection.api_settings_requested.connect(self._show_api_settings)
        self.mode_selection.diagnostics_requested.connect(self._show_diagnostics)
        self.stack.addWidget(self.mode_selection)

        if recent_project is None and self._draft_path is not None:
            recent_project = self._load_recent_project()
        if recent_project is not None:
            self.set_recent_project(recent_project)
        self.show_new_project(trigger="application_start")
        if self._update_client is not None:
            from v3_updater import UpdateController

            self._update_controller = UpdateController(
                self,
                self._update_client,
                self._diagnostic_journal,
            )

    def start_update_check(self) -> bool:
        if self._update_controller is None:
            return False
        return self._update_controller.start_check()

    def _runtime_settings(self) -> Mapping[str, Any]:
        base = dict(self._runtime_settings_provider() or {}) if self._runtime_settings_provider else {}
        base.update(self._v3_runtime_settings)
        return base

    def _show_api_settings(self) -> None:
        from v3_api_settings import ApiSettingsDialog
        dialog = ApiSettingsDialog(initial=self._runtime_settings(), parent=self.shell or self)
        if dialog.exec():
            self._v3_runtime_settings.update(dialog.settings)
            from runtime_settings import normalize_provider_concurrency

            updated_provider_concurrency = False
            for key in ("kie_concurrency", "photoroom_concurrency"):
                if key in dialog.settings:
                    self._preferences[key] = normalize_provider_concurrency(
                        dialog.settings.get(key)
                    )
                    updated_provider_concurrency = True
            if updated_provider_concurrency:
                if self._preferences_path is not None:
                    try:
                        save_preferences_atomic(
                            self._preferences_path,
                            self._preferences,
                        )
                    except OSError:
                        pass
            self._diagnostic_event(
                "api_settings_saved",
                "Настройки API сохранены.",
                details={
                    "configured": {
                        "kie": bool(dialog.settings.get("kie_api_key")),
                        "photoroom": bool(dialog.settings.get("photoroom_api_key")),
                    }
                },
            )
            if self.shell is not None:
                self.shell.state_changed.emit()

    def _show_diagnostics(self) -> None:
        if self._diagnostic_journal is None:
            QMessageBox.warning(
                self.shell or self,
                "Журнал диагностики",
                "Журнал диагностики недоступен.",
            )
            return
        from v3_diagnostics import DiagnosticJournalDialog

        dialog = DiagnosticJournalDialog(
            self._diagnostic_journal,
            parent=self.shell or self,
        )
        self._diagnostics_dialog = dialog
        dialog.show()

    def _diagnostic_event(self, event: str, summary: str, **fields: Any) -> None:
        if self._diagnostic_journal is None:
            return
        self._diagnostic_journal.record(event, summary, **fields)

    def _show_license(self) -> None:
        if self._license_gate is None:
            QMessageBox.warning(
                self.shell or self,
                "Лицензия",
                "Лицензионный сервис не настроен",
            )
            return
        dialog = LicenseDialog(self._license_gate, parent=self.shell or self)
        result = dialog.exec()
        self._diagnostic_event(
            "license_dialog_closed",
            "Окно лицензии закрыто.",
            outcome="accepted" if result else "cancelled",
        )
        self.refresh_license_status()

    def refresh_license_status(self) -> None:
        status = "Лицензия не активирована"
        verification = "Онлайн-проверка не выполнена"
        if self._license_gate is not None:
            status = self._license_gate.status_text
            verification = self._license_gate.verification_text
        self.mode_selection.set_license_status(status, verification)

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

    def _set_application_screen(self, widget: QWidget, screen: str, status: str) -> None:
        preserved_size = self.size()
        preserve_window_state = self.isMaximized() or self.isFullScreen()
        self.stack.setCurrentWidget(widget)
        if not preserve_window_state:
            self.resize(preserved_size)
        self.screen_changed.emit(screen)
        self._diagnostic_event(
            "screen_changed",
            "Изменился экран приложения.",
            screen=screen,
            details={"status": status},
        )

    def show_new_project(self, *, trigger: str = "new_project_requested") -> None:
        self._selection_intent = SelectionIntent.NEW_PROJECT
        self.mode_selection.reset_selection()
        self.mode_selection.set_mode_switch_context(False)
        self.mode_selection.set_recent_project_summary(self._recent_project)
        self.refresh_license_status()
        self._set_application_screen(self.mode_selection, "mode_selection", trigger)

    def show_mode_switcher(self) -> None:
        if self.shell is None:
            self.show_new_project()
            return
        if self.shell.active_run_controller() is not None:
            self.shell.set_save_error(
                "Сначала остановите текущее задание или дождитесь его завершения."
            )
            self._diagnostic_event(
                "mode_switch_blocked",
                "Смена режима заблокирована во время выполнения задания.",
                screen="wizard",
            )
            return
        self._selection_intent = SelectionIntent.SWITCH_MODE
        self.mode_selection.reset_selection()
        self.mode_selection.set_mode_switch_context(True)
        self.mode_selection.set_recent_project_summary(None)
        self._set_application_screen(
            self.mode_selection,
            "mode_selection",
            "mode_switch_requested",
        )

    def cancel_mode_switch(self) -> bool:
        if self.shell is None:
            return False
        self.mode_selection.set_mode_switch_context(False)
        self._set_application_screen(
            self.shell,
            "wizard",
            "mode_switch_cancelled",
        )
        return True

    def _handle_mode_selected(self, mode_value: str) -> None:
        mode = ProjectMode(mode_value)
        self._diagnostic_event(
            "mode_selected",
            "Выбран режим работы.",
            screen="mode_selection",
            details={"mode": mode.value},
        )
        if (
            self._selection_intent is SelectionIntent.SWITCH_MODE
            and self.shell is not None
        ):
            if self.shell.active_run_controller() is not None:
                self._set_application_screen(
                    self.shell,
                    "wizard",
                    "workflow_still_running",
                )
                return
            controller = self._ensure_mode_controller(self.shell, mode)
            if self.shell.state.mode is not mode:
                self.shell.request_mode_switch(mode)
            if not controller.run_queue.reset_for_new_workflow():
                self._set_application_screen(
                    self.shell,
                    "wizard",
                    "workflow_still_running",
                )
                return
            controller.start_processing_again()
            self._set_application_screen(
                self.shell,
                "wizard",
                "workflow_restarted",
            )
            return

        state = ProjectState(mode=mode)
        self._apply_preferences(state, mode)
        self._replace_shell(state)
        self.new_project_started.emit(mode.value)

    def continue_last_project(self) -> bool:
        if self._recent_project is None:
            return False
        state = ProjectState.from_dict(self._recent_project.to_dict())
        self._replace_shell(state)
        self._diagnostic_event(
            "project_continued",
            "Продолжен последний черновик.",
            details={"mode": state.mode.value},
        )
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

    def _load_preferences(self) -> dict[str, Any]:
        return load_preferences(self._preferences_path)

    def _apply_preferences(self, state: ProjectState, mode: ProjectMode) -> None:
        data = self._preferences.get(mode.value, {})
        if not isinstance(data, dict):
            data = {}
        use_legacy = not data and self._legacy_project is not None
        if use_legacy:
            if mode is ProjectMode.PROCESSING:
                state.processing.operations = state.processing.operations.from_dict(
                    self._legacy_project.processing.operations.to_dict()
                )
            elif mode is ProjectMode.CLIPART:
                state.clipart.operations = state.clipart.operations.from_dict(
                    self._legacy_project.clipart.operations.to_dict()
                )
        work_dir = str(self._preferences.get("last_work_dir", "")).strip()
        if not work_dir and use_legacy:
            work_dir = str(self._legacy_project.common.work_dir).strip()
        work_path = Path(work_dir).expanduser() if work_dir else default_work_directory()
        if not work_path.is_dir() or not os.access(work_path, os.W_OK):
            work_path = default_work_directory()
            try:
                work_path.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        state.common.work_dir = str(work_path)
        if mode is ProjectMode.PROCESSING:
            state.processing.recipe = str(data.get("recipe", "custom"))
            state.processing.overwrite_existing = bool(data.get("overwrite_existing", False))
            state.processing.deep_watermark_consent = bool(data.get("deep_watermark_consent", False))
            operations = data.get("operations")
            if isinstance(operations, dict):
                state.processing.operations = state.processing.operations.from_dict(operations)
        elif mode is ProjectMode.CLIPART and isinstance(data.get("operations"), dict):
            restored = state.clipart.operations.__class__.from_dict(data["operations"])
            state.clipart.operations = restored
        if mode in {ProjectMode.CLIPART, ProjectMode.PINTEREST}:
            output_dir = str(work_path / "output")
        else:
            output_dir = str(resolve_output_directory(
                work_path,
                data.get("output_dir") or self._preferences.get("last_output_dir"),
            ))
        state.set_output_dir_for_mode(output_dir, mode)

    def _save_preferences(self) -> bool:
        path = self._preferences_path
        if path is None or self.shell is None:
            return True
        state = self.shell.state
        work_dir = state.common.work_dir.strip()
        if work_dir and Path(work_dir).expanduser().is_dir():
            self._preferences["last_work_dir"] = work_dir
        output_dir = state.output_dir_for_mode(state.mode).strip()
        if state.mode is ProjectMode.PROCESSING and output_dir:
            self._preferences["last_output_dir"] = output_dir
        if state.mode is ProjectMode.PROCESSING:
            payload = {
                "output_dir": state.output_dir_for_mode(state.mode),
                "recipe": state.processing.recipe,
                "overwrite_existing": state.processing.overwrite_existing,
                "deep_watermark_consent": state.processing.deep_watermark_consent,
                "operations": state.processing.operations.to_dict(),
            }
        elif state.mode is ProjectMode.CLIPART:
            payload = {"output_dir": state.output_dir_for_mode(state.mode), "operations": state.clipart.operations.to_dict()}
        else:
            # Pinterest Pins has its own generation/pin schema and no legacy
            # processing operations. Keep only the shared folder preference.
            payload = {"output_dir": state.output_dir_for_mode(state.mode)}
        self._preferences[state.mode.value] = payload
        try:
            save_preferences_atomic(path, self._preferences)
        except OSError:
            return False
        return True

    def _save_draft(self) -> None:
        path = self._draft_path
        if path is None or self.shell is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            save_project_draft(self.shell.state, path)
            preferences_saved = self._save_preferences()
        except (OSError, ProjectStateError):
            self.shell.set_save_error("Не удалось сохранить изменения")
            return
        self.shell.set_save_error(
            None if preferences_saved else "Не удалось сохранить изменения"
        )

    def _replace_shell(self, state: ProjectState) -> None:
        previous = self.shell
        if previous is not None:
            previous.state_changed.disconnect(self._save_draft)
            self.stack.removeWidget(previous)
            previous.deleteLater()

        shell = AppShell(state, tokens=self.tokens)
        shell.diagnostic_journal = self._diagnostic_journal
        shell.initialization_stage.connect(self._show_initialization_stage)
        self._ensure_mode_controller(shell, state.mode)
        shell.state_changed.connect(self._save_draft)
        shell.step_changed.connect(self._record_workflow_step)
        shell.mode_picker_requested.connect(self.show_mode_switcher)
        shell.api_settings_requested.connect(self._show_api_settings)
        shell.diagnostics_requested.connect(self._show_diagnostics)
        shell.finish_requested.connect(self._finish_workflow)
        self.shell = shell
        self.stack.addWidget(shell)
        self._set_application_screen(shell, "wizard", "project_opened")
        self._save_draft()

    def _ensure_mode_controller(self, shell: AppShell, mode: ProjectMode) -> Any:
        attribute_by_mode = {
            ProjectMode.CLIPART: "clipart_flow_controller",
            ProjectMode.PINTEREST: "pinterest_flow_controller",
            ProjectMode.PROCESSING: "processing_flow_controller",
        }
        attribute = attribute_by_mode[mode]
        existing = getattr(shell, attribute, None)
        if existing is not None:
            return existing

        installer_by_mode = {
            ProjectMode.CLIPART: install_clipart_flow,
            ProjectMode.PINTEREST: install_pinterest_flow,
            ProjectMode.PROCESSING: install_processing_flow,
        }
        installer_kwargs = {
            "runtime_settings_provider": self._runtime_settings,
            "worker_factory": self._worker_factory,
            "authorization_provider": (
                self._license_gate.authorize_run
                if self._license_gate is not None
                else None
            ),
        }
        if mode is ProjectMode.PINTEREST:
            installer_kwargs["locale"] = app_locale_from_settings(self._preferences)
        controller = installer_by_mode[mode](
            shell,
            **installer_kwargs,
        )
        return controller

    def _show_initialization_stage(
        self,
        label: str,
        completed: int,
        total: int,
    ) -> None:
        if self._initialization_overlay is None:
            self._initialization_overlay = InitializationProgressOverlay(
                self.shell or self
            )
        stage = InitializationStage(label, completed, total)
        overlay = self._initialization_overlay
        overlay.update_stage(stage)
        if completed < total:
            overlay.show()
            QApplication.processEvents(
                QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                | QEventLoop.ProcessEventsFlag.ExcludeSocketNotifiers
            )
        if completed == total:
            overlay.close()
            overlay.deleteLater()
            self._initialization_overlay = None


    def closeEvent(self, event) -> None:
        self._diagnostic_event(
            "application_exit",
            "Приложение закрыто штатно.",
            outcome="success",
        )
        if self._diagnostic_journal is not None:
            self._diagnostic_journal.close()
        super().closeEvent(event)

    def _finish_workflow(self, _mode: str) -> None:
        """Return to mode selection without reusing the completed shell."""
        self._diagnostic_event(
            "workflow_finished",
            "Пользователь завершил работу с экраном результатов.",
            screen="results",
            outcome="success",
            details={
                "mode": _mode,
                "status": "explicit_user_action",
            },
        )
        self.show_new_project(trigger="workflow_finished")

    def _record_workflow_step(self, mode: str, step: str) -> None:
        self._diagnostic_event(
            "workflow_step_changed",
            "Открыт следующий этап рабочего процесса.",
            screen=step,
            details={"mode": mode, "stage": step},
        )
