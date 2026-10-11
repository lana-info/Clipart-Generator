"""Shared image-generation settings UI for built-in workflows."""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QFormLayout, QFrame, QLabel, QSpinBox, QVBoxLayout, QWidget

from model_catalog import ratios_for_mode
from v3_components import AdvancedSection, DEFAULT_TOKENS, V3DesignTokens
from v3_flow_ui import ScrollableStepPage
from v3_image_generation_runtime import GenerationModelOption, _model_option, generation_model_options
from v3_project_state import GenerationData

def _capability_summary(option: GenerationModelOption) -> str:
    ratios = ", ".join(option.ratios[:4]) if option.ratios else "любой"
    if option.resolutions:
        resolutions = ", ".join(option.resolutions[:4])
    else:
        resolutions = "задаётся моделью"
    if option.model_id == "piapi/gpt-image-2.5":
        return "Бюджетный GPT Image 2.5: размер и качество выбирает модель. Один файл за запрос."
    reference_mode = (
        "поддерживает reference-mode"
        if option.reference_compatible_text or option.model_type in {"image_to_image", "edit"}
        else "без reference-mode"
    )
    best_for = {
        "gpt-image/1.5-text-to-image": "совместимость со старыми проектами",
        "gpt-image-2": "универсальный клипарт и точное следование промпту",
        "nano-banana-2": "быстрые иллюстрации и работа с референсами",
        "nano-banana-pro": "детализированный клипарт и сложные референсы",
        "qwen-image-2": "стилизованные иллюстрации и вариации",
        "flux-2/flex-text-to-image": "разные художественные стили",
        "flux-2/pro-text-to-image": "финальное качество и детализация",
    }.get(option.model_id, "универсальные изображения")
    return (
        f"Лучше всего для: {best_for}. {option.label} · {reference_mode} · "
        f"форматы: {ratios} · разрешения: {resolutions}"
    )


class ImageGenerationSettingsPage(ScrollableStepPage):
    allow_shared_text_models = True
    allow_fal_models = True
    shared_generation_settings = False
    shared_reference_format = False
    reference_controls_compact = True
    show_primary_scope = False
    show_model_capabilities = True
    show_ratio_preview = True
    def __init__(
        self,
        data: Any,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Генерация",
            "Выберите модель, формат и число вариантов до платного запуска.",
            tokens=tokens,
        )
        self.data = data
        self.changed = changed
        self.text_options = generation_model_options(
            references=False,
            include_shared_reference_text=self.allow_shared_text_models,
            include_fal_models=self.allow_fal_models,
        )
        self.reference_options = generation_model_options(
            references=True,
            include_fal_models=self.allow_fal_models,
        )
        self.primary_scope_label = QLabel()
        self.primary_scope_label.setProperty("v3Selection", True)
        self.primary_scope_label.setAccessibleName("Промпты без референсов")
        self.add_widget(self.primary_scope_label)
        if not self.show_primary_scope:
            self.primary_scope_label.hide()
        form = QFormLayout()
        self.model_combo = QComboBox()
        self.ratio_combo = QComboBox()
        self.resolution_combo = QComboBox()
        self.variants_spin = QSpinBox()
        self.variants_spin.setRange(1, 100)
        for option in self._model_options_for_current_prompts():
            self.model_combo.addItem(option.label, option.model_id)
        form.addRow("Модель", self.model_combo)
        form.addRow("Пропорция", self.ratio_combo)
        form.addRow("Разрешение", self.resolution_combo)
        form.addRow("Вариантов на промпт", self.variants_spin)
        container = QWidget()
        container.setLayout(form)
        self.primary_controls_container = container
        self.add_widget(container)

        if self.show_ratio_preview:
            self.ratio_preview = QFrame()
            self.ratio_preview.setProperty("v3Card", True)
            preview_layout = QVBoxLayout(self.ratio_preview)
            self.ratio_preview_label = QLabel()
            self.ratio_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview_layout.addWidget(self.ratio_preview_label)
            self.add_widget(self.ratio_preview)

        self.model_capability_label = QLabel()
        self.model_capability_label.setWordWrap(True)
        self.model_capability_label.setProperty("v3Small", True)
        self.add_widget(self.model_capability_label)
        if not self.show_model_capabilities:
            self.model_capability_label.hide()

        if not self.shared_generation_settings:
            reference_form = QFormLayout()
            self.reference_model_combo = QComboBox()
            for option in self.reference_options:
                self.reference_model_combo.addItem(option.label, option.model_id)
            reference_form.addRow("Модель с референсом", self.reference_model_combo)
            reference_widget = QWidget()
            reference_widget.setLayout(reference_form)
            if not self.shared_reference_format:
                self.reference_ratio_combo = QComboBox()
                self.reference_resolution_combo = QComboBox()
                reference_form.addRow("Пропорция с референсом", self.reference_ratio_combo)
                reference_form.addRow(
                    "Разрешение с референсом",
                    self.reference_resolution_combo,
                )
            if self.reference_controls_compact:
                self.reference_controls_container = reference_widget
                self.add_widget(reference_widget)
            else:
                advanced = AdvancedSection("Промпты с референсами", tokens=tokens)
                self.reference_advanced = advanced
                advanced.set_expanded(True)
                self.reference_capability_label = QLabel()
                self.reference_capability_label.setWordWrap(True)
                self.reference_capability_label.setProperty("v3Small", True)
                advanced.add_widget(self.reference_capability_label)
                advanced.add_widget(reference_widget)
                self.add_widget(advanced)

        for label, control in (
            ("Модель", self.model_combo),
            ("Пропорция", self.ratio_combo),
            ("Разрешение", self.resolution_combo),
            ("Вариантов на промпт", self.variants_spin),
            *((
                ("Модель с референсом", self.reference_model_combo),
            ) if not self.shared_generation_settings and self.shared_reference_format else (
                ("Модель с референсом", self.reference_model_combo),
                ("Пропорция с референсом", self.reference_ratio_combo),
                ("Разрешение с референсом", self.reference_resolution_combo),
            ) if not self.shared_generation_settings else ()),
        ):
            control.setAccessibleName(label)

        self._select_model(self.model_combo, data.generation.model)
        if not self.shared_generation_settings:
            self._select_model(
                self.reference_model_combo,
                data.generation.reference_model,
            )
        self._refresh_profile_controls(primary=True, sync=False)
        if not self.shared_generation_settings and not self.shared_reference_format:
            self._refresh_profile_controls(primary=False, sync=False)
        self.variants_spin.setValue(data.generation.variants)
        self.model_combo.currentIndexChanged.connect(
            lambda: self._refresh_profile_controls(primary=True)
        )
        if not self.shared_generation_settings:
            self.reference_model_combo.currentIndexChanged.connect(
                self._sync if self.shared_reference_format else lambda: self._refresh_profile_controls(primary=False)
            )
        self.ratio_combo.currentTextChanged.connect(self._sync)
        self.resolution_combo.currentIndexChanged.connect(self._sync)
        if not self.shared_generation_settings and not self.shared_reference_format:
            self.reference_ratio_combo.currentTextChanged.connect(self._sync)
            self.reference_resolution_combo.currentIndexChanged.connect(self._sync)
        self.variants_spin.valueChanged.connect(self._sync)
        self._sync(mark=False)
        if self.show_ratio_preview:
            self.ratio_combo.currentTextChanged.connect(self._refresh_ratio_preview)
            self._refresh_ratio_preview()
        ImageGenerationSettingsPage.refresh_from_state(self)

    def _select_model(self, combo: QComboBox, model_id: str) -> None:
        index = combo.findData(model_id)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _has_references(self) -> bool:
        return any(entry.references for entry in self.data.prompts)

    def _model_options_for_current_prompts(self) -> tuple[GenerationModelOption, ...]:
        if not self.shared_generation_settings or not self._has_references():
            return self.text_options
        reference_ids = {option.model_id for option in self.reference_options}
        return tuple(
            option for option in self.text_options if option.model_id in reference_ids
        )

    def _replace_model_options(self) -> None:
        selected_model = str(self.model_combo.currentData() or self.data.generation.model)
        options = self._model_options_for_current_prompts()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        for option in options:
            self.model_combo.addItem(option.label, option.model_id)
        self._select_model(self.model_combo, selected_model)
        self.model_combo.blockSignals(False)

    def _option_for_combo(self, combo: QComboBox) -> GenerationModelOption:
        return _model_option(str(combo.currentData() or ""))

    def _supported_primary_ratios(
        self,
        option: GenerationModelOption,
    ) -> tuple[str, ...]:
        """Expose only ratios valid for every prompt routed through this model."""
        modes = {False}
        if self.shared_generation_settings:
            prompts = getattr(self.data, "prompts", ())
            modes = {bool(entry.references) for entry in prompts} or {False}
        allowed: set[str] | None = None
        for has_references in modes:
            supported = set(ratios_for_mode(option.model_id, has_references))
            allowed = supported if allowed is None else allowed & supported
        return tuple(ratio for ratio in option.ratios if ratio in (allowed or set()))

    def _set_values(
        self,
        combo: QComboBox,
        values: Sequence[str],
        preferred: str,
        *,
        fixed_value: str | None = None,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        if tuple(values) == ("auto",):
            combo.addItem("Авто (выбирает модель)", "auto")
            combo.setEnabled(False)
        elif values:
            combo.addItems(values)
            combo.setCurrentText(
                preferred if preferred in values else str(values[0])
            )
            combo.setEnabled(True)
        else:
            combo.addItem("Задаётся моделью", fixed_value or "1K")
            combo.setEnabled(False)
        combo.blockSignals(False)

    def _refresh_profile_controls(
        self,
        *,
        primary: bool,
        sync: bool = True,
    ) -> None:
        generation = self.data.generation
        if primary:
            option = self._option_for_combo(self.model_combo)
            self.model_capability_label.setText(_capability_summary(option))
            self._set_values(
                self.ratio_combo,
                self._supported_primary_ratios(option) or ("1:1",),
                generation.ratio,
            )
            self._set_values(
                self.resolution_combo,
                option.resolutions,
                generation.resolution,
                fixed_value="1K",
            )
        elif not self.shared_generation_settings and not self.shared_reference_format:
            option = self._option_for_combo(self.reference_model_combo)
            if hasattr(self, "reference_capability_label"):
                self.reference_capability_label.setText(_capability_summary(option))
            self._set_values(
                self.reference_ratio_combo,
                option.ratios or ("1:1",),
                generation.reference_ratio,
            )
            self._set_values(
                self.reference_resolution_combo,
                option.resolutions,
                generation.reference_resolution,
                fixed_value="1K",
            )
        if sync:
            self._sync()
        if hasattr(self, "ratio_preview"):
            self._refresh_ratio_preview()

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        return str(combo.currentData() or combo.currentText())

    def _sync(self, *_: Any, mark: bool = True) -> None:
        self.data.generation = GenerationData(
            model=str(self.model_combo.currentData() or ""),
            ratio=self._combo_value(self.ratio_combo),
            resolution=self._combo_value(self.resolution_combo),
            reference_model=(
                str(self.model_combo.currentData() or "")
                if self.shared_generation_settings
                else str(self.reference_model_combo.currentData() or "")
            ),
            reference_ratio=(
                self._combo_value(self.ratio_combo)
                if self.shared_generation_settings or self.shared_reference_format
                else self._combo_value(self.reference_ratio_combo)
            ),
            reference_resolution=(
                self._combo_value(self.resolution_combo)
                if self.shared_generation_settings or self.shared_reference_format
                else self._combo_value(self.reference_resolution_combo)
            ),
            variants=self.variants_spin.value(),
        )
        if mark:
            self.changed()

    def refresh_from_state(self) -> None:
        prompts = getattr(self.data, "prompts", [])
        reference_count = sum(bool(entry.references) for entry in prompts)
        text_count = len(prompts) - reference_count
        has_references = reference_count > 0
        if self.shared_generation_settings:
            label = f"Все промпты · {len(prompts)}"
            if has_references:
                label += f" · с референсами: {reference_count}"
            self.primary_scope_label.setText(label)
            self.primary_scope_label.setAccessibleDescription(
                "Общие настройки применяются ко всем промптам"
            )
            self._replace_model_options()
            self._refresh_profile_controls(primary=True, sync=False)
        else:
            self.primary_scope_label.setText(
                f"Промпты без референсов · {text_count}"
            )
            self.primary_scope_label.setAccessibleDescription(
                f"Настройки применяются к промптам без референсов: {text_count}"
            )
            if self.reference_controls_compact:
                self.reference_controls_container.setVisible(has_references)
            else:
                self.reference_advanced.toggle_button.setText(
                    f"Промпты с референсами · {reference_count}"
                )
                self.reference_advanced.toggle_button.setAccessibleName(
                    f"Промпты с референсами: {reference_count}"
                )
                self.reference_advanced.set_expanded(has_references)
                self.reference_advanced.setVisible(has_references)
        current = self._option_for_combo(self.model_combo)
        self.model_capability_label.setText(_capability_summary(current))
        self._sync(mark=False)

    def _refresh_ratio_preview(self, *_: Any) -> None:
        ratio = self._combo_value(self.ratio_combo)
        self.ratio_preview.setVisible(ratio != "auto")
        try:
            width_value, height_value = (
                max(1, int(value)) for value in ratio.split(":", 1)
            )
        except (TypeError, ValueError):
            width_value, height_value = 1, 1
        scale = 180 / max(width_value, height_value)
        self.ratio_preview.setFixedSize(
            max(20, round(width_value * scale)),
            max(20, round(height_value * scale)),
        )
        self.ratio_preview_label.setText(ratio)
        self.ratio_preview.setAccessibleName(ratio)
