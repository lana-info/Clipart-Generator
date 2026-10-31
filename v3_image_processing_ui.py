"""Shared image-processing UI and operation planning for Studio workflows."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import white_background
from PyQt6.QtCore import Qt

from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFrame, QFormLayout, QGridLayout,
    QGroupBox, QLabel, QLineEdit, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from v3_components import DEFAULT_TOKENS, V3DesignTokens
from v3_provider_registry import (
    CHROMA_KEY_COLOR_OPTIONS,
    CHROMA_SUBJECT_PROFILE_OPTIONS,
    FAL_BIREFNET_MODEL_OPTIONS,
    FAL_BIREFNET_RESOLUTION_OPTIONS,
    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
    FAL_TOPAZ_PRECISION_MODEL_ID,
    FAL_REMOVE_BG_MODEL_OPTIONS,
    FAL_UPSCALE_MODEL_OPTIONS,
    KIE_TOPAZ_MODEL_ID,
    KIE_REMOVE_BG_MODEL_OPTIONS,
    KIE_MODEL_OPTIONS,
    LOCAL_REMBG_MODEL_OPTIONS,
    LOCAL_REMBG_PROFILE_OPTIONS,
    LOCAL_REMBG_PROFILE_MODELS,
    TOPAZ_UPSCALE_FACTORS,
    BRIA_HINT_TEXT,
    BRIA_UPSCALE_MODEL_IDS,
    processing_provider_options,
    provider_visible_controls,
)
from v3_project_state import ImageOperationData

SYNTHID_UNAVAILABLE_LABEL = (
    "Глубокая обработка скрытых водяных знаков (SynthID) — недоступно"
)
SYNTHID_UNAVAILABLE_TOOLTIP = (
    "Функция не включена: нет подтверждённого production-контракта "
    "обнаружения и удаления SynthID."
)
UPSCALE_AFTER_UI_ENABLED = True
WHITE_BACKGROUND_UNAVAILABLE_MESSAGE = (
    "Белый фон с чётким контуром недоступен: нужны локальная модель U2Net "
    "и установленные rembg/onnxruntime."
)
METADATA_CLEANUP_FIELDS = (
    "remove_exif",
    "remove_xmp",
    "remove_iptc",
    "remove_comments_text",
    "remove_embedded_thumbnail",
    "remove_generator_fields",
    "remove_embedded_c2pa",
)


CLEANUP_OPERATION_LABELS = {
    "remove_exif": "Удалить EXIF",
    "remove_xmp": "Удалить XMP",
    "remove_iptc": "Удалить IPTC",
    "remove_comments_text": "Удалить текстовые комментарии",
    "remove_embedded_thumbnail": "Удалить встроенную миниатюру",
    "remove_generator_fields": "Удалить поля программы-создателя",
    "remove_embedded_c2pa": "Удалить встроенные данные C2PA",
}


def configure_unavailable_synthid(control: QCheckBox) -> None:
    """Present SynthID consistently without exposing a non-production action."""
    previous = control.blockSignals(True)
    control.setChecked(False)
    control.setEnabled(False)
    control.setText(SYNTHID_UNAVAILABLE_LABEL)
    control.setAccessibleName(SYNTHID_UNAVAILABLE_LABEL)
    control.setToolTip(SYNTHID_UNAVAILABLE_TOOLTIP)
    control.blockSignals(previous)

def processing_pipeline_steps(
    operations: ImageOperationData,
    *,
    include_cleanup: bool = False,
) -> tuple[str, ...]:
    steps: list[str] = []
    if include_cleanup and any(
        (
            operations.remove_exif,
            operations.remove_xmp,
            operations.remove_iptc,
            operations.remove_comments_text,
            operations.remove_embedded_thumbnail,
            operations.remove_generator_fields,
            operations.remove_embedded_c2pa,
        )
    ):
        steps.append("Очистка метаданных")
    if operations.visible_mark_cleanup:
        steps.append("Удаление видимой метки")
    if operations.invisible_watermark_cleanup:
        steps.append("Экспериментальная очистка невидимого watermark")
    if operations.upscale_before:
        steps.append("Апскейл до подготовки прозрачного фона")
    if operations.unsharp:
        steps.append("Unsharp Mask")
    if operations.remove_background:
        steps.append("Подготовка прозрачного фона")
    if operations.upscale_after:
        steps.append("Апскейл после подготовки прозрачного фона")
    if operations.edge_shrink:
        steps.append("Очистка края alpha")
    if operations.trim:
        steps.append("Trim")
    if operations.export_300_dpi:
        steps.append("Экспорт 300 DPI")
    if steps:
        steps.append("Экспорт нового PNG")
    return tuple(steps)


class RunPlanBuilder:
    @staticmethod
    def processing_steps(
        operations: ImageOperationData,
        *,
        include_cleanup: bool = False,
    ) -> tuple[str, ...]:
        return processing_pipeline_steps(
            operations,
            include_cleanup=include_cleanup,
        )

class ProcessingPipelineEditor(QScrollArea):
    _STAGE_TITLES = {
        "upscale_before": "Апскейл до подготовки прозрачного фона",
        "unsharp": "Unsharp Mask",
        "remove_background": "Подготовить прозрачный фон",
        "upscale_after": "Апскейл после подготовки прозрачного фона",
        "edge_shrink": "Очистить край alpha",
        "trim": "Trim",
        "export_300_dpi": "Установить 300 DPI",
    }
    _STAGE_ORDER = tuple(_STAGE_TITLES)
    _BOOL_LABELS = {
        "visible_mark_cleanup": "Удалить водяной знак Gemini",
        "invisible_watermark_cleanup": "Обработать скрытые водяные знаки (SynthID)",
        "upscale_before": "Апскейл до подготовки прозрачного фона",
        "upscale_after": "Апскейл после подготовки прозрачного фона",
        "remove_background": "Подготовить прозрачный фон",
        "fal_birefnet_refine_foreground": "Fal.ai BiRefNet: уточнить foreground",
        "fal_rembg_crop_to_bbox": "Fal.ai rembg: обрезать по объекту",
        "local_ben2_refine_foreground": "BEN2: уточнить foreground",
        "unsharp": "Unsharp Mask",
        "edge_shrink": "Очистить край alpha",
        "trim": "Trim",
        "export_300_dpi": "Экспорт 300 DPI",
        **CLEANUP_OPERATION_LABELS,
        "preserve_icc": "Сохранить ICC",
        "preserve_dpi": "Сохранить DPI",
    }
    _CLEANUP_FIELDS = (
        "remove_exif",
        "remove_xmp",
        "remove_iptc",
        "remove_comments_text",
        "remove_embedded_thumbnail",
        "remove_generator_fields",
        "remove_embedded_c2pa",
    )
    _BACKGROUND_INTERNAL_CONTROLS = (
        "remove_background_provider", "kie_remove_bg_model", "fal_remove_bg_model",
        "fal_birefnet_model", "fal_birefnet_resolution",
        "fal_birefnet_refine_foreground", "fal_rembg_crop_to_bbox",
        "chroma_key_color", "chroma_subject_profile", "local_rembg_profile", "local_rembg_model",
        "local_rembg_edge_quality", "local_ben2_refine_foreground",
        "local_ben2_alpha_threshold", "local_ben2_edge_softness",
        "local_ben2_corner_radius",
    )

    def __init__(
        self,
        state_owner: Any,
        changed: Callable[[], None],
        *,
        title: str,
        description: str,
        include_cleanup: bool,
        show_background_controls: bool = False,
        require_operation: bool = True,
        allowed_operations: Sequence[str] | None = None,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setAccessibleName(title)
        outer = QWidget()
        self.setWidget(outer)
        self._layout = QVBoxLayout(outer)
        self._layout.setContentsMargins(
            tokens.space_4,
            0,
            tokens.space_4,
            tokens.space_4,
        )
        self._layout.setSpacing(tokens.space_4)
        title_label = QLabel(title)
        title_label.setProperty("v3Title", True)
        self._layout.addWidget(title_label)
        if description:
            description_label = QLabel(description)
            description_label.setWordWrap(True)
            description_label.setProperty("v3Subtitle", True)
            self._layout.addWidget(description_label)
        self.state_owner = state_owner
        self.changed = changed
        self.include_cleanup = include_cleanup
        self.show_background_controls = show_background_controls
        self.require_operation = require_operation
        self.allowed_operations = (
            None if allowed_operations is None else frozenset(allowed_operations)
        )
        self.operation_widgets: dict[str, QWidget] = {}
        operations = state_owner.operations
        if not UPSCALE_AFTER_UI_ENABLED:
            operations.upscale_after = False

        operations_group = QGroupBox("Операции")
        self.operations_grid = QGridLayout(operations_group)
        self.operations_grid.setContentsMargins(12, 8, 12, 8)
        self.operations_grid.setHorizontalSpacing(24)
        self.operations_grid.setVerticalSpacing(4)
        self._control_staging = QWidget()
        form = QFormLayout(self._control_staging)
        operation_names = (
            "upscale_before",
            "unsharp",
            "remove_background",
            "upscale_after",
            "edge_shrink",
            "trim",
            "export_300_dpi",
        )
        operation_checkboxes: list[tuple[str, QCheckBox]] = []
        for name in operation_names:
            operation_checkboxes.append(
                (name, self._new_bool_control(name, operations))
            )
        if include_cleanup:
            self.cleanup_checkbox = QCheckBox("Удалить служебные данные изображения")
            self.cleanup_checkbox.setAccessibleName("Удалить служебные данные изображения")
            operation_checkboxes.append(("cleanup", self.cleanup_checkbox))
            operation_checkboxes.append(
                (
                    "visible_mark_cleanup",
                    self._new_bool_control("visible_mark_cleanup", operations),
                )
            )
        else:
            self.cleanup_checkbox = None
        self._add_bool(form, "invisible_watermark_cleanup", operations)
        invisible_control = self.operation_widgets["invisible_watermark_cleanup"]
        operations.invisible_watermark_cleanup = False
        configure_unavailable_synthid(invisible_control)
        operation_rows = (len(operation_checkboxes) + 2) // 3
        for index, (_name, control) in enumerate(operation_checkboxes):
            self.operations_grid.addWidget(
                control,
                index % operation_rows,
                index // operation_rows,
            )
        for column in range(3):
            self.operations_grid.setColumnStretch(column, 1)
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
            "Провайдер подготовки прозрачного фона",
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
        self.add_widget(operations_group)

        advanced = QGroupBox("Параметры этапов")
        advanced_form = QFormLayout(advanced)
        self._add_combo(
            advanced_form,
            "kie_upscale_model",
            "KIE модель апскейла до",
            KIE_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "kie_upscale_after_model",
            "KIE модель апскейла после",
            KIE_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_upscale_model",
            "Fal.ai модель апскейла до",
            FAL_UPSCALE_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_upscale_after_model",
            "Fal.ai модель апскейла после",
            FAL_UPSCALE_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_upscale_scale",
            "Fal.ai масштаб до",
            (("2×", 2), ("4×", 4)),
            operations,
        )
        self._add_combo(
            advanced_form,
            "fal_upscale_after_scale",
            "Fal.ai масштаб после",
            (("2×", 2), ("4×", 4)),
            operations,
        )
        self._add_combo(
            advanced_form,
            "upscale_factor",
            "Topaz масштаб",
            tuple((f"{factor}x", factor) for factor in TOPAZ_UPSCALE_FACTORS),
            operations,
        )
        self._add_combo(
            advanced_form,
            "kie_remove_bg_model",
            "KIE модель подготовки прозрачного фона",
            KIE_REMOVE_BG_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(advanced_form, "fal_remove_bg_model", "Fal.ai модель подготовки прозрачного фона", FAL_REMOVE_BG_MODEL_OPTIONS, operations)
        self._add_combo(advanced_form, "fal_birefnet_model", "Fal.ai BiRefNet вариант", FAL_BIREFNET_MODEL_OPTIONS, operations)
        self._add_combo(advanced_form, "fal_birefnet_resolution", "Fal.ai BiRefNet разрешение", FAL_BIREFNET_RESOLUTION_OPTIONS, operations)
        self._add_bool(advanced_form, "fal_birefnet_refine_foreground", operations)
        self._add_bool(advanced_form, "fal_rembg_crop_to_bbox", operations)
        self._add_combo(
            advanced_form,
            "chroma_key_color",
            "Chroma Key цвет",
            (("Авто", "auto"),) + CHROMA_KEY_COLOR_OPTIONS
            if self.show_background_controls else CHROMA_KEY_COLOR_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "chroma_subject_profile",
            "Тип изображения",
            CHROMA_SUBJECT_PROFILE_OPTIONS,
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
        self._add_combo(
            advanced_form,
            "local_rembg_profile",
            "rembg профиль",
            LOCAL_REMBG_PROFILE_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "local_rembg_model",
            "rembg модель",
            LOCAL_REMBG_MODEL_OPTIONS,
            operations,
        )
        self._add_combo(
            advanced_form,
            "local_rembg_edge_quality",
            "Качество края rembg",
            (("Мягкое", "soft"), ("Обычное", "normal"), ("Резкое", "sharp"),
             ("Чёткий контур без размытия", "cutout")),
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
        self.add_widget(advanced)
        self._build_stage_sections(operations_group, advanced)

        self.cleanup_group = None
        if self.cleanup_checkbox is not None:
            self.cleanup_checkbox.toggled.connect(self._sync)

        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.pipeline_label.setAccessibleName("Порядок обработки")
        self.add_widget(self.pipeline_label)
        self._layout.addStretch(1)
        self._connect_controls()
        self.refresh_from_state()

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def _build_stage_sections(
        self,
        operations_group: QGroupBox,
        advanced_group: QGroupBox,
    ) -> None:
        """Move controls into lightweight enabled-stage sections.

        The controls remain the same widgets, so the editor continues to own a
        single source of truth for state and provider-specific visibility.
        """
        self.stage_headers: dict[str, QLabel] = {}
        self.stage_sections: dict[str, QWidget] = {}
        self._stage_layout = QVBoxLayout()
        self._stage_layout.setContentsMargins(0, 0, 0, 0)
        self._stage_layout.setSpacing(0)
        stages_widget = QWidget()
        stages_widget.setLayout(self._stage_layout)
        self.add_widget(stages_widget)

        stage_forms = {
            key: self._add_stage_section(key, title)
            for key, title in self._STAGE_TITLES.items()
        }
        labels = {
            "upscale_before_provider": "Провайдер",
            "kie_upscale_model": "Модель",
            "fal_upscale_model": "Модель",
            "fal_upscale_scale": "Масштаб",
            "upscale_factor": "Масштаб",
            "local_realesrgan_profile": "Профиль",
            "local_realesrgan_scale": "Масштаб",
            "unsharp_amount": "Интенсивность",
            "unsharp_radius": "Радиус",
            "unsharp_threshold": "Порог",
            "remove_background_provider": "Метод",
            "kie_remove_bg_model": "Модель",
            "fal_remove_bg_model": "Модель Fal.ai",
            "fal_birefnet_model": "Вариант BiRefNet",
            "fal_birefnet_resolution": "Разрешение BiRefNet",
            "chroma_key_color": "Цвет фона",
            "chroma_subject_profile": "Тип изображения",
            "local_rembg_profile": "Профиль rembg",
            "local_rembg_model": "Модель rembg",
            "local_rembg_edge_quality": "Качество края",
            "local_ben2_alpha_threshold": "Порог alpha",
            "local_ben2_edge_softness": "Мягкость края",
            "local_ben2_corner_radius": "Радиус углов",
            "upscale_after_provider": "Провайдер",
            "kie_upscale_after_model": "Модель",
            "fal_upscale_after_model": "Модель",
            "fal_upscale_after_scale": "Масштаб",
            "local_realesrgan_after_scale": "Масштаб",
            "edge_shrink_pixels": "Очистка края, px",
            "trim_mode": "Trim по",
        }
        groups = {
            "upscale_before": (
                "upscale_before_provider", "kie_upscale_model", "upscale_factor",
                "fal_upscale_model", "fal_upscale_scale",
                "local_realesrgan_profile", "local_realesrgan_scale",
            ),
            "unsharp": ("unsharp_amount", "unsharp_radius", "unsharp_threshold"),
            "remove_background": (
                "remove_background_provider", "kie_remove_bg_model",
                "fal_remove_bg_model", "fal_birefnet_model",
                "fal_birefnet_resolution", "fal_birefnet_refine_foreground",
                "fal_rembg_crop_to_bbox", "chroma_key_color", "chroma_subject_profile",
                "local_rembg_profile", "local_rembg_model",
                "local_rembg_edge_quality", "local_ben2_refine_foreground",
                "local_ben2_alpha_threshold", "local_ben2_edge_softness",
                "local_ben2_corner_radius",
            ),
            "upscale_after": (
                "upscale_after_provider", "kie_upscale_after_model",
                "fal_upscale_after_model", "fal_upscale_after_scale",
                "local_realesrgan_after_scale",
            ),
            "edge_shrink": ("edge_shrink_pixels",),
            "trim": ("trim_mode",),
            "export_300_dpi": (),
        }
        for stage_key, control_names in groups.items():
            for name in control_names:
                self._move_control_to_stage(
                    self.operation_widgets[name],
                    stage_forms[stage_key],
                    labels.get(name),
                )
        advanced_group.setVisible(False)
        self.white_background_note = QLabel()
        self.white_background_note.setWordWrap(True)
        self.white_background_note.setProperty("v3Subtitle", True)
        stage_forms["remove_background"].addRow("", self.white_background_note)
        self.chroma_subject_note = QLabel(
            "Для тюля и прозрачной ткани выбирайте полупрозрачные материалы. "
            "Проверьте результат на разных подложках."
        )
        self.chroma_subject_note.setWordWrap(True)
        self.chroma_subject_note.setMaximumWidth(600)
        self.chroma_subject_note.setProperty("v3Subtitle", True)
        stage_forms["remove_background"].addRow("", self.chroma_subject_note)
        self.bria_upscale_note = QLabel(BRIA_HINT_TEXT)
        self.bria_upscale_note.setWordWrap(True)
        self.bria_upscale_note.setProperty("v3Subtitle", True)
        stage_forms["upscale_after"].addRow("", self.bria_upscale_note)
        operations_group.layout().activate()

    def _add_stage_section(self, key: str, title: str) -> QFormLayout:
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 12, 0, 12)
        section_layout.setSpacing(8)
        header = QLabel(title)
        header.setProperty("v3StageTitle", True)
        section_layout.addWidget(header)
        form_container = QWidget()
        form = QFormLayout(form_container)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(8)
        section_layout.addWidget(form_container)
        self.stage_headers[key] = header
        self.stage_sections[key] = section
        if not hasattr(self, "stage_dividers"):
            self.stage_dividers: dict[str, QFrame] = {}
        if self._stage_layout.count():
            divider = QFrame()
            divider.setFrameShape(QFrame.Shape.HLine)
            divider.setFrameShadow(QFrame.Shadow.Sunken)
            divider.setProperty("v3StageDivider", True)
            self._stage_layout.addWidget(divider)
            self.stage_dividers[key] = divider
        self._stage_layout.addWidget(section)
        return form

    @staticmethod
    def _move_control_to_stage(
        control: QWidget,
        target: QFormLayout,
        label: str | None,
    ) -> None:
        source = control.parentWidget()
        source_layout = source.layout() if source is not None else None
        if isinstance(source_layout, QFormLayout):
            original_label = source_layout.labelForField(control)
            source_layout.removeWidget(control)
            if original_label is not None:
                source_layout.removeWidget(original_label)
                original_label.hide()
        if isinstance(control, QCheckBox):
            target.addRow(control)
        else:
            target.addRow(label or control.accessibleName(), control)

    def visible_stage_keys(self) -> tuple[str, ...]:
        return tuple(
            key for key in self._STAGE_ORDER
            if not self.stage_sections[key].isHidden()
        )

    def _add_bool(self, form: QFormLayout, name: str, operations: ImageOperationData) -> None:
        control = self._new_bool_control(name, operations)
        form.addRow(control)

    def _new_bool_control(
        self,
        name: str,
        operations: ImageOperationData,
    ) -> QCheckBox:
        control = QCheckBox(self._BOOL_LABELS[name])
        control.setChecked(bool(getattr(operations, name)))
        control.setAccessibleName(self._BOOL_LABELS[name])
        if name == "visible_mark_cleanup":
            control.setToolTip(
                "Пытается удалить только подтверждённую видимую метку на пикселях. "
                "Метаданные и SynthID эта настройка не удаляет."
            )
        self.operation_widgets[name] = control
        return control

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
        if self.show_background_controls:
            control.setMinimumContentsLength(12)
            control.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
            control.setMaximumWidth(
                300 if name == "chroma_subject_profile" else
                360 if "model" in name or name == "remove_background_provider" else 240
            )
            control.setToolTip(control.currentText())
            control.currentTextChanged.connect(control.setToolTip)
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
        self.operation_widgets["chroma_key_color"].activated.connect(self._chroma_color_activated)
        for control in self.operation_widgets.values():
            if isinstance(control, QCheckBox):
                control.toggled.connect(self._sync)
            elif isinstance(control, QComboBox):
                control.currentIndexChanged.connect(self._sync)
            elif isinstance(control, (QSpinBox, QDoubleSpinBox)):
                control.valueChanged.connect(self._sync)
            elif isinstance(control, QLineEdit):
                control.textChanged.connect(self._sync)

    def _chroma_color_activated(self, *_: Any) -> None:
        self.state_owner.operations.chroma_key_color_override = (
            self.operation_widgets["chroma_key_color"].currentData() != "auto"
        )
        self.changed()

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
        profile_combo = self.operation_widgets.get("local_rembg_profile")
        model_combo = self.operation_widgets.get("local_rembg_model")
        if self.sender() is profile_combo and isinstance(model_combo, QComboBox):
            model_index = model_combo.findData(
                LOCAL_REMBG_PROFILE_MODELS.get(profile_combo.currentData(), "")
            )
            if model_index >= 0:
                previous = model_combo.blockSignals(True)
                model_combo.setCurrentIndex(model_index)
                model_combo.blockSignals(previous)
                if self.show_background_controls:
                    model_combo.setToolTip(model_combo.currentText())
        current = self.state_owner.operations.to_dict()
        for name, control in self.operation_widgets.items():
            current[name] = self._value(control)
        if self.cleanup_checkbox is not None:
            cleanup_enabled = self.cleanup_checkbox.isChecked()
            for name in self._CLEANUP_FIELDS:
                current[name] = cleanup_enabled
            current["preserve_icc"] = True
            current["preserve_dpi"] = True
        current["visible_mark_cleanup_mode"] = "gemini_auto"
        operations = self.state_owner.operations
        for name, value in current.items():
            setattr(operations, name, value)
        self.state_owner.operations = operations
        if isinstance(getattr(self.state_owner, "recipe", None), str):
            self.state_owner.recipe = "custom"
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
        operations = self.state_owner.operations
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
            "fal_upscale_model": operations.upscale_before
            and "fal_upscale_model" in before_controls,
            "fal_upscale_after_model": operations.upscale_after
            and "fal_upscale_after_model" in after_controls,
            "fal_upscale_scale": (
                operations.upscale_before
                and operations.upscale_before_provider == "fal"
                and operations.fal_upscale_model in {
                    FAL_TOPAZ_PRECISION_MODEL_ID,
                    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
                }
            ),
            "fal_upscale_after_scale": (
                operations.upscale_after
                and operations.upscale_after_provider == "fal"
                and operations.fal_upscale_after_model in {
                    FAL_TOPAZ_PRECISION_MODEL_ID,
                    FAL_BRIA_INCREASE_RESOLUTION_MODEL_ID,
                }
            ),
            "upscale_factor": (
                operations.upscale_before
                and operations.upscale_before_provider == "kie"
                and operations.kie_upscale_model == KIE_TOPAZ_MODEL_ID
            )
            or (
                operations.upscale_after
                and operations.upscale_after_provider == "kie"
                and operations.kie_upscale_after_model == KIE_TOPAZ_MODEL_ID
            ),
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
            "fal_remove_bg_model": operations.remove_background
            and "fal_remove_bg_model" in remove_controls,
            "fal_birefnet_model": operations.remove_background
            and "fal_birefnet_model" in remove_controls
            and operations.fal_remove_bg_model == "fal-ai/birefnet/v2",
            "fal_birefnet_resolution": operations.remove_background
            and "fal_birefnet_resolution" in remove_controls
            and operations.fal_remove_bg_model == "fal-ai/birefnet/v2",
            "fal_birefnet_refine_foreground": operations.remove_background
            and "fal_birefnet_refine_foreground" in remove_controls
            and operations.fal_remove_bg_model == "fal-ai/birefnet/v2",
            "fal_rembg_crop_to_bbox": operations.remove_background
            and "fal_rembg_crop_to_bbox" in remove_controls
            and operations.fal_remove_bg_model == "fal-ai/imageutils/rembg",
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
            "chroma_subject_profile": operations.remove_background
            and "chroma_subject_profile" in remove_controls,
            "unsharp_amount": operations.unsharp,
            "unsharp_radius": operations.unsharp,
            "unsharp_threshold": operations.unsharp,
        }
        for name, visible in visibility.items():
            self._set_control_visible(name, visible)
        if not self.show_background_controls:
            for name in self._BACKGROUND_INTERNAL_CONTROLS:
                self._set_control_visible(name, False)
        self._refresh_stage_visibility()
        self._refresh_white_background_method()
        self.chroma_subject_note.setVisible(
            self.show_background_controls and operations.remove_background
            and operations.remove_background_provider == "local_chroma_key"
        )
        self.bria_upscale_note.setVisible(
            operations.upscale_after
            and operations.upscale_after_provider == "fal"
            and operations.fal_upscale_after_model in BRIA_UPSCALE_MODEL_IDS
        )

    def _refresh_white_background_method(self) -> None:
        control = self.operation_widgets["remove_background_provider"]
        index = control.findData("local_white_background")
        available = white_background.white_background_available()
        item = control.model().item(index)
        item.setEnabled(available)
        item.setData(
            "Чёткий контур без мягких теней. Обработка локально."
            if available else WHITE_BACKGROUND_UNAVAILABLE_MESSAGE,
            Qt.ItemDataRole.ToolTipRole,
        )
        operations = self.state_owner.operations
        selected = operations.remove_background_provider == "local_white_background"
        self.white_background_note.setVisible(
            self.show_background_controls and operations.remove_background and selected
        )
        self.white_background_note.setText(
            "Чёткий контур без мягких теней. Обработка локально."
            if available else WHITE_BACKGROUND_UNAVAILABLE_MESSAGE
        )
        if selected:
            control.setToolTip(
                control.currentText() if available else WHITE_BACKGROUND_UNAVAILABLE_MESSAGE
            )

    def _refresh_stage_visibility(self) -> None:
        operations = self.state_owner.operations
        enabled = {
            "upscale_before": operations.upscale_before,
            "unsharp": operations.unsharp,
            "remove_background": operations.remove_background,
            "upscale_after": (
                UPSCALE_AFTER_UI_ENABLED and operations.upscale_after
            ),
            "edge_shrink": operations.edge_shrink,
            "trim": operations.trim,
            "export_300_dpi": operations.export_300_dpi,
        }
        for key, section in self.stage_sections.items():
            section.setVisible(bool(enabled[key]))
        if not UPSCALE_AFTER_UI_ENABLED:
            self._set_control_visible("upscale_after", False)
        has_visible_stage = False
        for key in self._STAGE_ORDER:
            visible = bool(enabled[key])
            divider = self.stage_dividers.get(key)
            if divider is not None:
                divider.setVisible(visible and has_visible_stage)
            has_visible_stage = has_visible_stage or visible
        self._apply_workflow_visibility()
        self._refresh_model_compatibility()

    def _apply_workflow_visibility(self) -> None:
        """Apply the active workflow's operation surface after provider rules."""
        if self.allowed_operations is None:
            return
        operations = self.state_owner.operations
        operation_names = (
            "visible_mark_cleanup",
            "invisible_watermark_cleanup",
            "upscale_before",
            "unsharp",
            "remove_background",
            "upscale_after",
            "edge_shrink",
            "trim",
            "export_300_dpi",
            *self._CLEANUP_FIELDS,
        )
        for name in operation_names:
            allowed = name in self.allowed_operations or (
                name in self._CLEANUP_FIELDS
                and "metadata_cleanup" in self.allowed_operations
            )
            if name == "upscale_after" and not UPSCALE_AFTER_UI_ENABLED:
                allowed = False
            self._set_control_visible(name, allowed)
            if not allowed and hasattr(operations, name):
                setattr(operations, name, False)

        operation_for_control = {
            "upscale_before_provider": "upscale_before",
            "upscale_after_provider": "upscale_after",
            "remove_background_provider": "remove_background",
            "edge_shrink_pixels": "edge_shrink",
            "trim_mode": "trim",
            "kie_upscale_model": "upscale_before",
            "kie_upscale_after_model": "upscale_after",
            "upscale_factor": "upscale_before",
            "local_realesrgan_profile": "upscale_before",
            "local_realesrgan_scale": "upscale_before",
            "local_realesrgan_after_scale": "upscale_after",
            "kie_remove_bg_model": "remove_background",
            "fal_remove_bg_model": "remove_background",
            "fal_birefnet_model": "remove_background",
            "fal_birefnet_resolution": "remove_background",
            "fal_birefnet_refine_foreground": "remove_background",
            "fal_rembg_crop_to_bbox": "remove_background",
            "local_rembg_profile": "remove_background",
            "local_rembg_model": "remove_background",
            "local_rembg_edge_quality": "remove_background",
            "local_ben2_refine_foreground": "remove_background",
            "local_ben2_alpha_threshold": "remove_background",
            "local_ben2_edge_softness": "remove_background",
            "local_ben2_corner_radius": "remove_background",
            "chroma_key_color": "remove_background",
            "chroma_subject_profile": "remove_background",
            "unsharp_amount": "unsharp",
            "unsharp_radius": "unsharp",
            "unsharp_threshold": "unsharp",
        }
        for control_name, operation_name in operation_for_control.items():
            provider_visible = self.operation_widgets.get(control_name)
            self._set_control_visible(
                control_name,
                operation_name in self.allowed_operations
                and (self.show_background_controls
                     or control_name not in self._BACKGROUND_INTERNAL_CONTROLS)
                and (provider_visible is None or not provider_visible.isHidden()),
            )
        cleanup_visible = "metadata_cleanup" in self.allowed_operations
        if self.cleanup_group is not None:
            self.cleanup_group.setVisible(cleanup_visible)
        if self.cleanup_checkbox is not None:
            self.cleanup_checkbox.setVisible(cleanup_visible)

    def _refresh_model_compatibility(self) -> None:
        operations = self.state_owner.operations
        model_combo = self.operation_widgets.get("kie_upscale_after_model")
        if not isinstance(model_combo, QComboBox):
            return
        recraft_index = model_combo.findData("recraft/crisp-upscale")
        if recraft_index < 0:
            return
        blocked = bool(
            operations.remove_background
            and operations.upscale_after
            and operations.upscale_after_provider == "kie"
        )
        item = model_combo.model().item(recraft_index)
        item.setEnabled(not blocked)
        if blocked:
            item.setToolTip(
                "Недоступно после подготовки прозрачного фона: Recraft Crisp не поддерживает "
                "прозрачный вход. Используйте Local Real-ESRGAN или Recraft Crisp "
                "до подготовки прозрачного фона."
            )
        else:
            item.setToolTip("")

    def _refresh_pipeline(self) -> None:
        steps = RunPlanBuilder.processing_steps(
            self.state_owner.operations,
            include_cleanup=self.include_cleanup,
        )
        text = "Порядок: " + (" → ".join(steps) if steps else "операции не выбраны")
        self.pipeline_label.setText(text)
        self.pipeline_label.setAccessibleName(text)

    def refresh_from_state(self) -> None:
        operations = self.state_owner.operations
        if not UPSCALE_AFTER_UI_ENABLED:
            operations.upscale_after = False
        for name, control in self.operation_widgets.items():
            control.blockSignals(True)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(getattr(operations, name)))
            elif isinstance(control, QComboBox):
                index = control.findData(getattr(operations, name))
                control.setCurrentIndex(index if index >= 0 else 0)
            elif isinstance(control, QSpinBox):
                control.setValue(int(getattr(operations, name)))
            elif isinstance(control, QDoubleSpinBox):
                control.setValue(float(getattr(operations, name)))
            elif isinstance(control, QLineEdit):
                control.setText(str(getattr(operations, name)))
            control.blockSignals(False)
            if self.show_background_controls and isinstance(control, QComboBox):
                control.setToolTip(control.currentText())
        if self.cleanup_checkbox is not None:
            cleanup_enabled = all(
                bool(getattr(operations, name))
                for name in self._CLEANUP_FIELDS
            ) and bool(getattr(operations, "preserve_icc", True)) and bool(
                getattr(operations, "preserve_dpi", True)
            )
            self.cleanup_checkbox.blockSignals(True)
            self.cleanup_checkbox.setChecked(cleanup_enabled)
            self.cleanup_checkbox.blockSignals(False)
        self._refresh_control_visibility()
        self._refresh_pipeline()

    def validation_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if (
            self.state_owner.operations.remove_background
            and self.state_owner.operations.remove_background_provider == "local_white_background"
            and not white_background.white_background_available()
        ):
            issues.append("white_background_unavailable")
        if self.require_operation and not processing_pipeline_steps(
            self.state_owner.operations,
            include_cleanup=self.include_cleanup,
        ):
            issues.append("processing_operation_required")
        if (
            self.state_owner.operations.visible_mark_cleanup
            and self.state_owner.operations.visible_mark_cleanup_mode == "confirmed_area"
        ):
            issues.append("confirmed_area_unavailable")
        return tuple(issues)
