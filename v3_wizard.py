from __future__ import annotations

from collections.abc import Callable, Mapping

from PyQt6.QtCore import Qt, pyqtSignal
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
    FormCard,
    V3Button,
    V3DesignTokens,
    V3_WINDOW_MINIMUM_SIZE,
    apply_v3_theme,
)
from app_identity import APP_NAME
from v3_project_state import (
    ProjectMode,
    ProjectState,
    ProjectStateValidationError,
    StepId,
    route_for_mode,
)
from workflow_definitions import WorkflowDefinition, workflow_for_mode


MODE_TITLES: dict[ProjectMode, str] = {
    ProjectMode.CLIPART: "Клипарт",
    ProjectMode.PINTEREST: "Pinterest-пины",
    ProjectMode.PROCESSING: "Обработка изображений",
}

STEP_TITLES: dict[StepId, str] = {
    StepId.PROJECT: "Рабочая папка",
    StepId.PROMPTS: "Промпты",
    StepId.PROMPT_REVIEW: "Проверка промптов",
    StepId.GENERATION: "Генерация",
    StepId.PROCESSING_OPTIONS: "Обработка",
    StepId.PIN_FORMAT_MODEL: "Формат и модель",
    StepId.FILES: "Файлы",
    StepId.GOAL: "Цель обработки",
    StepId.PIPELINE: "Обработка изображений",
    StepId.REVIEW_RUN: "Проверка и запуск",
    StepId.RESULTS: "Результаты",
    StepId.TRANSPARENCY: "Проверка прозрачности",
}

STEP_DESCRIPTIONS: dict[StepId, str] = {
    StepId.PROJECT: "Выберите рабочую папку для сохранения результатов.",
    StepId.PROMPTS: "Введите, вставьте, импортируйте или создайте список промптов.",
    StepId.PROMPT_REVIEW: "Проверьте и отредактируйте итоговую серию промптов.",
    StepId.GENERATION: "Выберите модель, пропорции, разрешение и варианты.",
    StepId.PROCESSING_OPTIONS: "Настройте операции над созданными изображениями.",
    StepId.PIN_FORMAT_MODEL: "Выберите вертикальный формат пинов и модель генерации.",
    StepId.FILES: "Добавьте изображения, которые нужно обработать.",
    StepId.GOAL: "Определите ожидаемый результат обработки.",
    StepId.PIPELINE: "Проверьте точный порядок включённых операций.",
    StepId.REVIEW_RUN: "Проверьте настройки, стоимость и ожидаемый результат.",
    StepId.RESULTS: "Просмотрите результаты и журнал выполненных операций.",
    StepId.TRANSPARENCY: "Проверьте и исправьте прозрачность готовых PNG.",
}

VALIDATION_MESSAGES: dict[str, str] = {
    "work_dir_required": "Выберите рабочую папку.",
    "work_dir_unavailable": "Рабочая папка недоступна для записи.",
    "prompts_required": "Добавьте хотя бы один промпт.",
    "prompt_empty": "Удалите или заполните пустые промпты.",
    "generation_model_required": "Выберите модель генерации.",
    "generation_ratio_required": "Выберите пропорции изображения.",
    "generation_resolution_required": "Выберите разрешение изображения.",
    "selected_files_required": "Добавьте хотя бы один исходный файл.",
    "invalid_selected_files": "Удалите недоступные или недопустимые файлы.",
    "processing_file_limit_exceeded": "Уменьшите пакет до 200 файлов.",
    "duplicate_output_names": "Файлы с одинаковыми именами создадут один путь результата. Переименуйте их.",
    "processing_operation_required": "Включите хотя бы одну операцию обработки.",
    "deep_watermark_consent_required": "Разрешите обработку скрытых водяных знаков только для этой операции.",
    "confirmed_area_unavailable": "Ручная область метки пока недоступна в этом интерфейсе.",
    "full_image_change_consent_required": "Подтвердите операцию, меняющую всё изображение.",
    "external_transfer_consent_required": "Подтвердите передачу файлов выбранному внешнему сервису.",
    "fal_cost_confirmation_required": "Подтвердите актуальную цену Fal.ai перед запуском.",
}


class WizardStepPage(FormCard):
    def __init__(
        self,
        mode: ProjectMode,
        step: StepId,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        workflow_definitions: Mapping[ProjectMode, WorkflowDefinition] | None = None,
    ) -> None:
        super().__init__(
            STEP_TITLES[step],
            STEP_DESCRIPTIONS[step],
            parent,
            tokens=tokens,
        )
        self.mode = mode
        self.step = step
        placeholder = QLabel("Содержимое шага будет подключено отдельной задачей.")
        placeholder.setProperty("v3Small", True)
        placeholder.setWordWrap(True)
        self.add_widget(placeholder)
        self.setAccessibleName(f"{MODE_TITLES[mode]} — {STEP_TITLES[step]}")


class AppShell(QWidget):
    step_changed = pyqtSignal(str, str)
    mode_changed = pyqtSignal(str)
    dirty_changed = pyqtSignal(bool)
    state_changed = pyqtSignal()
    validation_failed = pyqtSignal(str, object)
    unsaved_mode_switch_requested = pyqtSignal(str, str)
    mode_picker_requested = pyqtSignal()
    api_settings_requested = pyqtSignal()
    diagnostics_requested = pyqtSignal()
    run_requested = pyqtSignal(str)
    finish_requested = pyqtSignal(str)
    initialization_stage = pyqtSignal(str, int, int)

    def __init__(
        self,
        state: ProjectState | None = None,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        workflow_definitions: Mapping[ProjectMode, WorkflowDefinition] | None = None,
    ) -> None:
        super().__init__(parent)
        self.state = state if state is not None else ProjectState()
        self.tokens = tokens
        self._workflow_definitions = dict(workflow_definitions or {})
        for mode in ProjectMode:
            self._workflow_definitions.setdefault(mode, workflow_for_mode(mode))
            self.state.set_workflow_route(
                mode, self._workflow_definitions[mode].page_steps
            )
        self._dirty = False
        self._pending_mode: ProjectMode | None = None
        self._invalid_key: tuple[ProjectMode, StepId] | None = None
        self._run_request_key: tuple[ProjectMode, StepId] | None = None
        self._pages: dict[tuple[ProjectMode, StepId], QWidget] = {}
        self._workflow_controllers: dict[str, object] = {}
        self._page_factories: dict[
            tuple[ProjectMode, StepId], Callable[[], QWidget]
        ] = {}
        self.step_labels: list[QLabel] = []

        self.setMinimumSize(*V3_WINDOW_MINIMUM_SIZE)
        self.setObjectName("v3AppShell")
        self.setAccessibleName(f"{APP_NAME} 3.0")
        apply_v3_theme(self, tokens)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(
            tokens.space_6,
            tokens.space_6,
            tokens.space_6,
            tokens.space_6,
        )
        root_layout.setSpacing(tokens.space_4)

        self.top_bar = self._build_top_bar()
        root_layout.addWidget(self.top_bar)

        self.save_error_label = QLabel()
        self.save_error_label.setWordWrap(True)
        self.save_error_label.setProperty("v3Status", True)
        self.save_error_label.setProperty("state", "error")
        self.save_error_label.hide()
        root_layout.addWidget(self.save_error_label)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(tokens.space_4)

        self.sidebar = self._build_sidebar()
        body_layout.addWidget(self.sidebar)

        self.page_stack = QStackedWidget()
        self.page_stack.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        body_layout.addWidget(self.page_stack, 1)
        root_layout.addWidget(body, 1)

        self.mode_switch_banner = self._build_mode_switch_banner()
        root_layout.addWidget(self.mode_switch_banner)

        self.footer = self._build_footer()
        root_layout.addWidget(self.footer)

        self._create_default_pages()
        self.refresh()

    def register_workflow_controller(self, module_id: str, controller: object) -> None:
        if not isinstance(module_id, str) or not module_id or len(module_id) > 64:
            raise ValueError("Workflow module id is invalid")
        if controller is None:
            raise ValueError("Workflow controller is required")
        existing = self._workflow_controllers.get(module_id)
        if existing is not None and existing is not controller:
            raise RuntimeError("Workflow controller is already registered")
        self._workflow_controllers[module_id] = controller

    def workflow_controller(self, module_id: str) -> object | None:
        return self._workflow_controllers.get(module_id)

    def active_run_controller(self) -> object | None:
        """Return the one registered workflow controller that still owns an active run."""
        for controller in tuple(self._workflow_controllers.values()):
            worker = getattr(controller, "worker", None)
            adapter = getattr(controller, "runtime_adapter", None)
            is_running = getattr(adapter, "is_running", None)
            if worker is not None and callable(is_running):
                try:
                    if bool(is_running(worker)):
                        return controller
                except (RuntimeError, TypeError):
                    pass
            session = getattr(getattr(controller, "run_queue", None), "session", None)
            if session is not None and bool(getattr(session, "running", False)):
                return controller
        return None

    def another_run_is_active(self, controller: object) -> bool:
        active = self.active_run_controller()
        return active is not None and active is not controller

    def set_canvas_focus_mode(self, enabled: bool) -> None:
        """Temporarily maximize an editor canvas without changing OS fullscreen."""
        focused = bool(enabled)
        self.top_bar.setVisible(not focused)
        self.sidebar.setVisible(not focused)
        self.footer.setVisible(not focused)
        if focused:
            self.save_error_label.hide()
            self.mode_switch_banner.hide()
        else:
            self.save_error_label.setVisible(bool(self.save_error_label.text()))
            self.mode_switch_banner.setVisible(self._pending_mode is not None)
        self.updateGeometry()

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def pending_mode(self) -> ProjectMode | None:
        return self._pending_mode

    @property
    def current_page(self) -> QWidget:
        return self.ensure_step_page(self.state.mode, self.state.current_step)

    def workflow_definition(self, mode: ProjectMode | str | None = None) -> WorkflowDefinition:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode or self.state.mode)
        return self._workflow_definitions[normalized]

    def _card_frame(self) -> QFrame:
        frame = QFrame()
        frame.setProperty("v3Card", True)
        return frame

    def _build_top_bar(self) -> QFrame:
        frame = self._card_frame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            self.tokens.space_4,
            self.tokens.space_3,
            self.tokens.space_4,
            self.tokens.space_3,
        )
        layout.setSpacing(self.tokens.space_3)

        self.mode_label = QLabel()
        self.mode_label.setProperty("v3Title", True)
        layout.addWidget(self.mode_label)
        layout.addStretch()

        self.change_mode_button = V3Button(
            "Сменить режим",
            ButtonVariant.GHOST,
        )
        self.change_mode_button.clicked.connect(self.mode_picker_requested.emit)
        layout.addWidget(self.change_mode_button)
        self.api_settings_button = V3Button("Настройки API", ButtonVariant.GHOST)
        self.api_settings_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.api_settings_button.clicked.connect(self.api_settings_requested.emit)
        layout.addWidget(self.api_settings_button)
        self.diagnostics_button = V3Button("Диагностика", ButtonVariant.GHOST)
        self.diagnostics_button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.diagnostics_button.clicked.connect(self.diagnostics_requested.emit)
        layout.addWidget(self.diagnostics_button)
        return frame

    def set_save_error(self, message: str | None) -> None:
        normalized = str(message or "")[:200]
        self.save_error_label.setText(normalized)
        self.save_error_label.setAccessibleName(normalized)
        self.save_error_label.setVisible(bool(normalized))

    def _build_sidebar(self) -> QFrame:
        frame = self._card_frame()
        frame.setFixedWidth(240)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(
            self.tokens.space_4,
            self.tokens.space_4,
            self.tokens.space_4,
            self.tokens.space_4,
        )
        layout.setSpacing(self.tokens.space_3)

        title = QLabel("Шаги")
        title.setProperty("v3Title", True)
        layout.addWidget(title)

        self.steps_container = QWidget()
        self.steps_layout = QVBoxLayout(self.steps_container)
        self.steps_layout.setContentsMargins(0, 0, 0, 0)
        self.steps_layout.setSpacing(self.tokens.space_2)
        layout.addWidget(self.steps_container)
        layout.addStretch()
        return frame

    def _build_footer(self) -> QFrame:
        frame = self._card_frame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            self.tokens.space_4,
            self.tokens.space_3,
            self.tokens.space_4,
            self.tokens.space_3,
        )
        layout.setSpacing(self.tokens.space_3)

        self.validation_label = QLabel()
        self.validation_label.setProperty("v3Status", True)
        self.validation_label.setProperty("state", "error")
        self.validation_label.setWordWrap(True)
        self.validation_label.hide()
        layout.addWidget(self.validation_label, 1)
        layout.addStretch()

        self.back_button = V3Button("Назад", ButtonVariant.SECONDARY)
        self.back_button.clicked.connect(self.go_back)
        layout.addWidget(self.back_button)

        self.retry_page_button = V3Button(
            "Повторить открытие",
            ButtonVariant.SECONDARY,
        )
        self.retry_page_button.clicked.connect(self._retry_current_page)
        self.retry_page_button.hide()
        layout.addWidget(self.retry_page_button)

        self.next_button = V3Button("Далее", ButtonVariant.PRIMARY)
        self.next_button.clicked.connect(self.go_next)
        layout.addWidget(self.next_button)
        return frame

    def _build_mode_switch_banner(self) -> QFrame:
        frame = self._card_frame()
        frame.setProperty("state", "warning")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(
            self.tokens.space_4,
            self.tokens.space_3,
            self.tokens.space_4,
            self.tokens.space_3,
        )
        layout.setSpacing(self.tokens.space_3)

        self.mode_switch_label = QLabel()
        self.mode_switch_label.setProperty("v3Status", True)
        self.mode_switch_label.setProperty("state", "warning")
        self.mode_switch_label.setWordWrap(True)
        layout.addWidget(self.mode_switch_label, 1)

        self.stay_mode_button = V3Button("Остаться", ButtonVariant.SECONDARY)
        self.stay_mode_button.clicked.connect(
            lambda: self.resolve_pending_mode_switch(False)
        )
        layout.addWidget(self.stay_mode_button)

        self.continue_mode_button = V3Button("Продолжить", ButtonVariant.PRIMARY)
        self.continue_mode_button.clicked.connect(
            lambda: self.resolve_pending_mode_switch(True)
        )
        layout.addWidget(self.continue_mode_button)

        frame.hide()
        return frame

    def _create_default_pages(self) -> None:
        for mode in ProjectMode:
            for step in self.workflow_definition(mode).page_steps:
                page = WizardStepPage(mode, step, tokens=self.tokens)
                self._pages[(mode, step)] = page
                self.page_stack.addWidget(page)

    def set_step_page(
        self,
        mode: ProjectMode | str,
        step: StepId | str,
        page: QWidget,
    ) -> None:
        normalized_mode = (
            mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        )
        normalized_step = step if isinstance(step, StepId) else StepId(step)
        if normalized_step not in self.workflow_definition(normalized_mode).page_steps:
            raise ValueError(
                f"Step {normalized_step.value!r} is outside "
                f"{normalized_mode.value!r} route"
            )

        key = (normalized_mode, normalized_step)
        previous = self._pages[key]
        if page is previous:
            return
        if page in self._pages.values() or self.page_stack.indexOf(page) >= 0:
            raise ValueError("A wizard page can only be registered for one step")
        self.page_stack.removeWidget(previous)
        previous.deleteLater()
        self._pages[key] = page
        self.page_stack.addWidget(page)
        if key == (self.state.mode, self.state.current_step):
            self.page_stack.setCurrentWidget(page)

    def set_step_factory(
        self,
        mode: ProjectMode | str,
        step: StepId | str,
        factory: Callable[[], QWidget],
    ) -> None:
        normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        normalized_step = step if isinstance(step, StepId) else StepId(step)
        key = (normalized_mode, normalized_step)
        if normalized_step not in self.workflow_definition(normalized_mode).page_steps:
            raise ValueError("Page factory step is outside the mode route")
        if key in self._page_factories:
            raise ValueError("Page factory is already registered")
        self._page_factories[key] = factory

    def set_workflow_factory(
        self,
        mode: ProjectMode | str,
        step: StepId | str,
        factory: Callable[[], QWidget],
        *,
        component_id: str | None = None,
    ) -> None:
        """Register a page factory against the active definition contract."""

        normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        normalized_step = step if isinstance(step, StepId) else StepId(step)
        expected = self.workflow_definition(normalized_mode).page_for_step(
            normalized_step
        ).component_id
        if component_id is not None and str(component_id).strip() != expected:
            raise ValueError(
                f"Component {component_id!r} does not match workflow component {expected!r}"
            )
        self.set_step_factory(normalized_mode, normalized_step, factory)

    def ensure_step_page(
        self,
        mode: ProjectMode | str,
        step: StepId | str,
    ) -> QWidget:
        normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        normalized_step = step if isinstance(step, StepId) else StepId(step)
        key = (normalized_mode, normalized_step)
        factory = self._page_factories.get(key)
        if factory is not None:
            self.initialization_stage.emit(
                f"Открываем: {STEP_TITLES[normalized_step]}", 0, 1
            )
            try:
                page = factory()
            except Exception:
                self.initialization_stage.emit(
                    f"Не открыто: {STEP_TITLES[normalized_step]}", 1, 1
                )
                self.validation_label.setText(
                    "✕ Не удалось открыть страницу. Попробуйте ещё раз."
                )
                self.validation_label.setAccessibleName(
                    "Ошибка открытия страницы. Доступна повторная попытка."
                )
                self.validation_label.show()
                self.retry_page_button.show()
                return self._pages[key]
            self.set_step_page(normalized_mode, normalized_step, page)
            self._page_factories.pop(key, None)
            self.retry_page_button.hide()
            self.initialization_stage.emit(
                f"Открыто: {STEP_TITLES[normalized_step]}", 1, 1
            )
        return self._pages[key]

    def _retry_current_page(self) -> None:
        key = (self.state.mode, self.state.current_step)
        self.ensure_step_page(*key)
        if key not in self._page_factories:
            self._clear_validation()
            self.retry_page_button.hide()
            self.refresh()

    def refresh(self) -> None:
        self.mode_label.setText(MODE_TITLES[self.state.mode])
        self.mode_label.setAccessibleName(self.mode_label.text())
        self._refresh_stepper()
        self.page_stack.setCurrentWidget(self.current_page)
        self._refresh_footer()

    def _refresh_stepper(self) -> None:
        while self.steps_layout.count():
            item = self.steps_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.step_labels.clear()

        current_index = self.state.route.index(self.state.current_step)
        for index, step in enumerate(self.state.route):
            key = (self.state.mode, step)
            if key == self._invalid_key:
                marker = "✕"
                status = "Ошибка"
            elif index < current_index:
                marker = "✓"
                status = "Пройден"
            elif index == current_index:
                marker = "●"
                status = "Текущий"
            else:
                marker = "○"
                status = "Далее"

            label = QLabel(f"{marker} {index + 1}. {STEP_TITLES[step]}")
            label.setWordWrap(True)
            if status in {"Текущий", "Пройден"}:
                label.setProperty("v3Selection", True)
            elif status == "Ошибка":
                label.setProperty("v3Status", True)
                label.setProperty("state", "error")
            else:
                label.setProperty("v3Description", True)
            label.setAccessibleName(f"{STEP_TITLES[step]}: {status}")
            self.steps_layout.addWidget(label)
            self.step_labels.append(label)
        self.steps_layout.addStretch()

    def _refresh_footer(self) -> None:
        index = self.state.route.index(self.state.current_step)
        on_terminal_page = self.state.current_step in {
            StepId.RESULTS,
            StepId.TRANSPARENCY,
        }
        self.back_button.setVisible(not on_terminal_page)
        self.next_button.setVisible(not on_terminal_page)
        self.back_button.setEnabled(index > 0 and not on_terminal_page)

        if self.state.current_step is StepId.REVIEW_RUN:
            text = "Запустить"
        else:
            text = "Далее"
        self.next_button.setText(text)
        self.next_button.setAccessibleName(text)

    def mark_dirty(self) -> None:
        self._run_request_key = None
        if not self._dirty:
            self._dirty = True
            self.dirty_changed.emit(True)
        self.state_changed.emit()
        self.refresh()

    def mark_saved(self) -> None:
        if self._dirty:
            self._dirty = False
            self.dirty_changed.emit(False)
        self.refresh()

    def _clear_validation(self) -> None:
        self._invalid_key = None
        self.validation_label.clear()
        self.validation_label.hide()

    def _page_validation_issues(self) -> tuple[str, ...]:
        validator = getattr(self.current_page, "validation_issues", None)
        if not callable(validator):
            return ()
        issues = validator()
        if not isinstance(issues, tuple) or not all(
            isinstance(issue, str) and issue for issue in issues
        ):
            raise TypeError("Page validation must return a tuple of issue ids")
        return issues

    def _show_validation(self, issues: tuple[str, ...]) -> None:
        messages = tuple(
            VALIDATION_MESSAGES.get(issue, f"Проверьте поле: {issue}")
            for issue in issues
        )
        self._invalid_key = (self.state.mode, self.state.current_step)
        self.validation_label.setText("✕ " + " ".join(messages))
        self.validation_label.setAccessibleName(
            "Ошибка шага. " + " ".join(messages)
        )
        self.validation_label.show()
        self.validation_failed.emit(self.state.current_step.value, issues)
        self.refresh()

    def go_next(self) -> StepId:
        if self.state.current_step is StepId.RESULTS:
            # Results have their own terminal-only action.  Reusing this
            # focused button would turn the preceding "Запустить" input into
            # an accidental reset to mode selection.
            return self.state.current_step

        if self.state.current_step is StepId.REVIEW_RUN:
            self._run_request_key = None
            issues = (
                self.state.validation_issues()
                + self._page_validation_issues()
            )
            if issues:
                self._show_validation(issues)
                return self.state.current_step
            self._clear_validation()
            self._run_request_key = (self.state.mode, self.state.current_step)
            self.run_requested.emit(self.state.mode.value)
            self.refresh()
            return self.state.current_step

        page_issues = self._page_validation_issues()
        if page_issues:
            self._show_validation(page_issues)
            return self.state.current_step

        previous = self.state.current_step
        try:
            current = self.state.next_step()
        except ProjectStateValidationError:
            self._show_validation(self.state.validation_issues())
            return self.state.current_step

        self._clear_validation()
        if current is not previous:
            self.mark_dirty()
            self.step_changed.emit(self.state.mode.value, current.value)
        else:
            self.refresh()
        return current

    def go_back(self) -> StepId:
        self._run_request_key = None
        previous = self.state.current_step
        current = self.state.previous_step()
        self._clear_validation()
        if current is not previous:
            self.mark_dirty()
            self.step_changed.emit(self.state.mode.value, current.value)
        else:
            self.refresh()
        return current

    def show_results(self) -> StepId:
        if (
            self.state.current_step is not StepId.REVIEW_RUN
            or self._run_request_key
            != (self.state.mode, StepId.REVIEW_RUN)
        ):
            raise RuntimeError(
                "Results can only follow an explicit review and run"
            )
        self._run_request_key = None
        current = self.state.next_step(require_valid=False)
        self._clear_validation()
        self.mark_dirty()
        self.step_changed.emit(self.state.mode.value, current.value)
        return current

    def request_mode_switch(self, mode: ProjectMode | str) -> bool:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        if normalized is self.state.mode:
            self._pending_mode = None
            self.mode_switch_banner.hide()
            return True
        self._pending_mode = None
        self.mode_switch_banner.hide()
        self._switch_mode(normalized)
        return True

    def resolve_pending_mode_switch(self, continue_switch: bool) -> bool:
        pending = self._pending_mode
        self._pending_mode = None
        self.mode_switch_banner.hide()
        if pending is None or not continue_switch:
            return False
        self._switch_mode(pending)
        return True

    def _switch_mode(self, mode: ProjectMode) -> None:
        self._run_request_key = None
        self.mode_switch_banner.hide()
        restart_workflow = self.state.current_step in {
            StepId.RESULTS,
            StepId.TRANSPARENCY,
        }
        self.state.switch_mode(mode)
        if restart_workflow:
            # Results are terminal for the previous run.  Reusing that step
            # after switching mode makes the new mode open on the old results
            # page, with no way to start a fresh workflow.
            self.state.set_step(self.workflow_definition(mode).page_steps[0])
        self._invalid_key = None
        self.validation_label.clear()
        self.validation_label.hide()
        self.mark_dirty()
        self.mode_changed.emit(mode.value)
        if restart_workflow:
            self.step_changed.emit(mode.value, self.state.current_step.value)
