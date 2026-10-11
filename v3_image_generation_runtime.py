"""Neutral prompt-image generation runtime shared by built-in workflows."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any

from fal_model_catalog import is_fal_generation_model, is_fal_model_id
from model_catalog import generation_provider_id
from model_catalog import (
    GENERATION_MODELS as CATALOG_GENERATION_MODELS,
    PROCESSING_PRICING as CATALOG_PROCESSING_PRICING,
    VISIBLE_GENERATION_MODEL_IDS as CATALOG_VISIBLE_GENERATION_MODEL_IDS,
    MODEL_SPECS, model_spec, ratios_for_mode, validate_generation_contract,
)
from output_naming import workspace_layout
from v3_flow_runtime import CostEstimate, FlowRunRequest
from v3_image_worker_settings import build_image_run_settings
from v3_project_state import ImageOperationData, PromptEntry
from v3_provider_registry import (
    provider_requires_api_key, provider_supports_operation, upscale_model_preserves_alpha,
)

MAX_IMAGE_GENERATION_REQUESTS = 5000


MAX_REFERENCE_FILE_BYTES = 10 * 1024 * 1024


_DOLLAR_PATTERN = re.compile(r"\$(\d+(?:\.\d+)?)")


_CHROMA_PROMPT_SUFFIX_MARKER = (
    "Isolated on a completely flat, uniform, solid pure "
)


def _split_user_prompt(prompt: str) -> tuple[str, str]:
    """Hide the generated background-preparation suffix from user-facing editors."""
    text = str(prompt or "")
    index = text.find(_CHROMA_PROMPT_SUFFIX_MARKER)
    if index < 0:
        return text, ""
    suffix_start = index
    if suffix_start > 0 and text[suffix_start - 1] in " \t\r\n":
        suffix_start -= 1
    return text[:suffix_start].rstrip(), text[suffix_start:]


def _user_prompt_text(prompt: str) -> str:
    return _split_user_prompt(prompt)[0]


class ImageGenerationFlowError(ValueError):
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


_LEGACY_RATIO_OPTIONS_ORDER = (
    "auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
    "1:2", "2:1", "1:3", "3:1", "9:16", "16:9", "9:21", "21:9",
    "1:4", "4:1", "1:8", "8:1"
)


_LEGACY_RESOLUTION_OPTIONS_ORDER = ("1K", "2K", "4K", "8K")


_LEGACY_VISIBLE_GENERATION_MODEL_IDS = CATALOG_VISIBLE_GENERATION_MODEL_IDS


_LEGACY_GENERATION_MODELS = CATALOG_GENERATION_MODELS


_LEGACY_PROCESSING_PRICING = CATALOG_PROCESSING_PRICING


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
    # model remains selectable for ordinary prompts.
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
        raise ImageGenerationFlowError(
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


def estimate_image_generation_cost(data: Any) -> CostEstimate:
    from result_background_policy import keeps_background
    generation = data.generation
    variants = generation.variants
    generation_total = Decimal("0")
    processing_total = Decimal("0")
    complete = True
    generation_request_count = len(data.prompts) * variants
    processing_request_count = 0
    provider_totals: dict[str, Decimal] = {}
    incomplete_providers: set[str] = set()

    def use_provider(provider: str) -> None:
        provider_totals.setdefault(provider, Decimal("0"))

    def add_provider_cost(provider: str, amount: Decimal) -> None:
        use_provider(provider)
        provider_totals[provider] += amount

    for entry in data.prompts:
        has_references = bool(entry.references)
        option = _model_option(
            generation.reference_model if has_references else generation.model
        )
        resolution = (
            generation.reference_resolution
            if has_references
            else generation.resolution
        )
        provider = generation_provider_id(option.model_id)
        use_provider(provider)
        if provider in {"fal", "atlascloud", "piapi"}:
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
    operations = data.operations
    output_count = len(data.prompts) * variants
    removal_count = sum(not keeps_background(entry.result_kind) for entry in data.prompts) * variants
    processing_models: list[tuple[str, int]] = []
    if operations.upscale_before and operations.upscale_before_provider == "kie":
        use_provider("kie")
        processing_models.append((operations.kie_upscale_model, output_count))
    elif operations.upscale_before and operations.upscale_before_provider == "fal":
        use_provider("fal")
        incomplete_providers.add("fal")
        processing_request_count += output_count
    if operations.remove_background and removal_count:
        if operations.remove_background_provider == "kie":
            use_provider("kie")
            processing_models.append((operations.kie_remove_bg_model, removal_count))
        elif operations.remove_background_provider == "photoroom":
            amount = Decimal("0.02") * removal_count
            processing_total += amount
            add_provider_cost("photoroom", amount)
            processing_request_count += removal_count
        elif operations.remove_background_provider == "fal":
            use_provider("fal")
            incomplete_providers.add("fal")
            processing_request_count += removal_count
    if operations.upscale_after and operations.upscale_after_provider == "kie":
        use_provider("kie")
        processing_models.append((operations.kie_upscale_after_model, output_count))
    elif operations.upscale_after and operations.upscale_after_provider == "fal":
        use_provider("fal")
        incomplete_providers.add("fal")
        processing_request_count += output_count

    processing_request_count += sum(count for _, count in processing_models)
    for model_id, count in processing_models:
        unit = _price_usd(processing_pricing.get(model_id), "")
        if unit is None:
            complete = False
            incomplete_providers.add("kie")
        else:
            amount = unit * count
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


def image_generation_pipeline_steps(
    operations: ImageOperationData,
) -> tuple[str, ...]:
    if not isinstance(operations, ImageOperationData):
        raise TypeError("operations must be ImageOperationData")
    steps = ["Генерация изображения"]
    if operations.visible_mark_cleanup:
        steps.append("Удаление видимой метки")
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
    return len(image_generation_pipeline_steps(operations)) > 2


def _validate_generation_profile(
    option: GenerationModelOption,
    ratio: str,
    resolution: str,
) -> None:
    if option.ratios and ratio not in option.ratios:
        raise ImageGenerationFlowError(
            f"Пропорция {ratio} недоступна для модели {option.label}"
        )
    if option.resolutions and resolution not in option.resolutions:
        raise ImageGenerationFlowError(
            f"Разрешение {resolution} недоступно для модели {option.label}"
        )


def _worker_settings(
    runtime: Any,
    data: Any,
    runtime_settings: Mapping[str, Any] | None,
) -> dict[str, Any]:
    del runtime_settings  # compatibility parameter; Core owns runtime enrichment.
    return build_image_run_settings(
        runtime, data.generation, data.operations,
        run_mode=("both" if _processing_requested(data.operations) else "generate_only"),
    )


def _validate_prompt_references(prompts: Sequence[PromptEntry]) -> None:
    import main

    for entry in prompts:
        for reference in entry.references:
            normalized = reference.strip()
            if normalized.lower().startswith(("https://", "http://")):
                try:
                    main.validate_https_url(normalized, "Reference URL")
                except (RuntimeError, ValueError) as error:
                    raise ImageGenerationFlowError(
                        "URL референса должен быть корректным HTTPS-адресом"
                    ) from error
                continue
            path = Path(normalized).expanduser()
            if not path.is_file():
                name = path.name or "референс"
                raise ImageGenerationFlowError(f"Файл референса не найден: {name}")
            size_error = _reference_file_size_error(
                str(path),
                attachment=False,
            )
            if size_error:
                raise ImageGenerationFlowError(size_error)
            try:
                main.validate_local_image_input(path)
            except (OSError, ValueError) as error:
                raise ImageGenerationFlowError(
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
        raise ImageGenerationFlowError(
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
                raise ImageGenerationFlowError(
                    f"Провайдер {provider_id} не поддерживает операцию {operation_field}"
                )
    except KeyError as error:
        raise ImageGenerationFlowError(f"Неизвестный провайдер: {error.args[0]}") from error


def _validate_alpha_safe_upscale(operations: ImageOperationData, alpha_checker=upscale_model_preserves_alpha) -> None:
    if not (operations.remove_background and operations.upscale_after):
        return
    if alpha_checker(
        operations.upscale_after_provider,
        operations.fal_upscale_after_model
        if operations.upscale_after_provider == "fal"
        else operations.kie_upscale_after_model,
    ):
        return
    if (
        operations.upscale_after_provider == "kie"
        and operations.kie_upscale_after_model == "recraft/crisp-upscale"
    ):
        raise ImageGenerationFlowError(
            "Recraft Crisp нельзя использовать после подготовки прозрачного фона: "
            "модель не поддерживает прозрачный вход"
        )
    raise ImageGenerationFlowError("Апскейл после подготовки прозрачного фона должен сохранять прозрачность")


def build_image_generation_run_request(
    common: Any,
    runtime: Any,
    data: Any,
    output_dir: str,
    runtime_settings: Mapping[str, Any] | None = None,
    *,
    upscale_alpha_checker=upscale_model_preserves_alpha,
) -> FlowRunRequest:
    work_dir = Path(common.work_dir).expanduser()
    if not work_dir.is_dir() or not os.access(work_dir, os.W_OK):
        raise ImageGenerationFlowError("Рабочая папка не существует или недоступна для записи")
    if not data.prompts:
        raise ImageGenerationFlowError("Добавьте хотя бы один промпт")

    generation = data.generation
    operations = data.operations
    _validate_prompt_references(data.prompts)
    _validate_processing_providers(operations)
    _validate_alpha_safe_upscale(operations, upscale_alpha_checker)
    _validate_processing_models(operations)
    text_option = _model_option(generation.model)
    if text_option.model_type != "text_to_image" and not text_option.reference_compatible_text:
        raise ImageGenerationFlowError("Основная модель должна поддерживать text-to-image")
    _validate_generation_profile(
        text_option,
        generation.ratio,
        generation.resolution,
    )

    if any(entry.references for entry in data.prompts):
        reference_option = _model_option(generation.reference_model)
        if (
            reference_option.model_type not in {"image_to_image", "edit"}
            and not reference_option.reference_compatible_text
        ):
            raise ImageGenerationFlowError(
                "Модель с референсом не поддерживает промпты с референсами"
            )
        _validate_generation_profile(
            reference_option,
            generation.reference_ratio,
            generation.reference_resolution,
        )

    request_count = len(data.prompts) * generation.variants
    if request_count > MAX_IMAGE_GENERATION_REQUESTS:
        raise ImageGenerationFlowError(
            f"Максимум {MAX_IMAGE_GENERATION_REQUESTS} запросов за один запуск"
        )
    if (
        data.operations.visible_mark_cleanup
        and data.operations.visible_mark_cleanup_mode == "confirmed_area"
    ):
        raise ImageGenerationFlowError(
            "Ручная область видимой метки недоступна для ещё не созданных файлов"
        )

    prompts: list[dict[str, Any]] = []
    for entry in data.prompts:
        from result_background_policy import keeps_background
        if keeps_background(entry.result_kind) and entry.chroma_key_color:
            raise ImageGenerationFlowError("Для этого типа результата настройка прозрачного фона недоступна")
        if not _user_prompt_text(entry.prompt).strip():
            raise ImageGenerationFlowError("Пустой промпт нельзя отправить на генерацию")
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
            raise ImageGenerationFlowError(str(error)) from error
        for _ in range(generation.variants):
            prompts.append(
                {
                    "prompt": entry.prompt,
                    "references": list(entry.references),
                    "chroma_key_color": entry.chroma_key_color,
                    "result_kind": entry.result_kind,
                    **({"object_id": entry.object_id} if entry.object_id else {}),
                }
            )

    settings = _worker_settings(runtime, data, runtime_settings)
    layout = workspace_layout(
        output_dir or work_dir
    )
    settings["output_dir"] = str(layout.output)
    settings["workspace_root"] = str(layout.root)
    mode = "mode_both" if _processing_requested(operations) else "mode1_generate_only"
    return FlowRunRequest(
        mode=mode,
        work_dir=str(work_dir),
        settings=settings,
        generated_prompts=prompts,
    )


def missing_runtime_requirements(request: FlowRunRequest) -> tuple[str, ...]:
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
        for provider_id, field, label in (
            ("fal", "fal_api_key", "Fal.ai API Key"),
            ("kie", "kie_api_key", "KIE API Key"),
            ("atlascloud", "atlascloud_api_key", "AtlasCloud API Key"),
            ("piapi", "piapi_api_key", "PiAPI API Key"),
        ):
            if any(generation_provider_id(model) == provider_id for model in generation_models):
                if not str(request.settings.get(field) or "").strip():
                    add_missing(label)

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
            missing.append("Local Real-ESRGAN")
    return tuple(missing)


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


def fal_endpoint_quantities(data: Any) -> dict[str, int]:
    """Return paid Fal.ai call counts for the current image-generation run."""
    from result_background_policy import keeps_background
    generation = data.generation
    variants = max(1, int(generation.variants))
    quantities: dict[str, int] = {}

    def add(model_id: str, count: int) -> None:
        if is_fal_model_id(model_id) and count > 0:
            quantities[model_id] = quantities.get(model_id, 0) + count

    for entry in data.prompts:
        add(
            generation.reference_model if entry.references else generation.model,
            variants,
        )
    operations = data.operations
    output_count = len(data.prompts) * variants
    if operations.upscale_before and operations.upscale_before_provider == "fal":
        add(operations.fal_upscale_model, output_count)
    if operations.remove_background and operations.remove_background_provider == "fal":
        removal_count = sum(not keeps_background(entry.result_kind) for entry in data.prompts) * variants
        add(operations.fal_remove_bg_model, removal_count)
    if operations.upscale_after and operations.upscale_after_provider == "fal":
        add(operations.fal_upscale_after_model, output_count)
    return quantities
