from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from v3_components import DEFAULT_TOKENS, V3DesignTokens
from v3_provider_registry import (
    KIE_MODEL_OPTIONS,
    processing_provider_options,
    provider_visible_controls,
)
from v3_project_state import ImageOperationData, ProjectState


@dataclass(frozen=True, slots=True)
class ProcessingRecipe:
    key: str
    title: str
    description: str
    operations: ImageOperationData | None


def _operations(**overrides: Any) -> ImageOperationData:
    values = {
        name: getattr(ImageOperationData(), name)
        for name in ImageOperationData.__dataclass_fields__
    }
    for name in (
        "visible_mark_cleanup",
        "upscale_before",
        "upscale_after",
        "remove_background",
        "unsharp",
        "edge_shrink",
        "trim",
        "export_300_dpi",
        "remove_exif",
        "remove_xmp",
        "remove_iptc",
        "remove_comments_text",
        "remove_embedded_thumbnail",
        "remove_generator_fields",
        "remove_embedded_c2pa",
    ):
        values[name] = False
    values.update(overrides)
    return ImageOperationData(**values)


PROCESSING_RECIPES: dict[str, ProcessingRecipe] = {
    "basic_enhancement": ProcessingRecipe(
        key="basic_enhancement",
        title="Базовое улучшение",
        description="Локальная резкость без сетевой передачи.",
        operations=_operations(unsharp=True),
    ),
    "prepare_clipart": ProcessingRecipe(
        key="prepare_clipart",
        title="Подготовить клипарт",
        description="Локальное удаление фона, очистка края и trim.",
        operations=_operations(
            remove_background=True,
            remove_background_provider="local_rembg",
            edge_shrink=True,
            trim=True,
        ),
    ),
    "check_cleanup": ProcessingRecipe(
        key="check_cleanup",
        title="Проверить и очистить",
        description="Удаление служебных метаданных с сохранением ICC и DPI.",
        operations=_operations(
            remove_exif=True,
            remove_xmp=True,
            remove_iptc=True,
            remove_comments_text=True,
            remove_embedded_thumbnail=True,
            remove_generator_fields=True,
        ),
    ),
    "custom": ProcessingRecipe(
        key="custom",
        title="Свой рецепт",
        description="Настройки не меняются; операции выбираются вручную.",
        operations=None,
    ),
}


def apply_processing_recipe(state: ProjectState, recipe: str) -> None:
    if recipe not in PROCESSING_RECIPES:
        raise ValueError("Неизвестный рецепт обработки")
    state.processing.recipe = recipe
    preset = PROCESSING_RECIPES[recipe].operations
    if preset is None:
        return
    current = state.processing.operations
    for name in ImageOperationData.__dataclass_fields__:
        setattr(current, name, getattr(preset, name))


def processing_pipeline_steps(
    operations: ImageOperationData,
    *,
    include_cleanup: bool = False,
) -> tuple[str, ...]:
    steps: list[str] = []
    if operations.visible_mark_cleanup:
        steps.append("Удаление видимой метки")
    if operations.upscale_before:
        steps.append("Апскейл до удаления фона")
    if operations.unsharp:
        steps.append("Unsharp Mask")
    if operations.remove_background:
        steps.append("Удаление фона")
    if operations.upscale_after:
        steps.append("Апскейл после удаления фона")
    if operations.edge_shrink:
        steps.append("Очистка края alpha")
    if operations.trim:
        steps.append("Trim")
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
        steps.append("Очистка данных файла")
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
    _BOOL_LABELS = {
        "visible_mark_cleanup": "Удалить видимую метку автоматически",
        "upscale_before": "Апскейл до удаления фона",
        "upscale_after": "Апскейл после удаления фона",
        "remove_background": "Удалить фон",
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
        state_owner: Any,
        changed: Callable[[], None],
        *,
        title: str,
        description: str,
        include_cleanup: bool,
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
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
        )
        self._layout.setSpacing(tokens.space_4)
        title_label = QLabel(title)
        title_label.setProperty("v3Title", True)
        description_label = QLabel(description)
        description_label.setWordWrap(True)
        description_label.setProperty("v3Subtitle", True)
        self._layout.addWidget(title_label)
        self._layout.addWidget(description_label)
        self.state_owner = state_owner
        self.changed = changed
        self.include_cleanup = include_cleanup
        self.operation_widgets: dict[str, QWidget] = {}
        operations = state_owner.operations

        operations_group = QGroupBox("Операции")
        form = QFormLayout(operations_group)
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
            "kie_remove_bg_model",
            "KIE модель удаления фона",
            KIE_MODEL_OPTIONS,
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
        self.add_widget(advanced)

        if include_cleanup:
            cleanup = QGroupBox("Центр проверки и очистки файла")
            cleanup_form = QFormLayout(cleanup)
            for name in (
                "remove_exif",
                "remove_xmp",
                "remove_iptc",
                "remove_comments_text",
                "remove_embedded_thumbnail",
                "remove_generator_fields",
                "remove_embedded_c2pa",
                "preserve_icc",
                "preserve_dpi",
            ):
                self._add_bool(cleanup_form, name, operations)
            self.add_widget(cleanup)

        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.pipeline_label.setAccessibleName("Порядок обработки")
        self.add_widget(self.pipeline_label)
        self._connect_controls()
        self.refresh_from_state()

    def add_widget(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def _add_bool(self, form: QFormLayout, name: str, operations: ImageOperationData) -> None:
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
        current = self.state_owner.operations.to_dict()
        for name, control in self.operation_widgets.items():
            current[name] = self._value(control)
        current["visible_mark_cleanup_mode"] = "gemini_auto"
        operations = self.state_owner.operations
        for name, value in current.items():
            setattr(operations, name, value)
        if hasattr(self.state_owner, "recipe"):
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
            "remove_exif": self.include_cleanup,
            "remove_xmp": self.include_cleanup,
            "remove_iptc": self.include_cleanup,
            "remove_comments_text": self.include_cleanup,
            "remove_embedded_thumbnail": self.include_cleanup,
            "remove_generator_fields": self.include_cleanup,
            "remove_embedded_c2pa": self.include_cleanup,
            "preserve_icc": self.include_cleanup,
            "preserve_dpi": self.include_cleanup,
            "unsharp_amount": operations.unsharp,
            "unsharp_radius": operations.unsharp,
            "unsharp_threshold": operations.unsharp,
        }
        for name, visible in visibility.items():
            self._set_control_visible(name, visible)

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
        self._refresh_control_visibility()
        self._refresh_pipeline()

    def validation_issues(self) -> tuple[str, ...]:
        issues: list[str] = []
        if not processing_pipeline_steps(
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
