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
from chroma_key import chroma_key_prompt_block
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
from v3_processing_editor import (
    ProcessingPipelineEditor,
    RunPlanBuilder,
    UPSCALE_AFTER_UI_ENABLED,
)
from v3_provider_registry import CHROMA_KEY_COLOR_OPTIONS
from fal_model_catalog import is_fal_generation_model, is_fal_model_id
from processing_cleanup import METADATA_CLEANUP_FIELDS
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
from v3_prompt_generator import (
    PromptGeneratorError,
    generate_into_project,
    generate_prompt_series,
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


MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CLIPART_REQUESTS = 5000
CHROMA_KEY_MATERIAL_OPTIONS = (
    ("Акварель", "watercolor"),
    ("Тонкие листья", "thin_leaves"),
    ("Хвоя", "conifer_needles"),
    ("Металл", "metal"),
    ("Лента / сатин", "ribbon_satin"),
    ("Прозрачные детали", "transparent_details"),
    ("Снег / лёд", "snow_ice"),
)


def configure_chroma_material_buttons(buttons: Sequence[QPushButton]) -> None:
    """Keep the compact Chroma Key helper readable and prompt-safe."""

    def refresh() -> None:
        selected_count = sum(button.isChecked() for button in buttons)
        limit_reached = selected_count >= MAX_CHROMA_KEY_MATERIALS
        for button in buttons:
            button.setEnabled(button.isChecked() or not limit_reached)

    for button in buttons:
        button.setProperty("v3ChromaMaterial", True)
        button.setToolTip("Можно выбрать до трёх материалов")
        button.toggled.connect(refresh)
    refresh()
MAX_REFERENCE_FILE_BYTES = 10 * 1024 * 1024
_DOLLAR_PATTERN = re.compile(r"\$(\d+(?:\.\d+)?)")
_CHROMA_PROMPT_SUFFIX_MARKER = (
    "\nIsolated on a completely flat, uniform, solid pure "
)


class ClipartFlowError(ValueError):
    pass


@dataclass(frozen=True)
class GenerationModelOption:
    model_id: str
    label: str
    model_type: str
    ratios: tuple[str, ...]
    resolutions: tuple[str, ...]
    pricing: str | Mapping[str, str] | None
    reference_compatible_text: bool = False


@dataclass(frozen=True)
class CostEstimate:
    request_count: int
    estimated_usd: Decimal
    complete: bool
    generation_request_count: int = 0
    processing_request_count: int = 0
    generation_usd: Decimal = Decimal("0")
    processing_usd: Decimal = Decimal("0")
    provider_usd: Mapping[str, Decimal] = field(default_factory=dict)
    incomplete_providers: tuple[str, ...] = ()

    @property
    def summary(self) -> str:
        if not self.complete:
            return (
                f"{self.request_count} запросов · "
                "стоимость не рассчитана полностью"
            )
        return (
            f"{self.request_count} запросов · "
            f"ориентировочно ${self.estimated_usd:.3f}"
        )


@dataclass
class ClipartRunRequest:
    mode: str
    work_dir: str
    settings: dict[str, Any] = field(repr=False)
    generated_prompts: list[dict[str, Any]] = field(default_factory=list)
    selected_files: list[str] = field(default_factory=list, repr=False)

    def worker_kwargs(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "work_dir": self.work_dir,
            "settings": dict(self.settings),
            "selected_files": list(self.selected_files),
            "generated_prompts": [
                {
                    "prompt": entry["prompt"],
                    "references": list(entry["references"]),
                }
                for entry in self.generated_prompts
            ],
        }


_LEGACY_VISIBLE_GENERATION_MODEL_IDS = {
    "gpt-image/1.5-text-to-image",
    "gpt-image-2",
    "nano-banana-2",
    "nano-banana-pro",
    "qwen-image-2",
    "flux-2/pro-text-to-image",
    "flux-2/flex-text-to-image",
    "gpt-image/1.5-image-to-image",
    "flux-2/pro-image-to-image",
    "flux-2/flex-image-to-image",
}

_LEGACY_MODEL_CAPABILITIES: dict[str, dict[str, Any]] = {
    "gpt-image/1.5-text-to-image": {
        "ratios": {"1:1", "2:3", "3:2"},
        "qualities": {"medium", "high"},
        "pricing": "4 / 22 credits ($0.02 / $0.11)",
        "reference_compatible_text": False,
    },
    "gpt-image/1.5-image-to-image": {
        "ratios": {"1:1", "2:3", "3:2"},
        "qualities": {"medium", "high"},
        "pricing": "4 / 22 credits ($0.02 / $0.11)",
        "reference_compatible_text": False,
    },
    "gpt-image-2": {
        "ratios": {"auto", "1:1", "9:16", "16:9", "4:3", "3:4"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "6 credits / $0.03", "2K": "10 credits / $0.05", "4K": "16 credits / $0.08"},
        "reference_compatible_text": True,
    },
    "nano-banana-2": {
        "ratios": {"auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "8 credits / $0.04", "2K": "12 credits / $0.06", "4K": "18 credits / $0.09"},
        "reference_compatible_text": True,
    },
    "nano-banana-pro": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "18 credits / $0.09", "2K": "18 credits / $0.09", "4K": "24 credits / $0.12"},
        "reference_compatible_text": True,
    },
    "qwen-image-2": {
        "ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"},
        "pricing": "6 credits / $0.03",
        "reference_compatible_text": True,
    },
    "flux-2/flex-text-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"},
        "reference_compatible_text": False,
    },
    "flux-2/pro-text-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"},
        "reference_compatible_text": False,
    },
    "flux-2/flex-image-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"},
        "reference_compatible_text": False,
    },
    "flux-2/pro-image-to-image": {
        "ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"},
        "resolutions": {"1K", "2K"},
        "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"},
        "reference_compatible_text": False,
    },
}

_LEGACY_GENERATION_MODELS = (
    {"id": "gpt4o-image", "label": "GPT‑4o Image", "type": "text_to_image"},
    {"id": "gpt-image/1.5-text-to-image", "label": "GPT Image 1.5 (Text→Image)", "type": "text_to_image"},
    {"id": "gpt-image-2", "label": "GPT Image 2", "type": "text_to_image"},
    {"id": "nano-banana-2", "label": "Nano Banana 2", "type": "text_to_image"},
    {"id": "z-image", "label": "Z-Image", "type": "text_to_image"},
    {"id": "google/imagen4", "label": "Google Imagen 4", "type": "text_to_image"},
    {"id": "google/imagen4-fast", "label": "Google Imagen 4 Fast", "type": "text_to_image"},
    {"id": "google/imagen4-ultra", "label": "Google Imagen 4 Ultra", "type": "text_to_image"},
    {"id": "google/nano-banana", "label": "Google Nano Banana", "type": "text_to_image"},
    {"id": "qwen-image-2", "label": "Qwen Image 2.0", "type": "text_to_image"},
    {"id": "flux-2/flex-text-to-image", "label": "FLUX.2 Flex (Text→Image)", "type": "text_to_image"},
    {"id": "flux-2/pro-text-to-image", "label": "FLUX.2 Pro (Text→Image)", "type": "text_to_image"},
    {"id": "grok-imagine/text-to-image", "label": "Grok Imagine (Text→Image)", "type": "text_to_image"},
    {"id": "qwen/text-to-image", "label": "Qwen (Text→Image)", "type": "text_to_image"},
    {"id": "nano-banana-pro", "label": "Google Nano Banana Pro", "type": "image_to_image"},
    {"id": "gpt-image-2", "label": "GPT Image 2", "type": "image_to_image"},
    {"id": "nano-banana-2", "label": "Nano Banana 2", "type": "image_to_image"},
    {"id": "flux-2/pro-image-to-image", "label": "FLUX.2 Pro (Image→Image)", "type": "image_to_image"},
    {"id": "flux-2/flex-image-to-image", "label": "FLUX.2 Flex (Image→Image)", "type": "image_to_image"},
    {"id": "qwen-image-2", "label": "Qwen Image 2.0", "type": "edit"},
    {"id": "grok-imagine/image-to-image", "label": "Grok Imagine (Image→Image)", "type": "image_to_image"},
    {"id": "gpt-image/1.5-image-to-image", "label": "GPT Image 1.5 (Image→Image)", "type": "image_to_image"},
    {"id": "qwen/image-to-image", "label": "Qwen (Image→Image)", "type": "image_to_image"},
    {"id": "google/nano-banana-edit", "label": "Google Nano Banana Edit", "type": "edit"},
    {"id": "qwen/image-edit", "label": "Qwen Image Edit", "type": "edit"},
)

_LEGACY_RATIO_OPTIONS_ORDER = (
    "auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
    "1:2", "2:1", "1:3", "3:1", "9:16", "16:9", "9:21", "21:9",
    "1:4", "4:1", "1:8", "8:1"
)
_LEGACY_RESOLUTION_OPTIONS_ORDER = ("1K", "2K", "4K", "8K")
_LEGACY_PROCESSING_PRICING = {
    "topaz/image-upscale": "40 credits / $0.20",
    "recraft/crisp-upscale": "0.5 credits / $0.0025",
    "recraft/remove-background": "1 credit / $0.005",
}

# Keep the old private names for callers/tests while sourcing every option
# from the shared immutable catalog.
_LEGACY_VISIBLE_GENERATION_MODEL_IDS = CATALOG_VISIBLE_GENERATION_MODEL_IDS
_LEGACY_GENERATION_MODELS = CATALOG_GENERATION_MODELS
_LEGACY_PROCESSING_PRICING = CATALOG_PROCESSING_PRICING
_LEGACY_MODEL_CAPABILITIES = MappingProxyType({
    model_id: {
        "ratios": frozenset(spec.ratios),
        "resolutions": frozenset(spec.resolutions),
        "qualities": frozenset(spec.qualities),
        "pricing": spec.pricing,
        "reference_compatible_text": spec.reference_compatible_text,
    }
    for model_id, spec in MODEL_SPECS.items()
})


def _legacy_model_capabilities(model_id: str) -> dict[str, Any]:
    spec = model_spec(model_id)
    return {
        "ratios": set(spec.ratios),
        "resolutions": set(spec.resolutions),
        "qualities": set(spec.qualities),
        "pricing": spec.pricing,
        "reference_compatible_text": spec.reference_compatible_text,
    }


def _legacy_catalog() -> tuple[
    dict[str, GenerationModelOption],
    dict[str, str],
]:
    options: dict[str, GenerationModelOption] = {}
    labels = {entry["id"]: entry["label"] for entry in _LEGACY_GENERATION_MODELS}
    # Some legacy catalog rows describe the same model twice (text and
    # reference variants). Keep the first, primary text capability so the
    # model remains selectable for ordinary clipart prompts.
    model_types: dict[str, str] = {}
    for entry in _LEGACY_GENERATION_MODELS:
        model_types.setdefault(entry["id"], entry["type"])
    for model_id in sorted(_LEGACY_VISIBLE_GENERATION_MODEL_IDS):
        capabilities = _legacy_model_capabilities(model_id)
        options[model_id] = GenerationModelOption(
            model_id=model_id,
            label=labels.get(model_id, model_id),
            model_type=model_types.get(model_id, ""),
            ratios=tuple(
                value
                for value in _LEGACY_RATIO_OPTIONS_ORDER
                if value in capabilities["ratios"]
            )
            or tuple(sorted(capabilities["ratios"])),
            resolutions=tuple(
                value
                for value in _LEGACY_RESOLUTION_OPTIONS_ORDER
                if value in capabilities["resolutions"]
            )
            or tuple(sorted(capabilities["resolutions"])),
            pricing=capabilities["pricing"],
            reference_compatible_text=capabilities[
                "reference_compatible_text"
            ],
        )
    return options, dict(_LEGACY_PROCESSING_PRICING)


def generation_model_options(
    *,
    references: bool,
    include_shared_reference_text: bool = False,
    include_fal_models: bool = True,
) -> tuple[GenerationModelOption, ...]:
    options, _ = _legacy_catalog()
    result: list[GenerationModelOption] = []
    for option in options.values():
        if not include_fal_models and is_fal_generation_model(option.model_id):
            continue
        if references:
            allowed = option.model_type in {"image_to_image", "edit"}
            allowed = allowed or option.reference_compatible_text
        else:
            # Some KIE models expose a shared text/reference endpoint and are
            # catalogued as image-to-image while still supporting plain prompts.
            allowed = option.model_type == "text_to_image" or (
                include_shared_reference_text and option.reference_compatible_text
            )
        if allowed:
            mode_ratios = ratios_for_mode(option.model_id, has_references=references)
            ordered_ratios = tuple(
                value for value in _LEGACY_RATIO_OPTIONS_ORDER if value in mode_ratios
            ) or tuple(sorted(mode_ratios))
            result.append(replace(option, ratios=ordered_ratios))
    return tuple(sorted(result, key=lambda option: option.label.casefold()))


def _model_option(model_id: str) -> GenerationModelOption:
    options, _ = _legacy_catalog()
    try:
        return options[model_id]
    except KeyError as error:
        raise ClipartFlowError(
            f"Модель не поддерживается текущим каталогом: {model_id}"
        ) from error


def _price_usd(
    pricing: str | Mapping[str, str] | None,
    resolution: str,
) -> Decimal | None:
    if isinstance(pricing, Mapping):
        selected = pricing.get(resolution)
        if selected is None and pricing:
            selected = next(iter(pricing.values()))
    else:
        selected = pricing
    match = _DOLLAR_PATTERN.search(str(selected or ""))
    return Decimal(match.group(1)) if match else None


def estimate_clipart_cost(state: ProjectState) -> CostEstimate:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    generation = state.clipart.generation
    variants = generation.variants
    generation_total = Decimal("0")
    processing_total = Decimal("0")
    complete = True
    generation_request_count = len(state.clipart.prompts) * variants
    processing_request_count = 0
    provider_totals: dict[str, Decimal] = {}
    incomplete_providers: set[str] = set()

    def use_provider(provider: str) -> None:
        provider_totals.setdefault(provider, Decimal("0"))

    def add_provider_cost(provider: str, amount: Decimal) -> None:
        use_provider(provider)
        provider_totals[provider] += amount

    for entry in state.clipart.prompts:
        has_references = bool(entry.references)
        option = _model_option(
            generation.reference_model if has_references else generation.model
        )
        resolution = (
            generation.reference_resolution
            if has_references
            else generation.resolution
        )
        provider = "fal" if is_fal_generation_model(option.model_id) else "kie"
        use_provider(provider)
        if provider == "fal":
            incomplete_providers.add(provider)
            continue
        unit = _price_usd(option.pricing, resolution)
        if unit is None:
            complete = False
            incomplete_providers.add(provider)
        else:
            amount = unit * variants
            generation_total += amount
            add_provider_cost(provider, amount)

    _, processing_pricing = _legacy_catalog()
    operations = state.clipart.operations
    output_count = len(state.clipart.prompts) * variants
    processing_models: list[str] = []
    if operations.upscale_before and operations.upscale_before_provider == "kie":
        use_provider("kie")
        processing_models.append(operations.kie_upscale_model)
    elif operations.upscale_before and operations.upscale_before_provider == "fal":
        use_provider("fal")
        incomplete_providers.add("fal")
        processing_request_count += output_count
    if operations.remove_background:
        if operations.remove_background_provider == "kie":
            use_provider("kie")
            processing_models.append(operations.kie_remove_bg_model)
        elif operations.remove_background_provider == "photoroom":
            amount = Decimal("0.02") * output_count
            processing_total += amount
            add_provider_cost("photoroom", amount)
            processing_request_count += output_count
        elif operations.remove_background_provider == "fal":
            use_provider("fal")
            incomplete_providers.add("fal")
            processing_request_count += output_count
    if operations.upscale_after and operations.upscale_after_provider == "kie":
        use_provider("kie")
        processing_models.append(operations.kie_upscale_after_model)

    processing_request_count += len(processing_models) * output_count
    for model_id in processing_models:
        unit = _price_usd(processing_pricing.get(model_id), "")
        if unit is None:
            complete = False
            incomplete_providers.add("kie")
        else:
            amount = unit * output_count
            processing_total += amount
            add_provider_cost("kie", amount)

    if incomplete_providers:
        complete = False

    return CostEstimate(
        request_count=generation_request_count + processing_request_count,
        estimated_usd=generation_total + processing_total,
        complete=complete,
        generation_request_count=generation_request_count,
        processing_request_count=processing_request_count,
        generation_usd=generation_total,
        processing_usd=processing_total,
        provider_usd=MappingProxyType(dict(provider_totals)),
        incomplete_providers=tuple(sorted(incomplete_providers)),
    )


def clipart_pipeline_steps(
    operations: ImageOperationData,
) -> tuple[str, ...]:
    if not isinstance(operations, ImageOperationData):
        raise TypeError("operations must be ImageOperationData")
    steps = ["Генерация изображения"]
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
    if any(
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
    steps.append("Экспорт PNG")
    return tuple(steps)


def _processing_requested(operations: ImageOperationData) -> bool:
    return len(clipart_pipeline_steps(operations)) > 2


def _validate_generation_profile(
    option: GenerationModelOption,
    ratio: str,
    resolution: str,
) -> None:
    if option.ratios and ratio not in option.ratios:
        raise ClipartFlowError(
            f"Пропорция {ratio} недоступна для модели {option.label}"
        )
    if option.resolutions and resolution not in option.resolutions:
        raise ClipartFlowError(
            f"Разрешение {resolution} недоступно для модели {option.label}"
        )


def _worker_settings(
    state: ProjectState,
    runtime_settings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    source = runtime_settings or {}
    settings = {
        name: value
        for name in (
            "kie_api_key",
            "photoroom_api_key",
            "fal_api_key",
            "local_realesrgan_dir",
        )
        if isinstance((value := source.get(name)), str)
    }
    settings.update(RuntimeData.from_dict(state.runtime.to_dict()).to_dict())
    generation = state.clipart.generation
    operations = state.clipart.operations
    settings.update(
        {
            "run_mode": (
                "both" if _processing_requested(operations) else "generate_only"
            ),
            "text_generation_model": generation.model,
            "text_generation_ratio": generation.ratio,
            "text_generation_resolution": generation.resolution,
            "reference_generation_model": generation.reference_model,
            "reference_generation_ratio": generation.reference_ratio,
            "reference_generation_resolution": generation.reference_resolution,
            "visible_mark_cleanup_enabled": operations.visible_mark_cleanup,
            "visible_mark_cleanup_mode": operations.visible_mark_cleanup_mode,
            "invisible_watermark_cleanup_enabled": operations.invisible_watermark_cleanup,
            "upscale": operations.upscale_before,
            "upscale_provider": operations.upscale_before_provider,
            "upscale_after": operations.upscale_after,
            "upscale_after_provider": operations.upscale_after_provider,
            "upscale_factor": operations.upscale_factor,
            "kie_upscale_model": operations.kie_upscale_model,
            "kie_upscale_after_model": operations.kie_upscale_after_model,
            "fal_upscale_model": operations.fal_upscale_model,
            "fal_upscale_after_model": operations.fal_upscale_after_model,
            "fal_upscale_scale": normalize_fal_upscale_factor(
                operations.fal_upscale_model,
                operations.fal_upscale_scale,
            ),
            "fal_upscale_after_scale": operations.fal_upscale_after_scale,
            "local_realesrgan_profile": operations.local_realesrgan_profile,
            "local_realesrgan_scale": operations.local_realesrgan_scale,
            "local_realesrgan_after_scale": (
                operations.local_realesrgan_after_scale
            ),
            "remove_bg": operations.remove_background,
            "skip_remover_for_alpha": True,
            "remove_bg_provider": operations.remove_background_provider,
            "kie_remove_bg_model": operations.kie_remove_bg_model,
            "fal_remove_bg_model": operations.fal_remove_bg_model,
            "fal_birefnet_model": operations.fal_birefnet_model,
            "fal_birefnet_resolution": operations.fal_birefnet_resolution,
            "fal_birefnet_refine_foreground": operations.fal_birefnet_refine_foreground,
            "fal_rembg_crop_to_bbox": operations.fal_rembg_crop_to_bbox,
            "local_rembg_profile": operations.local_rembg_profile,
            "local_rembg_model": operations.local_rembg_model,
            "local_rembg_edge_quality": operations.local_rembg_edge_quality,
            "local_ben2_refine_foreground": (
                operations.local_ben2_refine_foreground
            ),
            "local_ben2_alpha_threshold": (
                operations.local_ben2_alpha_threshold
            ),
            "local_ben2_edge_softness": operations.local_ben2_edge_softness,
            "local_ben2_corner_radius": operations.local_ben2_corner_radius,
            "chroma_key_color": operations.chroma_key_color,
            "unsharp_enabled": operations.unsharp,
            "unsharp_amount": operations.unsharp_amount,
            "unsharp_radius": operations.unsharp_radius,
            "unsharp_threshold": operations.unsharp_threshold,
            "edge_shrink_enabled": operations.edge_shrink,
            "edge_shrink_pixels": operations.edge_shrink_pixels,
            "trim_enabled": operations.trim,
            "trim_mode": operations.trim_mode,
            "export_300_dpi": operations.export_300_dpi,
            "cleanup_remove_exif": operations.remove_exif,
            "cleanup_remove_xmp": operations.remove_xmp,
            "cleanup_remove_iptc": operations.remove_iptc,
            "cleanup_remove_comments_text": operations.remove_comments_text,
            "cleanup_remove_embedded_thumbnail": (
                operations.remove_embedded_thumbnail
            ),
            "cleanup_remove_generator_fields": (
                operations.remove_generator_fields
            ),
            "cleanup_remove_embedded_c2pa": operations.remove_embedded_c2pa,
            "cleanup_preserve_icc": operations.preserve_icc,
            "cleanup_preserve_dpi": operations.preserve_dpi,
        }
    )
    return settings


def _validate_prompt_references(prompts: Sequence[PromptEntry]) -> None:
    import main

    for entry in prompts:
        for reference in entry.references:
            normalized = reference.strip()
            if normalized.lower().startswith(("https://", "http://")):
                try:
                    main.validate_https_url(normalized, "Reference URL")
                except (RuntimeError, ValueError) as error:
                    raise ClipartFlowError(
                        "URL референса должен быть корректным HTTPS-адресом"
                    ) from error
                continue
            path = Path(normalized).expanduser()
            if not path.is_file():
                name = path.name or "референс"
                raise ClipartFlowError(f"Файл референса не найден: {name}")
            size_error = _reference_file_size_error(
                str(path),
                attachment=False,
            )
            if size_error:
                raise ClipartFlowError(size_error)
            try:
                main.validate_local_image_input(path)
            except (OSError, ValueError) as error:
                raise ClipartFlowError(
                    f"Файл референса не является допустимым изображением: {path.name}"
                ) from error


def _validate_processing_models(operations: ImageOperationData) -> None:
    _, pricing = _legacy_catalog()
    selected: list[str] = []
    if operations.upscale_before and operations.upscale_before_provider == "kie":
        selected.append(operations.kie_upscale_model)
    if operations.upscale_after and operations.upscale_after_provider == "kie":
        selected.append(operations.kie_upscale_after_model)
    if operations.remove_background and operations.remove_background_provider == "kie":
        selected.append(operations.kie_remove_bg_model)
    unknown = sorted({model for model in selected if model not in pricing})
    if unknown:
        raise ClipartFlowError(
            "Модель обработки не поддерживается: " + ", ".join(unknown)
        )


def _validate_processing_providers(operations: ImageOperationData) -> None:
    try:
        for operation_field, provider_field in (
            ("upscale_before", "upscale_before_provider"),
            ("remove_background", "remove_background_provider"),
            ("upscale_after", "upscale_after_provider"),
        ):
            if not getattr(operations, operation_field):
                continue
            provider_id = getattr(operations, provider_field)
            if not provider_supports_operation(provider_id, operation_field):
                raise ClipartFlowError(
                    f"Провайдер {provider_id} не поддерживает операцию {operation_field}"
                )
    except KeyError as error:
        raise ClipartFlowError(f"Неизвестный провайдер: {error.args[0]}") from error


def _validate_alpha_safe_upscale(operations: ImageOperationData) -> None:
    if not (operations.remove_background and operations.upscale_after):
        return
    if upscale_model_preserves_alpha(
        operations.upscale_after_provider,
        operations.kie_upscale_after_model,
    ):
        return
    if (
        operations.upscale_after_provider == "kie"
        and operations.kie_upscale_after_model == "recraft/crisp-upscale"
    ):
        raise ClipartFlowError(
            "Recraft Crisp нельзя использовать после удаления фона: "
            "модель не поддерживает прозрачный вход"
        )
    raise ClipartFlowError("Апскейл после удаления фона должен сохранять прозрачность")


def build_clipart_run_request(
    state: ProjectState,
    runtime_settings: Mapping[str, Any] | None = None,
) -> ClipartRunRequest:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    if state.mode is not ProjectMode.CLIPART:
        raise ClipartFlowError("Запуск клипарта доступен только в режиме clipart")

    work_dir = Path(state.common.work_dir).expanduser()
    if not work_dir.is_dir() or not os.access(work_dir, os.W_OK):
        raise ClipartFlowError("Рабочая папка не существует или недоступна для записи")
    if not state.clipart.prompts:
        raise ClipartFlowError("Добавьте хотя бы один промпт")

    generation = state.clipart.generation
    operations = state.clipart.operations
    _validate_prompt_references(state.clipart.prompts)
    _validate_processing_providers(operations)
    _validate_alpha_safe_upscale(operations)
    _validate_processing_models(operations)
    text_option = _model_option(generation.model)
    if text_option.model_type != "text_to_image" and not text_option.reference_compatible_text:
        raise ClipartFlowError("Основная модель должна поддерживать text-to-image")
    _validate_generation_profile(
        text_option,
        generation.ratio,
        generation.resolution,
    )

    if any(entry.references for entry in state.clipart.prompts):
        reference_option = _model_option(generation.reference_model)
        if (
            reference_option.model_type not in {"image_to_image", "edit"}
            and not reference_option.reference_compatible_text
        ):
            raise ClipartFlowError(
                "Модель с референсом не поддерживает промпты с референсами"
            )
        _validate_generation_profile(
            reference_option,
            generation.reference_ratio,
            generation.reference_resolution,
        )

    request_count = len(state.clipart.prompts) * generation.variants
    if request_count > MAX_CLIPART_REQUESTS:
        raise ClipartFlowError(
            f"Максимум {MAX_CLIPART_REQUESTS} запросов за один запуск"
        )
    if (
        state.clipart.operations.visible_mark_cleanup
        and state.clipart.operations.visible_mark_cleanup_mode
        == "confirmed_area"
    ):
        raise ClipartFlowError(
            "Ручная область видимой метки недоступна для ещё не созданных файлов"
        )

    prompts: list[dict[str, Any]] = []
    for entry in state.clipart.prompts:
        if not entry.prompt.strip():
            raise ClipartFlowError("Пустой промпт нельзя отправить на генерацию")
        has_references = bool(entry.references)
        contract_model = (
            generation.reference_model if has_references else generation.model
        )
        contract_ratio = (
            generation.reference_ratio if has_references else generation.ratio
        )
        contract_resolution = (
            generation.reference_resolution
            if has_references
            else generation.resolution
        )
        reference_sizes = tuple(
            Path(reference).expanduser().stat().st_size
            for reference in entry.references
            if not reference.lower().startswith(("https://", "http://"))
        )
        try:
            validate_generation_contract(
                contract_model,
                has_references=has_references,
                ratio=contract_ratio,
                resolution=contract_resolution,
                prompt=entry.prompt,
                reference_count=len(entry.references),
                reference_sizes=reference_sizes,
            )
        except (KeyError, OSError, ValueError) as error:
            raise ClipartFlowError(str(error)) from error
        for _ in range(generation.variants):
            prompts.append(
                {
                    "prompt": entry.prompt,
                    "references": list(entry.references),
                }
            )

    settings = _worker_settings(state, runtime_settings)
    layout = workspace_layout(
        state.output_dir_for_mode(ProjectMode.CLIPART) or work_dir
    )
    settings["output_dir"] = str(layout.output)
    settings["workspace_root"] = str(layout.root)
    mode = "mode_both" if _processing_requested(operations) else "mode1_generate_only"
    return ClipartRunRequest(
        mode=mode,
        work_dir=str(work_dir),
        settings=settings,
        generated_prompts=prompts,
    )


def missing_runtime_requirements(request: ClipartRunRequest) -> tuple[str, ...]:
    missing: list[str] = []
    seen: set[str] = set()

    def add_missing(label: str) -> None:
        if label not in seen:
            seen.add(label)
            missing.append(label)

    if request.generated_prompts:
        generation_models = {
            str(
                request.settings.get(
                    "reference_generation_model"
                    if entry.get("references")
                    else "text_generation_model",
                    "",
                )
            ).strip()
            for entry in request.generated_prompts
        }
        if any(is_fal_generation_model(model) for model in generation_models):
            if not str(request.settings.get("fal_api_key") or "").strip():
                add_missing("Fal.ai API Key")
        if any(not is_fal_generation_model(model) for model in generation_models):
            if not str(request.settings.get("kie_api_key") or "").strip():
                add_missing("KIE API Key")

    for enabled_field, provider_field in (
        ("upscale", "upscale_provider"),
        ("upscale_after", "upscale_after_provider"),
        ("remove_bg", "remove_bg_provider"),
    ):
        if not request.settings.get(enabled_field):
            continue
        provider_id = str(request.settings.get(provider_field) or "")
        api_key_name = (
            "photoroom_api_key"
            if provider_id == "photoroom"
            else "fal_api_key"
            if provider_id == "fal"
            else "kie_api_key"
        )
        if provider_requires_api_key(provider_id) and not str(request.settings.get(api_key_name) or "").strip():
            add_missing(
                "KIE API Key"
                if api_key_name == "kie_api_key"
                else "PhotoRoom API Key"
                if api_key_name == "photoroom_api_key"
                else "Fal.ai API Key"
            )
    local_upscale = (
        request.settings.get("upscale")
        and request.settings.get("upscale_provider") == "local_realesrgan"
    ) or (
        request.settings.get("upscale_after")
        and request.settings.get("upscale_after_provider") == "local_realesrgan"
    )
    if local_upscale:
        import main

        _, local_error = main.validate_local_realesrgan_exe(
            request.settings.get("local_realesrgan_dir")
        )
        if local_error:
            missing.append(local_error)
    return tuple(missing)


def apply_prompt_text_edit(
    entries: Sequence[PromptEntry], *, rows: Sequence[int], action: str,
    find_text: str, new_text: str,
) -> tuple[list[PromptEntry], int]:
    """Apply one text-only batch edit without changing references or order."""
    if action not in {"replace", "prepend", "append"}:
        raise ValueError("Unknown prompt text edit action")
    selected = {row for row in rows if 0 <= row < len(entries)}
    find_text, new_text = find_text.strip(), new_text.strip()
    result = [PromptEntry(entry.prompt, list(entry.references)) for entry in entries]
    matches = 0
    for row in selected:
        if action in {"prepend", "append"} and not new_text:
            continue
        prompt = result[row].prompt
        editable_prompt, marker, chroma_suffix = prompt.rpartition(
            _CHROMA_PROMPT_SUFFIX_MARKER
        )
        if not marker:
            editable_prompt, chroma_suffix = prompt, ""
        if action == "replace":
            if not find_text or find_text not in editable_prompt:
                continue
            editable_prompt = editable_prompt.replace(find_text, new_text)
        elif action == "prepend":
            editable_prompt = "\n".join(
                part for part in (new_text, editable_prompt) if part
            )
        else:
            editable_prompt = "\n".join(
                part for part in (editable_prompt, new_text) if part
            )
        updated_prompt = (
            editable_prompt + marker + chroma_suffix
            if marker
            else editable_prompt
        )
        if updated_prompt == prompt:
            continue
        result[row].prompt = updated_prompt
        matches += 1
    return result, matches


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


def export_prompt_csv(
    entries: Sequence[PromptEntry],
    path: str | os.PathLike[str],
) -> None:
    """Write the prompt review table in the same format accepted by CSV import."""

    destination = Path(path)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("Prompt", "References"))
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "Prompt": entry.prompt,
                    "References": "|".join(entry.references),
                }
            )


class _ScrollableStepPage(QScrollArea):
    def __init__(
        self,
        title: str,
        description: str,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setSizeAdjustPolicy(
            QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        )
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        self.card = FormCard(title, description, tokens=tokens)
        self.setWidget(self.card)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

    def add_widget(self, widget: QWidget) -> None:
        self.card.add_widget(widget)

    def refresh_from_state(self) -> None:
        return


def _supported_local_reference(path: str) -> bool:
    source = Path(path)
    return source.is_file() and source.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
    }


def _reference_file_size_error(
    reference: str,
    *,
    attachment: bool = True,
) -> str:
    path = Path(reference).expanduser()
    try:
        size = path.stat().st_size
    except OSError:
        return ""
    if size <= MAX_REFERENCE_FILE_BYTES:
        return ""
    size_mb = f"{size / (1024 * 1024):.1f}".replace(".", ",")
    name = path.name or "файл"
    if not attachment:
        return (
            f"Референс «{name}» превышает 10 МБ (размер: {size_mb} МБ). "
            "Уменьшите файл и повторите запуск."
        )
    return (
        f"Референс «{name}» не добавлен: {size_mb} МБ. "
        "Максимальный размер — 10 МБ. Выберите файл меньшего размера."
    )


def _reference_icon(path: str) -> QIcon:
    if _supported_local_reference(path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return QIcon(pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio))
    placeholder = QPixmap(120, 120)
    placeholder.fill()
    return QIcon(placeholder)


def _reference_label(path: str) -> str:
    name = Path(path).name or path
    if _supported_local_reference(path):
        return name
    return f"{name} (нет файла)"


def _reference_summary(paths: Sequence[str]) -> str:
    if not paths:
        return "Нет референсов"
    missing = sum(1 for path in paths if not _supported_local_reference(path))
    names = ", ".join(_reference_label(path) for path in paths[:3])
    if len(paths) > 3:
        names = f"{names}, …"
    if missing:
        return f"{len(paths)} референсов, {missing} недоступно: {names}"
    return f"{len(paths)} референсов: {names}"


def _review_action_icon(kind: str) -> QIcon:
    """Draw stable cross-platform review icons without relying on emoji fonts."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outline = QColor("#9fb3c8")
    accent = QColor("#2dd4bf")
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(outline, 2.0))

    is_reference = kind.startswith("reference_")
    operation = kind.split("_", 1)[1]
    if is_reference:
        painter.drawRoundedRect(QRectF(3.5, 5.5, 24, 19), 3, 3)
        painter.drawEllipse(QRectF(20, 8, 4, 4))
        painter.drawLine(6, 21, 12, 15)
        painter.drawLine(12, 15, 16, 19)
        painter.drawLine(16, 19, 20, 15)
        painter.drawLine(20, 15, 25, 21)
    elif operation in {"duplicate", "delete_all"}:
        painter.drawRoundedRect(QRectF(4.5, 7.5, 16, 19), 2.5, 2.5)
        painter.drawRoundedRect(QRectF(10.5, 3.5, 16, 19), 2.5, 2.5)
        painter.drawLine(14, 10, 23, 10)
        painter.drawLine(14, 14, 22, 14)
    else:
        painter.drawRoundedRect(QRectF(5.5, 3.5, 20, 24), 3, 3)
        painter.drawLine(10, 10, 21, 10)
        painter.drawLine(10, 15, 20, 15)
        painter.drawLine(10, 20, 17, 20)

    if operation in {"add", "delete", "delete_all", "replace"}:
        painter.setPen(QPen(accent, 2.4))
        painter.setBrush(QColor("#1f2937"))
        painter.drawEllipse(QRectF(18, 18, 12, 12))
        if operation == "add":
            painter.drawLine(21, 24, 27, 24)
            painter.drawLine(24, 21, 24, 27)
        elif operation in {"delete", "delete_all"}:
            painter.drawLine(21, 24, 27, 24)
        else:
            painter.drawArc(QRectF(20, 20, 8, 8), 30 * 16, 285 * 16)
            painter.drawLine(26, 20, 29, 20)
            painter.drawLine(29, 20, 29, 23)

    painter.end()
    return QIcon(pixmap)


def _compact_review_action_button(kind: str, label: str) -> V3Button:
    button = V3Button("", ButtonVariant.SECONDARY)
    button.setIcon(_review_action_icon(kind))
    button.setIconSize(QSize(26, 26))
    button.setFixedSize(50, 40)
    button.setToolTip(label)
    button.setAccessibleName(label)
    return button


def _confirm_delete_all_prompts(parent: QWidget, count: int) -> bool:
    if count <= 0:
        return False
    answer = QMessageBox.question(
        parent,
        "Удалить все промпты?",
        (
            f"Из текущего проекта будут удалены все промпты ({count}) и их "
            "привязки к референсам. Файлы референсов на диске останутся."
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


class _PromptReviewTable(QTableWidget):
    """Keep the prompt/reference columns at the product-defined 2:1 ratio."""

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        width = max(self.viewport().width(), 2)
        prompt_width = round(width * 2 / 3)
        self.setColumnWidth(0, prompt_width)
        self.setColumnWidth(1, width - prompt_width)


class _CsvDropZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("v3Status", True)
        self.setMinimumHeight(150)

    @staticmethod
    def _csv_paths(event: Any) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [
            url.toLocalFile()
            for url in mime.urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.casefold() == ".csv"
        ]

    def dragEnterEvent(self, event: Any) -> None:
        if self._csv_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:
        paths = self._csv_paths(event)
        if not paths:
            event.ignore()
            return
        self.file_dropped.emit(paths[0])
        event.acceptProposedAction()


def _capability_summary(option: GenerationModelOption) -> str:
    ratios = ", ".join(option.ratios[:4]) if option.ratios else "любой"
    if option.resolutions:
        resolutions = ", ".join(option.resolutions[:4])
    else:
        resolutions = "задаётся моделью"
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


class PromptReferenceEditorDialog(QDialog):
    def __init__(
        self,
        entry: PromptEntry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Редактор промпта")
        self.setModal(True)
        self._prompt_edit = QPlainTextEdit(entry.prompt)
        self._prompt_edit.setMinimumHeight(120)
        self._references = QListWidget()
        self._references.setIconSize(QSize(120, 120))
        self._references.setMinimumHeight(190)
        self._references.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._load_references(entry.references)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Промпт"))
        layout.addWidget(self._prompt_edit)
        layout.addWidget(QLabel("Референсы"))
        layout.addWidget(self._references, 1)
        self.reference_status_label = QLabel("")
        self.reference_status_label.setWordWrap(True)
        self.reference_status_label.setProperty("v3Status", True)
        self.reference_status_label.setProperty("state", "error")
        self.reference_status_label.hide()
        layout.addWidget(self.reference_status_label)

        buttons = QHBoxLayout()
        self.add_files_button = V3Button("Добавить файлы", ButtonVariant.SECONDARY)
        self.remove_button = V3Button("Удалить выбранные", ButtonVariant.SECONDARY)
        buttons.addWidget(self.add_files_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.add_files_button.clicked.connect(self._choose_files)
        self.remove_button.clicked.connect(self._remove_selected)

    def _load_references(self, references: Sequence[str]) -> None:
        self._references.clear()
        for reference in references:
            item = QListWidgetItem(_reference_icon(reference), _reference_label(reference))
            item.setData(Qt.ItemDataRole.UserRole, reference)
            item.setToolTip(reference)
            self._references.addItem(item)

    def _choose_files(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
        )
        self.add_references(selected)

    def add_references(self, references: Sequence[str]) -> None:
        existing = [self._references.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self._references.count())]
        errors: list[str] = []
        for reference in references:
            normalized = str(Path(reference))
            if (
                not normalized
                or normalized in existing
                or not _supported_local_reference(normalized)
            ):
                continue
            size_error = _reference_file_size_error(normalized)
            if size_error:
                errors.append(size_error)
                continue
            if len(existing) >= MAX_REFERENCES_PER_PROMPT:
                break
            item = QListWidgetItem(_reference_icon(normalized), _reference_label(normalized))
            item.setData(Qt.ItemDataRole.UserRole, normalized)
            item.setToolTip(normalized)
            self._references.addItem(item)
            existing.append(normalized)
        if errors:
            self.reference_status_label.setText(errors[0])
            self.reference_status_label.show()
        else:
            self.reference_status_label.clear()
            self.reference_status_label.hide()

    def _remove_selected(self) -> None:
        for item in list(self._references.selectedItems()):
            row = self._references.row(item)
            self._references.takeItem(row)

    def prompt_text(self) -> str:
        return self._prompt_edit.toPlainText().strip()[:MAX_TEXT_LENGTH]

    def references(self) -> list[str]:
        references: list[str] = []
        for index in range(self._references.count()):
            reference = str(
                self._references.item(index).data(Qt.ItemDataRole.UserRole) or ""
            ).strip()
            if reference:
                references.append(reference)
        return references[:MAX_REFERENCES_PER_PROMPT]

    def prompt_entry(self) -> PromptEntry:
        return PromptEntry(self.prompt_text(), self.references())


class ReferenceScopeDialog(QDialog):
    def __init__(
        self,
        *,
        has_selection: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Область действия")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("К каким промптам применить изменения?"))

        self.scope_group = QButtonGroup(self)
        self.current_radio = QRadioButton("Текущая строка")
        self.selected_radio = QRadioButton("Выбранные строки")
        self.all_radio = QRadioButton("Все промпты")
        for index, button in enumerate(
            (self.current_radio, self.selected_radio, self.all_radio)
        ):
            self.scope_group.addButton(button, index)
            layout.addWidget(button)

        self.current_radio.setChecked(not has_selection)
        self.selected_radio.setChecked(has_selection)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def scope(self) -> str:
        if self.all_radio.isChecked():
            return "all"
        if self.selected_radio.isChecked():
            return "selected"
        return "current"


class PromptBatchEditDialog(QDialog):
    """Preview and configure one reversible edit of prompt text."""

    def __init__(
        self,
        entries: Sequence[PromptEntry],
        *,
        selected_rows: Sequence[int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Найти и заменить")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._entries = [
            PromptEntry(entry.prompt, list(entry.references)) for entry in entries
        ]
        self._selected_rows = tuple(
            sorted({row for row in selected_rows if 0 <= row < len(entries)})
        )
        self._preview_entries = list(self._entries)
        self._affected_count = 0

        layout = QVBoxLayout(self)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Изменить:"))
        self.scope_group = QButtonGroup(self)
        self.selected_radio = QRadioButton(
            f"Выбранные ({len(self._selected_rows)})"
        )
        self.all_radio = QRadioButton(f"Все ({len(self._entries)})")
        self.scope_group.addButton(self.selected_radio)
        self.scope_group.addButton(self.all_radio)
        self.selected_radio.setEnabled(bool(self._selected_rows))
        self.selected_radio.setChecked(bool(self._selected_rows))
        self.all_radio.setChecked(not self._selected_rows)
        scope_row.addWidget(self.selected_radio)
        scope_row.addWidget(self.all_radio)
        scope_row.addStretch()
        layout.addLayout(scope_row)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Действие:"))
        self.action_group = QButtonGroup(self)
        self.replace_radio = QRadioButton("Заменить")
        self.prepend_radio = QRadioButton("В начало")
        self.append_radio = QRadioButton("В конец")
        for button in (
            self.replace_radio,
            self.prepend_radio,
            self.append_radio,
        ):
            self.action_group.addButton(button)
            action_row.addWidget(button)
        self.replace_radio.setChecked(True)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.form = QFormLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Текст, который нужно найти")
        self.find_edit.setAccessibleName("Найти текст")
        self.new_text_edit = QPlainTextEdit()
        self.new_text_edit.setPlaceholderText("Новый текст")
        self.new_text_edit.setAccessibleName("Новый текст")
        self.new_text_edit.setMaximumHeight(110)
        self.form.addRow("Найти", self.find_edit)
        self.form.addRow("Текст", self.new_text_edit)
        layout.addLayout(self.form)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("v3Selection", True)
        layout.addWidget(self.summary_label)
        self.preview_list = QListWidget()
        self.preview_list.setAccessibleName("Предварительный результат")
        self.preview_list.setMinimumHeight(120)
        layout.addWidget(self.preview_list)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = V3Button("Отмена", ButtonVariant.GHOST)
        self.apply_button = V3Button("Применить", ButtonVariant.PRIMARY)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.apply_button)
        layout.addLayout(button_row)

        for button in (
            self.selected_radio,
            self.all_radio,
            self.replace_radio,
            self.prepend_radio,
            self.append_radio,
        ):
            button.toggled.connect(self._refresh_preview)
        self.find_edit.textChanged.connect(self._refresh_preview)
        self.new_text_edit.textChanged.connect(self._refresh_preview)
        self._refresh_preview()

    def action(self) -> str:
        if self.prepend_radio.isChecked():
            return "prepend"
        if self.append_radio.isChecked():
            return "append"
        return "replace"

    def rows(self) -> tuple[int, ...]:
        if self.selected_radio.isChecked() and self._selected_rows:
            return self._selected_rows
        return tuple(range(len(self._entries)))

    def affected_count(self) -> int:
        return self._affected_count

    def edited_entries(self) -> tuple[list[PromptEntry], int]:
        return (
            [
                PromptEntry(entry.prompt, list(entry.references))
                for entry in self._preview_entries
            ],
            self._affected_count,
        )

    def _refresh_preview(self, *_: Any) -> None:
        replace_action = self.action() == "replace"
        self.find_edit.setVisible(replace_action)
        find_label = self.form.labelForField(self.find_edit)
        if find_label is not None:
            find_label.setVisible(replace_action)

        rows = self.rows()
        self._preview_entries, self._affected_count = apply_prompt_text_edit(
            self._entries,
            rows=rows,
            action=self.action(),
            find_text=self.find_edit.text(),
            new_text=self.new_text_edit.toPlainText(),
        )
        too_long = any(
            len(self._preview_entries[row].prompt) > MAX_TEXT_LENGTH for row in rows
        )
        unchanged_rows = tuple(
            row
            for row in rows
            if self._entries[row].prompt == self._preview_entries[row].prompt
        )
        unchanged_row_labels = ", ".join(
            str(row + 1) for row in unchanged_rows[:10]
        )
        if len(unchanged_rows) > 10:
            unchanged_row_labels += ", …"
        self.preview_list.clear()
        for row in rows:
            before = self._entries[row].prompt
            after = self._preview_entries[row].prompt
            if before == after:
                continue
            before_preview = before.replace("\n", " ")[:100]
            after_preview = after.replace("\n", " ")[:100]
            self.preview_list.addItem(
                f"{row + 1}. {before_preview}  →  {after_preview}"
            )
            if self.preview_list.count() >= 3:
                break

        if too_long:
            summary = f"Текст превышает максимум {MAX_TEXT_LENGTH} символов"
        elif replace_action and not self.find_edit.text().strip():
            summary = "Введите текст, который нужно найти"
        elif not self.new_text_edit.toPlainText().strip() and not replace_action:
            summary = "Введите текст для добавления"
        elif not self._affected_count:
            summary = (
                "Совпадений не найдено"
                + (
                    f" · строки: {unchanged_row_labels}"
                    if unchanged_row_labels
                    else ""
                )
            )
        else:
            unchanged = len(rows) - self._affected_count
            summary = (
                f"Будет изменено: {self._affected_count} из {len(rows)}"
                + (
                    f" · без совпадений: {unchanged}"
                    f" · строки: {unchanged_row_labels}"
                    if replace_action and unchanged
                    else ""
                )
            )
        self.summary_label.setText(summary)
        has_required_text = (
            bool(self.find_edit.text().strip())
            if replace_action
            else bool(self.new_text_edit.toPlainText().strip())
        )
        self.apply_button.setEnabled(
            self._affected_count > 0 and has_required_text and not too_long
        )


class ClipartProjectPage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Рабочая папка",
            "Выберите папку для записи результатов.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        form = QFormLayout()
        work_widget = QWidget()
        work_layout = QHBoxLayout(work_widget)
        work_layout.setContentsMargins(0, 0, 0, 0)
        self.work_dir_edit = QLineEdit(state.common.work_dir)
        self.work_dir_edit.setAccessibleName("Рабочая папка")
        self.browse_button = V3Button("Выбрать", ButtonVariant.SECONDARY)
        self.browse_button.clicked.connect(self._browse)
        work_layout.addWidget(self.work_dir_edit, 1)
        work_layout.addWidget(self.browse_button)
        form.addRow("Рабочая папка", work_widget)
        container = QWidget()
        container.setLayout(form)
        self.add_widget(container)

        self.path_status = QLabel()
        self.path_status.setWordWrap(True)
        self.path_status.setProperty("v3Small", True)
        self.add_widget(self.path_status)

        self.work_dir_edit.textChanged.connect(self._sync)
        self._refresh_status()

    def _browse(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            "Выберите рабочую папку",
            self.work_dir_edit.text() or os.getcwd(),
        )
        if selected:
            self.work_dir_edit.setText(selected)

    def _sync(self) -> None:
        self.state.common.work_dir = self.work_dir_edit.text().strip()
        self.state.set_output_dir_for_mode(
            str(Path(self.state.common.work_dir) / "output")
            if self.state.common.work_dir
            else "",
            ProjectMode.CLIPART,
        )
        self._refresh_status()
        self.changed()

    def _refresh_status(self) -> None:
        path = Path(self.work_dir_edit.text().strip()).expanduser()
        valid = path.is_dir() and os.access(path, os.W_OK)
        text = (
            "✓ Папка доступна для записи."
            if valid
            else "✕ Выберите существующую папку, доступную для записи."
        )
        self.path_status.setText(text)
        self.path_status.setAccessibleName(text)

    def validation_issues(self) -> tuple[str, ...]:
        path = Path(self.work_dir_edit.text().strip()).expanduser()
        if not path.is_dir() or not os.access(path, os.W_OK):
            return ("work_dir_unavailable",)
        return ()


class ClipartPromptInputPage(_ScrollableStepPage):
    generator_mode = ProjectMode.CLIPART
    supports_prompt_chroma = True

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        advance: Callable[[], Any] | None = None,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Содержание",
            "Создайте серию, добавьте готовый промпт или импортируйте CSV.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self.advance = advance
        self.tokens = tokens
        self.progress_label = QLabel("Шаг 1 из 2 · Добавление промптов")
        self.progress_label.setProperty("v3Selection", True)
        self.progress_label.setAccessibleName(self.progress_label.text())
        self.add_widget(self.progress_label)
        source_choices = (
            "Сгенерировать серию",
            "Вставить готовый промпт",
            "Импортировать CSV",
        )
        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(tokens.space_3)
        self.source_button_group = QButtonGroup(self)
        self.source_button_group.setExclusive(True)
        self.source_buttons: list[QPushButton] = []
        for index, title in enumerate(source_choices):
            button = QPushButton(title)
            button.setProperty("v3SourceChoice", True)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(title)
            button.clicked.connect(
                lambda checked=False, target=index: self._select_source(target)
            )
            self.source_button_group.addButton(button, index)
            self.source_buttons.append(button)
            source_layout.addWidget(button, 1)
        self.add_widget(source_row)

        self.source_combo = QComboBox()
        self.source_combo.setAccessibleName("Источник промптов")
        self.source_combo.addItem("Сгенерировать серию", "generator")
        self.source_combo.addItem("Вставить готовые промпты", "paste")
        self.source_combo.addItem("Импортировать CSV", "csv")
        self.source_combo.hide()

        self.source_stack = QStackedWidget()
        self.generator_widget = self._build_generator()
        self.paste_widget = self._build_paste()
        self.csv_widget = self._build_csv()
        for widget in (
            self.generator_widget,
            self.paste_widget,
            self.csv_widget,
        ):
            self.source_stack.addWidget(widget)
        if self.supports_prompt_chroma:
            source_area = QWidget()
            source_layout = QHBoxLayout(source_area)
            source_layout.setContentsMargins(0, 0, 0, 0)
            source_layout.setSpacing(tokens.space_3)
            source_layout.addWidget(self.source_stack, 2)
            self.chroma_advisor = self._build_chroma_advisor()
            source_layout.addWidget(self.chroma_advisor, 1)
            self.add_widget(source_area)
        else:
            self.add_widget(self.source_stack)
        self.source_combo.currentIndexChanged.connect(self._select_source)
        self.source_combo.setCurrentIndex(1)
        self._select_source(1)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        if hasattr(self, "prompt_count_label"):
            self.prompt_count_label.setText(
                f"В проекте: {len(self.state.clipart.prompts)} промптов"
            )

    def _select_source(self, index: int) -> None:
        if not 0 <= index < self.source_stack.count():
            return
        self.source_stack.setCurrentIndex(index)
        if self.source_combo.currentIndex() != index:
            self.source_combo.blockSignals(True)
            self.source_combo.setCurrentIndex(index)
            self.source_combo.blockSignals(False)
        for button_index, button in enumerate(self.source_buttons):
            button.setChecked(button_index == index)
        if hasattr(self, "chroma_advisor"):
            self.chroma_advisor.setVisible(index in (0, 1))

    def _build_chroma_advisor(self) -> AdvancedSection:
        advisor = AdvancedSection("Помощник чистого фона", tokens=self.tokens)
        advisor.setMinimumWidth(214)
        advisor.setMaximumWidth(280)
        advisor.toggle_button.setText("Помощник\nчистого фона")
        advisor.toggle_button.setStyleSheet("font-size: 12px;")
        advisor.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        for text in (
            "Синий подходит для растений и большинства обычных клип-артов.",
            "Синий или фиолетовый предмет? Выберите красный фон.",
            "Синий и красный не подходят? Тогда выберите зелёный фон.",
            (
                "Материалы и детали выбираются слева и автоматически "
                "добавляют нужную фразу."
            ),
        ):
            label = QLabel(text)
            label.setWordWrap(True)
            label.setProperty("v3Description", True)
            advisor.add_widget(label)
        advisor.set_expanded(True)
        return advisor

    def _build_chroma_color_buttons(
        self,
        combo: QComboBox,
    ) -> tuple[QWidget, dict[str, QPushButton]]:
        colors = {
            "blue": QColor("#0000FF"),
            "red": QColor("#FF0000"),
            "green": QColor("#00FF00"),
        }
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.tokens.space_2)
        group = QButtonGroup(widget)
        group.setExclusive(True)
        buttons: dict[str, QPushButton] = {}
        for label, value in CHROMA_KEY_COLOR_OPTIONS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("v3ChromaMaterial", True)
            swatch = QPixmap(14, 14)
            swatch.fill(colors[value])
            button.setIcon(QIcon(swatch))
            button.setChecked(combo.currentData() == value)
            button.clicked.connect(
                lambda checked=False, selected=value: combo.setCurrentIndex(
                    combo.findData(selected)
                )
            )
            group.addButton(button)
            buttons[value] = button
            layout.addWidget(button)

        def sync_buttons() -> None:
            current = combo.currentData()
            if current in buttons:
                buttons[current].setChecked(True)

        combo.currentIndexChanged.connect(sync_buttons)
        combo.hide()
        return widget, buttons

    def _build_generator(self) -> QWidget:
        draft = self.state.clipart.prompt_generator
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Новая серия промптов")
        title.setProperty("v3Title", True)
        layout.addWidget(title)

        variable_group = QGroupBox("Меняется в каждом промпте")
        variable_layout = QGridLayout(variable_group)
        self.theme_edit = QLineEdit(draft.theme)
        self.subjects_edit = QPlainTextEdit("\n".join(draft.subjects))
        self.variations_edit = QPlainTextEdit("\n".join(draft.variations))
        for edit in (self.subjects_edit, self.variations_edit):
            edit.setMinimumHeight(115)
            edit.setMaximumHeight(115)
        subjects_label = QLabel("Объекты — каждый с новой строки")
        variations_label = QLabel("Варианты или позы — каждый с новой строки")
        variable_layout.addWidget(subjects_label, 0, 0)
        variable_layout.addWidget(variations_label, 0, 1)
        variable_layout.addWidget(self.subjects_edit, 1, 0)
        variable_layout.addWidget(self.variations_edit, 1, 1)
        self.combinations_label = QLabel()
        self.combinations_label.setProperty("v3Selection", True)
        variable_layout.addWidget(self.combinations_label, 2, 0, 1, 2)
        variable_layout.setColumnStretch(0, 1)
        variable_layout.setColumnStretch(1, 1)
        layout.addWidget(variable_group)

        fixed_group = QGroupBox("Остаётся одинаковым во всей серии")
        form = QFormLayout(fixed_group)
        self.style_edit = QLineEdit(draft.style)
        self.palette_edit = QLineEdit(draft.palette)
        self.composition_edit = QLineEdit(draft.composition)
        self.background_edit = QLineEdit(draft.background)
        self.consistency_edit = QLineEdit(draft.consistency)
        for edit in (
            self.theme_edit,
            self.style_edit,
            self.palette_edit,
            self.composition_edit,
            self.background_edit,
            self.consistency_edit,
        ):
            edit.setMaxLength(MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        self.restrictions_edit = QPlainTextEdit("\n".join(draft.restrictions))
        self.restrictions_edit.setMaximumHeight(72)
        self.restrictions_edit.setPlaceholderText(
            "Например: текст, рамки, водяные знаки"
        )
        fields = (
            ("Что нужно создать", self.theme_edit),
            ("Стиль", self.style_edit),
            ("Палитра", self.palette_edit),
            ("Композиция", self.composition_edit),
            ("Фон", self.background_edit),
            ("Единообразие серии", self.consistency_edit),
            ("Исключить", self.restrictions_edit),
        )
        for label, control in fields:
            control.setAccessibleName(label)
            form.addRow(label, control)
        layout.addWidget(fixed_group)

        key_group = QGroupBox("Подготовить изображение для лёгкого удаления фона")
        key_form = QFormLayout(key_group)
        self.chroma_key_enabled = QCheckBox(
            "Генерировать на однотонном chroma-key фоне"
        )
        self.chroma_key_enabled.setChecked(draft.chroma_key_enabled)
        self.chroma_key_enabled.setAccessibleName(
            "Генерировать на chroma-key фоне"
        )
        self.chroma_key_color = QComboBox()
        for label, value in CHROMA_KEY_COLOR_OPTIONS:
            self.chroma_key_color.addItem(label, value)
        index = self.chroma_key_color.findData(draft.chroma_key_color)
        self.chroma_key_color.setCurrentIndex(index if index >= 0 else 0)
        self.chroma_key_color.setAccessibleName("Цвет chroma-key фона")
        color_buttons_widget, self.chroma_key_color_buttons = (
            self._build_chroma_color_buttons(self.chroma_key_color)
        )
        materials_widget = QWidget()
        materials_layout = QGridLayout(materials_widget)
        materials_layout.setContentsMargins(0, 0, 0, 0)
        materials_layout.setSpacing(self.tokens.space_2)
        self.chroma_material_buttons: list[QPushButton] = []
        for index, (label, value) in enumerate(CHROMA_KEY_MATERIAL_OPTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("chromaMaterial", value)
            button.setChecked(value in draft.chroma_key_materials)
            self.chroma_material_buttons.append(button)
            materials_layout.addWidget(button, index // 2, index % 2)
        configure_chroma_material_buttons(self.chroma_material_buttons)
        key_form.addRow(self.chroma_key_enabled)
        key_form.addRow("Цвет фона для удаления", color_buttons_widget)
        key_form.addRow("Материалы и детали", materials_widget)
        layout.addWidget(key_group)

        self.preview_label = QLabel("Пример итогового промпта появится здесь.")
        self.preview_label.setWordWrap(True)
        self.preview_label.setProperty("v3Status", True)
        self.preview_label.setAccessibleName("Предпросмотр вариантов")
        layout.addWidget(self.preview_label)

        self.create_series_button = V3Button("Создать серию промптов")
        self.create_series_button.clicked.connect(self._create_series)
        layout.addWidget(self.create_series_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._generated_variants: list[PromptEntry] = []
        for edit in (
            self.theme_edit,
            self.style_edit,
            self.palette_edit,
            self.composition_edit,
            self.background_edit,
            self.consistency_edit,
        ):
            edit.textChanged.connect(self._generator_changed)
        self.subjects_edit.textChanged.connect(self._generator_changed)
        self.variations_edit.textChanged.connect(self._generator_changed)
        self.restrictions_edit.textChanged.connect(self._generator_changed)
        self.chroma_key_enabled.toggled.connect(self._generator_changed)
        self.chroma_key_color.currentIndexChanged.connect(self._generator_changed)
        for button in self.chroma_material_buttons:
            button.toggled.connect(self._generator_changed)
        self._preview()
        return widget

    def _generator_data(self) -> PromptGeneratorData:
        return PromptGeneratorData(
            theme=self.theme_edit.text(),
            subjects=self.subjects_edit.toPlainText().splitlines(),
            variations=self.variations_edit.toPlainText().splitlines(),
            style=self.style_edit.text(),
            palette=self.palette_edit.text(),
            composition=self.composition_edit.text(),
            background=self.background_edit.text(),
            consistency=self.consistency_edit.text(),
            restrictions=self.restrictions_edit.toPlainText().splitlines(),
            chroma_key_enabled=self.chroma_key_enabled.isChecked(),
            chroma_key_color=self.chroma_key_color.currentData(),
            chroma_key_materials=[
                str(button.property("chromaMaterial"))
                for button in self.chroma_material_buttons
                if button.isChecked()
            ],
        )

    def _generator_changed(self, *_: Any) -> None:
        data = self._generator_data()
        self.state.clipart.prompt_generator = data
        if data.chroma_key_enabled:
            self.state.clipart.operations.remove_background_provider = "local_chroma_key"
            self.state.clipart.operations.chroma_key_color = data.chroma_key_color
        elif self.state.clipart.operations.remove_background_provider == "local_chroma_key":
            # Turning off chroma-key generation must not leave the pipeline
            # silently removing an ordinary generated background by color.
            self.state.clipart.operations.remove_background_provider = "kie"
        self._preview()
        self.changed()

    def _preview(self, *_: Any) -> None:
        try:
            entries = generate_prompt_series(
                self.generator_mode,
                self._generator_data(),
            )
        except PromptGeneratorError as error:
            self._generated_variants = []
            self.preview_label.setText("Заполните хотя бы одно поле конструктора.")
            self.create_series_button.setEnabled(False)
            subjects = len([line for line in self.subjects_edit.toPlainText().splitlines() if line.strip()])
            variations = len([line for line in self.variations_edit.toPlainText().splitlines() if line.strip()]) or 1
            self.combinations_label.setText(
                f"{subjects} объектов × {variations} вариантов"
            )
            return
        self.card.set_state("default")
        self._generated_variants = entries
        example_lines = [f"{index}. {entry.prompt}" for index, entry in enumerate(entries[:2], 1)]
        self.preview_label.setText("Пример итогового промпта:\n" + "\n\n".join(example_lines))
        self.combinations_label.setText(f"Будет создано {len(entries)} промптов")
        self.create_series_button.setEnabled(True)

    def _create_series(self) -> None:
        self._preview()
        if self._generated_variants and self._store_entries(
            self._generated_variants,
            action="append",
        ):
            if self.advance is not None:
                self.advance()

    def _store_entries(
        self,
        entries: Sequence[PromptEntry],
        *,
        action: str,
        deduplicate: bool = True,
    ) -> bool:
        normalized = list(entries)
        if action == "append":
            if len(self.state.clipart.prompts) + len(normalized) > MAX_PROMPT_ENTRIES:
                self.card.set_state(
                    "error",
                    f"Максимум {MAX_PROMPT_ENTRIES} промптов. Уменьшите добавляемый список.",
                )
                return False
            normalized = list(self.state.clipart.prompts) + normalized
        replace_project_prompts(
            self.state,
            ProjectMode.CLIPART,
            normalized,
            deduplicate=deduplicate,
        )
        self.card.set_state("default")
        self.refresh_from_state()
        self.changed()
        return True

    def _generate(self) -> None:
        try:
            self._preview()
        except PromptGeneratorError as error:
            self.card.set_state("error", str(error))
            return

    def _build_paste(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.paste_edit = QPlainTextEdit()
        self.paste_edit.setPlaceholderText("Вставьте один готовый промпт. Он может занимать несколько строк.")
        self.paste_edit.setAccessibleName("Готовый промпт")
        self.paste_edit.setMinimumHeight(140)
        self.paste_edit.setMaximumHeight(180)
        layout.addWidget(self.paste_edit)
        actions = QWidget()
        actions.setMaximumHeight(self.tokens.control_height + 2)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.add_references_button = V3Button(
            "Добавить референсы",
            ButtonVariant.SECONDARY,
        )
        self.add_references_button.clicked.connect(self._choose_paste_references)
        self.paste_references_label = QLabel("Референсы не выбраны")
        self.paste_references_label.setProperty("v3Small", True)
        self.clear_references_button = V3Button("Очистить", ButtonVariant.GHOST)
        self.clear_references_button.clicked.connect(self._clear_paste_references)
        self.clear_references_button.hide()
        action_layout.addWidget(self.add_references_button)
        action_layout.addWidget(self.paste_references_label, 1)
        action_layout.addWidget(self.clear_references_button)
        action_layout.addStretch()
        layout.addWidget(actions)
        if self.supports_prompt_chroma:
            self._add_prompt_chroma_controls(layout, "paste")
        self.add_prompt_button = V3Button("Добавить промпт")
        self.add_prompt_button.clicked.connect(self._apply_paste)
        layout.addWidget(self.add_prompt_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.paste_status_label = QLabel("")
        self.paste_status_label.setWordWrap(True)
        self.paste_status_label.setProperty("v3Selection", True)
        layout.addWidget(self.paste_status_label)
        self._paste_references: list[str] = []
        layout.addStretch()
        return widget

    def _add_prompt_chroma_controls(self, layout: QVBoxLayout, prefix: str) -> None:
        group = QGroupBox("Фон для лёгкого удаления")
        form = QFormLayout(group)
        enabled = QCheckBox("Добавить Chroma Key-блок в конец промпта")
        color = QComboBox()
        for label, value in CHROMA_KEY_COLOR_OPTIONS:
            color.addItem(label, value)
        color_buttons_widget, color_buttons = self._build_chroma_color_buttons(color)
        materials = QWidget()
        material_layout = QGridLayout(materials)
        material_layout.setContentsMargins(0, 0, 0, 0)
        material_layout.setSpacing(self.tokens.space_2)
        buttons: dict[str, QPushButton] = {}
        for index, (label, value) in enumerate(CHROMA_KEY_MATERIAL_OPTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            buttons[value] = button
            material_layout.addWidget(button, index // 2, index % 2)
        configure_chroma_material_buttons(tuple(buttons.values()))
        form.addRow(enabled)
        form.addRow("Цвет фона", color_buttons_widget)
        form.addRow("Материалы и детали", materials)
        setattr(self, f"{prefix}_chroma_enabled", enabled)
        setattr(self, f"{prefix}_chroma_color", color)
        setattr(self, f"{prefix}_chroma_color_buttons", color_buttons)
        setattr(self, f"{prefix}_chroma_material_buttons", buttons)
        layout.addWidget(group)

    def _prompt_with_chroma(self, prompt: str, prefix: str) -> str:
        if not self.supports_prompt_chroma:
            return prompt
        enabled = getattr(self, f"{prefix}_chroma_enabled")
        if not enabled.isChecked():
            return prompt
        color = getattr(self, f"{prefix}_chroma_color").currentData()
        buttons = getattr(self, f"{prefix}_chroma_material_buttons")
        materials = [value for value, button in buttons.items() if button.isChecked()]
        return prompt + "\n" + chroma_key_prompt_block(color, materials=materials)

    def _choose_paste_references(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите до 5 референсов",
            self.state.common.work_dir or os.getcwd(),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
        )
        self._add_paste_references(selected)

    def _add_paste_references(self, references: Sequence[str]) -> None:
        errors: list[str] = []
        for reference in references:
            normalized = str(Path(reference))
            if normalized in self._paste_references or not _supported_local_reference(normalized):
                continue
            size_error = _reference_file_size_error(normalized)
            if size_error:
                errors.append(size_error)
                continue
            if len(self._paste_references) >= MAX_REFERENCES_PER_PROMPT:
                break
            self._paste_references.append(normalized)
        self._refresh_paste_references()
        if errors:
            self.card.set_state("error", errors[0])

    def _clear_paste_references(self) -> None:
        self._paste_references = []
        self._refresh_paste_references()

    def _refresh_paste_references(self) -> None:
        if not self._paste_references:
            self.paste_references_label.setText("Референсы не выбраны")
            self.paste_references_label.setToolTip("")
            self.clear_references_button.hide()
            return
        labels = []
        for reference in self._paste_references:
            name = Path(reference).name
            labels.append(name if len(name) <= 18 else "…" + name[-17:])
        self.paste_references_label.setText(" · ".join(labels))
        self.paste_references_label.setToolTip("\n".join(self._paste_references))
        self.clear_references_button.show()

    def _apply_paste(self) -> None:
        text = self.paste_edit.toPlainText()
        if len(text) > MAX_CSV_BYTES:
            self.card.set_state("error", "Вставленный текст превышает допустимый размер")
            return
        prompt = " ".join(text.split())
        if not prompt:
            self.card.set_state("error", "Введите промпт")
            return
        if len(prompt) > MAX_TEXT_LENGTH:
            self.card.set_state("error", "Промпт слишком длинный")
            return
        prompt = self._prompt_with_chroma(prompt, "paste")
        if self._store_entries(
            [PromptEntry(prompt=prompt, references=self._paste_references)],
            action="append",
            deduplicate=False,
        ):
            self.paste_edit.clear()
            self._clear_paste_references()
            self.paste_status_label.setText(
                "Промпт добавлен в проект. Вы сможете проверить и "
                "отредактировать его на следующем шаге."
            )

    def _build_csv(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.csv_drop_zone = _CsvDropZone()
        drop_layout = QVBoxLayout(self.csv_drop_zone)
        drop_layout.setContentsMargins(
            self.tokens.space_4,
            self.tokens.space_4,
            self.tokens.space_4,
            self.tokens.space_4,
        )
        text = QLabel("Перетащите CSV-файл сюда")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(text)
        self.csv_button = V3Button("Выбрать CSV", ButtonVariant.PRIMARY)
        self.csv_button.clicked.connect(self._choose_csv)
        drop_layout.addWidget(self.csv_button, 0, Qt.AlignmentFlag.AlignCenter)
        mapping_hint = QLabel(
            "Перед импортом можно проверить разделитель и сопоставить колонки."
        )
        mapping_hint.setProperty("v3Small", True)
        mapping_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(mapping_hint)
        self.csv_drop_zone.file_dropped.connect(self._import_csv_file)
        layout.addWidget(self.csv_drop_zone)
        layout.addStretch(1)
        return widget

    def _choose_csv(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Импортировать CSV",
            self.state.common.work_dir or os.getcwd(),
            "CSV files (*.csv)",
        )
        if not selected:
            return
        self._import_csv_file(selected)

    def _import_csv_file(self, selected: str) -> None:
        try:
            dialog = PromptCsvImportDialog(selected, self)
        except RuntimeError as error:
            self.card.set_state("error", str(error))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entries = [PromptEntry.from_value(entry) for entry in dialog.get_entries()]
        normalized_entries = [entry for entry in entries if entry is not None]
        if not normalized_entries:
            self.card.set_state("error", "Не найдено ни одной валидной строки CSV")
            return
        imported = self._store_entries(
            normalized_entries,
            action="append",
            deduplicate=False,
        )
        if imported and self.advance is not None:
            self.advance()


class ClipartPromptReviewPage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Проверка промптов",
            "Редактируйте текст и референсы, удаляйте и меняйте порядок строк.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self._updating = False
        self._batch_undo_snapshot: list[PromptEntry] | None = None
        self.progress_label = QLabel("Шаг 2 из 2 · Проверка серии")
        self.progress_label.setProperty("v3Selection", True)
        self.progress_label.setAccessibleName(self.progress_label.text())
        self.add_widget(self.progress_label)
        self.batch_edit_button = V3Button(
            "Найти и заменить",
            ButtonVariant.SECONDARY,
        )
        self.undo_batch_button = V3Button(
            "Отменить изменение",
            ButtonVariant.GHOST,
        )
        self.undo_batch_button.setEnabled(False)
        self.undo_batch_button.hide()
        search_row = QWidget()
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Найти промпт")
        self.search_edit.setAccessibleName("Поиск по промптам")
        self.search_result_label = QLabel()
        self.search_result_label.setProperty("v3Small", True)
        search_layout.addWidget(self.search_edit, 1)
        search_layout.addWidget(self.search_result_label)
        search_layout.addWidget(self.batch_edit_button)
        search_layout.addWidget(self.undo_batch_button)
        self.add_widget(search_row)
        self.table = _PromptReviewTable(0, 2)
        self.table.setHorizontalHeaderLabels(["Промпт", "Референсы"])
        self.table.setAccessibleName("Таблица промптов")
        self.table.setMinimumHeight(360)
        self.table.setMaximumHeight(520)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive,
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.cellDoubleClicked.connect(self._edit_row)
        self.table.itemChanged.connect(self._table_changed)
        self.table.model().rowsMoved.connect(self._rows_moved)
        self.search_edit.textChanged.connect(self._apply_search)
        self.add_widget(self.table)

        prompt_actions = QWidget()
        action_layout = QHBoxLayout(prompt_actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(tokens.space_2)
        prompt_actions_label = QLabel("Промпты:")
        prompt_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(prompt_actions_label)
        self.add_button = _compact_review_action_button(
            "prompt_add",
            "Добавить промпт",
        )
        self.duplicate_button = _compact_review_action_button(
            "prompt_duplicate",
            "Дублировать выбранные промпты",
        )
        self.delete_button = _compact_review_action_button(
            "prompt_delete",
            "Удалить выбранные промпты",
        )
        self.delete_all_button = _compact_review_action_button(
            "prompt_delete_all",
            "Удалить все промпты",
        )
        for button in (
            self.add_button,
            self.duplicate_button,
            self.delete_button,
            self.delete_all_button,
        ):
            action_layout.addWidget(button)

        action_layout.addSpacing(tokens.space_4)
        references_actions_label = QLabel("Референсы:")
        references_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(references_actions_label)
        self.add_refs_button = _compact_review_action_button(
            "reference_add",
            "Добавить референсы",
        )
        self.replace_refs_button = _compact_review_action_button(
            "reference_replace",
            "Заменить референсы",
        )
        self.delete_refs_button = _compact_review_action_button(
            "reference_delete",
            "Удалить референсы",
        )
        self.up_button = V3Button("Выше", ButtonVariant.GHOST)
        self.down_button = V3Button("Ниже", ButtonVariant.GHOST)
        self.up_button.hide()
        self.down_button.hide()
        for button in (
            self.add_refs_button,
            self.replace_refs_button,
            self.delete_refs_button,
        ):
            action_layout.addWidget(button)
        action_layout.addSpacing(tokens.space_4)
        self.export_actions_label = QLabel("Экспорт:")
        self.export_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(self.export_actions_label)
        self.export_csv_button = V3Button("CSV", ButtonVariant.PRIMARY)
        self.export_csv_button.setIcon(_review_action_icon("prompt_export"))
        self.export_csv_button.setIconSize(QSize(22, 22))
        self.export_csv_button.setFixedHeight(40)
        self.export_csv_button.setToolTip("Экспортировать все строки в CSV")
        self.export_csv_button.setAccessibleName(
            "Экспортировать все строки в CSV"
        )
        action_layout.addWidget(self.export_csv_button)
        action_layout.addStretch()
        self.add_widget(prompt_actions)
        self.issues_label = QLabel()
        self.issues_label.setWordWrap(True)
        self.issues_label.setProperty("v3Small", True)
        self.add_widget(self.issues_label)

        self.add_button.clicked.connect(self._add)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.delete_button.clicked.connect(self._delete)
        self.delete_all_button.clicked.connect(self._delete_all)
        self.batch_edit_button.clicked.connect(self._open_batch_editor)
        self.undo_batch_button.clicked.connect(self._undo_batch_edit)
        self.add_refs_button.clicked.connect(self._add_references)
        self.replace_refs_button.clicked.connect(self._replace_references)
        self.delete_refs_button.clicked.connect(self._delete_references)
        self.export_csv_button.clicked.connect(self._export_csv)
        self.refresh_from_state()

    def _open_batch_editor(self) -> None:
        if not self.state.clipart.prompts:
            self.card.set_state("error", "Сначала добавьте промпты")
            return
        dialog = PromptBatchEditDialog(
            self.state.clipart.prompts,
            selected_rows=self._selected_rows(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entries, affected_count = dialog.edited_entries()
        self._apply_batch_result(entries, affected_count=affected_count)

    def _apply_batch_result(
        self,
        entries: Sequence[PromptEntry],
        *,
        affected_count: int,
    ) -> None:
        if affected_count <= 0:
            return
        self._batch_undo_snapshot = [
            PromptEntry(entry.prompt, list(entry.references))
            for entry in self.state.clipart.prompts
        ]
        self.state.clipart.prompts = [
            PromptEntry(entry.prompt, list(entry.references))
            for entry in entries
        ]
        self.undo_batch_button.setEnabled(True)
        self.undo_batch_button.show()
        self.refresh_from_state()
        self.card.set_state("default", f"Изменено промптов: {affected_count}")
        self.changed()

    def _undo_batch_edit(self) -> None:
        if self._batch_undo_snapshot is None:
            return
        self.state.clipart.prompts = self._batch_undo_snapshot
        self._invalidate_batch_undo()
        self.refresh_from_state()
        self.card.set_state("default", "Массовое изменение отменено")
        self.changed()

    def _invalidate_batch_undo(self) -> None:
        self._batch_undo_snapshot = None
        self.undo_batch_button.setEnabled(False)
        self.undo_batch_button.hide()

    def _rows_moved(self, *_: Any) -> None:
        if self._updating:
            return
        # The references column is a display summary, not the source data.
        # Rebuilding entries from its text during drag/drop loses references
        # and can blank prompts while Qt is moving rows. Keep the original
        # entry index on the prompt item and only reorder existing entries.
        reordered: list[PromptEntry] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            source_row = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(source_row, int) and 0 <= source_row < len(self.state.clipart.prompts):
                reordered.append(self.state.clipart.prompts[source_row])
        if len(reordered) == len(self.state.clipart.prompts):
            self._invalidate_batch_undo()
            self.state.clipart.prompts = reordered
            self._updating = True
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row)
            self._updating = False
            self._refresh_issues()
            self.changed()

    def refresh_from_state(self) -> None:
        self._updating = True
        self.table.setRowCount(len(self.state.clipart.prompts))
        for row, entry in enumerate(self.state.clipart.prompts):
            prompt_item = QTableWidgetItem(entry.prompt)
            prompt_item.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(row, 0, prompt_item)
            refs_item = QTableWidgetItem(_reference_summary(entry.references))
            refs_item.setData(
                Qt.ItemDataRole.UserRole,
                tuple(entry.references),
            )
            refs_item.setFlags(
                refs_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            refs_item.setToolTip("\n".join(entry.references) or "Нет референсов")
            self.table.setItem(row, 1, refs_item)
        self._updating = False
        self._apply_search()
        self._refresh_issues()

    def _apply_search(self, *_: Any) -> None:
        query = self.search_edit.text().strip().casefold()
        visible = 0
        for row, entry in enumerate(self.state.clipart.prompts):
            haystack = " ".join((entry.prompt, *entry.references)).casefold()
            matches = not query or query in haystack
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        self.search_result_label.setText(
            f"Показано {visible} из {len(self.state.clipart.prompts)}"
        )

    def _selected_rows(self) -> list[int]:
        rows = {
            index.row()
            for index in self.table.selectionModel().selectedRows()
            if 0 <= index.row() < len(self.state.clipart.prompts)
        }
        return sorted(rows)

    def _edit_row(self, row: int, *_: Any) -> None:
        if not 0 <= row < len(self.state.clipart.prompts):
            return
        entry = self.state.clipart.prompts[row]
        dialog = PromptReferenceEditorDialog(entry, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._invalidate_batch_undo()
        self.state.clipart.prompts[row] = dialog.prompt_entry()
        self.refresh_from_state()
        self.changed()

    def _pick_reference_scope(self) -> str | None:
        dialog = ReferenceScopeDialog(
            has_selection=bool(self.table.selectionModel().selectedRows()),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.scope()

    def _choose_reference_files(self) -> list[str]:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            self.state.common.work_dir or os.getcwd(),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
        )
        files = [str(Path(path)) for path in selected if path]
        accepted: list[str] = []
        errors: list[str] = []
        for path in files:
            if not _supported_local_reference(path):
                continue
            size_error = _reference_file_size_error(path)
            if size_error:
                errors.append(size_error)
                continue
            accepted.append(path)
        if errors:
            self.card.set_state("error", errors[0])
        return accepted

    def _apply_references(
        self,
        *,
        replace: bool,
    ) -> None:
        scope = self._pick_reference_scope()
        if scope is None:
            return
        if scope == "all":
            rows = list(range(len(self.state.clipart.prompts)))
        elif scope == "selected":
            rows = self._selected_rows()
        else:
            row = self._selected_row()
            rows = [row] if row >= 0 else []
        if not rows:
            return
        files = self._choose_reference_files()
        if not files or not rows:
            return
        changed_any = False
        for row in rows:
            entry = self.state.clipart.prompts[row]
            if replace:
                entry.references = list(files[:MAX_REFERENCES_PER_PROMPT])
            else:
                merged = list(entry.references)
                for reference in files:
                    if reference not in merged:
                        merged.append(reference)
                entry.references = merged[:MAX_REFERENCES_PER_PROMPT]
            changed_any = True
        if changed_any:
            self._invalidate_batch_undo()
            self.refresh_from_state()
            self.changed()

    def _add_references(self) -> None:
        self._apply_references(replace=False)

    def _replace_references(self) -> None:
        self._apply_references(replace=True)

    def _delete_references(self) -> None:
        if not self.state.clipart.prompts:
            return
        scope = self._pick_reference_scope()
        if scope is None:
            return
        if scope == "all":
            rows = range(len(self.state.clipart.prompts))
        elif scope == "selected":
            rows = self._selected_rows()
        else:
            row = self._selected_row()
            rows = [row] if row >= 0 else []
        rows = list(rows)
        if not rows:
            return
        self._invalidate_batch_undo()
        for row in rows:
            self.state.clipart.prompts[row].references = []
        self.refresh_from_state()
        self.changed()

    def _export_csv(self) -> None:
        if not self.state.clipart.prompts:
            self.card.set_state("error", "Сначала добавьте промпты")
            return
        initial_path = str(
            Path(self.state.common.work_dir or os.getcwd()) / "prompts.csv"
        )
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Экспортировать промпты",
            initial_path,
            "CSV files (*.csv)",
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.casefold() != ".csv":
            destination = destination.with_suffix(".csv")
        try:
            export_prompt_csv(self.state.clipart.prompts, destination)
        except OSError:
            self.card.set_state("error", "Не удалось сохранить CSV")
            return
        self.card.set_state("default", f"CSV сохранён: {destination.name}")

    # Backward-compatible test and keyboard action name.
    def _delete_all_references(self) -> None:
        if not self.state.clipart.prompts:
            return
        self._invalidate_batch_undo()
        for entry in self.state.clipart.prompts:
            entry.references = []
        self.refresh_from_state()
        self.changed()

    def _table_changed(self, _: QTableWidgetItem) -> None:
        if self._updating:
            return
        self._invalidate_batch_undo()
        entries: list[PromptEntry] = []
        for row in range(self.table.rowCount()):
            prompt_item = self.table.item(row, 0)
            refs_item = self.table.item(row, 1)
            prompt = prompt_item.text() if prompt_item else ""
            stored_references = (
                refs_item.data(Qt.ItemDataRole.UserRole)
                if refs_item is not None
                else ()
            )
            references = [
                str(value)
                for value in (
                    stored_references
                    if isinstance(stored_references, (list, tuple))
                    else ()
                )
                if str(value)
            ]
            if len(prompt) > MAX_TEXT_LENGTH:
                self.card.set_state("error", "Промпт превышает допустимую длину")
                self.refresh_from_state()
                return
            if len(references) > MAX_REFERENCES_PER_PROMPT:
                self.card.set_state(
                    "error",
                    f"Максимум {MAX_REFERENCES_PER_PROMPT} референсов на промпт",
                )
                self.refresh_from_state()
                return
            if any(len(value) > MAX_TEXT_LENGTH for value in references):
                self.card.set_state("error", "Референс превышает допустимую длину")
                self.refresh_from_state()
                return
            entries.append(PromptEntry(prompt=prompt, references=references))
        self.state.clipart.prompts = entries
        self._apply_search()
        self._refresh_issues()
        self.changed()

    def _selected_row(self) -> int:
        row = self.table.currentRow()
        return row if 0 <= row < len(self.state.clipart.prompts) else -1

    def _add(self) -> None:
        if len(self.state.clipart.prompts) >= MAX_PROMPT_ENTRIES:
            self.card.set_state("error", f"Максимум {MAX_PROMPT_ENTRIES} промптов")
            return
        self.card.set_state("default")
        self._invalidate_batch_undo()
        self.state.clipart.prompts.append(PromptEntry(prompt="Новый промпт"))
        self.refresh_from_state()
        self.table.setCurrentCell(len(self.state.clipart.prompts) - 1, 0)
        self.changed()

    def _duplicate(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        if len(self.state.clipart.prompts) >= MAX_PROMPT_ENTRIES:
            self.card.set_state("error", f"Максимум {MAX_PROMPT_ENTRIES} промптов")
            return
        self.card.set_state("default")
        self._invalidate_batch_undo()
        source = self.state.clipart.prompts[row]
        self.state.clipart.prompts.insert(
            row + 1,
            PromptEntry(source.prompt, list(source.references)),
        )
        self.refresh_from_state()
        self.table.setCurrentCell(row + 1, 0)
        self.changed()

    def _delete(self) -> None:
        rows = self._selected_rows()
        if not rows:
            row = self._selected_row()
            rows = [row] if row >= 0 else []
        if not rows:
            return
        self._invalidate_batch_undo()
        for row in reversed(rows):
            del self.state.clipart.prompts[row]
        self.refresh_from_state()
        self.changed()

    def _delete_all(self) -> None:
        if not _confirm_delete_all_prompts(
            self,
            len(self.state.clipart.prompts),
        ):
            return
        self._invalidate_batch_undo()
        self.state.clipart.prompts = []
        self.refresh_from_state()
        self.changed()

    def _move(self, offset: int) -> None:
        row = self._selected_row()
        target = row + offset
        if row < 0 or not 0 <= target < len(self.state.clipart.prompts):
            return
        self._invalidate_batch_undo()
        prompts = self.state.clipart.prompts
        prompts[row], prompts[target] = prompts[target], prompts[row]
        self.refresh_from_state()
        self.table.setCurrentCell(target, 0)
        self.changed()

    def _refresh_issues(self) -> None:
        empty = 0
        duplicates = 0
        seen: set[str] = set()
        for entry in self.state.clipart.prompts:
            key = entry.prompt.strip().casefold()
            if not key:
                empty += 1
            elif key in seen:
                duplicates += 1
            else:
                seen.add(key)
        text = (
            f"Строк: {len(self.state.clipart.prompts)} · "
            f"пустых: {empty} · дублей: {duplicates}"
        )
        self.issues_label.setText(text)
        self.issues_label.setAccessibleName(text)

    def validation_issues(self) -> tuple[str, ...]:
        if any(not entry.prompt.strip() for entry in self.state.clipart.prompts):
            return ("prompt_empty",)
        return ()


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


class ClipartGenerationPage(_ScrollableStepPage):
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
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Генерация",
            "Выберите модель, формат и число вариантов до платного запуска.",
            tokens=tokens,
        )
        self.state = state
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

        self._select_model(self.model_combo, state.clipart.generation.model)
        if not self.shared_generation_settings:
            self._select_model(
                self.reference_model_combo,
                state.clipart.generation.reference_model,
            )
        self._refresh_profile_controls(primary=True, sync=False)
        if not self.shared_generation_settings and not self.shared_reference_format:
            self._refresh_profile_controls(primary=False, sync=False)
        self.variants_spin.setValue(state.clipart.generation.variants)
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
        ClipartGenerationPage.refresh_from_state(self)

    def _select_model(self, combo: QComboBox, model_id: str) -> None:
        index = combo.findData(model_id)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _has_references(self) -> bool:
        return any(entry.references for entry in self.state.clipart.prompts)

    def _model_options_for_current_prompts(self) -> tuple[GenerationModelOption, ...]:
        if not self.shared_generation_settings or not self._has_references():
            return self.text_options
        reference_ids = {option.model_id for option in self.reference_options}
        return tuple(
            option for option in self.text_options if option.model_id in reference_ids
        )

    def _replace_model_options(self) -> None:
        selected_model = str(self.model_combo.currentData() or self.state.clipart.generation.model)
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
            prompts = getattr(self.state.clipart, "prompts", ())
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
        if values:
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
        generation = self.state.clipart.generation
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

    @staticmethod
    def _combo_value(combo: QComboBox) -> str:
        return str(combo.currentData() or combo.currentText())

    def _sync(self, *_: Any, mark: bool = True) -> None:
        self.state.clipart.generation = GenerationData(
            model=str(self.model_combo.currentData() or ""),
            ratio=self.ratio_combo.currentText(),
            resolution=self._combo_value(self.resolution_combo),
            reference_model=(
                str(self.model_combo.currentData() or "")
                if self.shared_generation_settings
                else str(self.reference_model_combo.currentData() or "")
            ),
            reference_ratio=(
                self.ratio_combo.currentText()
                if self.shared_generation_settings or self.shared_reference_format
                else self.reference_ratio_combo.currentText()
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
        prompts = getattr(self.state.clipart, "prompts", [])
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
        ratio = self.ratio_combo.currentText()
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


def fal_endpoint_quantities(state: ProjectState) -> dict[str, int]:
    """Return paid Fal.ai call counts for the current clipart run."""
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    generation = state.clipart.generation
    variants = max(1, int(generation.variants))
    quantities: dict[str, int] = {}

    def add(model_id: str, count: int) -> None:
        if is_fal_model_id(model_id) and count > 0:
            quantities[model_id] = quantities.get(model_id, 0) + count

    for entry in state.clipart.prompts:
        add(
            generation.reference_model if entry.references else generation.model,
            variants,
        )
    operations = state.clipart.operations
    output_count = len(state.clipart.prompts) * variants
    if operations.upscale_before and operations.upscale_before_provider == "fal":
        add(operations.fal_upscale_model, output_count)
    if operations.remove_background and operations.remove_background_provider == "fal":
        add(operations.fal_remove_bg_model, output_count)
    return quantities


class ClipartReviewRunPage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        fal_cost_refresh: Callable[[], tuple[float, str]] | None = None,
    ) -> None:
        super().__init__(
            "Проверка и запуск",
            "Проверьте объём, стоимость и точный порядок до запуска.",
            tokens=tokens,
        )
        self.state = state
        self.fal_cost_refresh = fal_cost_refresh
        self._fal_cost_amount: Decimal | None = None
        self._fal_cost_currency = "USD"
        self._fal_cost_signature: tuple[tuple[str, int], ...] | None = None
        self._fal_cost_error = ""
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.output_label.setProperty("v3Status", True)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("v3Status", True)
        self.requests_label = QLabel()
        self.requests_label.setWordWrap(True)
        self.requests_label.setProperty("v3Status", True)
        self.cost_breakdown_label = QLabel()
        self.cost_breakdown_label.setWordWrap(True)
        self.cost_breakdown_label.setProperty("v3Status", True)
        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.pipeline_label.setProperty("v3Status", True)
        self.requirements_label = QLabel()
        self.requirements_label.setWordWrap(True)
        self.requirements_label.setProperty("v3Status", True)
        self.requirements_label.hide()
        self.run_status_label = QLabel()
        self.run_status_label.setWordWrap(True)
        self.run_status_label.setProperty("v3Small", True)
        self.fal_cost_refresh_button = V3Button(
            "Обновить оценку Fal.ai", ButtonVariant.SECONDARY
        )
        self.fal_cost_refresh_button.clicked.connect(self.refresh_fal_cost)
        self.cost_row = QWidget()
        cost_layout = QHBoxLayout(self.cost_row)
        cost_layout.setContentsMargins(0, 0, 0, 0)
        cost_layout.setSpacing(tokens.space_2)
        cost_layout.addWidget(self.cost_breakdown_label)
        cost_layout.addWidget(self.fal_cost_refresh_button)
        cost_layout.addStretch(1)
        for widget in (
            self.output_label,
            self.summary_label,
            self.requests_label,
            self.cost_row,
            self.pipeline_label,
            self.requirements_label,
            self.run_status_label,
        ):
            self.add_widget(widget)
        self.card.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.card.content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        for label in (
            self.card.title_label,
            self.card.description_label,
            self.output_label,
            self.summary_label,
            self.requests_label,
            self.cost_breakdown_label,
            self.pipeline_label,
            self.requirements_label,
            self.run_status_label,
        ):
            label.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            )
            label.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Maximum,
            )
        self.refresh_from_state()

    def _fal_selected(self) -> bool:
        return bool(fal_endpoint_quantities(self.state))

    def validation_issues(self) -> tuple[str, ...]:
        return ()

    def refresh_from_state(self) -> None:
        output_dir = self.state.output_dir_for_mode(ProjectMode.CLIPART)
        if not output_dir and self.state.common.work_dir:
            output_dir = str(Path(self.state.common.work_dir) / "output")
            self.state.set_output_dir_for_mode(output_dir, ProjectMode.CLIPART)
        if not output_dir:
            output_dir = "не выбрана"
        estimate = estimate_clipart_cost(self.state)
        fal_signature = tuple(sorted(fal_endpoint_quantities(self.state).items()))
        if self._fal_cost_signature != fal_signature:
            self._fal_cost_amount = None
            self._fal_cost_currency = "USD"
            self._fal_cost_error = ""
        generation = self.state.clipart.generation
        self.output_label.setText(f"Папка результата: {output_dir}")
        variants = generation.variants
        model_summary = f"модель {generation.model}"
        output_count = len(self.state.clipart.prompts) * variants
        self.summary_label.setText(
            f"Всего изображений {output_count} · {model_summary} · "
            f"формат {generation.ratio} · {generation.resolution}"
        )
        self.requests_label.setText(
            "API-вызовы: "
            f"генерация {estimate.generation_request_count} · "
            f"обработка {estimate.processing_request_count} · "
            f"всего {estimate.request_count}"
        )
        self._render_cost_breakdown(estimate)
        self.pipeline_label.setText(
            "Порядок: "
            + " → ".join(
                clipart_pipeline_steps(self.state.clipart.operations)
            )
        )
        has_fal = self._fal_selected()
        self.fal_cost_refresh_button.setVisible(has_fal)

    def _render_cost_breakdown(self, estimate: CostEstimate) -> None:
        labels = {
            "kie": "KIE",
            "fal": "Fal.ai",
            "photoroom": "PhotoRoom",
        }
        lines = ["Ориентировочная стоимость"]
        total = Decimal("0")
        total_complete = True
        for provider in ("kie", "fal", "photoroom"):
            if provider not in estimate.provider_usd:
                continue
            if provider == "fal":
                if self._fal_cost_amount is not None:
                    lines.append(
                        f"Fal.ai — {self._fal_cost_amount:.3f} "
                        f"{self._fal_cost_currency}"
                    )
                    if self._fal_cost_currency == "USD":
                        total += self._fal_cost_amount
                    else:
                        total_complete = False
                elif self._fal_cost_error:
                    lines.append(f"Fal.ai — {self._fal_cost_error}")
                    total_complete = False
                else:
                    lines.append("Fal.ai — требуется обновить")
                    total_complete = False
                continue
            amount = estimate.provider_usd[provider]
            if provider in estimate.incomplete_providers:
                lines.append(f"{labels[provider]} — стоимость недоступна")
                total_complete = False
            else:
                lines.append(f"{labels[provider]} — {amount:.3f} USD")
                total += amount
        if total_complete:
            lines.append(f"Итого — {total:.3f} USD")
        else:
            lines.append("Итого — не рассчитано полностью")
        lines.append("Фактическая сумма может отличаться.")
        self.cost_breakdown_label.setText("\n".join(lines))

    def refresh_fal_cost(self) -> None:
        current_signature = tuple(
            sorted(fal_endpoint_quantities(self.state).items())
        )
        if self.fal_cost_refresh is None:
            self._fal_cost_amount = None
            self._fal_cost_signature = current_signature
            self._fal_cost_error = "добавьте API-ключ в настройках"
            self._render_cost_breakdown(estimate_clipart_cost(self.state))
            return
        try:
            amount, currency = self.fal_cost_refresh()
        except (RuntimeError, ValueError, TypeError) as error:
            self._fal_cost_amount = None
            self._fal_cost_signature = current_signature
            self._fal_cost_error = f"не удалось обновить: {error}"
            self._render_cost_breakdown(estimate_clipart_cost(self.state))
            return
        self._fal_cost_amount = Decimal(str(amount))
        self._fal_cost_currency = str(currency or "USD").upper()
        self._fal_cost_signature = current_signature
        self._fal_cost_error = ""
        self._render_cost_breakdown(estimate_clipart_cost(self.state))

    def set_preflight_status(self, text: str, *, ready: bool) -> None:
        if ready:
            self.requirements_label.clear()
            self.requirements_label.setVisible(False)
            self.requirements_label.setAccessibleName("")
            return
        self.requirements_label.setVisible(True)
        prefix = "✓ " if ready else "✕ "
        self.requirements_label.setText(prefix + text)
        self.requirements_label.setProperty(
            "state",
            "default" if ready else "error",
        )
        self.requirements_label.setAccessibleName(prefix + text)
    def set_run_status(self, text: str, *, error: bool = False) -> None:
        prefix = "✕ " if error else "✓ "
        self.run_status_label.setText(prefix + text)
        self.run_status_label.setAccessibleName(prefix + text)


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


def _safe_runtime_error(
    error: Any,
    runtime_settings: Mapping[str, Any] | None = None,
) -> str:
    import main

    if isinstance(error, PermissionError) or getattr(error, "winerror", None) == 5:
        return (
            "Нет доступа к файлу или папке. Выберите другую папку результата "
            "или проверьте права доступа."
        )
    source = runtime_settings or {}
    secrets = tuple(
        source.get(name)
        for name in ("kie_api_key", "photoroom_api_key", "fal_api_key")
        if isinstance(source.get(name), str)
    )
    safe_message = main.safe_error_text(error, secrets=secrets, limit=500)
    classified = friendly_provider_error(safe_message)
    return classified[1] if classified is not None else safe_message


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
