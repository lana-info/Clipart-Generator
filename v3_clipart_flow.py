from __future__ import annotations

import csv
import io
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QCheckBox,
    QButtonGroup,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QScrollArea,
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
)
from processing_cleanup import METADATA_CLEANUP_FIELDS
from v3_prompt_csv_import import PromptCsvImportDialog
from v3_project_state import (
    MAX_PROMPT_ENTRIES,
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
    KIE_MODEL_OPTIONS,
    processing_provider_options,
    provider_preserves_alpha,
    provider_requires_api_key,
    provider_supports_operation,
    provider_visible_controls,
)
from v3_wizard import AppShell


MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CLIPART_REQUESTS = 5000
_DOLLAR_PATTERN = re.compile(r"\$(\d+(?:\.\d+)?)")


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
    "auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9", "1:4", "4:1", "1:8", "8:1"
)
_LEGACY_RESOLUTION_OPTIONS_ORDER = ("1K", "2K", "4K", "8K")
_LEGACY_PROCESSING_PRICING = {
    "topaz/upscale": "40 credits / $0.20",
    "recraft/crisp-upscale": "0.5 credits / $0.0025",
    "recraft/remove-background": "1 credit / $0.005",
}


def _legacy_model_capabilities(model_id: str) -> dict[str, Any]:
    limits = _LEGACY_MODEL_CAPABILITIES.get(model_id) or {}
    return {
        "ratios": set(limits.get("ratios") or set()),
        "resolutions": set(limits.get("resolutions") or set()),
        "qualities": set(limits.get("qualities") or set()),
        "pricing": limits.get("pricing"),
        "reference_compatible_text": bool(limits.get("reference_compatible_text", False)),
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
) -> tuple[GenerationModelOption, ...]:
    options, _ = _legacy_catalog()
    result: list[GenerationModelOption] = []
    for option in options.values():
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
            result.append(option)
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
    total = Decimal("0")
    complete = True
    provider_request_count = len(state.clipart.prompts) * variants

    for entry in state.clipart.prompts:
        if entry.references:
            option = _model_option(generation.reference_model)
            resolution = generation.reference_resolution
        else:
            option = _model_option(generation.model)
            resolution = generation.resolution
        unit = _price_usd(option.pricing, resolution)
        if unit is None:
            complete = False
        else:
            total += unit * variants

    _, processing_pricing = _legacy_catalog()
    operations = state.clipart.operations
    processing_models: list[str] = []
    if operations.upscale_before and operations.upscale_before_provider == "kie":
        processing_models.append(operations.kie_upscale_model)
    if operations.remove_background:
        if operations.remove_background_provider == "kie":
            processing_models.append(operations.kie_remove_bg_model)
        elif operations.remove_background_provider == "photoroom":
            total += Decimal("0.02") * len(state.clipart.prompts) * variants
            provider_request_count += len(state.clipart.prompts) * variants
    if operations.upscale_after and operations.upscale_after_provider == "kie":
        processing_models.append(operations.kie_upscale_after_model)

    output_count = len(state.clipart.prompts) * variants
    provider_request_count += len(processing_models) * output_count
    for model_id in processing_models:
        unit = _price_usd(processing_pricing.get(model_id), "")
        if unit is None:
            complete = False
        else:
            total += unit * output_count

    return CostEstimate(
        request_count=provider_request_count,
        estimated_usd=total,
        complete=complete,
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
        for name in ("kie_api_key", "photoroom_api_key", "local_realesrgan_dir")
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
            "local_realesrgan_profile": operations.local_realesrgan_profile,
            "local_realesrgan_scale": operations.local_realesrgan_scale,
            "local_realesrgan_after_scale": (
                operations.local_realesrgan_after_scale
            ),
            "remove_bg": operations.remove_background,
            "remove_bg_provider": operations.remove_background_provider,
            "kie_remove_bg_model": operations.kie_remove_bg_model,
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
    if provider_preserves_alpha(operations.upscale_after_provider):
        return
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
        if not (
            reference_option.model_type in {"image_to_image", "edit"}
            or reference_option.reference_compatible_text
        ):
            raise ClipartFlowError(
                "Референсная модель не поддерживает image-to-image"
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
        for _ in range(generation.variants):
            prompts.append(
                {
                    "prompt": entry.prompt,
                    "references": list(entry.references),
                }
            )

    settings = _worker_settings(state, runtime_settings)
    settings["output_dir"] = state.output_dir_for_mode(ProjectMode.CLIPART)
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

    if request.generated_prompts and not str(request.settings.get("kie_api_key") or "").strip():
        add_missing("KIE API Key")

    for enabled_field, provider_field in (
        ("upscale", "upscale_provider"),
        ("upscale_after", "upscale_after_provider"),
        ("remove_bg", "remove_bg_provider"),
    ):
        if not request.settings.get(enabled_field):
            continue
        provider_id = str(request.settings.get(provider_field) or "")
        api_key_name = "photoroom_api_key" if provider_id == "photoroom" else "kie_api_key"
        if provider_requires_api_key(provider_id) and not str(request.settings.get(api_key_name) or "").strip():
            add_missing(
                "KIE API Key" if api_key_name == "kie_api_key" else "PhotoRoom API Key"
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
        for reference in references:
            normalized = str(Path(reference))
            if (
                not normalized
                or normalized in existing
                or not _supported_local_reference(normalized)
            ):
                continue
            if len(existing) >= MAX_REFERENCES_PER_PROMPT:
                break
            item = QListWidgetItem(_reference_icon(normalized), _reference_label(normalized))
            item.setData(Qt.ItemDataRole.UserRole, normalized)
            item.setToolTip(normalized)
            self._references.addItem(item)
            existing.append(normalized)

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
    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Содержание",
            "Создайте серию, вставьте готовые строки или импортируйте CSV.",
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self.source_combo = QComboBox()
        self.source_combo.setAccessibleName("Источник промптов")
        self.source_combo.addItem("Сгенерировать серию", "generator")
        self.source_combo.addItem("Вставить готовые промпты", "paste")
        self.source_combo.addItem("Импортировать CSV", "csv")
        self.add_widget(self.source_combo)

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
        self.add_widget(self.source_stack)
        self.source_combo.currentIndexChanged.connect(
            self.source_stack.setCurrentIndex
        )
        self.source_combo.setCurrentIndex(1)

    def _build_generator(self) -> QWidget:
        draft = self.state.clipart.prompt_generator
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.generator_section = AdvancedSection(
            "Создать варианты промптов по шаблону"
        )
        self.generator_section.set_expanded(False)
        layout.addWidget(self.generator_section)

        section_intro = QLabel(
            "Этот блок помогает быстро собрать варианты промптов по шаблону. "
            "Он не запускает генерацию изображений и его можно пропустить."
        )
        section_intro.setWordWrap(True)
        self.generator_section.add_widget(section_intro)

        form = QFormLayout()
        self.theme_edit = QLineEdit(draft.theme)
        self.subjects_edit = QPlainTextEdit("\n".join(draft.subjects))
        self.subjects_edit.setMaximumHeight(90)
        self.style_edit = QLineEdit(draft.style)
        self.palette_edit = QLineEdit(draft.palette)
        self.composition_edit = QLineEdit(draft.composition)
        self.background_edit = QLineEdit(draft.background)
        for edit in (
            self.theme_edit,
            self.style_edit,
            self.palette_edit,
            self.composition_edit,
            self.background_edit,
        ):
            edit.setMaxLength(MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        self.restrictions_edit = QPlainTextEdit("\n".join(draft.restrictions))
        self.restrictions_edit.setMaximumHeight(90)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 500)
        self.count_spin.setValue(draft.count)
        fields = (
            ("Тема", self.theme_edit),
            ("Объекты — по одному в строке", self.subjects_edit),
            ("Стиль", self.style_edit),
            ("Палитра", self.palette_edit),
            ("Композиция", self.composition_edit),
            ("Фон", self.background_edit),
            ("Запреты — по одному в строке", self.restrictions_edit),
            ("Количество", self.count_spin),
        )
        for label, control in fields:
            control.setAccessibleName(label)
            form.addRow(label, control)
        form_widget = QWidget()
        form_widget.setLayout(form)
        self.generator_section.add_widget(form_widget)

        self.preview_label = QLabel(
            "Нажмите «Создать варианты», чтобы увидеть будущие промпты."
        )
        self.preview_label.setWordWrap(True)
        self.preview_label.setProperty("v3Small", True)
        self.preview_label.setAccessibleName("Предпросмотр вариантов")
        self.generator_section.add_widget(self.preview_label)

        self.preview_button = V3Button("Создать варианты")
        self.preview_button.clicked.connect(self._preview)
        self.generate_button = self.preview_button
        self.generator_section.add_widget(self.preview_button)

        self.generated_variants_label = QLabel("")
        self.generated_variants_label.setWordWrap(True)
        self.generated_variants_label.setProperty("v3Small", True)
        self.generator_section.add_widget(self.generated_variants_label)

        action_row = QWidget()
        action_layout = QHBoxLayout(action_row)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.add_variants_button = V3Button("Добавить варианты")
        self.replace_variants_button = V3Button("Заменить все промпты")
        self.add_variants_button.setEnabled(False)
        self.replace_variants_button.setEnabled(False)
        action_layout.addWidget(self.add_variants_button)
        action_layout.addWidget(self.replace_variants_button)
        action_layout.addStretch()
        self.generator_section.add_widget(action_row)

        self.add_variants_button.clicked.connect(lambda: self._apply_generated("append"))
        self.replace_variants_button.clicked.connect(lambda: self._apply_generated("replace"))

        self._generated_variants: list[PromptEntry] = []
        for edit in (
            self.theme_edit,
            self.style_edit,
            self.palette_edit,
            self.composition_edit,
            self.background_edit,
        ):
            edit.textChanged.connect(self._generator_changed)
        self.subjects_edit.textChanged.connect(self._generator_changed)
        self.restrictions_edit.textChanged.connect(self._generator_changed)
        self.count_spin.valueChanged.connect(self._generator_changed)
        self._clear_preview()
        return widget

    def _generator_data(self, *, preview: bool = False) -> PromptGeneratorData:
        return PromptGeneratorData(
            theme=self.theme_edit.text(),
            subjects=self.subjects_edit.toPlainText().splitlines(),
            style=self.style_edit.text(),
            palette=self.palette_edit.text(),
            composition=self.composition_edit.text(),
            background=self.background_edit.text(),
            restrictions=self.restrictions_edit.toPlainText().splitlines(),
            count=1 if preview else self.count_spin.value(),
        )

    def _generator_changed(self, *_: Any) -> None:
        self.state.clipart.prompt_generator = self._generator_data()
        self._clear_preview()
        self.changed()

    def _clear_preview(self) -> None:
        self._generated_variants = []
        self.preview_label.setText(
            "Нажмите «Создать варианты», чтобы увидеть будущие промпты."
        )
        self.generated_variants_label.setText("")
        self.add_variants_button.setEnabled(False)
        self.replace_variants_button.setEnabled(False)

    def _preview(self, *_: Any) -> None:
        try:
            entries = generate_prompt_series(
                ProjectMode.CLIPART,
                self._generator_data(),
            )
        except PromptGeneratorError:
            self.card.set_state("error", "Добавьте тему или хотя бы один объект.")
            self._clear_preview()
            return
        self.card.set_state("default")
        self._generated_variants = entries
        self.preview_label.setText(
            "Будущие промпты готовы. Ниже можно добавить их к текущему списку "
            "или заменить все промпты."
        )
        preview_lines = []
        for index, entry in enumerate(entries[:8], start=1):
            preview_lines.append(f"{index}. {entry.prompt}")
        if len(entries) > 8:
            preview_lines.append(f"… и ещё {len(entries) - 8} вариантов")
        self.generated_variants_label.setText("\n".join(preview_lines))
        self.add_variants_button.setEnabled(True)
        self.replace_variants_button.setEnabled(True)

    def _apply_generated(self, action: str) -> None:
        if not self._generated_variants:
            self._preview()
        if not self._generated_variants:
            return
        if action == "append":
            replace_project_prompts(
                self.state,
                ProjectMode.CLIPART,
                list(self.state.clipart.prompts) + list(self._generated_variants),
            )
        else:
            replace_project_prompts(
                self.state,
                ProjectMode.CLIPART,
                list(self._generated_variants),
            )
        self.card.set_state("default")
        self.changed()

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
        self.paste_edit.setPlaceholderText("Один промпт в каждой строке")
        self.paste_edit.setAccessibleName("Готовые промпты")
        layout.addWidget(self.paste_edit)
        self.paste_button = V3Button("Заменить список")
        self.paste_button.clicked.connect(self._apply_paste)
        layout.addWidget(self.paste_button)
        return widget

    def _apply_paste(self) -> None:
        text = self.paste_edit.toPlainText()
        if len(text) > MAX_CSV_BYTES:
            self.card.set_state("error", "Вставленный текст превышает допустимый размер")
            return
        entries: list[PromptEntry] = []
        for line in text.splitlines():
            prompt = line.strip()
            if not prompt:
                continue
            if len(prompt) > MAX_TEXT_LENGTH:
                self.card.set_state("error", "Один из промптов слишком длинный")
                return
            if len(entries) >= MAX_PROMPT_ENTRIES:
                self.card.set_state(
                    "error",
                    f"Максимум {MAX_PROMPT_ENTRIES} промптов",
                )
                return
            entries.append(PromptEntry(prompt=prompt))
        replace_project_prompts(self.state, ProjectMode.CLIPART, entries)
        self.card.set_state("default")
        self.changed()

    def _build_csv(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        text = QLabel("CSV: сопоставьте столбцы и выберите действие импорта.")
        text.setWordWrap(True)
        layout.addWidget(text)
        self.csv_button = V3Button("Выбрать CSV", ButtonVariant.SECONDARY)
        self.csv_button.clicked.connect(self._choose_csv)
        layout.addWidget(self.csv_button)
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
        if dialog.import_action() == "append":
            replace_project_prompts(
                self.state,
                ProjectMode.CLIPART,
                list(self.state.clipart.prompts) + normalized_entries,
            )
        else:
            replace_project_prompts(self.state, ProjectMode.CLIPART, normalized_entries)
        self.card.set_state("default")
        self.changed()


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
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Промпт", "Референсы через |"])
        self.table.setAccessibleName("Таблица промптов")
        self.table.horizontalHeader().setStretchLastSection(True)
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
        self.add_widget(self.table)

        actions = QWidget()
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        prompt_actions_label = QLabel("Промпты:")
        prompt_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(prompt_actions_label)
        self.add_button = V3Button("Добавить", ButtonVariant.SECONDARY)
        self.duplicate_button = V3Button("Дублировать", ButtonVariant.SECONDARY)
        self.delete_button = V3Button("Удалить", ButtonVariant.SECONDARY)
        action_layout.addWidget(self.add_button)
        action_layout.addWidget(self.duplicate_button)
        action_layout.addWidget(self.delete_button)
        references_actions_label = QLabel("Референсы:")
        references_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(references_actions_label)
        self.add_refs_button = V3Button("🖼 +", ButtonVariant.SECONDARY)
        self.replace_refs_button = V3Button("🖼 ↻", ButtonVariant.SECONDARY)
        self.delete_refs_button = V3Button("🖼 −", ButtonVariant.SECONDARY)
        self.add_refs_button.setToolTip("Добавить референсы")
        self.replace_refs_button.setToolTip("Заменить референсы")
        self.delete_refs_button.setToolTip("Удалить референсы")
        self.add_refs_button.setAccessibleName("Добавить референсы")
        self.replace_refs_button.setAccessibleName("Заменить референсы")
        self.delete_refs_button.setAccessibleName("Удалить референсы")
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
        self.add_widget(actions)
        self.issues_label = QLabel()
        self.issues_label.setWordWrap(True)
        self.issues_label.setProperty("v3Small", True)
        self.add_widget(self.issues_label)

        self.add_button.clicked.connect(self._add)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.delete_button.clicked.connect(self._delete)
        self.add_refs_button.clicked.connect(self._add_references)
        self.replace_refs_button.clicked.connect(self._replace_references)
        self.delete_refs_button.clicked.connect(self._delete_references)
        self.refresh_from_state()

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
            self.state.clipart.prompts = reordered
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
            refs_item.setToolTip("\n".join(entry.references) or "Нет референсов")
            self.table.setItem(row, 1, refs_item)
        self._updating = False
        self._refresh_issues()

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
        return [path for path in files if _supported_local_reference(path)]

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
        for row in rows:
            self.state.clipart.prompts[row].references = []
        self.refresh_from_state()
        self.changed()

    # Backward-compatible test and keyboard action name.
    def _delete_all_references(self) -> None:
        for entry in self.state.clipart.prompts:
            entry.references = []
        self.refresh_from_state()
        self.changed()

    def _table_changed(self, _: QTableWidgetItem) -> None:
        if self._updating:
            return
        entries: list[PromptEntry] = []
        for row in range(self.table.rowCount()):
            prompt_item = self.table.item(row, 0)
            refs_item = self.table.item(row, 1)
            prompt = prompt_item.text() if prompt_item else ""
            references = [
                value.strip()
                for value in (refs_item.text() if refs_item else "").split("|")
                if value.strip()
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
        source = self.state.clipart.prompts[row]
        self.state.clipart.prompts.insert(
            row + 1,
            PromptEntry(source.prompt, list(source.references)),
        )
        self.refresh_from_state()
        self.table.setCurrentCell(row + 1, 0)
        self.changed()

    def _delete(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        del self.state.clipart.prompts[row]
        self.refresh_from_state()
        self.changed()

    def _move(self, offset: int) -> None:
        row = self._selected_row()
        target = row + offset
        if row < 0 or not 0 <= target < len(self.state.clipart.prompts):
            return
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
        )
        self.reference_options = generation_model_options(references=True)
        form = QFormLayout()
        self.model_combo = QComboBox()
        self.ratio_combo = QComboBox()
        self.resolution_combo = QComboBox()
        self.variants_spin = QSpinBox()
        self.variants_spin.setRange(1, 100)
        for option in self.text_options:
            self.model_combo.addItem(option.label, option.model_id)
        form.addRow("Модель", self.model_combo)
        form.addRow("Пропорция", self.ratio_combo)
        form.addRow("Разрешение", self.resolution_combo)
        form.addRow("Вариантов на промпт", self.variants_spin)
        container = QWidget()
        container.setLayout(form)
        self.add_widget(container)

        self.model_capability_label = QLabel()
        self.model_capability_label.setWordWrap(True)
        self.model_capability_label.setProperty("v3Small", True)
        self.add_widget(self.model_capability_label)

        advanced = AdvancedSection("Генерация по референсам", tokens=tokens)
        self.reference_advanced = advanced
        advanced.toggle_button.setVisible(False)
        advanced.set_expanded(True)
        self.reference_capability_label = QLabel()
        self.reference_capability_label.setWordWrap(True)
        self.reference_capability_label.setProperty("v3Small", True)
        advanced.add_widget(self.reference_capability_label)
        reference_form = QFormLayout()
        self.reference_model_combo = QComboBox()
        self.reference_ratio_combo = QComboBox()
        self.reference_resolution_combo = QComboBox()
        for option in self.reference_options:
            self.reference_model_combo.addItem(option.label, option.model_id)
        reference_form.addRow("Модель с референсом", self.reference_model_combo)
        reference_form.addRow("Пропорция с референсом", self.reference_ratio_combo)
        reference_form.addRow(
            "Разрешение с референсом",
            self.reference_resolution_combo,
        )
        reference_widget = QWidget()
        reference_widget.setLayout(reference_form)
        advanced.add_widget(reference_widget)
        self.add_widget(advanced)

        self.cost_label = QLabel()
        self.cost_label.setWordWrap(True)
        self.cost_label.setProperty("v3Status", True)
        self.add_widget(self.cost_label)
        for label, control in (
            ("Модель", self.model_combo),
            ("Пропорция", self.ratio_combo),
            ("Разрешение", self.resolution_combo),
            ("Вариантов на промпт", self.variants_spin),
            ("Модель с референсом", self.reference_model_combo),
            ("Пропорция с референсом", self.reference_ratio_combo),
            ("Разрешение с референсом", self.reference_resolution_combo),
        ):
            control.setAccessibleName(label)

        self._select_model(self.model_combo, state.clipart.generation.model)
        self._select_model(
            self.reference_model_combo,
            state.clipart.generation.reference_model,
        )
        self._refresh_profile_controls(primary=True, sync=False)
        self._refresh_profile_controls(primary=False, sync=False)
        self.variants_spin.setValue(state.clipart.generation.variants)
        self.model_combo.currentIndexChanged.connect(
            lambda: self._refresh_profile_controls(primary=True)
        )
        self.reference_model_combo.currentIndexChanged.connect(
            lambda: self._refresh_profile_controls(primary=False)
        )
        self.ratio_combo.currentTextChanged.connect(self._sync)
        self.resolution_combo.currentIndexChanged.connect(self._sync)
        self.reference_ratio_combo.currentTextChanged.connect(self._sync)
        self.reference_resolution_combo.currentIndexChanged.connect(self._sync)
        self.variants_spin.valueChanged.connect(self._sync)
        self._sync(mark=False)
        ClipartGenerationPage.refresh_from_state(self)

    def _select_model(self, combo: QComboBox, model_id: str) -> None:
        index = combo.findData(model_id)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _option_for_combo(self, combo: QComboBox) -> GenerationModelOption:
        return _model_option(str(combo.currentData() or ""))

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
                option.ratios or ("1:1",),
                generation.ratio,
            )
            self._set_values(
                self.resolution_combo,
                option.resolutions,
                generation.resolution,
                fixed_value="1K",
            )
        else:
            option = self._option_for_combo(self.reference_model_combo)
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
            reference_model=str(self.reference_model_combo.currentData() or ""),
            reference_ratio=self.reference_ratio_combo.currentText(),
            reference_resolution=self._combo_value(
                self.reference_resolution_combo
            ),
            variants=self.variants_spin.value(),
        )
        estimate = estimate_clipart_cost(self.state)
        self.cost_label.setText(estimate.summary)
        self.cost_label.setAccessibleName("Стоимость. " + estimate.summary)
        if mark:
            self.changed()

    def refresh_from_state(self) -> None:
        has_references = any(
            entry.references for entry in getattr(self.state.clipart, "prompts", [])
        )
        self.reference_advanced.set_expanded(has_references)
        self.reference_advanced.setVisible(True)
        current = self._option_for_combo(self.model_combo)
        self.model_capability_label.setText(_capability_summary(current))
        self._sync(mark=False)


class ClipartProcessingPage(_ScrollableStepPage):
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
        self.operations = operations
        upscale_models = KIE_MODEL_OPTIONS
        remove_bg_models = KIE_MODEL_OPTIONS

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
            "unsharp_amount": operations.unsharp,
            "unsharp_radius": operations.unsharp,
            "unsharp_threshold": operations.unsharp,
        }
        for name, visible in visibility.items():
            self._set_control_visible(name, visible)

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
            description="Единые настройки обработки изображений для всех режимов.",
            include_cleanup=True,
            tokens=tokens,
        )
        self.state = state
        self.changed = changed


ClipartProcessingPage = _SharedClipartProcessingPage


class ClipartReviewRunPage(_ScrollableStepPage):
    def __init__(
        self,
        state: ProjectState,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Проверка и запуск",
            "Проверьте объём, стоимость и точный порядок до запуска.",
            tokens=tokens,
        )
        self.state = state
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.pipeline_label = QLabel()
        self.pipeline_label.setWordWrap(True)
        self.requirements_label = QLabel()
        self.requirements_label.setWordWrap(True)
        self.requirements_label.setProperty("v3Status", True)
        self.warning_label = QLabel(
            "API-ключи не сохраняются в проекте и читаются из настроек только при запуске."
        )
        self.warning_label.setWordWrap(True)
        self.warning_label.setProperty("v3Status", True)
        self.warning_label.setProperty("state", "warning")
        self.run_status_label = QLabel()
        self.run_status_label.setWordWrap(True)
        self.run_status_label.setProperty("v3Small", True)
        for widget in (
            self.output_label,
            self.summary_label,
            self.pipeline_label,
            self.requirements_label,
            self.warning_label,
            self.run_status_label,
        ):
            self.add_widget(widget)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        output_dir = self.state.output_dir_for_mode(ProjectMode.CLIPART)
        if not output_dir and self.state.common.work_dir:
            output_dir = str(Path(self.state.common.work_dir) / "output")
            self.state.set_output_dir_for_mode(output_dir, ProjectMode.CLIPART)
        if not output_dir:
            output_dir = "не выбрана"
        estimate = estimate_clipart_cost(self.state)
        generation = self.state.clipart.generation
        self.output_label.setText(f"Папка результата: {output_dir}")
        variants = generation.variants
        text_count = sum(not entry.references for entry in self.state.clipart.prompts) * variants
        reference_count = sum(bool(entry.references) for entry in self.state.clipart.prompts) * variants
        model_summary = f"без референса {text_count}: {generation.model}"
        if reference_count:
            model_summary += (
                f" · с референсом {reference_count}: "
                f"{generation.reference_model}"
            )
        output_count = len(self.state.clipart.prompts) * variants
        self.summary_label.setText(
            f"{estimate.summary} · изображений {output_count} · {model_summary} · "
            f"{generation.ratio} · {generation.resolution}"
        )
        self.pipeline_label.setText(
            "Порядок: "
            + " → ".join(
                clipart_pipeline_steps(self.state.clipart.operations)
            )
        )

    def set_preflight_status(self, text: str, *, ready: bool) -> None:
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
        for name in ("kie_api_key", "photoroom_api_key")
        if isinstance(source.get(name), str)
    )
    return main.safe_error_text(error, secrets=secrets, limit=500)


def _legacy_worker_factory(**kwargs: Any) -> Any:
    from main import WorkerThread

    return WorkerThread(**kwargs)


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
        self.runtime_settings_provider = (
            runtime_settings_provider or _read_legacy_runtime_settings
        )
        self.worker_factory = worker_factory or _legacy_worker_factory
        self.authorization_provider = authorization_provider or self._missing_authorization
        self.worker: Any | None = None
        self._runtime_settings: Mapping[str, Any] = {}
        from v3_run_queue import RunQueueSupport

        self.run_queue = RunQueueSupport(self, ProjectMode.CLIPART)
        self.pages: dict[StepId, Any] = {}
        self._install_pages()
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

    def _install_pages(self) -> None:
        changed = self.shell.mark_dirty
        self.pages = {
            StepId.PROJECT: ClipartProjectPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
            StepId.PROMPTS: PromptWorkspacePage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
            StepId.GENERATION: ClipartGenerationPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
            StepId.PROCESSING_OPTIONS: ClipartProcessingPage(
                self.shell.state,
                changed,
                tokens=self.shell.tokens,
            ),
            StepId.REVIEW_RUN: ClipartReviewRunPage(
                self.shell.state,
                tokens=self.shell.tokens,
            ),            StepId.RESULTS: self.run_queue.page,

        }
        for step, page in self.pages.items():
            self.shell.set_step_page(ProjectMode.CLIPART, step, page)
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

    def start(self) -> ClipartRunRequest | None:
        if self.worker is not None and bool(self.worker.isRunning()):
            message = "Запуск уже выполняется"
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        try:
            runtime_settings = self.runtime_settings_provider()
            if not isinstance(runtime_settings, Mapping):
                raise ClipartFlowError("Настройки запуска повреждены")
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
        worker.start()
        self.shell.show_results()
        self.review_page.set_run_status("Запуск передан существующему pipeline 2.0")
        self.started.emit(request)
        return request

    def stop(self) -> None:
        if self.worker is not None and hasattr(self.worker, "stop"):
            self.worker.stop()

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
