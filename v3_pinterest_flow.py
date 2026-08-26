from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout

from license_client import LicenseError

from v3_clipart_flow import (
    DEFAULT_TOKENS,
    ClipartFlowError,
    ClipartGenerationPage,
    ClipartProjectPage,
    ClipartPromptInputPage,
    ClipartPromptReviewPage,
    ClipartReviewRunPage,
    ClipartRunRequest,
    V3DesignTokens,
    _safe_runtime_error,
    build_clipart_run_request,
    estimate_clipart_cost,
    generate_prompt_series,
    missing_runtime_requirements,
    replace_project_prompts,
)
from v3_project_state import (
    GenerationData,
    ImageOperationData,
    PinterestModeData,
    ProjectMode,
    ProjectState,
    PromptGeneratorData,
    StepId,
)
from v3_prompt_generator import PromptGeneratorError
from v3_processing_editor import ProcessingPipelineEditor
from v3_wizard import AppShell
from v3_lazy_loading import LazyPageRegistry


_PINTEREST_REFERENCE_MODEL_BY_TEXT = {
    "flux-2/flex-text-to-image": "flux-2/flex-image-to-image",
    "flux-2/pro-text-to-image": "flux-2/pro-image-to-image",
    "gpt-image/1.5-text-to-image": "gpt-image/1.5-image-to-image",
    "gpt-image-2": "gpt-image-2",
    "nano-banana-2": "nano-banana-2",
    "nano-banana-pro": "nano-banana-pro",
    "qwen-image-2": "qwen-image-2",
}


class _PinterestDataAdapter:
    def __init__(self, data: PinterestModeData) -> None:
        self.data = data
        self.operations = data.operations

    @property
    def prompts(self):
        return self.data.prompts

    @prompts.setter
    def prompts(self, value):
        self.data.prompts = value

    @property
    def prompt_generator(self) -> PromptGeneratorData:
        return self.data.prompt_generator

    @prompt_generator.setter
    def prompt_generator(self, value: PromptGeneratorData) -> None:
        self.data.prompt_generator = value

    @property
    def generation(self) -> GenerationData:
        return self.data.generation

    @generation.setter
    def generation(self, value: GenerationData) -> None:
        self.data.generation = value


def _pinterest_project_adapter(state: ProjectState) -> ProjectState:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    adapter = ProjectState(mode=ProjectMode.CLIPART)
    adapter.common = state.common
    adapter.common.output_dir = state.output_dir_for_mode(ProjectMode.PINTEREST)
    if not adapter.common.output_dir and adapter.common.work_dir:
        adapter.common.output_dir = str(Path(adapter.common.work_dir) / "output")
        state.set_output_dir_for_mode(adapter.common.output_dir, ProjectMode.PINTEREST)
    adapter.runtime = state.runtime
    adapter.clipart = _PinterestDataAdapter(state.pinterest)
    return adapter


def estimate_pinterest_cost(state: ProjectState):
    return estimate_clipart_cost(_pinterest_project_adapter(state))


def build_pinterest_run_request(
    state: ProjectState,
    runtime_settings: Mapping[str, Any] | None = None,
) -> ClipartRunRequest:
    if state.mode is not ProjectMode.PINTEREST:
        raise ClipartFlowError(
            "Запуск Pinterest-пинов доступен только в режиме pinterest"
        )
    request = build_clipart_run_request(
        _pinterest_project_adapter(state),
        runtime_settings,
    )
    return request


class PinterestPromptInputPage(ClipartPromptInputPage):
    generator_mode = ProjectMode.PINTEREST


class PinterestFormatModelPage(ClipartGenerationPage):
    allow_shared_text_models = True

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        requested_model = state.clipart.generation.model
        requested_reference_model = state.clipart.generation.reference_model
        super().__init__(state, changed, tokens=tokens)
        for combo, model_id, label in (
            (self.model_combo, requested_model, "GPT Image 2"),
            (self.reference_model_combo, requested_reference_model, "GPT Image 2"),
        ):
            if model_id == "gpt-image-2" and combo.findData(model_id) < 0:
                combo.addItem(label, model_id)
        if requested_model == "gpt-image-2":
            self.model_combo.setCurrentIndex(self.model_combo.findData(requested_model))
            state.clipart.generation.model = requested_model
        if requested_reference_model == "gpt-image-2":
            self.reference_model_combo.setCurrentIndex(
                self.reference_model_combo.findData(requested_reference_model)
            )
            state.clipart.generation.reference_model = requested_reference_model
        self.card.title_label.setText("Формат и модель")
        self.setAccessibleName("Формат и модель Pinterest-пинов")
        self.recommendation_label = QLabel(
            "Рекомендуемый вертикальный формат — 9:16. "
            "Можно выбрать любую пропорцию, поддерживаемую моделью."
        )
        self.recommendation_label.setWordWrap(True)
        self.recommendation_label.setProperty("v3Status", True)
        self.add_widget(self.recommendation_label)

        self.ratio_preview = QFrame()
        self.ratio_preview.setProperty("v3Card", True)
        preview_layout = QVBoxLayout(self.ratio_preview)
        self.ratio_preview_label = QLabel()
        self.ratio_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.ratio_preview_label)
        self.add_widget(self.ratio_preview)
        self.reference_status_label = QLabel()
        self.reference_status_label.setWordWrap(True)
        self.reference_status_label.setProperty("v3Small", True)
        self.add_widget(self.reference_status_label)
        self.processing_editor = ProcessingPipelineEditor(
            state.clipart,
            changed,
            title="Обработка",
            description="Тот же порядок обработки, что и в режимах Clipart и Обработка.",
            include_cleanup=True,
            require_operation=False,
            tokens=tokens,
        )
        # Processing is a separate wizard step shared with the other modes.
        self.processing_editor.setParent(None)
        self._format_syncing = False
        self._format_issue = ""
        self.model_combo.currentIndexChanged.connect(self._enforce_single_format)
        self.ratio_combo.currentTextChanged.connect(self._enforce_single_format)
        self.resolution_combo.currentIndexChanged.connect(
            self._enforce_single_format
        )
        self.reference_model_combo.currentIndexChanged.connect(
            self._enforce_single_format
        )
        self.ratio_combo.currentTextChanged.connect(self._refresh_ratio_preview)
        self._enforce_single_format()
        self._refresh_ratio_preview()
        self.reference_advanced.setVisible(False)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        super().refresh_from_state()
        has_references = any(
            entry.references for entry in getattr(self.state.clipart, "prompts", [])
        )
        visible = has_references or bool(self._format_issue)
        self.reference_advanced.setVisible(visible)
        self.reference_advanced.set_expanded(visible)
        self._enforce_single_format()

    def _enforce_single_format(self, *_: Any) -> None:
        if self._format_syncing:
            return
        self._format_syncing = True
        try:
            ratio = self.ratio_combo.currentText()
            resolution = self._combo_value(self.resolution_combo)
            primary_model = str(self.model_combo.currentData() or "")
            reference_model = _PINTEREST_REFERENCE_MODEL_BY_TEXT.get(primary_model)
            compatible = [
                option
                for option in self.reference_options
                if option.model_id == reference_model
                and (not option.ratios or ratio in option.ratios)
                and (
                    resolution in option.resolutions
                    if option.resolutions
                    else resolution == "1K"
                )
            ]
            if not compatible:
                self._format_issue = (
                    "Нет парной reference-модели для "
                    f"{primary_model}, {ratio} / {resolution}. "
                    "Выберите другую модель или другой формат."
                )
                self.reference_status_label.setText(self._format_issue)
                self.reference_advanced.setVisible(True)
                self.reference_advanced.set_expanded(True)
                self.reference_model_combo.blockSignals(True)
                self.reference_model_combo.clear()
                self.reference_model_combo.addItem(
                    "Нет совместимой reference-модели", primary_model
                )
                self.reference_model_combo.setEnabled(False)
                self.reference_ratio_combo.setEnabled(False)
                self.reference_resolution_combo.setEnabled(False)
                self.reference_model_combo.blockSignals(False)
                self.state.clipart.generation.reference_model = primary_model
                ClipartGenerationPage._sync(self, mark=False)
                return

            self._format_issue = ""
            self.reference_status_label.setText(
                "Reference-mode готов: выбранная модель и формат совместимы."
            )
            current_model = compatible[0].model_id
            self.reference_model_combo.blockSignals(True)
            self.reference_model_combo.clear()
            for option in compatible:
                self.reference_model_combo.addItem(option.label, option.model_id)
            self._select_model(self.reference_model_combo, current_model)
            self.reference_model_combo.blockSignals(False)
            self.reference_model_combo.setEnabled(True)

            self._set_values(
                self.reference_ratio_combo,
                (ratio,),
                ratio,
            )
            self.reference_ratio_combo.setEnabled(False)
            self._set_values(
                self.reference_resolution_combo,
                (resolution,),
                resolution,
            )
            self.reference_resolution_combo.setEnabled(False)
            self.reference_advanced.setVisible(True)
            self.reference_advanced.set_expanded(True)
            ClipartGenerationPage._sync(self, mark=False)
        finally:
            self._format_syncing = False

    def validation_issues(self) -> tuple[str, ...]:
        issues = list(super().validation_issues()) if hasattr(super(), "validation_issues") else []
        if self._format_issue:
            issues.append("incompatible_reference_model")
        return tuple(issues)

    def _refresh_ratio_preview(self, *_: Any) -> None:
        ratio = self.ratio_combo.currentText()
        try:
            width_value, height_value = (
                max(1, int(value)) for value in ratio.split(":", 1)
            )
        except (TypeError, ValueError):
            width_value, height_value = 9, 16
        scale = 180 / max(width_value, height_value)
        width = max(20, round(width_value * scale))
        height = max(20, round(height_value * scale))
        self.ratio_preview.setFixedSize(width, height)
        text = ratio
        self.ratio_preview_label.setText(text)
        self.ratio_preview.setAccessibleName(text)


class PinterestProcessingPage(ProcessingPipelineEditor):
    def __init__(self, state: ProjectState, changed: Callable[[], None], *, tokens: V3DesignTokens = DEFAULT_TOKENS) -> None:
        super().__init__(
            state.clipart,
            changed,
            title="Обработка изображений",
            description="Единые настройки обработки изображений для Pinterest.",
            include_cleanup=True,
            require_operation=False,
            tokens=tokens,
        )


class PinterestReviewRunPage(ClipartReviewRunPage):
    def __init__(
        self,
        state: ProjectState,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(state, tokens=tokens)
        self.card.description_label.setText(
            "Проверьте пакет изображений и стоимость перед явным запуском."
        )

    def refresh_from_state(self) -> None:
        super().refresh_from_state()
        self.pipeline_label.setText(
            self.pipeline_label.text().replace(
                "Экспорт PNG",
                "Пакетный экспорт PNG",
            )
        )


class PinterestFlowController(QObject):
    started = pyqtSignal(object)
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        shell: AppShell,
        *,
        runtime_settings_provider: Callable[[], Mapping[str, Any]] | None = None,
        worker_factory: Callable[..., Any] | None = None,
        authorization_provider: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(shell)
        self.shell = shell
        from v3_runtime_adapter import runtime_adapter_for

        self.runtime_adapter = runtime_adapter_for(
            runtime_settings_provider, worker_factory
        )
        self.runtime_settings_provider = (
            runtime_settings_provider or self.runtime_adapter.read_settings
        )
        self.worker_factory = worker_factory or self.runtime_adapter.create_worker
        self.authorization_provider = authorization_provider or self._missing_authorization
        self.worker: Any | None = None
        self._runtime_settings: Mapping[str, Any] = {}
        from v3_run_queue import RunQueueSupport

        self.run_queue = RunQueueSupport(self, ProjectMode.PINTEREST)
        self.adapter_state = _pinterest_project_adapter(shell.state)
        self.pages = LazyPageRegistry(shell, ProjectMode.PINTEREST)
        self._install_pages()
        shell.step_changed.connect(self._step_changed)
        shell.run_requested.connect(self._run_requested)
        if shell.state.current_step is StepId.REVIEW_RUN:
            self._refresh_preflight()

    @staticmethod
    def _missing_authorization() -> None:
        raise LicenseError("Лицензионный сервис не настроен")

    def start_processing_again(self) -> None:
        self.shell.state.pinterest.prompts.clear()
        self.shell.state.set_step(StepId.PROJECT)
        self.pages[StepId.PROJECT].refresh_from_state()
        self.shell.mark_dirty()

    def _install_pages(self) -> None:
        changed = self.shell.mark_dirty
        self.pages.register(
            StepId.PROJECT,
            lambda: ClipartProjectPage(
                self.adapter_state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROMPTS,
            lambda: PinterestPromptInputPage(
                self.adapter_state,
                changed,
                advance=self.shell.go_next,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROMPT_REVIEW,
            lambda: ClipartPromptReviewPage(
                self.adapter_state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PIN_FORMAT_MODEL,
            lambda: PinterestFormatModelPage(
                self.adapter_state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROCESSING_OPTIONS,
            lambda: PinterestProcessingPage(
                self.adapter_state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.REVIEW_RUN,
            lambda: PinterestReviewRunPage(
                self.adapter_state,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register_instance(StepId.RESULTS, self.run_queue.page)
        if self.shell.state.mode is ProjectMode.PINTEREST:
            self.pages[self.shell.state.current_step]
        self.shell.refresh()

    @property
    def review_page(self) -> PinterestReviewRunPage:
        page = self.pages[StepId.REVIEW_RUN]
        if not isinstance(page, PinterestReviewRunPage):
            raise RuntimeError("Pinterest review page is not installed")
        return page

    def _step_changed(self, mode: str, step: str) -> None:
        if mode != ProjectMode.PINTEREST.value:
            return
        normalized_step = StepId(step)
        page = self.pages.get(normalized_step)
        if page is not None:
            page.refresh_from_state()
        if normalized_step is StepId.REVIEW_RUN:
            self._refresh_preflight()

    def _refresh_preflight(self) -> None:
        try:
            runtime_settings = self.runtime_settings_provider()
            if not isinstance(runtime_settings, Mapping):
                raise ClipartFlowError("Настройки запуска повреждены")
            request = build_pinterest_run_request(
                self.shell.state,
                runtime_settings,
            )
            missing = missing_runtime_requirements(request)
        except (ClipartFlowError, OSError, TypeError, ValueError) as error:
            self.review_page.set_preflight_status(str(error)[:500], ready=False)
            return
        if missing:
            self.review_page.set_preflight_status(
                "Укажите в настройках: " + ", ".join(missing),
                ready=False,
            )
        else:
            self.review_page.set_preflight_status(
                "Пакет готов к генерации после нажатия «Запустить».",
                ready=True,
            )

    def _run_requested(self, mode: str) -> None:
        if mode == ProjectMode.PINTEREST.value:
            self.start()

    def start(self) -> ClipartRunRequest | None:
        if self.worker is not None and self.runtime_adapter.is_running(self.worker):
            message = "Запуск уже выполняется"
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        try:
            runtime_settings = self.runtime_settings_provider()
            if not isinstance(runtime_settings, Mapping):
                raise ClipartFlowError("Настройки запуска повреждены")
            request = build_pinterest_run_request(
                self.shell.state,
                runtime_settings,
            )
            self._runtime_settings = runtime_settings
            missing = missing_runtime_requirements(request)
            if missing:
                raise ClipartFlowError(
                    "Укажите в настройках: " + ", ".join(missing)
                )
            self.authorization_provider()
            worker = self.worker_factory(**request.worker_kwargs())
        except (ClipartFlowError, LicenseError, OSError, TypeError, ValueError) as error:
            message = _safe_runtime_error(
                error,
                locals().get("runtime_settings"),
            )
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None

        self.worker = worker
        self.run_queue.start_new(request)
        self.run_queue.connect_worker(worker)
        self.runtime_adapter.start(worker)
        self.shell.show_results()
        self.review_page.set_run_status(
            "Пакет передан существующей генерации 2.0"
        )
        self.started.emit(request)
        return request

    def stop(self) -> None:
        if self.worker is not None:
            self.runtime_adapter.stop(self.worker)

    def _finished(self, message: str) -> None:
        self.run_queue.finished()
        safe_message = _safe_runtime_error(message, self._runtime_settings)
        self.review_page.set_run_status(safe_message)
        self.finished.emit(safe_message)

    def _error(self, message: str) -> None:
        self.run_queue.fatal_error(message)
        safe_message = _safe_runtime_error(message, self._runtime_settings)
        self.review_page.set_run_status(safe_message, error=True)
        self.error.emit(safe_message)


def install_pinterest_flow(
    shell: AppShell,
    *,
    runtime_settings_provider: Callable[[], Mapping[str, Any]] | None = None,
    worker_factory: Callable[..., Any] | None = None,
    authorization_provider: Callable[[], Any] | None = None,
) -> PinterestFlowController:
    if not isinstance(shell, AppShell):
        raise TypeError("shell must be an AppShell")
    existing = getattr(shell, "pinterest_flow_controller", None)
    if isinstance(existing, PinterestFlowController):
        return existing
    controller = PinterestFlowController(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
        authorization_provider=authorization_provider,
    )
    shell.pinterest_flow_controller = controller
    return controller
