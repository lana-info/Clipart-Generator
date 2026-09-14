from __future__ import annotations

import csv
import io
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

from PyQt6.QtCore import QObject, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QRadioButton,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from license_client import LicenseError
from v3_flow_runtime import CostEstimate, FlowRunRequest, safe_runtime_error as _safe_runtime_error
from v3_image_generation_ui import ImageGenerationSettingsPage
from v3_image_review_ui import ImageReviewRunPage
from v3_prompt_editor_ui import (
    CHROMA_KEY_MATERIAL_OPTIONS,
    MAX_CSV_BYTES,
    PromptBatchEditDialog,
    PromptInputPage,
    PromptReferenceEditorDialog,
    PromptReviewPage,
    ReferenceScopeDialog,
    _compact_review_action_button,
    _confirm_delete_all_prompts,
    _reference_icon,
    _reference_label,
    _reference_summary,
    _review_action_icon,
    _supported_local_reference,
    apply_prompt_text_edit,
    configure_chroma_material_buttons,
    export_prompt_csv,
)
from v3_image_generation_runtime import (
    MAX_IMAGE_GENERATION_REQUESTS,
    GenerationModelOption,
    ImageGenerationFlowError,
    _model_option,
    _reference_file_size_error,
    _split_user_prompt,
    _user_prompt_text,
    build_image_generation_run_request,
    estimate_image_generation_cost,
    fal_endpoint_quantities as _image_fal_endpoint_quantities,
    generation_model_options,
    image_generation_pipeline_steps,
    missing_runtime_requirements,
)
from v3_flow_ui import ProjectDirectoryPage, ScrollableStepPage as _ScrollableStepPage
from v3_image_worker_settings import build_image_worker_settings
from chroma_key import chroma_key_prompt_block
from chroma_key_selection import select_chroma_key_color
from provider_error_messages import friendly_provider_error
from v3_api_settings import estimate_fal_cost

from v3_components import (
    AdvancedSection,
    ButtonVariant,
    DEFAULT_TOKENS,
    FormCard,
    V3Button,
    V3DesignTokens,
)
from v3_image_processing_ui import (
    METADATA_CLEANUP_FIELDS, ProcessingPipelineEditor, RunPlanBuilder,
    UPSCALE_AFTER_UI_ENABLED,
)
from v3_provider_registry import CHROMA_KEY_COLOR_OPTIONS
from fal_model_catalog import is_fal_generation_model, is_fal_model_id
from output_naming import workspace_layout
from v3_prompt_csv_import import PromptCsvImportDialog
from v3_project_state import (
    MAX_PROMPT_ENTRIES,
    MAX_CHROMA_KEY_MATERIALS,
    MAX_PROMPT_GENERATOR_TEXT_LENGTH,
    MAX_REFERENCES_PER_PROMPT,
    MAX_TEXT_LENGTH,
    GenerationData,
    ImageOperationData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    PromptGeneratorData,
    RuntimeData,
    StepId,
)
from clipart_prompt_generator import generate_clipart_prompt_series
from v3_prompt_generator import (
    PromptGeneratorError,
    generate_into_project,
    replace_project_prompts,
)
from v3_provider_registry import (
    FAL_BIREFNET_MODEL_OPTIONS,
    FAL_BIREFNET_RESOLUTION_OPTIONS,
    FAL_REMOVE_BG_MODEL_OPTIONS,
    KIE_MODEL_OPTIONS,
    KIE_REMOVE_BG_MODEL_OPTIONS,
    normalize_fal_upscale_factor,
    processing_provider_options,
    provider_requires_api_key,
    provider_supports_operation,
    provider_visible_controls,
    upscale_model_preserves_alpha,
)
from workflow_definitions import workflow_for_mode
from v3_wizard import AppShell
from v3_lazy_loading import LazyPageRegistry
from v3_transparency_preview import ClipartTransparencyEditorPage
from model_catalog import (
    GENERATION_MODELS as CATALOG_GENERATION_MODELS,
    PROCESSING_PRICING as CATALOG_PROCESSING_PRICING,
    VISIBLE_GENERATION_MODEL_IDS as CATALOG_VISIBLE_GENERATION_MODEL_IDS,
    MODEL_SPECS,
    model_spec,
    ratios_for_mode,
    validate_generation_contract,
)


ClipartFlowError = ImageGenerationFlowError
ClipartRunRequest = FlowRunRequest
MAX_CLIPART_REQUESTS = MAX_IMAGE_GENERATION_REQUESTS


def estimate_clipart_cost(state: ProjectState) -> CostEstimate:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    return estimate_image_generation_cost(state.clipart)


def clipart_pipeline_steps(operations: ImageOperationData) -> tuple[str, ...]:
    return image_generation_pipeline_steps(operations)


def build_clipart_run_request(
    state: ProjectState,
    runtime_settings: Mapping[str, Any] | None = None,
) -> FlowRunRequest:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    if state.mode is not ProjectMode.CLIPART:
        raise ClipartFlowError("Запуск клипарта доступен только в режиме clipart")
    return build_image_generation_run_request(
        state.common,
        state.runtime,
        state.clipart,
        state.output_dir_for_mode(ProjectMode.CLIPART),
        runtime_settings,
        upscale_alpha_checker=upscale_model_preserves_alpha,
    )


def fal_endpoint_quantities(state: ProjectState) -> dict[str, int]:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    return _image_fal_endpoint_quantities(state.clipart)

















# Keep the old private names for callers/tests while sourcing every option
# from the shared immutable catalog.




































def parse_prompt_csv(path: str | os.PathLike[str]) -> list[PromptEntry]:
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as error:
        raise ClipartFlowError("Не удалось прочитать CSV") from error
    if size > MAX_CSV_BYTES:
        raise ClipartFlowError("CSV превышает допустимый размер")
    try:
        content = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ClipartFlowError("CSV должен быть корректным UTF-8 файлом") from error

    try:
        reader = csv.DictReader(io.StringIO(content))
        field_names = {
            str(name or "").strip().casefold(): name
            for name in (reader.fieldnames or [])
        }
    except csv.Error as error:
        raise ClipartFlowError("CSV имеет повреждённую структуру") from error
    prompt_field = field_names.get("prompt")
    references_field = field_names.get("references")
    if prompt_field is None:
        raise ClipartFlowError("В CSV нужен столбец Prompt")

    entries: list[PromptEntry] = []
    try:
        for row in reader:
            prompt = str(row.get(prompt_field) or "").strip()
            raw_references = (
                str(row.get(references_field) or "") if references_field else ""
            )
            references = [
                value.strip()
                for value in raw_references.split("|")
                if value.strip()
            ]
            if len(prompt) > MAX_TEXT_LENGTH:
                raise ClipartFlowError("Промпт в CSV превышает допустимую длину")
            if len(references) > MAX_REFERENCES_PER_PROMPT:
                raise ClipartFlowError(
                    f"Максимум {MAX_REFERENCES_PER_PROMPT} референсов на промпт"
                )
            if any(len(value) > MAX_TEXT_LENGTH for value in references):
                raise ClipartFlowError("Референс в CSV превышает допустимую длину")
            entry = PromptEntry.from_value(
                {"prompt": prompt, "references": references}
            )
            if entry is not None and entry.prompt:
                entries.append(entry)
            if len(entries) > MAX_PROMPT_ENTRIES:
                raise ClipartFlowError(
                    f"Максимум {MAX_PROMPT_ENTRIES} промптов в CSV"
                )
    except csv.Error as error:
        raise ClipartFlowError("CSV имеет повреждённую структуру") from error
    if not entries:
        raise ClipartFlowError("CSV не содержит непустых промптов")
    return entries
































class ClipartProjectPage(ProjectDirectoryPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(state, changed, output_mode=ProjectMode.CLIPART, tokens=tokens)
        self.builder_button = V3Button("Настроить набор клипартов", ButtonVariant.SECONDARY)
        self.builder_button.clicked.connect(self._open_builder)
        self.add_widget(self.builder_button)

    def _open_builder(self) -> None:
        from studio_clipart_builder_ui import ClipartBuilderDialog
        dialog = ClipartBuilderDialog(self.state, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.changed()






class ClipartPromptInputPage(PromptInputPage):
    generator_mode = ProjectMode.CLIPART
    supports_prompt_chroma = True

    def _generate_series(self, data: PromptGeneratorData) -> list[PromptEntry]:
        return generate_clipart_prompt_series(data)

    def _file_dialog_type(self):
        return QFileDialog

    def _csv_import_dialog_type(self):
        return PromptCsvImportDialog

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        advance: Callable[[], Any] | None = None,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(state, state.clipart, changed, advance=advance, tokens=tokens)

class ClipartPromptReviewPage(PromptReviewPage):
    def _file_dialog_type(self):
        return QFileDialog

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(state, state.clipart, changed, tokens=tokens)


class PromptWorkspacePage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        input_page_cls: type[ClipartPromptInputPage] = ClipartPromptInputPage,
        review_page_cls: type[ClipartPromptReviewPage] = ClipartPromptReviewPage,
    ) -> None:
        super().__init__(
            "Промпты",
            "Создавайте, импортируйте и редактируйте промпты в одном месте.",
            tokens=tokens,
        )
        self.state = state
        self._external_changed = changed
        self.input_section = input_page_cls(
            state,
            self._on_section_changed,
            tokens=tokens,
        )
        self.review_section = review_page_cls(
            state,
            self._on_section_changed,
            tokens=tokens,
        )
        # The legacy combined workspace remains compact for saved drafts and
        # compatibility tests. The routed input page shows the selected source
        # directly, without hiding its controls behind another disclosure.
        if hasattr(self.input_section, "generator_section"):
            self.input_section.generator_section.toggle_button.show()
            self.input_section.generator_section.set_expanded(False)
        if hasattr(self.review_section, "up_button"):
            self.review_section.up_button.hide()
        if hasattr(self.review_section, "down_button"):
            self.review_section.down_button.hide()
        self.add_widget(self.input_section)
        self.add_widget(self.review_section)

    def _on_section_changed(self) -> None:
        self.review_section.refresh_from_state()
        self._external_changed()

    def __getattr__(self, name: str) -> Any:
        if hasattr(self.input_section, name):
            return getattr(self.input_section, name)
        if hasattr(self.review_section, name):
            return getattr(self.review_section, name)
        raise AttributeError(name)

    def refresh_from_state(self) -> None:
        self.review_section.refresh_from_state()

    def validation_issues(self) -> tuple[str, ...]:
        return self.review_section.validation_issues()




class ClipartGenerationPage(ImageGenerationSettingsPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        self.state = state
        super().__init__(state.clipart, changed, tokens=tokens)






class ClipartProcessingPage(_ScrollableStepPage):
    _BOOL_LABELS = {
        "visible_mark_cleanup": "Удалить видимую метку автоматически",
        "upscale_before": "Апскейл до удаления фона",
        "upscale_after": "Апскейл после удаления фона",
        "remove_background": "Удалить фон",
        "fal_birefnet_refine_foreground": "Fal.ai BiRefNet: уточнить foreground",
        "fal_rembg_crop_to_bbox": "Fal.ai rembg: обрезать по объекту",
        "local_ben2_refine_foreground": "BEN2: уточнить foreground",
        "unsharp": "Unsharp Mask",
        "edge_shrink": "Очистить край alpha",
        "trim": "Trim",
        "export_300_dpi": "Экспорт 300 DPI",
        "remove_exif": "Удалить EXIF",
        "remove_xmp": "Удалить XMP",
        "remove_iptc": "Удалить IPTC",
        "remove_comments_text": "Удалить comments/text",
        "remove_embedded_thumbnail": "Удалить embedded thumbnail",
        "remove_generator_fields": "Удалить generator fields",
        "remove_embedded_c2pa": "Удалить embedded C2PA",
        "preserve_icc": "Сохранить ICC",
        "preserve_dpi": "Сохранить DPI",
    }

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Обработка",
            "Рецепт «Готовый клипарт» использует существующий pipeline 2.0.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self.operation_widgets: dict[str, QWidget] = {}
        operations = state.clipart.operations
        if not UPSCALE_AFTER_UI_ENABLED:
            operations.upscale_after = False
        self.operations = operations
        upscale_models = KIE_MODEL_OPTIONS
        remove_bg_models = KIE_REMOVE_BG_MODEL_OPTIONS

        recipe = QLabel(
            "Рекомендуемый рецепт: апскейл → удаление фона → экспорт PNG."
        )
        recipe.setWordWrap(True)
        recipe.setProperty("v3Status", True)
        self.add_widget(recipe)

        pipeline_group = QGroupBox("Операции")
        form = QFormLayout(pipeline_group)
        for name in (
            "visible_mark_cleanup",
            "upscale_before",
            "unsharp",
            "remove_background",
            "upscale_after",
            "edge_shrink",
            "trim",
            "export_300_dpi",
        ):
            self._add_bool(form, name, operations)
        self._add_combo(
            form,
            "upscale_before_provider",
            "Провайдер первого апскейла",
            processing_provider_options("upscale_before_provider"),
            operations,
        )
        self._add_combo(
            form,
            "remove_background_provider",
            "Провайдер удаления фона",
            processing_provider_options("remove_background_provider"),
            operations,
        )
        self._add_combo(
            form,
            "upscale_after_provider",
            "Провайдер второго апскейла",
            processing_provider_options("upscale_after_provider"),
            operations,
        )

        self._add_int(
            form,
            "edge_shrink_pixels",
            "Очистка края, px",
            1,
            3,
            operations,
        )
        self._add_combo(
            form,
            "trim_mode",
            "Trim по",
            (("Alpha", "alpha"), ("Белому", "white"), ("Чёрному", "black")),
            operations,
        )
        self.add_widget(pipeline_group)

        advanced = AdvancedSection("Параметры операций", tokens=tokens)
        advanced_group = QWidget()
        advanced_form = QFormLayout(advanced_group)
        self._add_combo(
            advanced_form,
            "kie_upscale_model",
            "KIE модель апскейла до",
            upscale_models,
            operations,
        )
        self._add_combo(
            advanced_form,
            "kie_upscale_after_model",
            "KIE модель апскейла после",
            upscale_models,
            operations,
        )
        self._add_combo(
            advanced_form,
            "kie_remove_bg_model",
            "KIE модель удаления фона",
            remove_bg_models,
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_remove_bg_model",
            "Fal.ai модель удаления фона",
            FAL_REMOVE_BG_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_birefnet_model",
            "Fal.ai BiRefNet вариант",
            FAL_BIREFNET_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_birefnet_resolution",
            "Fal.ai BiRefNet разрешение",
            FAL_BIREFNET_RESOLUTION_OPTIONS,
            operations,
        )
        self._add_bool(advanced_form, "fal_birefnet_refine_foreground", operations)
        self._add_bool(advanced_form, "fal_rembg_crop_to_bbox", operations)
        self._add_combo(
            advanced_form,
            "chroma_key_color",
            "Chroma Key цвет",
            CHROMA_KEY_COLOR_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "local_realesrgan_profile",
            "Real-ESRGAN профиль",
            (("Клипарт", "clipart"), ("Фото", "photo")),
            operations,
        )
        self._add_combo(
            advanced_form,
            "local_realesrgan_scale",
            "Real-ESRGAN scale до",
            (("2x", 2), ("4x", 4)),
            operations,
        )
        self._add_combo(
            advanced_form,
            "local_realesrgan_after_scale",
            "Real-ESRGAN scale после",
            (("2x", 2), ("4x", 4)),
            operations,
        )
        self._add_text(
            advanced_form,
            "local_rembg_profile",
            "rembg профиль",
            operations,
        )
        self._add_text(
            advanced_form,
            "local_rembg_model",
            "rembg модель",
            operations,
        )
        self._add_combo(
            advanced_form,
            "local_rembg_edge_quality",
            "Качество края rembg",
            (("Мягкое", "soft"), ("Обычное", "normal"), ("Резкое", "sharp")),
            operations,
        )
        self._add_bool(
            advanced_form,
            "local_ben2_refine_foreground",
            operations,
        )
        self._add_int(
            advanced_form,
            "local_ben2_alpha_threshold",
            "BEN2 alpha threshold",
            0,
            255,
            operations,
        )
        self._add_int(
            advanced_form,
            "local_ben2_edge_softness",
            "BEN2 мягкость края",
            0,
            3,
            operations,
        )
        self._add_int(
            advanced_form,
            "local_ben2_corner_radius",
            "BEN2 радиус углов",
            0,
            3,
            operations,
        )
        self._add_int(
            advanced_form,
            "unsharp_amount",
            "Unsharp amount",
            0,
            500,
            operations,
        )
        self._add_float(
            advanced_form,
            "unsharp_radius",
            "Unsharp radius",
            0.1,
            200.0,
            operations,
        )
        self._add_int(
            advanced_form,
            "unsharp_threshold",
            "Unsharp threshold",
            0,
            255,
            operations,
        )
        advanced.add_widget(advanced_group)
        self.add_widget(advanced)

        cleanup_group = QGroupBox("Центр проверки и очистки файла")
        cleanup_form = QFormLayout(cleanup_group)
        self.cleanup_all_checkbox = QCheckBox("Очистить служебные метаданные")
        self.cleanup_all_checkbox.setToolTip("Удаляет EXIF, XMP, IPTC, комментарии, миниатюры, данные генератора и C2PA; ICC и DPI сохраняются.")
        self.cleanup_all_checkbox.setChecked(any(bool(getattr(operations, name)) for name in ("remove_exif", "remove_xmp", "remove_iptc", "remove_comments_text", "remove_embedded_thumbnail", "remove_generator_fields", "remove_embedded_c2pa")))
        self.cleanup_all_checkbox.toggled.connect(self._set_cleanup_all)
        cleanup_form.addRow(self.cleanup_all_checkbox)
        for name in (*METADATA_CLEANUP_FIELDS, "preserve_icc", "preserve_dpi"):
            self._add_bool(cleanup_form, name, operations)
            self.operation_widgets[name].setVisible(False)
        self.add_widget(cleanup_group)

        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.pipeline_label.setAccessibleName("Порядок обработки")
        self.add_widget(self.pipeline_label)
        self._connect_controls()
        self._refresh_control_visibility()
        self._refresh_pipeline()

    def _set_cleanup_all(self, checked: bool) -> None:
        for name in METADATA_CLEANUP_FIELDS:
            control = self.operation_widgets.get(name)
            if control is not None:
                control.blockSignals(True)
                control.setChecked(checked)
                control.blockSignals(False)
            setattr(self.state_owner.operations if hasattr(self, "state_owner") else self.operations, name, checked)
        self._sync()

    def _add_bool(
        self,
        form: QFormLayout,
        name: str,
        operations: ImageOperationData,
    ) -> None:
        control = QCheckBox(self._BOOL_LABELS[name])
        control.setChecked(bool(getattr(operations, name)))
        control.setAccessibleName(self._BOOL_LABELS[name])
        form.addRow(control)
        self.operation_widgets[name] = control

    def _add_combo(
        self,
        form: QFormLayout,
        name: str,
        label: str,
        options: Sequence[tuple[str, Any]],
        operations: ImageOperationData,
    ) -> None:
        control = QComboBox()
        for option_label, value in options:
            control.addItem(option_label, value)
        index = control.findData(getattr(operations, name))
        control.setCurrentIndex(index if index >= 0 else 0)
        control.setAccessibleName(label)
        form.addRow(label, control)
        self.operation_widgets[name] = control

    def _add_int(
        self,
        form: QFormLayout,
        name: str,
        label: str,
        minimum: int,
        maximum: int,
        operations: ImageOperationData,
    ) -> None:
        control = QSpinBox()
        control.setRange(minimum, maximum)
        control.setValue(int(getattr(operations, name)))
        control.setAccessibleName(label)
        form.addRow(label, control)
        self.operation_widgets[name] = control

    def _add_float(
        self,
        form: QFormLayout,
        name: str,
        label: str,
        minimum: float,
        maximum: float,
        operations: ImageOperationData,
    ) -> None:
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(1)
        control.setValue(float(getattr(operations, name)))
        control.setAccessibleName(label)
        form.addRow(label, control)
        self.operation_widgets[name] = control

    def _add_text(
        self,
        form: QFormLayout,
        name: str,
        label: str,
        operations: ImageOperationData,
    ) -> None:
        control = QLineEdit(str(getattr(operations, name)))
        control.setAccessibleName(label)
        form.addRow(label, control)
        self.operation_widgets[name] = control

    def _connect_controls(self) -> None:
        for control in self.operation_widgets.values():
            if isinstance(control, QCheckBox):
                control.toggled.connect(self._sync)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._sync)
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.valueChanged.connect(self._sync)
            elif isinstance(control, QLineEdit):
                control.textChanged.connect(self._sync)

    @staticmethod
    def _value(control: QWidget) -> Any:
        if isinstance(control, QCheckBox):
            return control.isChecked()
        if isinstance(control, QComboBox):
            return control.currentData()
        if isinstance(control, (QSpinBox, QDoubleSpinBox)):
            return control.value()
        if isinstance(control, QLineEdit):
            return control.text()
        raise TypeError(f"Unsupported control: {type(control).__name__}")

    def _sync(self, *_: Any) -> None:
        current = self.state.clipart.operations.to_dict()
        for name, control in self.operation_widgets.items():
            current[name] = self._value(control)
        if not UPSCALE_AFTER_UI_ENABLED:
            current["upscale_after"] = False
        current["visible_mark_cleanup_mode"] = "gemini_auto"
        self.state.clipart.operations = ImageOperationData(**current)
        self._refresh_control_visibility()
        self._refresh_pipeline()
        self.changed()

    def _set_control_visible(self, name: str, visible: bool) -> None:
        control = self.operation_widgets.get(name)
        if control is None:
            return
        control.setVisible(visible)
        parent = control.parentWidget()
        layout = parent.layout() if parent is not None else None
        if isinstance(layout, QFormLayout):
            label = layout.labelForField(control)
            if label is not None:
                label.setVisible(visible)

    def _refresh_control_visibility(self) -> None:
        operations = self.state.clipart.operations
        before_controls = set(provider_visible_controls(operations.upscale_before_provider))
        after_controls = set(provider_visible_controls(operations.upscale_after_provider))
        remove_controls = set(provider_visible_controls(operations.remove_background_provider))
        visibility = {
            "upscale_before_provider": operations.upscale_before,
            "upscale_after_provider": operations.upscale_after,
            "remove_background_provider": operations.remove_background,
            "edge_shrink_pixels": operations.edge_shrink,
            "trim_mode": operations.trim,
            "kie_upscale_model": operations.upscale_before
            and "kie_upscale_model" in before_controls,
            "kie_upscale_after_model": operations.upscale_after
            and "kie_upscale_after_model" in after_controls,
            "local_realesrgan_profile": (
                operations.upscale_before
                and "local_realesrgan_profile" in before_controls
            )
            or (
                operations.upscale_after
                and "local_realesrgan_profile" in after_controls
            ),
            "local_realesrgan_scale": operations.upscale_before
            and "local_realesrgan_scale" in before_controls,
            "local_realesrgan_after_scale": operations.upscale_after
            and "local_realesrgan_after_scale" in after_controls,
            "kie_remove_bg_model": operations.remove_background
            and "kie_remove_bg_model" in remove_controls,
            "local_rembg_profile": operations.remove_background
            and "local_rembg_profile" in remove_controls,
            "local_rembg_model": operations.remove_background
            and "local_rembg_model" in remove_controls,
            "local_rembg_edge_quality": operations.remove_background
            and "local_rembg_edge_quality" in remove_controls,
            "local_ben2_refine_foreground": operations.remove_background
            and "local_ben2_refine_foreground" in remove_controls,
            "local_ben2_alpha_threshold": operations.remove_background
            and "local_ben2_alpha_threshold" in remove_controls,
            "local_ben2_edge_softness": operations.remove_background
            and "local_ben2_edge_softness" in remove_controls,
            "local_ben2_corner_radius": operations.remove_background
            and "local_ben2_corner_radius" in remove_controls,
            "chroma_key_color": operations.remove_background
            and "chroma_key_color" in remove_controls,
            "unsharp_amount": operations.unsharp,
            "unsharp_radius": operations.unsharp,
            "unsharp_threshold": operations.unsharp,
        }
        for name, visible in visibility.items():
            self._set_control_visible(name, visible)
        self._set_control_visible(
            "upscale_after",
            UPSCALE_AFTER_UI_ENABLED,
        )

    def _refresh_pipeline(self) -> None:
        steps = clipart_pipeline_steps(self.state.clipart.operations)
        text = "Порядок: " + " → ".join(steps)
        self.pipeline_label.setText(text)
        self.pipeline_label.setAccessibleName(text)


class _SharedClipartProcessingPage(ProcessingPipelineEditor):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            state.clipart,
            changed,
            title="Обработка изображений",
            description="",
            include_cleanup=True,
            require_operation=False,
            allowed_operations=workflow_for_mode(ProjectMode.CLIPART).processing_operations,
            tokens=tokens,
        )
        self.state = state
        self.changed = changed


ClipartProcessingPage = _SharedClipartProcessingPage




class ClipartReviewRunPage(ImageReviewRunPage):
    def __init__(
        self,
        state: ProjectState,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        fal_cost_refresh: Callable[[], tuple[float, str]] | None = None,
    ) -> None:
        self.state = state
        super().__init__(
            state.common,
            state.clipart,
            lambda: state.output_dir_for_mode(ProjectMode.CLIPART),
            lambda value: state.set_output_dir_for_mode(value, ProjectMode.CLIPART),
            tokens=tokens,
            fal_cost_refresh=fal_cost_refresh,
        )


def _read_legacy_runtime_settings() -> Mapping[str, Any]:
    import main

    path = Path(main.CONFIG_FILE)
    if not path.is_file():
        return {}
    try:
        if path.stat().st_size > MAX_CSV_BYTES:
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _legacy_worker_factory(**kwargs: Any) -> Any:
    from v3_runtime_adapter import DEFAULT_LEGACY_RUNTIME_ADAPTER

    return DEFAULT_LEGACY_RUNTIME_ADAPTER.create_worker(**kwargs)


class ClipartFlowController(QObject):
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

        self.run_queue = RunQueueSupport(self, ProjectMode.CLIPART)
        self.pages = LazyPageRegistry(shell, ProjectMode.CLIPART)
        self._install_pages()
        self.run_queue.page.transparency_requested.connect(
            self._open_transparency_editor
        )
        shell.step_changed.connect(self._step_changed)
        shell.run_requested.connect(self._run_requested)
        if (
            shell.state.mode is ProjectMode.CLIPART
            and shell.state.current_step is StepId.REVIEW_RUN
        ):
            self._refresh_preflight()

    @staticmethod
    def _missing_authorization() -> None:
        raise LicenseError("Лицензионный сервис не настроен")

    def start_processing_again(self) -> None:
        self.shell.state.clipart.prompts.clear()
        self.shell.state.set_step(StepId.PROJECT)
        self.pages[StepId.PROJECT].refresh_from_state()
        self.shell.mark_dirty()

    def _create_transparency_page(self) -> ClipartTransparencyEditorPage:
        page = ClipartTransparencyEditorPage()
        page.back_requested.connect(self._close_transparency_editor)
        page.copy_saved.connect(self.run_queue.page.use_edited_output)
        page.focus_mode_changed.connect(self.shell.set_canvas_focus_mode)
        return page

    def _open_transparency_editor(self, item_index: int) -> None:
        session = self.run_queue.session
        if session is None or session.running:
            return
        from v3_run_queue import transparency_candidate_paths

        selected_item = (
            session.items[item_index]
            if 0 <= item_index < len(session.items)
            else None
        )
        paths = transparency_candidate_paths(session)
        if not paths:
            return
        selected = 0
        if selected_item is not None and selected_item.output_path:
            selected_path = Path(selected_item.output_path)
            try:
                selected = paths.index(selected_path)
            except ValueError:
                pass
        page = self.pages[StepId.TRANSPARENCY]
        if not isinstance(page, ClipartTransparencyEditorPage):
            return
        page.set_files(
            paths,
            selected_index=selected,
            rough_dir=workspace_layout(session.output_dir).rough,
        )
        self.shell.state.set_step(StepId.TRANSPARENCY)
        self.shell.mark_dirty()
        self.shell.step_changed.emit(
            ProjectMode.CLIPART.value,
            StepId.TRANSPARENCY.value,
        )

    def _close_transparency_editor(self) -> None:
        page = self.pages.get(StepId.TRANSPARENCY)
        if isinstance(page, ClipartTransparencyEditorPage):
            page.leave_focus_mode()
        self.shell.set_canvas_focus_mode(False)
        self.shell.state.set_step(StepId.RESULTS)
        self.shell.mark_dirty()
        self.shell.step_changed.emit(
            ProjectMode.CLIPART.value,
            StepId.RESULTS.value,
        )

    def _install_pages(self) -> None:
        changed = self.shell.mark_dirty
        self.pages.register(
            StepId.PROJECT,
            lambda: ClipartProjectPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROMPTS,
            lambda: ClipartPromptInputPage(
                self.shell.state,
                changed,
                advance=self.shell.go_next,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROMPT_REVIEW,
            lambda: ClipartPromptReviewPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.GENERATION,
            lambda: ClipartGenerationPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROCESSING_OPTIONS,
            lambda: ClipartProcessingPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.REVIEW_RUN,
            lambda: ClipartReviewRunPage(
                self.shell.state,
                tokens=self.shell.tokens,
                fal_cost_refresh=self._refresh_fal_cost,
            ),
        )
        self.pages.register_instance(StepId.RESULTS, self.run_queue.page)
        self.pages.register(
            StepId.TRANSPARENCY,
            self._create_transparency_page,
        )
        if self.shell.state.mode is ProjectMode.CLIPART:
            self.pages[self.shell.state.current_step]
        self.shell.refresh()

    @property
    def review_page(self) -> ClipartReviewRunPage:
        page = self.pages[StepId.REVIEW_RUN]
        if not isinstance(page, ClipartReviewRunPage):
            raise RuntimeError("Clipart review page is not installed")
        return page

    def _step_changed(self, mode: str, step: str) -> None:
        if mode != ProjectMode.CLIPART.value:
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
            runtime_settings = dict(runtime_settings)
            request = build_clipart_run_request(
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
                "Обязательные поля заполнены; запуск готов.",
                ready=True,
            )

    def _run_requested(self, mode: str) -> None:
        if mode == ProjectMode.CLIPART.value:
            self.start()

    def _refresh_fal_cost(self) -> tuple[float, str]:
        runtime_settings = self.runtime_settings_provider()
        if not isinstance(runtime_settings, Mapping):
            raise ClipartFlowError("Настройки запуска повреждены")
        api_key = str(runtime_settings.get("fal_api_key") or "").strip()
        if not api_key:
            raise ClipartFlowError("Добавьте Fal.ai API Key в настройках API")
        quantities = fal_endpoint_quantities(self.shell.state)
        if not quantities:
            raise ClipartFlowError("В текущем запуске нет операций Fal.ai")
        return estimate_fal_cost(api_key, quantities)

    def start(self) -> ClipartRunRequest | None:
        if self.shell.another_run_is_active(self):
            message = "Сначала завершите текущее задание в другом режиме"
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        if self.worker is not None and self.runtime_adapter.is_running(self.worker):
            message = "Запуск уже выполняется"
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        try:
            runtime_settings = self.runtime_settings_provider()
            if not isinstance(runtime_settings, Mapping):
                raise ClipartFlowError("Настройки запуска повреждены")
            runtime_settings = dict(runtime_settings)
            request = build_clipart_run_request(
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
            message = _safe_runtime_error(error, locals().get("runtime_settings"))
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None

        self.worker = worker
        self.run_queue.start_new(request)
        self.run_queue.connect_worker(worker)
        self.runtime_adapter.start(worker)
        self.shell.show_results()
        self.review_page.set_run_status("Запуск передан существующему pipeline 2.0")
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


def install_clipart_flow(
    shell: AppShell,
    *,
    runtime_settings_provider: Callable[[], Mapping[str, Any]] | None = None,
    worker_factory: Callable[..., Any] | None = None,
    authorization_provider: Callable[[], Any] | None = None,
) -> ClipartFlowController:
    if not isinstance(shell, AppShell):
        raise TypeError("shell must be an AppShell")
    existing = getattr(shell, "clipart_flow_controller", None)
    if isinstance(existing, ClipartFlowController):
        return existing
    controller = ClipartFlowController(
        shell,
        runtime_settings_provider=runtime_settings_provider,
        worker_factory=worker_factory,
        authorization_provider=authorization_provider,
    )
    shell.clipart_flow_controller = controller
    return controller
