from __future__ import annotations

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
    FormCard,
    V3Button,
    V3DesignTokens,
    apply_v3_theme,
)
from v3_project_state import (
    ProjectMode,
    ProjectState,
    ProjectStateValidationError,
    StepId,
    route_for_mode,
)


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
    StepId.PIPELINE: "Порядок операций",
    StepId.EVIDENCE: "Проверка файла",
    StepId.REVIEW_RUN: "Проверка и запуск",
    StepId.RESULTS: "Результаты",
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
    StepId.EVIDENCE: "Выберите доступные проверки и способ интерпретации результата.",
    StepId.REVIEW_RUN: "Проверьте настройки, стоимость и ожидаемый результат.",
    StepId.RESULTS: "Просмотрите результаты и журнал выполненных операций.",
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
    "confirmed_area_unavailable": "Ручная область метки пока недоступна в этом интерфейсе.",
    "full_image_change_consent_required": "Подтвердите операцию, меняющую всё изображение.",
    "external_transfer_consent_required": "Подтвердите передачу файлов выбранному внешнему сервису.",
}


class WizardStepPage(FormCard):
    def __init__(
        self,
        mode: ProjectMode,
        step: StepId,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
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
    run_requested = pyqtSignal(str)
    finish_requested = pyqtSignal(str)

    def __init__(
        self,
        state: ProjectState | None = None,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        self.state = state if state is not None else ProjectState()
        self.tokens = tokens
        self._dirty = False
        self._pending_mode: ProjectMode | None = None
        self._invalid_key: tuple[ProjectMode, StepId] | None = None
        self._run_request_key: tuple[ProjectMode, StepId] | None = None
        self._pages: dict[tuple[ProjectMode, StepId], QWidget] = {}
        self.step_labels: list[QLabel] = []

        self.setMinimumSize(980, 700)
        self.setObjectName("v3AppShell")
        self.setAccessibleName("Clipart Generator 3.0")
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

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def pending_mode(self) -> ProjectMode | None:
        return self._pending_mode

    @property
    def current_page(self) -> QWidget:
        return self._pages[(self.state.mode, self.state.current_step)]

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

        title = QLabel("Clipart Generator 3.0")
        title.setProperty("v3Title", True)
        layout.addWidget(title)

        self.mode_label = QLabel()
        self.mode_label.setProperty("v3Description", True)
        layout.addWidget(self.mode_label)
        layout.addStretch()

        self.dirty_label = QLabel()
        self.dirty_label.setProperty("v3Small", True)
        layout.addWidget(self.dirty_label)

        self.change_mode_button = V3Button(
            "Сменить режим",
            ButtonVariant.GHOST,
        )
        self.change_mode_button.clicked.connect(self.mode_picker_requested.emit)
        layout.addWidget(self.change_mode_button)
        return frame

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
            for step in route_for_mode(mode):
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
        if normalized_step not in route_for_mode(normalized_mode):
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

    def refresh(self) -> None:
        self.mode_label.setText(f"Режим: {MODE_TITLES[self.state.mode]}")
        self.mode_label.setAccessibleName(self.mode_label.text())
        self.dirty_label.setText(
            "● Не сохранено" if self._dirty else "✓ Сохранено"
        )
        self.dirty_label.setAccessibleName(self.dirty_label.text())
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
        self.back_button.setEnabled(index > 0)

        if self.state.current_step is StepId.REVIEW_RUN:
            text = "Запустить"
        elif self.state.current_step is StepId.RESULTS:
            text = "Готово"
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
            self._clear_validation()
            self.finish_requested.emit(self.state.mode.value)
            self.refresh()
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
        self.state.switch_mode(mode)
        self._invalid_key = None
        self.validation_label.clear()
        self.validation_label.hide()
        self.mark_dirty()
        self.mode_changed.emit(mode.value)
