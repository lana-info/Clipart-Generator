from __future__ import annotations

import os
import sys
import weakref
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QEventLoop, QStandardPaths, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QMenu,
    QScrollArea,
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
from v3_project_state import (
    ProjectStateError, V3ProjectDocumentAdapter, load_project_draft, save_project_draft,
)
from studio_projects import ProjectStore
from studio_project_documents import ProjectDocumentService
from studio_catalog import CatalogEntry, ModuleAvailability, card_action
from studio_catalog_ui import BUILTIN_CATALOG, StudioCatalogCard, catalog_artwork
from studio_workflow_registry import WorkflowRegistry, discover_workflows
from studio_workflow_host import WorkflowHost
from studio_module_access import authorize_module_run
from v3_localization import app_locale_from_settings
from v3_lazy_loading import InitializationProgressOverlay, InitializationStage
from v3_license import LicenseDialog, OnlineLicenseGate
from license_client import LicenseError
from v3_wizard import AppShell, MODE_TITLES, STEP_TITLES
from app_identity import APP_NAME, APP_STORAGE_NAME
from config_schema import load_preferences, resolve_output_directory, save_preferences_atomic


@dataclass(frozen=True)
class ModeCardSpec:
    title: str
    description: str
    result: str


MODE_CARD_SPECS: dict[ProjectMode, ModeCardSpec] = {
    ProjectMode.CLIPART: ModeCardSpec(
        title="Генерация изображений",
        description=(
            "Массово создавайте изображения в нейросетях, включая "
            "согласованные серии клипартов, с гибкой генерацией и обработкой."
        ),
        result="серия готовых изображений, в том числе PNG-клипартов",
    ),
    ProjectMode.PINTEREST: ModeCardSpec(
        title="Pinterest",
        description=(
            "Создавайте только готовые вертикальные изображения по промптам — "
            "без публикации, редактора макетов и обязательного текста поверх."
        ),
        result="пакет изображений Pinterest-пинов",
    ),
    ProjectMode.PROCESSING: ModeCardSpec(
        title="Обработка изображений",
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
    return Path(pictures).expanduser() / APP_STORAGE_NAME


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
    project_requested = pyqtSignal(str)
    all_projects_requested = pyqtSignal()
    module_action_requested = pyqtSignal(str, str)
    module_updates_requested = pyqtSignal()

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        self.tokens = tokens
        self.mode_cards: dict[ProjectMode, ModeCard] = {}
        self.module_cards: dict[str, StudioCatalogCard] = {}

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
        layout.setSpacing(tokens.space_3)

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
        self.diagnostics_button = V3Button("Диагностика", ButtonVariant.GHOST)
        self.diagnostics_button.clicked.connect(self.diagnostics_requested.emit)
        account_layout.addWidget(self.diagnostics_button)
        layout.addWidget(self.account_card)

        title = QLabel("Модули")
        title.setProperty("v3Title", True)
        title.setAccessibleName(title.text())
        catalog_heading = QHBoxLayout()
        catalog_heading.addWidget(title)
        catalog_heading.addStretch()
        self.module_updates_button = V3Button("Обновления модулей", ButtonVariant.SECONDARY)
        self.module_updates_button.clicked.connect(self.module_updates_requested.emit)
        catalog_heading.addWidget(self.module_updates_button)
        layout.addLayout(catalog_heading)

        self.cards_container = QWidget()
        cards_layout = QGridLayout(self.cards_container)
        self.cards_layout = cards_layout
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(tokens.space_3)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for column in range(3):
            cards_layout.setColumnStretch(column, 1)
        for mode in (ProjectMode.CLIPART, ProjectMode.PROCESSING, ProjectMode.PINTEREST):
            spec = MODE_CARD_SPECS[mode]
            card = ModeCard(
                mode.value,
                spec.title,
                spec.description,
                spec.result,
                tokens=tokens,
                illustration_path=(catalog_artwork("generation") if mode is ProjectMode.CLIPART
                                   else mode_illustration_path(mode)),
                compact=True,
            )
            card.description_label.setText({
                ProjectMode.CLIPART: "Изображения и серии по промптам",
                ProjectMode.PROCESSING: "Фон, качество и прозрачность",
                ProjectMode.PINTEREST: "Пины по промптам, без публикации",
            }[mode])
            card.selected.connect(self._select_mode)
            card.setSizePolicy(
                QSizePolicy.Policy.Ignored,
                QSizePolicy.Policy.Expanding,
            )
            self.mode_cards[mode] = card
        self.catalog_scroll = QScrollArea()
        self.catalog_scroll.setWidgetResizable(True)
        self.catalog_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.catalog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.catalog_scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.catalog_scroll.setWidget(self.cards_container)
        layout.addWidget(self.catalog_scroll, 1)
        self.set_module_catalog(BUILTIN_CATALOG)

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
        layout.insertWidget(1, self.recent_project_card)

        self.saved_projects_card = QFrame()
        self.saved_projects_card.setProperty("v3Card", True)
        saved_layout = QVBoxLayout(self.saved_projects_card)
        saved_layout.setContentsMargins(10, 6, 10, 6)
        saved_layout.setSpacing(4)
        saved_heading = QHBoxLayout()
        heading = QLabel("Продолжить работу")
        saved_heading.addWidget(heading, 1)
        self.all_projects_button = V3Button("Все проекты", ButtonVariant.GHOST)
        self.all_projects_button.clicked.connect(self.all_projects_requested.emit)
        saved_heading.addWidget(self.all_projects_button)
        saved_layout.addLayout(saved_heading)
        self.saved_projects_layout = QHBoxLayout()
        saved_layout.addLayout(self.saved_projects_layout)
        self.saved_project_buttons: list[V3Button] = []
        self.saved_projects_card.hide()
        layout.insertWidget(1, self.saved_projects_card)
        from studio_news_ui import StudioNewsPanel
        self.news_panel = StudioNewsPanel()
        self.news_label = self.news_panel.body
        layout.insertWidget(2, self.news_panel)

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

    def set_module_catalog(self, entries, availability=None) -> None:
        """Render trusted catalog metadata; emitting intent never grants access."""
        entries = tuple(entries)
        if not all(isinstance(entry, CatalogEntry) for entry in entries):
            raise TypeError("Catalog entries must be CatalogEntry values")
        if len({entry.module_id for entry in entries}) != len(entries):
            raise ValueError("Duplicate catalog module")
        availability = availability or {}
        # Validate the entire replacement before disturbing the visible catalog.
        for entry in entries:
            card_action(entry, availability.get(entry.module_id, ModuleAvailability()))
        for card in self.module_cards.values():
            self.cards_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.module_cards = {}
        for entry in entries:
            card = StudioCatalogCard(entry, availability.get(entry.module_id, ModuleAvailability()),
                                     tokens=self.tokens)
            card.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            card.action_requested.connect(self.module_action_requested.emit)
            self.module_cards[entry.module_id] = card
        while self.cards_layout.count():
            self.cards_layout.takeAt(0)
        cards = [self.mode_cards[ProjectMode.CLIPART], self.mode_cards[ProjectMode.PROCESSING]]
        modules = list(self.module_cards.values())
        cards.extend(modules[:2])
        cards.append(self.mode_cards[ProjectMode.PINTEREST])
        cards.extend(modules[2:])
        for index, card in enumerate(cards):
            self.cards_layout.addWidget(card, index // 3, index % 3)

    def set_saved_projects(self, projects: list) -> None:
        while self.saved_projects_layout.count():
            item = self.saved_projects_layout.takeAt(0)
            item.widget().hide()
            item.widget().deleteLater()
        self.saved_project_buttons = []
        for project in projects[:3]:
            title = {"auto-clipart": "Автоматический Clipart", "clipart": "Генерация изображений",
                     "processing": "Обработка изображений", "pinterest": "Pinterest"}.get(project.module_id, project.module_id)
            button = V3Button(f"{project.name}\n{title} · {project.updated_at[:16].replace('T', ' ')}", ButtonVariant.SECONDARY)
            button.setMinimumHeight(64)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            button.setToolTip(f"{project.name}\n{project.updated_at}")
            button.setAccessibleName(f"Продолжить проект: {project.name}")
            button.clicked.connect(
                lambda _checked=False, project_id=project.project_id:
                self.project_requested.emit(project_id)
            )
            self.saved_projects_layout.addWidget(button, 1)
            self.saved_project_buttons.append(button)
        self.saved_projects_card.setVisible(bool(projects))

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
        workflow_registry: WorkflowRegistry | None = None,
        module_delivery: Any | None = None,
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
        self._module_delivery = module_delivery
        self._module_updates_dialog = None
        self._legacy_project = legacy_project
        workflow_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "studio_builtin_workflows"
        self._workflow_registry = workflow_registry or discover_workflows(workflow_root)
        self._project_state_extensions = self._workflow_registry.project_state_extensions()
        self._update_controller = None
        self._initialization_overlay: InitializationProgressOverlay | None = None
        self._draft_path = Path(draft_path) if draft_path is not None else None
        self._project_store = None
        self._project_documents = None
        self._project_store_unavailable = False
        if self._draft_path is not None:
            try:
                self._project_store = ProjectStore(self._draft_path.parent / "projects")
                self._project_documents = ProjectDocumentService(
                    self._project_store,
                    tuple(
                        V3ProjectDocumentAdapter(
                            mode.value, extensions=self._project_state_extensions
                        )
                        for mode in ProjectMode
                    ) + (
                        V3ProjectDocumentAdapter("auto-clipart", extensions=self._project_state_extensions),
                    ),
                )
            except (OSError, ValueError):
                self._project_store_unavailable = True
        self._active_project_id: str | None = None
        self._recent_saved_project_id: str | None = None
        self._preferences_path = (
            self._draft_path.with_name("preferences.json")
            if self._draft_path is not None else None
        )
        self._preferences = self._load_preferences()
        from runtime_settings import normalize_provider_concurrency

        for key in ("kie_concurrency", "photoroom_concurrency", "fal_concurrency"):
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
        self.mode_selection.module_updates_button.setVisible(module_delivery is not None)
        self.mode_selection.module_updates_requested.connect(self._show_module_updates)
        self.mode_selection.mode_selected.connect(self._handle_mode_selected)
        self.mode_selection.module_action_requested.connect(self._handle_module_action)
        self.mode_selection.continue_last_project_requested.connect(
            self.continue_last_project
        )
        self.mode_selection.cancel_requested.connect(self.cancel_mode_switch)
        self.mode_selection.license_requested.connect(self._show_license)
        self.mode_selection.api_settings_requested.connect(self._show_api_settings)
        self.mode_selection.diagnostics_requested.connect(self._show_diagnostics)
        self.mode_selection.project_requested.connect(self.continue_saved_project)
        self.mode_selection.all_projects_requested.connect(self._show_all_projects)
        self.stack.addWidget(self.mode_selection)
        from studio_news import StudioNewsClient
        from studio_news_ui import StudioNewsController
        news_client = getattr(module_delivery, 'news', None)
        self._news_controller = (StudioNewsController(news_client, self.mode_selection.news_panel, self)
                                 if isinstance(news_client, StudioNewsClient) else None)

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

    def _show_module_updates(self):
        if self._module_delivery is None:
            return
        from studio_module_update_ui import ModuleUpdatesDialog
        if self._module_updates_dialog is None:
            self._module_updates_dialog = ModuleUpdatesDialog(
                self._module_delivery, parent=self,
                busy_module=lambda module: self.shell is not None and self.shell.workflow_controller(module) is not None,
            )
            self._module_updates_dialog.finished.connect(self.refresh_license_status)
        self._module_updates_dialog.open()

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
            for key in ("kie_concurrency", "photoroom_concurrency", "fal_concurrency"):
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
                        "fal": bool(dialog.settings.get("fal_api_key")),
                        "runpod": bool(dialog.settings.get("runpod_api_key")),
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
        from license_client import LicenseAuthorization
        authorization = getattr(self._license_gate, "current_authorization", None)
        if isinstance(authorization, LicenseAuthorization):
            deadline = authorization.grace_expires_at if authorization.is_offline_grace else authorization.expires_at
            if deadline is None or datetime.now(timezone.utc) >= deadline:
                authorization = None
        card = self.mode_selection.module_cards.get("auto-clipart")
        if card is not None:
            installed = "auto-clipart" in self._workflow_registry.module_ids
            compatible = True
            if self._module_delivery is not None:
                try:
                    if self._module_delivery.has_active_workflow("auto-clipart"):
                        installed = self._module_delivery.store.verified_active_path("auto-clipart") is not None
                except (OSError, ValueError):
                    compatible = False
            card.set_availability(ModuleAvailability(
                installed=installed, open_supported=installed, compatible=compatible,
                download_supported=self._module_delivery is not None,
                update_available=bool(self._module_updates_dialog is not None
                    and "auto-clipart" in self._module_updates_dialog.releases),
                entitlement_known=isinstance(authorization, LicenseAuthorization),
                entitled=isinstance(authorization, LicenseAuthorization)
                and authorization.allows_module("auto-clipart"),
            ))

    def _handle_module_action(self, module_id: str, action: str) -> None:
        if module_id == "auto-clipart" and action in {"update", "download"}:
            self._show_module_updates()
            return
        if module_id == "auto-clipart" and action == "verify":
            if self._license_gate is not None:
                try:
                    self._license_gate.authorize_run()
                except LicenseError as exc:
                    QMessageBox.warning(self, "Доступ к модулю", str(exc))
                self.refresh_license_status()
            return
        if module_id != "auto-clipart" or action != "open":
            return
        if not self._save_automatic_before_leaving():
            return
        if self.shell is not None and self.shell.active_run_controller() is not None:
            return
        state = ProjectState(mode=ProjectMode.CLIPART)
        self._apply_preferences(state, ProjectMode.CLIPART)
        previous = self._active_project_id
        self._active_project_id = None
        if not self._replace_shell(state, module_id=module_id):
            self._active_project_id = previous
            return
        self.new_project_started.emit(module_id)

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
        if not self._save_automatic_before_leaving():
            return
        self._selection_intent = SelectionIntent.NEW_PROJECT
        self.mode_selection.reset_selection()
        self.mode_selection.set_mode_switch_context(False)
        self.mode_selection.set_recent_project_summary(self._recent_project)
        self._refresh_saved_projects()
        self.refresh_license_status()
        self._set_application_screen(self.mode_selection, "mode_selection", trigger)

    def show_mode_switcher(self) -> None:
        if not self._save_automatic_before_leaving():
            return
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
        self.mode_selection.set_mode_switch_context(False)
        self.mode_selection.set_recent_project_summary(None)
        self._refresh_saved_projects()
        self.refresh_license_status()
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
        if not self._save_automatic_before_leaving():
            return
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
            and getattr(self.shell, "module_id", None) != "auto-clipart"
        ):
            if self.shell.active_run_controller() is not None:
                self._set_application_screen(
                    self.shell,
                    "wizard",
                    "workflow_still_running",
                )
                return
            controller = self._try_ensure_mode_controller(self.shell, mode)
            if controller is None:
                return
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
        previous_project_id = self._active_project_id
        self._active_project_id = None
        if not self._replace_shell(state):
            self._active_project_id = previous_project_id
            return
        self.new_project_started.emit(mode.value)

    def continue_last_project(self) -> bool:
        if self._recent_saved_project_id is not None:
            return self.continue_saved_project(self._recent_saved_project_id)
        if self._recent_project is None:
            return False
        state = ProjectState.from_dict(self._recent_project.to_dict())
        if not self._replace_shell(state):
            return False
        self._diagnostic_event(
            "project_continued",
            "Продолжен последний черновик.",
            details={"mode": state.mode.value},
        )
        self.project_continued.emit(state.mode.value)
        return True

    def _refresh_saved_projects(self) -> None:
        if self._project_store is None:
            return
        try:
            records = self._project_store.recent()
        except (OSError, ValueError):
            records = []
        self.mode_selection.set_saved_projects(records)
        self._recent_saved_project_id = records[0].project_id if records else None
        if records:
            self.mode_selection.recent_project_card.hide()

    def continue_saved_project(self, project_id: str) -> bool:
        if not self._save_automatic_before_leaving():
            return False
        if self._project_store is None:
            return False
        if self.shell is not None and self.shell.active_run_controller() is not None:
            self.shell.set_save_error("Сначала остановите текущее задание.")
            return False
        try:
            if self._project_documents is None:
                raise ValueError("Project document service is unavailable")
            session = self._project_documents.open(project_id)
            if not session.editable:
                raise ValueError("Project document is read-only")
            state = ProjectState.from_dict(session.state)
            if (session.record.module_id == "auto-clipart"
                    and session.state.get("current_step_by_mode", {}).get("clipart") == "transparency"):
                state.set_step("transparency")
        except (OSError, ValueError):
            QMessageBox.warning(self, "Проект", "Не удалось открыть сохранённый проект.")
            return False
        previous_project_id = self._active_project_id
        self._active_project_id = session.record.project_id
        if not self._replace_shell(state, module_id=session.record.module_id):
            self._active_project_id = previous_project_id
            return False
        self.project_continued.emit(session.record.module_id)
        return True

    def _show_all_projects(self) -> None:
        if self._project_store is None:
            return
        menu = QMenu(self)
        try:
            records = self._project_store.recent(limit=None)
        except (OSError, ValueError):
            QMessageBox.warning(self, "Проекты", "Не удалось прочитать список проектов.")
            return
        for record in records:
            action = menu.addAction(record.name.replace("&", "&&"))
            action.triggered.connect(
                lambda _checked=False, project_id=record.project_id:
                self.continue_saved_project(project_id)
            )
        if not records:
            menu.addAction("Нет сохранённых проектов").setEnabled(False)
        button = self.mode_selection.all_projects_button
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))
        menu.deleteLater()

    def _load_recent_project(self) -> ProjectState | None:
        path = self._draft_path
        if path is None or not path.is_file():
            return None
        try:
            return load_project_draft(
                path, extensions=self._project_state_extensions
            )
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

    def _save_automatic_before_leaving(self) -> bool:
        if self.shell is None or getattr(self.shell, "module_id", None) != "auto-clipart":
            return True
        controller = self.shell.workflow_controller("auto-clipart")
        if controller is not None and controller.is_busy():
            self.shell.set_save_error("Дождитесь завершения текущего задания или остановите его.")
            return False
        return self._save_draft()

    def _save_draft(self) -> bool:
        path = self._draft_path
        if path is None or self.shell is None:
            return True
        try:
            module_id = getattr(self.shell, "module_id", self.shell.state.mode.value)
            controller = self.shell.workflow_controller(module_id)
            if module_id == "auto-clipart" and controller is not None:
                controller.flush()
            path.parent.mkdir(parents=True, exist_ok=True)
            if self._project_store is not None:
                if self._project_documents is None:
                    raise ValueError("Project document service is unavailable")
                state = self.shell.state
                name = state.common.project_name.strip() or "Без названия"
                if self._active_project_id is None:
                    record = self._project_documents.create(
                        module_id, "project", name, state.to_dict()
                    )
                    self._active_project_id = record.project_id
                else:
                    self._project_documents.save(
                        self._active_project_id, name, state.to_dict()
                    )
            # The separate project is authoritative. Never write a newer legacy
            # draft first, then hide it behind an older project after a failure.
            if module_id != "auto-clipart":
                save_project_draft(
                    self.shell.state, path, extensions=self._project_state_extensions
                )
                preferences_saved = self._save_preferences()
                self._recent_project = ProjectState.from_dict(self.shell.state.to_dict())
            else:
                preferences_saved = True
        except (OSError, ValueError):
            self.shell.set_save_error("Не удалось сохранить изменения")
            return False
        self.shell.set_save_error(
            None if preferences_saved and not self._project_store_unavailable
            else "Не удалось сохранить изменения"
        )
        return bool(preferences_saved and not self._project_store_unavailable)

    def _prepare_project_run(self, shell: AppShell) -> str | None:
        if shell is not self.shell:
            raise ValueError("Откройте проект заново перед запуском")
        if self._draft_path is None:
            return None
        if self._project_store is None or self._project_documents is None:
            raise OSError("Не удалось сохранить проект. Проверьте доступ к папке приложения")
        # Save immediately before any run worker is created, including retries
        # and module-owned local workers. A failed save blocks the run.
        state = shell.state
        name = state.common.project_name.strip() or "Без названия"
        try:
            if self._active_project_id is None:
                record = self._project_documents.create(
                    getattr(shell, "module_id", state.mode.value), "project", name, state.to_dict()
                )
                self._active_project_id = record.project_id
            else:
                self._project_documents.save(
                    self._active_project_id, name, state.to_dict()
                )
        except (OSError, ValueError) as error:
            raise OSError("Не удалось сохранить проект. Запуск не начат") from error
        return self._active_project_id

    def _create_raw_project_worker(self, shell: AppShell, **kwargs: Any) -> Any:
        from v3_runtime_adapter import DEFAULT_LEGACY_RUNTIME_ADAPTER

        if shell is not self.shell:
            raise ValueError("Откройте проект заново перед запуском")
        factory = self._worker_factory or DEFAULT_LEGACY_RUNTIME_ADAPTER.create_worker
        from studio_processing_api import PROCESSING_CONSUMERS
        consumer = getattr(shell, "module_id", shell.state.mode.value)
        settings = kwargs.get("settings", {})
        lease = None
        if (self._module_delivery is not None and consumer in PROCESSING_CONSUMERS
                and settings.get("remove_bg")
                and settings.get("remove_bg_provider") == "local_chroma_key"):
            lease = self._module_delivery.acquire_processing_engine(consumer)
            kwargs["processing_engine"] = lease.engine
        try:
            worker = factory(**kwargs)
            if lease is not None:
                worker.finished.connect(lease.close)
                worker.destroyed.connect(lease.close)
            return worker
        except Exception:
            if lease is not None:
                lease.close()
            raise

    def _create_prepared_project_worker(
        self, shell: AppShell, **kwargs: Any
    ) -> Any:
        raw_worker = self._create_raw_project_worker(shell, **kwargs)
        from studio_job_services import CoreWorkerJobHandle
        if isinstance(raw_worker, CoreWorkerJobHandle):
            return raw_worker
        return CoreWorkerJobHandle(raw_worker)

    def _create_project_worker(self, shell: AppShell, **kwargs: Any) -> Any:
        project_id = self._prepare_project_run(shell)
        if project_id is not None:
            kwargs["project_id"] = project_id
        return self._create_prepared_project_worker(shell, **kwargs)

    def _replace_shell(self, state: ProjectState, *, module_id: str | None = None) -> bool:
        previous = self.shell
        if module_id == "auto-clipart":
            from license_client import LicenseError
            try:
                if self._license_gate is None:
                    raise LicenseError("Лицензия не настроена")
                authorize_module_run(self._license_gate, module_id)
            except LicenseError:
                QMessageBox.warning(self, "Clipart", "Нет доступа к автоматическому Clipart.")
                return False
            from studio_auto_clipart_shell import AutoClipartShell
            shell = AutoClipartShell(state, tokens=self.tokens)
        else:
            shell = AppShell(state, tokens=self.tokens)
        shell.diagnostic_journal = self._diagnostic_journal
        shell.initialization_stage.connect(self._show_initialization_stage)
        try:
            controller = self._try_ensure_mode_controller(shell, state.mode)
        except (ValueError, OSError):
            shell.deleteLater()
            if module_id != "auto-clipart":
                raise
            QMessageBox.warning(self, "Clipart", "Не удалось восстановить проект. Сохранённые данные не изменены.")
            return False
        if controller is None:
            shell.deleteLater()
            return False
        if previous is not None:
            previous.state_changed.disconnect(self._save_draft)
            self.stack.removeWidget(previous)
            previous.deleteLater()
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
        return True

    def _try_ensure_mode_controller(self, shell: AppShell, mode: ProjectMode):
        from license_client import LicenseError
        from studio_module_api import ModuleApiError
        from studio_modules import ModulePackageError
        try:
            return self._ensure_mode_controller(shell, mode)
        except (LicenseError, ModuleApiError, ModulePackageError):
            QMessageBox.warning(self, "Модуль", "Не удалось открыть модуль. Проверьте доступ и установленную версию.")
            return None

    def _ensure_mode_controller(self, shell: AppShell, mode: ProjectMode) -> Any:
        module_id = getattr(shell, "module_id", mode.value)
        existing = shell.workflow_controller(module_id)
        if existing is not None:
            return existing
        registration = self._workflow_registry.require(module_id)
        view_ref = weakref.ref(self)
        shell_ref = weakref.ref(shell)

        def create_worker(**kwargs):
            view = view_ref()
            scoped_shell = shell_ref()
            if view is None or scoped_shell is None:
                raise OSError("Core worker service is unavailable")
            return view._create_project_worker(scoped_shell, **kwargs)

        def prepare_run():
            view = view_ref()
            scoped_shell = shell_ref()
            if view is None or scoped_shell is None:
                raise OSError("Core run preparation service is unavailable")
            return view._prepare_project_run(scoped_shell)

        def create_prepared_worker(**kwargs):
            view = view_ref()
            scoped_shell = shell_ref()
            if view is None or scoped_shell is None:
                raise OSError("Core worker service is unavailable")
            return view._create_raw_project_worker(scoped_shell, **kwargs)

        def authorize_run():
            view = view_ref()
            if view is None:
                raise OSError("Core authorization service is unavailable")
            if view._license_gate is None:
                from license_client import LicenseError
                raise LicenseError("Лицензионный сервис не настроен")
            return authorize_module_run(view._license_gate, module_id)

        from studio_image_run_services import CoreImageRunGateway
        image_run_gateway = CoreImageRunGateway(
            runtime_settings_provider=self._runtime_settings,
            authorization_provider=authorize_run,
            run_preparer=prepare_run,
            worker_factory=create_prepared_worker,
        )

        host = WorkflowHost(
            shell,
            module_id,
            runtime_settings_provider=self._runtime_settings,
            worker_factory=create_worker,
            run_preparer=prepare_run,
            authorization_provider=authorize_run,
            image_run_gateway=image_run_gateway,
        )
        locale = app_locale_from_settings(self._preferences)
        if self._module_delivery is not None and self._module_delivery.has_active_workflow(module_id):
            controller = self._module_delivery.install_workflow(
                module_id, host, locale=locale, owner=shell,
            )
        else:
            controller = registration.install(host, locale=locale)
        shell.register_workflow_controller(module_id, controller)
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
        if self.shell is not None and getattr(self.shell, "module_id", None) == "auto-clipart":
            controller = self.shell.workflow_controller("auto-clipart")
            if controller is not None and controller.is_busy():
                event.ignore()
                return
            if not self._save_draft():
                event.ignore()
                return
        if self._module_updates_dialog is not None and self._module_updates_dialog.busy:
            event.ignore()
            return
        if self._news_controller is not None:
            self._news_controller.shutdown()
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
