from __future__ import annotations

import os
import threading
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PIL import Image

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from license_client import LicenseError

from pinterest_pin_composer import (
    ProductLayer,
    assert_product_pixels_preserved,
    composite_product,
    load_product_layer,
    product_layer_digest,
    save_pin,
)
from pinterest_pin_templates import (
    pinterest_template_specs,
    render_template_background,
    template_product_box,
)
from security_redaction import redact_text

from v3_clipart_flow import (
    DEFAULT_TOKENS,
    ClipartFlowError,
    ClipartGenerationPage,
    ClipartProjectPage,
    ClipartPromptInputPage,
    ClipartPromptReviewPage,
    ClipartReviewRunPage,
    ClipartRunRequest,
    CostEstimate,
    ButtonVariant,
    V3DesignTokens,
    V3Button,
    _ScrollableStepPage,
    _safe_runtime_error,
    build_clipart_run_request,
    estimate_clipart_cost,
    estimate_fal_cost,
    fal_endpoint_quantities,
    generate_prompt_series,
    missing_runtime_requirements,
    replace_project_prompts,
)
from v3_project_state import (
    CommonProjectData,
    GenerationData,
    ImageOperationData,
    MAX_SELECTED_FILES,
    PINTEREST_AI_SCENE_COUNT,
    PINTEREST_TEMPLATE_COUNT,
    PinterestPinData,
    PinterestOperationData,
    PinterestModeData,
    PinterestPinResultData,
    ProjectMode,
    ProjectState,
    PromptGeneratorData,
    StepId,
)
from v3_prompt_generator import PromptGeneratorError
from v3_processing_editor import ProcessingPipelineEditor
from v3_wizard import AppShell
from v3_lazy_loading import LazyPageRegistry
from v3_localization import message_for, normalize_locale
from workflow_definitions import workflow_for_mode


_PINTEREST_REFERENCE_MODEL_BY_TEXT = {
    "flux-2/flex-text-to-image": "flux-2/flex-image-to-image",
    "flux-2/pro-text-to-image": "flux-2/pro-image-to-image",
    "gpt-image/1.5-text-to-image": "gpt-image/1.5-image-to-image",
    "gpt-image-2": "gpt-image-2",
    "nano-banana-2": "nano-banana-2",
    "nano-banana-pro": "nano-banana-pro",
    "qwen-image-2": "qwen-image-2",
}

_PINTEREST_UI_TEXT = {
    "ru": {
        "product_input_title": "Товар и текст пина",
        "product_input_description": "Загрузите товар, выберите один источник для серии и задайте текст пина.",
        "products": "Фотографии товара",
        "add_products": "Добавить фотографии",
        "selected_product": "Товар для серии",
        "title": "Заголовок",
        "subtitle": "Подзаголовок",
        "cta": "Призыв к действию",
        "style": "Стиль",
        "scene": "Описание сцены",
        "output_folder": "Папка результата",
        "choose": "Выбрать",
        "suggest_copy": "Подставить введённый текст",
        "no_products": "Фотографии товара не выбраны.",
        "preview_title": "Предпросмотр Pinterest-пинов",
        "preview_description": "Шесть фиксированных слотов: три шаблона и три AI-сцены.",
        "export": "Экспортировать принятые",
        "accept": "Принять вариант",
        "regenerate": "Перегенерировать",
        "source": "Источник",
        "variant": "Вариант",
        "fidelity_warning": "Предупреждение: точность товара не подтверждена защищённым слоем.",
        "export_ready": "К экспорту выбрано: {count}",
        "export_summary": "Сохранено: {count}; папка: {folder}",
        "regeneration_another_run_active": "Сначала завершите текущее задание в другом режиме",
        "regeneration_already_running": "Запуск уже выполняется",
        "regeneration_started": "Перегенерируется выбранный Pinterest-вариант",
        "status_pending": "Ожидает генерации",
        "status_success": "Готов",
        "status_failed": "Не удалось создать",
        "image_unavailable": "Предпросмотр изображения недоступен",
        "format_title": "Формат и модель",
        "format_accessible": "Формат и модель Pinterest-пинов",
        "format_recommendation": "Рекомендуемый вертикальный формат — 9:16. Можно выбрать любую пропорцию, поддерживаемую моделью.",
        "processing_title": "Обработка изображений",
        "processing_description": "Единые настройки обработки изображений для Pinterest.",
        "review_description": "Проверьте пакет изображений и стоимость перед явным запуском.",
        "project_title": "Рабочая папка",
        "project_description": "Выберите папку для записи результатов.",
        "prompt_review_title": "Проверка промптов",
        "prompt_review_description": "Проверьте и при необходимости исправьте промпты перед генерацией.",
        "review_title": "Проверка и запуск",
    },
    "en": {
        "product_input_title": "Product and pin copy",
        "product_input_description": "Upload product photos, select one source for the series, and set the pin copy.",
        "products": "Product photos",
        "add_products": "Add photos",
        "selected_product": "Product for this series",
        "title": "Title",
        "subtitle": "Subtitle",
        "cta": "Call to action",
        "style": "Style",
        "scene": "Scene description",
        "output_folder": "Output folder",
        "choose": "Choose",
        "suggest_copy": "Use entered copy",
        "no_products": "No product photos selected.",
        "preview_title": "Pinterest pin preview",
        "preview_description": "Six fixed slots: three templates and three AI scenes.",
        "export": "Export accepted",
        "accept": "Accept variant",
        "regenerate": "Regenerate",
        "source": "Source",
        "variant": "Variant",
        "fidelity_warning": "Warning: product fidelity is not confirmed by a protected layer.",
        "export_ready": "Ready to export: {count}",
        "export_summary": "Saved: {count}; folder: {folder}",
        "regeneration_another_run_active": "Finish the current task in the other mode first.",
        "regeneration_already_running": "Generation is already running.",
        "regeneration_started": "Regenerating selected Pinterest variant.",
        "status_pending": "Waiting for generation",
        "status_success": "Ready",
        "status_failed": "Could not generate",
        "image_unavailable": "Image preview is unavailable",
        "format_title": "Format and model",
        "format_accessible": "Pinterest pin format and model",
        "format_recommendation": "The recommended vertical format is 9:16. You can choose any ratio supported by the model.",
        "processing_title": "Image processing",
        "processing_description": "Shared image-processing settings for Pinterest.",
        "review_description": "Review the image package and cost before explicitly starting it.",
        "project_title": "Work folder",
        "project_description": "Choose a folder for saving results.",
        "prompt_review_title": "Prompt review",
        "prompt_review_description": "Review and edit prompts before generation if needed.",
        "review_title": "Review and run",
    },
}


def _pinterest_text(key: str, *, locale: str = "ru", **values: object) -> str:
    return message_for(f"pinterest.{key}", locale=locale, **values)


def scene_failure_message(*, locale: str = "ru") -> str:
    return message_for("pinterest.error.scene_failed", locale=locale)


def partial_export_message(count: int, *, locale: str = "ru") -> str:
    return message_for("pinterest.status.partial_export", locale=locale, count=count)


@dataclass(frozen=True)
class PinterestCopySuggestions:
    title: str = ""
    subtitle: str = ""
    cta: str = ""


BackgroundGenerator = Callable[[str, int], Image.Image]


@dataclass(frozen=True, slots=True)
class PinVariant:
    """One fixed Pinterest slot, with a protected product composed locally."""

    variant_id: str
    variant_kind: str
    image: Image.Image | None
    source_product_path: str
    scene_prompt: str
    status: str
    retryable: bool
    product_layer_digest: str
    error_code: str = ""
    error_message: str = ""
    product_box: tuple[int, int, int, int] = (0, 0, 1, 1)


def _safe_scene_detail(value: object) -> str:
    return redact_text(str(value or "").strip(), limit=300)


def _scene_prompt(draft: PinterestPinData, product_box: tuple[int, int, int, int]) -> str:
    details = [
        "Create only a Pinterest pin background and environment.",
        f"Reserve the empty product placement area {product_box}.",
        "Do not render any product, packaging, labels, logos, people, or text.",
    ]
    for label, value in (
        ("Environment", draft.background_description),
        ("Style", draft.style),
        ("Palette", draft.color_palette),
    ):
        safe_value = _safe_scene_detail(value)
        if safe_value:
            details.append(f"{label}: {safe_value}.")
    return " ".join(details)


def _failed_scene_variant(
    *,
    variant_id: str,
    product: ProductLayer,
    prompt: str,
    product_box: tuple[int, int, int, int],
    locale: str = "ru",
) -> PinVariant:
    return PinVariant(
        variant_id=variant_id,
        variant_kind="ai_scene",
        image=None,
        source_product_path=product.source_path,
        scene_prompt=prompt,
        status="failed",
        retryable=True,
        product_layer_digest=product_layer_digest(product),
        error_code="background_generation_failed",
        error_message=scene_failure_message(locale=locale),
        product_box=product_box,
    )


def build_pinterest_pin_series(
    draft: PinterestPinData,
    *,
    product: ProductLayer,
    generate_background: BackgroundGenerator | None = None,
    cancelled: Callable[[], bool] | None = None,
    variant_ids: set[str] | frozenset[str] | None = None,
    locale: str = "ru",
) -> tuple[PinVariant, ...]:
    """Build the fixed template/AI-scene series without giving product pixels to AI."""

    if not isinstance(draft, PinterestPinData):
        raise TypeError("draft must be a PinterestPinData")
    if not isinstance(product, ProductLayer):
        raise TypeError("product must be a ProductLayer")

    requested_ids = frozenset(variant_ids) if variant_ids is not None else None
    variants: list[PinVariant] = []
    digest = product_layer_digest(product)
    for index, spec in enumerate(pinterest_template_specs(), start=1):
        variant_id = f"template-{index:02d}"
        if requested_ids is not None and variant_id not in requested_ids:
            continue
        product_box = template_product_box(spec.template_id)
        background = render_template_background(
            title=draft.pin_title,
            subtitle=draft.pin_subtitle,
            cta=draft.pin_cta,
            template_id=spec.template_id,
        )
        image = composite_product(background, product, box=product_box)
        assert_product_pixels_preserved(product.rgba, image, product_box=product_box)
        variants.append(
            PinVariant(
                variant_id=variant_id,
                variant_kind="template",
                image=image,
                source_product_path=product.source_path,
                scene_prompt="",
                status="success",
                retryable=False,
                product_layer_digest=digest,
                product_box=product_box,
            )
        )

    scene_boxes = tuple(template_product_box(spec.template_id) for spec in pinterest_template_specs())
    for index, product_box in enumerate(scene_boxes, start=1):
        variant_id = f"ai-scene-{index:02d}"
        if requested_ids is not None and variant_id not in requested_ids:
            continue
        prompt = _scene_prompt(draft, product_box)
        if generate_background is None or (cancelled is not None and cancelled()):
            variants.append(
                _failed_scene_variant(
                    variant_id=variant_id,
                    product=product,
                    prompt=prompt,
                    product_box=product_box,
                    locale=locale,
                )
            )
            continue
        try:
            background = generate_background(prompt, index)
            if not isinstance(background, Image.Image) or background.size != (1000, 1500):
                raise ValueError("background artifact has an invalid canvas")
            image = composite_product(background, product, box=product_box)
            assert_product_pixels_preserved(product.rgba, image, product_box=product_box)
        except Exception:
            variants.append(
                _failed_scene_variant(
                    variant_id=variant_id,
                    product=product,
                    prompt=prompt,
                    product_box=product_box,
                )
            )
            continue
        variants.append(
            PinVariant(
                variant_id=variant_id,
                variant_kind="ai_scene",
                image=image,
                source_product_path=product.source_path,
                scene_prompt=prompt,
                status="success",
                retryable=False,
                product_layer_digest=digest,
                product_box=product_box,
            )
        )
    return tuple(variants)


class PinterestCopySuggestionService:
    """Return only entered facts; product features are never inferred."""

    def suggest(
        self,
        product_facts: Mapping[str, object],
        *,
        locale: str = "ru",
    ) -> PinterestCopySuggestions:
        del locale
        facts = product_facts if isinstance(product_facts, Mapping) else {}
        return PinterestCopySuggestions(
            title=str(facts.get("title") or "").strip(),
            subtitle=str(facts.get("subtitle") or "").strip(),
            cta=str(facts.get("cta") or "").strip(),
        )


class _PinterestDataAdapter:
    def __init__(self, data: PinterestModeData) -> None:
        self.data = data
        self.operations = ImageOperationData(
            upscale_before=False,
            upscale_after=False,
            unsharp=False,
            remove_background=False,
            edge_shrink=False,
            trim=False,
            export_300_dpi=False,
        )

    @property
    def prompts(self):
        return self.data.prompts

    @prompts.setter
    def prompts(self, value) -> None:
        self.data.prompts = list(value)

    @property
    def prompt_generator(self):
        return PromptGeneratorData()

    @property
    def generation(self) -> GenerationData:
        return self.data.generation

    @generation.setter
    def generation(self, value: GenerationData) -> None:
        self.data.generation = value

    @property
    def pin(self):
        return self.data.pin

    @property
    def results(self):
        return self.data.results

    @results.setter
    def results(self, value) -> None:
        self.data.results = value


def _pinterest_project_adapter(state: ProjectState) -> ProjectState:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    adapter = ProjectState(mode=ProjectMode.CLIPART)
    adapter.common = CommonProjectData.from_dict(state.common.to_dict())
    adapter.common.output_dir = state.output_dir_for_mode(ProjectMode.PINTEREST)
    adapter.common.output_dirs[ProjectMode.CLIPART.value] = adapter.common.output_dir
    if not adapter.common.output_dir and adapter.common.work_dir:
        adapter.common.output_dir = str(Path(adapter.common.work_dir) / "output")
        state.set_output_dir_for_mode(adapter.common.output_dir, ProjectMode.PINTEREST)
    adapter.runtime = state.runtime
    adapter.clipart = _PinterestDataAdapter(state.pinterest)
    return adapter


def estimate_pinterest_cost(state: ProjectState):
    del state
    return CostEstimate(
        request_count=0,
        estimated_usd=0,
        complete=True,
        generation_request_count=0,
        processing_request_count=0,
        generation_usd=0,
        processing_usd=0,
    )


@dataclass(frozen=True, slots=True)
class PinterestPinRunRequest:
    """Pinterest-only run contract consumed by the shared queue."""

    work_dir: str
    product_path: str
    pin: PinterestPinData
    settings: dict[str, Any] = field(repr=False)
    queue_items: tuple[dict[str, str], ...]
    scene_strategy: str = "ai_scene"
    status_message: str = ""
    locale: str = "ru"
    mode: str = "pinterest_pins"
    generate_background: BackgroundGenerator | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    product_layer: ProductLayer | None = field(
        default=None,
        repr=False,
        compare=False,
    )


class PinterestPinOrchestrator:
    """Build protected Pinterest variants without a provider-specific client."""

    def __init__(self) -> None:
        self._product_layers: dict[str, ProductLayer] = {}
        self.product_layer: ProductLayer | None = None

    def build(
        self,
        request: PinterestPinRunRequest,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> tuple[PinVariant, ...]:
        product = request.product_layer or self._product_layers.get(request.product_path)
        if product is None:
            product = load_product_layer(request.product_path)
        self._product_layers[request.product_path] = product
        self.product_layer = product
        requested_ids = {
            str(item.get("variant_id") or "").strip()
            for item in request.queue_items
            if isinstance(item, Mapping)
        }
        generate_background = request.generate_background
        if request.scene_strategy == "safe_template":
            def generate_requested_background(_: str, slot_index: int) -> Image.Image:
                return render_template_background(
                    title=request.pin.pin_title,
                    subtitle=request.pin.pin_subtitle,
                    cta=request.pin.pin_cta,
                    template_id=pinterest_template_specs()[slot_index - 1].template_id,
                )
        elif generate_background is not None:
            def generate_requested_background(prompt: str, slot_index: int) -> Image.Image:
                if f"ai-scene-{slot_index:02d}" not in requested_ids:
                    raise ValueError("AI scene is not selected for this run")
                return generate_background(prompt, slot_index)
        else:
            generate_requested_background = None
        variants = build_pinterest_pin_series(
            request.pin,
            product=product,
            generate_background=generate_requested_background,
            cancelled=cancelled,
            variant_ids=requested_ids,
            locale=request.locale,
        )
        variants_by_id = {variant.variant_id: variant for variant in variants}
        try:
            return tuple(
                variants_by_id[str(item["variant_id"])]
                for item in request.queue_items
            )
        except (KeyError, TypeError) as error:
            raise ValueError("Pinterest queue item is invalid") from error

    @staticmethod
    def output_path(request: PinterestPinRunRequest, variant: PinVariant) -> Path:
        output_dir = Path(str(request.settings["output_dir"])).resolve(strict=False)
        return output_dir / f"pinterest-{variant.variant_id}.png"


class PinterestPinWorkerAdapter(QThread):
    """Expose Pinterest orchestration through the existing worker signal contract."""

    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(
        self,
        request: PinterestPinRunRequest,
        *,
        orchestrator: PinterestPinOrchestrator | None = None,
    ) -> None:
        super().__init__()
        self.request = request
        self.orchestrator = orchestrator or PinterestPinOrchestrator()
        self.variants: tuple[PinVariant, ...] = ()
        self.output_paths: dict[str, str] = {}
        self.product_layer: ProductLayer | None = None
        self._cancelled = threading.Event()
        self._stop_after_current = threading.Event()

    def stop(self) -> None:
        self._cancelled.set()

    def request_stop_after_current(self) -> None:
        self._stop_after_current.set()

    def run(self) -> None:
        self._run()

    def _run(self) -> None:
        try:
            self.item_progress.emit(
                {
                    "item_index": 1,
                    "total_items": len(self.request.queue_items),
                    "stage": "pinterest_orchestration",
                    "status": "running",
                    "percent": 0,
                    "indeterminate": True,
                }
            )
            self.variants = self.orchestrator.build(
                self.request,
                cancelled=self._cancelled.is_set,
            )
            self.product_layer = getattr(self.orchestrator, "product_layer", None)
            cancel_remaining = False
            for index, variant in enumerate(self.variants, start=1):
                if self._cancelled.is_set() or cancel_remaining:
                    self.item_progress.emit(
                        {
                            "item_index": index,
                            "total_items": len(self.variants),
                            "stage": "pinterest_pin",
                            "status": "cancelled",
                            "message": message_for("pinterest.status.run_cancelled", locale=self.request.locale),
                        }
                    )
                    continue
                self.item_progress.emit(
                    {
                        "item_index": index,
                        "total_items": len(self.variants),
                        "stage": "pinterest_pin",
                        "status": "running",
                        "percent": 0,
                    }
                )
                if variant.status == "success" and variant.image is not None:
                    try:
                        output_path = save_pin(
                            variant.image,
                            str(self.orchestrator.output_path(self.request, variant)),
                            format="PNG",
                        )
                    except Exception:
                        self.item_progress.emit(
                            {
                                "item_index": index,
                                "total_items": len(self.variants),
                                "stage": "export",
                                "status": "failed",
                                "message": message_for("pinterest.error.pin_export_failed", locale=self.request.locale),
                            }
                        )
                    else:
                        self.output_paths[variant.variant_id] = output_path
                        self.item_progress.emit(
                            {
                                "item_index": index,
                                "total_items": len(self.variants),
                                "stage": "export",
                                "status": "succeeded",
                                "output_path": output_path,
                                "percent": 100,
                            }
                        )
                else:
                    self.item_progress.emit(
                        {
                            "item_index": index,
                            "total_items": len(self.variants),
                            "stage": "background_generation",
                            "status": "failed",
                            "message": variant.error_message,
                        }
                    )
                self.progress_value.emit(round(index * 100 / len(self.variants)))
                if self._stop_after_current.is_set():
                    cancel_remaining = True
        except Exception:
            self.variants = ()
            self.output_paths.clear()
            for index, _ in enumerate(self.request.queue_items, start=1):
                self.item_progress.emit(
                    {
                        "item_index": index,
                        "total_items": len(self.request.queue_items),
                        "stage": "pinterest_pin",
                        "status": "failed",
                        "message": message_for("pinterest.error.pin_prepare_failed", locale=self.request.locale),
                    }
                )
            self.error.emit(message_for("pinterest.error.pin_prepare_failed", locale=self.request.locale))
        finally:
            self.finished.emit(message_for("pinterest.status.run_finished", locale=self.request.locale))


def build_pinterest_run_request(
    state: ProjectState,
    runtime_settings: Mapping[str, Any] | None = None,
    *,
    locale: str = "ru",
    provider_capabilities: Mapping[str, object] | None = None,
) -> PinterestPinRunRequest:
    del runtime_settings
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    if state.mode is not ProjectMode.PINTEREST:
        raise ClipartFlowError(message_for("pinterest.error.run_wrong_mode", locale=locale))
    work_dir = Path(state.common.work_dir).expanduser()
    if not work_dir.is_dir():
        raise ClipartFlowError(message_for("pinterest.error.work_folder", locale=locale))
    pin = PinterestPinData.from_dict(state.pinterest.pin.to_dict())
    if not pin.product_paths:
        raise ClipartFlowError(message_for("pinterest.error.missing_product", locale=locale))
    product_path = Path(pin.product_paths[pin.selected_product_index]).expanduser()
    if not product_path.is_file():
        raise ClipartFlowError(message_for("pinterest.error.product_unavailable", locale=locale))
    output_dir = state.output_dir_for_mode(ProjectMode.PINTEREST)
    if not output_dir:
        output_dir = str(work_dir / "output")
        state.set_output_dir_for_mode(output_dir, ProjectMode.PINTEREST)
    output_path = Path(output_dir).expanduser()
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise ClipartFlowError(message_for("pinterest.error.output_folder", locale=locale))
    capabilities = provider_capabilities if isinstance(provider_capabilities, Mapping) else {}
    supports_scene = bool(capabilities.get("background_generation", True))
    protects_product = bool(capabilities.get("protected_product", True))
    scene_strategy = "ai_scene" if supports_scene and protects_product else "safe_template"
    status_message = (
        ""
        if scene_strategy == "ai_scene"
        else message_for("pinterest.status.safe_template_fallback", locale=locale)
    )
    queue_items = tuple(
        {
            "variant_id": f"template-{index:02d}",
            "variant_kind": "template",
        }
        for index in range(1, PINTEREST_TEMPLATE_COUNT + 1)
    ) + tuple(
        {
            "variant_id": f"ai-scene-{index:02d}",
            "variant_kind": "ai_scene",
        }
        for index in range(1, PINTEREST_AI_SCENE_COUNT + 1)
    )
    return PinterestPinRunRequest(
        work_dir=str(work_dir),
        product_path=str(product_path),
        pin=pin,
        settings={"output_dir": str(output_path)},
        queue_items=queue_items,
        scene_strategy=scene_strategy,
        status_message=status_message,
        locale=normalize_locale(locale),
    )


def _pinterest_export_format(source_path: str) -> tuple[str, str]:
    suffix = Path(source_path).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "JPG", ".jpg"
    if suffix == ".png":
        return "PNG", ".png"
    raise ValueError("Pinterest export source must be JPG or PNG")


def _pinterest_export_target(
    folder: Path,
    *,
    product_path: str,
    variant_id: str,
    suffix: str,
) -> Path:
    product_stem = re.sub(r"[^A-Za-z0-9]+", "_", Path(product_path).stem).strip("_")
    safe_product = product_stem or "product"
    variant_prefix, separator, variant_number = variant_id.rpartition("-")
    if not separator or not variant_prefix or not variant_number.isdigit():
        raise ValueError("Pinterest variant has an invalid export name")
    safe_variant = f"{variant_prefix}_{variant_number}"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{safe_product}_{safe_variant}{suffix}"
    collision_index = 2
    while True:
        try:
            descriptor = os.open(
                target,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            target = folder / f"{safe_product}_{safe_variant}-{collision_index:02d}{suffix}"
            collision_index += 1
            continue
        try:
            os.close(descriptor)
        except OSError:
            try:
                target.unlink()
            except OSError:
                pass
            raise
        return target


class PinterestProductInputPage(_ScrollableStepPage):
    """Pinterest product and destination input, separate from pin copy."""

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        locale: str = "ru",
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(
            _pinterest_text("product_input_title", locale=self.locale),
            _pinterest_text("product_input_description", locale=self.locale),
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self._syncing = False

        form = QFormLayout()
        product_widget = QWidget()
        product_layout = QHBoxLayout(product_widget)
        product_layout.setContentsMargins(0, 0, 0, 0)
        self.products_label = QLabel()
        self.products_label.setWordWrap(True)
        self.products_label.setProperty("v3Small", True)
        self.add_products_button = V3Button(
            _pinterest_text("add_products", locale=self.locale),
            ButtonVariant.SECONDARY,
        )
        self.add_products_button.clicked.connect(self._browse_products)
        product_layout.addWidget(self.products_label, 1)
        product_layout.addWidget(self.add_products_button)
        form.addRow(_pinterest_text("products", locale=self.locale), product_widget)

        self.selected_product_combo = QComboBox()
        self.selected_product_combo.setAccessibleName(
            _pinterest_text("selected_product", locale=self.locale)
        )
        form.addRow(
            _pinterest_text("selected_product", locale=self.locale),
            self.selected_product_combo,
        )
        output_widget = QWidget()
        output_layout = QHBoxLayout(output_widget)
        output_layout.setContentsMargins(0, 0, 0, 0)
        self.output_dir_edit = QLineEdit()
        self.output_dir_edit.setAccessibleName(
            _pinterest_text("output_folder", locale=self.locale)
        )
        self.output_browse_button = V3Button(
            _pinterest_text("choose", locale=self.locale), ButtonVariant.SECONDARY
        )
        self.output_browse_button.clicked.connect(self._browse_output_folder)
        output_layout.addWidget(self.output_dir_edit, 1)
        output_layout.addWidget(self.output_browse_button)
        form.addRow(_pinterest_text("output_folder", locale=self.locale), output_widget)

        container = QWidget()
        container.setLayout(form)
        self.add_widget(container)
        self.output_dir_edit.textChanged.connect(self._sync)
        self.selected_product_combo.currentIndexChanged.connect(self._sync)
        self.refresh_from_state()

    @property
    def pin(self):
        return self.state.clipart.pin

    def set_product_paths(self, paths: tuple[str, ...] | list[str]) -> None:
        normalized: list[str] = []
        for raw_path in paths:
            path = str(Path(raw_path))
            if path and path not in normalized:
                normalized.append(path)
            if len(normalized) >= MAX_SELECTED_FILES:
                break
        self.pin.product_paths = normalized
        self.pin.selected_product_index = min(
            self.pin.selected_product_index,
            max(0, len(normalized) - 1),
        )
        self.refresh_from_state()
        self.changed()

    def _browse_products(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            _pinterest_text("products", locale=self.locale),
            self.output_dir_edit.text() or str(Path.cwd()),
            "Images (*.png *.jpg *.jpeg *.webp);;All files (*)",
        )
        if selected:
            self.set_product_paths([*self.pin.product_paths, *selected])

    def _browse_output_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(
            self,
            _pinterest_text("output_folder", locale=self.locale),
            self.output_dir_edit.text() or str(Path.cwd()),
        )
        if selected:
            self.output_dir_edit.setText(selected)

    def _sync(self, *_: object) -> None:
        if self._syncing:
            return
        self.pin.selected_product_index = max(0, self.selected_product_combo.currentIndex())
        self.state.set_output_dir_for_mode(
            self.output_dir_edit.text().strip(), ProjectMode.PINTEREST
        )
        self.changed()

    def refresh_from_state(self) -> None:
        self._syncing = True
        try:
            self.selected_product_combo.clear()
            for path in self.pin.product_paths:
                self.selected_product_combo.addItem(Path(path).name, path)
            if self.pin.product_paths:
                self.selected_product_combo.setCurrentIndex(self.pin.selected_product_index)
                self.products_label.setText(str(len(self.pin.product_paths)))
            else:
                self.products_label.setText(
                    _pinterest_text("no_products", locale=self.locale)
                )
            self.output_dir_edit.setText(
                self.state.output_dir_for_mode(ProjectMode.PINTEREST)
            )
        finally:
            self._syncing = False


class PinterestCopyLayoutPage(ClipartPromptInputPage):
    """Pinterest prompt input: ready prompt with references or CSV only."""

    generator_mode = ProjectMode.PINTEREST
    supports_prompt_chroma = False

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        locale: str = "ru",
        advance: Callable[[], Any] | None = None,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(state, changed, advance=advance, tokens=tokens)
        self.card.title_label.setText(
            _pinterest_text("prompt_input_title", locale=self.locale)
        )
        self.card.description_label.setText(
            _pinterest_text("prompt_input_description", locale=self.locale)
        )
        self.setAccessibleName(
            _pinterest_text("prompt_input_title", locale=self.locale)
        )
        self.setAccessibleDescription(
            _pinterest_text("prompt_input_description", locale=self.locale)
        )
        # Pinterest intentionally has no prompt generator: only a ready prompt
        # with optional references or a CSV content batch is accepted.
        self.source_buttons[0].hide()
        self.source_stack.setCurrentIndex(1)
        self.source_combo.setCurrentIndex(1)


class PinterestPromptInputPage(PinterestCopyLayoutPage):
    """Compatibility name for the former copy input page."""


class PinterestProjectPage(ClipartProjectPage):
    """Pinterest-localized shell for the shared project-folder editor."""

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        locale: str = "ru",
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(state, changed, tokens=tokens)
        self._set_pinterest_copy()

    def _set_pinterest_copy(self) -> None:
        title = _pinterest_text("project_title", locale=self.locale)
        description = _pinterest_text("project_description", locale=self.locale)
        self.card.title_label.setText(title)
        self.card.description_label.setText(description)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.work_dir_edit.setAccessibleName(title)
        self.browse_button.setText(_pinterest_text("choose", locale=self.locale))
        self.browse_button.setAccessibleName(
            _pinterest_text("choose", locale=self.locale)
        )


class PinterestPromptReviewPage(ClipartPromptReviewPage):
    """Pinterest-localized shell for the shared prompt-review editor."""

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        locale: str = "ru",
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(state, changed, tokens=tokens)
        title = _pinterest_text("prompt_review_title", locale=self.locale)
        description = _pinterest_text("prompt_review_description", locale=self.locale)
        self.card.title_label.setText(title)
        self.card.description_label.setText(description)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)


class PinterestPinPreviewPage(_ScrollableStepPage):
    """Preview fixed Pinterest slots and delegate selective regeneration."""

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        locale: str = "ru",
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        regenerate_handler: Callable[[str], None] | None = None,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(
            _pinterest_text("preview_title", locale=self.locale),
            _pinterest_text("preview_description", locale=self.locale),
            tokens=tokens,
        )
        self.state = state
        self.changed = changed
        self._regenerate_handler = regenerate_handler
        self.variant_cards: dict[str, QFrame] = {}
        self.grid_widget = QWidget()
        self.grid = QGridLayout(self.grid_widget)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(tokens.space_3)
        self.add_widget(self.grid_widget)
        self.export_button = V3Button(
            _pinterest_text("export", locale=self.locale), ButtonVariant.PRIMARY
        )
        self.export_button.clicked.connect(self._show_export_selection)
        self.add_widget(self.export_button)
        self.export_status_label = QLabel()
        self.export_status_label.setProperty("v3Small", True)
        self.add_widget(self.export_status_label)
        self.refresh_from_state()

    @property
    def pin(self):
        return self.state.clipart.pin

    @property
    def results(self) -> list[PinterestPinResultData]:
        return self.state.clipart.results

    def _selected_product_path(self) -> str:
        if not self.pin.product_paths:
            return ""
        index = min(
            max(0, self.pin.selected_product_index), len(self.pin.product_paths) - 1
        )
        return self.pin.product_paths[index]

    def _ensure_six_slots(self) -> None:
        selected_product = self._selected_product_path()
        existing = {result.variant_id: result for result in self.results}
        slots: list[PinterestPinResultData] = []
        for kind, count in (
            ("template", PINTEREST_TEMPLATE_COUNT),
            ("ai_scene", PINTEREST_AI_SCENE_COUNT),
        ):
            for index in range(1, count + 1):
                variant_id = f"{kind.replace('_', '-')}-{index:02d}"
                result = existing.get(variant_id)
                if result is None:
                    result = PinterestPinResultData(
                        variant_id=variant_id,
                        variant_kind=kind,
                        source_product_path=selected_product,
                    )
                elif result.source_product_path != selected_product:
                    result.source_product_path = selected_product
                slots.append(result)
        self.state.clipart.results = slots

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _status_text(self, status: str) -> str:
        return _pinterest_text(f"status_{status}", locale=self.locale)

    def _rebuild_cards(self) -> None:
        self._clear_grid()
        self.variant_cards = {}
        for index, result in enumerate(self.results):
            card = QFrame()
            card.setProperty("v3Card", True)
            layout = QVBoxLayout(card)
            variant_label = QLabel(
                f"{_pinterest_text('variant', locale=self.locale)}: {result.variant_id}"
            )
            variant_label.setProperty("v3Title", True)
            source_name = Path(result.source_product_path).name if result.source_product_path else "—"
            source_label = QLabel(
                f"{_pinterest_text('source', locale=self.locale)}: {source_name}"
            )
            status = self._status_text(result.status)
            status_label = QLabel(status)
            status_label.setProperty("v3Small", True)
            card_description = "; ".join(
                (variant_label.text(), source_label.text(), status)
            )
            card.setAccessibleName(card_description)
            card.setAccessibleDescription(card_description)
            layout.addWidget(variant_label)
            layout.addWidget(source_label)
            layout.addWidget(status_label)
            if result.status == "success" and result.output_path:
                image_preview = QLabel()
                image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
                pixmap = QPixmap(result.output_path)
                if pixmap.isNull():
                    image_preview.setText(
                        _pinterest_text("image_unavailable", locale=self.locale)
                    )
                else:
                    image_preview.setPixmap(
                        pixmap.scaled(
                            220,
                            280,
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                    )
                image_preview.setAccessibleName(card_description)
                layout.addWidget(image_preview)
            if result.status == "success" and not result.product_layer_digest:
                warning = QLabel(
                    _pinterest_text("fidelity_warning", locale=self.locale)
                )
                warning.setWordWrap(True)
                warning.setProperty("v3Status", True)
                warning.setProperty("state", "warning")
                layout.addWidget(warning)
            accepted = QCheckBox(_pinterest_text("accept", locale=self.locale))
            accepted.setChecked(result.accepted)
            accepted.toggled.connect(
                lambda checked, variant_id=result.variant_id: self.set_variant_accepted(
                    variant_id, checked
                )
            )
            regenerate = V3Button(
                _pinterest_text("regenerate", locale=self.locale),
                ButtonVariant.SECONDARY,
            )
            regenerate.clicked.connect(
                lambda checked=False, variant_id=result.variant_id: self.regenerate_variant(
                    variant_id
                )
            )
            layout.addWidget(accepted)
            layout.addWidget(regenerate)
            self.grid.addWidget(card, index // 2, index % 2)
            self.variant_cards[result.variant_id] = card

    def _find_result(self, variant_id: str) -> PinterestPinResultData:
        for result in self.results:
            if result.variant_id == variant_id:
                return result
        raise ValueError(f"Unknown Pinterest variant: {variant_id}")

    def regenerate_variant(self, variant_id: str) -> None:
        """Regenerate one fixed slot through the owning Pinterest controller."""
        if self._regenerate_handler is not None:
            self._regenerate_handler(variant_id)
            return
        self._mark_variant_for_regeneration(variant_id)

    def _mark_variant_for_regeneration(self, variant_id: str) -> None:
        result = self._find_result(variant_id)
        result.status = "pending"
        result.retryable = True
        result.accepted = False
        result.output_path = ""
        result.product_layer_digest = ""
        result.export_status = "not_exported"
        result.error_code = ""
        result.error_message = ""
        self.changed()
        self.refresh_from_state()

    def set_variant_accepted(self, variant_id: str, accepted: bool) -> None:
        self._find_result(variant_id).accepted = bool(accepted)
        self.changed()
        self.refresh_from_state()

    def export_accepted(self) -> tuple[str, ...]:
        """Save accepted successful variants in the selected Pinterest folder."""
        output_dir = self.state.output_dir_for_mode(ProjectMode.PINTEREST)
        exported: list[str] = []
        if output_dir:
            folder = Path(output_dir).expanduser()
            for result in self.results:
                if not (
                    result.accepted
                    and result.status == "success"
                    and result.output_path
                ):
                    continue
                target: Path | None = None
                try:
                    format_name, suffix = _pinterest_export_format(result.output_path)
                    target = _pinterest_export_target(
                        folder,
                        product_path=result.source_product_path,
                        variant_id=result.variant_id,
                        suffix=suffix,
                    )
                    with Image.open(result.output_path) as source:
                        source.load()
                        exported.append(save_pin(source, str(target), format=format_name))
                except (OSError, RuntimeError, ValueError):
                    if target is not None:
                        try:
                            target.unlink()
                        except OSError:
                            pass
                    result.export_status = "failed"
                else:
                    result.export_status = "exported"
        summary = _pinterest_text(
            "export_summary",
            locale=self.locale,
            count=len(exported),
            folder=str(Path(output_dir).expanduser()) if output_dir else "—",
        )
        if any(result.export_status == "failed" for result in self.results):
            summary = f"{partial_export_message(len(exported), locale=self.locale)} {summary}"
        self.export_status_label.setText(summary)
        self.changed()
        self.refresh_from_state()
        return tuple(exported)

    def _show_export_selection(self) -> None:
        self.export_accepted()

    def refresh_from_state(self) -> None:
        self._ensure_six_slots()
        self._rebuild_cards()


class PinterestFormatModelPage(ClipartGenerationPage):
    allow_shared_text_models = True
    allow_fal_models = True
    shared_generation_settings = False
    shared_reference_format = True
    reference_controls_compact = True
    show_primary_scope = False
    show_model_capabilities = False

    def __init__(
        self,
        state: ProjectState,
        changed: Callable[[], None],
        *,
        locale: str = "ru",
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(state, changed, tokens=tokens)
        self.card.title_label.setText(_pinterest_text("format_title", locale=self.locale))
        self.card.description_label.hide()
        self.setAccessibleName(_pinterest_text("format_accessible", locale=self.locale))
        self.setAccessibleDescription(_pinterest_text("format_accessible", locale=self.locale))
        labels = (
            (_pinterest_text("generation_model", locale=self.locale), self.model_combo),
            (_pinterest_text("generation_ratio", locale=self.locale), self.ratio_combo),
            (_pinterest_text("generation_resolution", locale=self.locale), self.resolution_combo),
            (_pinterest_text("generation_variants", locale=self.locale), self.variants_spin),
        )
        for label, control in labels:
            control.setAccessibleName(label)
        for label in self.findChildren(QLabel):
            replacement = {
                "Модель": _pinterest_text("generation_model", locale=self.locale),
                "Пропорция": _pinterest_text("generation_ratio", locale=self.locale),
                "Разрешение": _pinterest_text("generation_resolution", locale=self.locale),
                "Вариантов на промпт": _pinterest_text("generation_variants", locale=self.locale),
            }.get(label.text())
            if replacement:
                label.setText(replacement)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        super().refresh_from_state()


class PinterestProcessingPage(ProcessingPipelineEditor):
    def __init__(self, state: ProjectState, changed: Callable[[], None], *, locale: str = "ru", tokens: V3DesignTokens = DEFAULT_TOKENS) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(
            state.clipart,
            changed,
            title=_pinterest_text("processing_title", locale=self.locale),
            description=_pinterest_text("processing_description", locale=self.locale),
            include_cleanup=False,
            require_operation=False,
            allowed_operations=workflow_for_mode(ProjectMode.PINTEREST).processing_operations,
            tokens=tokens,
        )


class PinterestReviewRunPage(ClipartReviewRunPage):
    """Pinterest uses the shared prompt-only generation review."""

    def __init__(
        self,
        state: ProjectState,
        *,
        locale: str = "ru",
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        fal_cost_refresh: Callable[[], tuple[float, str]] | None = None,
    ) -> None:
        self.locale = normalize_locale(locale)
        super().__init__(
            state,
            tokens=tokens,
            fal_cost_refresh=fal_cost_refresh,
        )
        self.card.title_label.setText(_pinterest_text("review_title", locale=self.locale))
        self.card.description_label.setText(
            _pinterest_text("review_description", locale=self.locale)
        )
        self.setAccessibleName(_pinterest_text("review_title", locale=self.locale))
        self.setAccessibleDescription(
            _pinterest_text("review_description", locale=self.locale)
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
        provider_capabilities_provider: Callable[[], Mapping[str, object]] | None = None,
        locale: str = "ru",
    ) -> None:
        super().__init__(shell)
        self.shell = shell
        self.locale = normalize_locale(locale)
        from v3_runtime_adapter import runtime_adapter_for

        self.runtime_adapter = runtime_adapter_for(
            runtime_settings_provider, worker_factory
        )
        self.runtime_settings_provider = (
            runtime_settings_provider or self.runtime_adapter.read_settings
        )
        self.worker_factory = worker_factory or self.runtime_adapter.create_worker
        self.authorization_provider = authorization_provider or self._missing_authorization
        self.provider_capabilities_provider = (
            provider_capabilities_provider or self._safe_template_capabilities
        )
        self.worker: Any | None = None
        self._product_layer: ProductLayer | None = None
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
        raise LicenseError(message_for("pinterest.error.authorization_unavailable"))

    @staticmethod
    def _safe_template_capabilities() -> Mapping[str, object]:
        """No Pinterest AI-scene provider is installed, so protect the product locally."""
        return {"background_generation": False, "protected_product": True}

    def _request(self, runtime_settings: Mapping[str, Any]) -> ClipartRunRequest:
        self.adapter_state.common.output_dirs[ProjectMode.CLIPART.value] = (
            self.adapter_state.common.output_dir
        )
        return build_clipart_run_request(self.adapter_state, runtime_settings)

    def start_processing_again(self) -> None:
        self.shell.state.pinterest.prompts.clear()
        self.shell.state.set_step(StepId.PROJECT)
        self.pages[StepId.PROJECT].refresh_from_state()
        self.shell.mark_dirty()

    def _install_pages(self) -> None:
        def changed() -> None:
            self.shell.state.common.work_dir = self.adapter_state.common.work_dir
            self.shell.state.set_output_dir_for_mode(
                self.adapter_state.common.output_dir,
                ProjectMode.PINTEREST,
            )
            self.shell.mark_dirty()

        self.pages.register(
            StepId.PROJECT,
            lambda: PinterestProjectPage(
                self.adapter_state,
                changed,
                locale=self.locale,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROMPTS,
            lambda: PinterestCopyLayoutPage(
                self.adapter_state,
                changed,
                locale=self.locale,
                advance=self.shell.go_next,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PROMPT_REVIEW,
            lambda: PinterestPromptReviewPage(
                self.adapter_state,
                changed,
                locale=self.locale,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.PIN_FORMAT_MODEL,
            lambda: PinterestFormatModelPage(
                self.adapter_state,
                changed,
                locale=self.locale,
                tokens=self.shell.tokens,
            ),
        )
        self.pages.register(
            StepId.REVIEW_RUN,
            lambda: PinterestReviewRunPage(
                self.adapter_state,
                locale=self.locale,
                tokens=self.shell.tokens,
                fal_cost_refresh=self._refresh_fal_cost,
            ),
        )
        # Materialize the shared results widget only when Pinterest reaches
        # the terminal step. This avoids replacing the default Qt page while
        # another mode is still being switched away from its results screen.
        self.pages.register(StepId.RESULTS, lambda: self.run_queue.page)
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
                raise ClipartFlowError(_pinterest_text("error.runtime_settings", locale=self.locale))
            runtime_settings = dict(runtime_settings)
            runtime_settings["fal_cost_confirmed"] = self.review_page.fal_cost_confirmed()
            request = self._request(runtime_settings)
            missing = missing_runtime_requirements(request)
        except (ClipartFlowError, OSError, TypeError, ValueError) as error:
            self.review_page.set_preflight_status(str(error)[:500], ready=False)
            return
        if missing:
            self.review_page.set_preflight_status(
                "Укажите в настройках: " + ", ".join(missing), ready=False
            )
        else:
            self.review_page.set_preflight_status(
                _pinterest_text("status.preflight_ready", locale=self.locale),
                ready=True,
            )

    def _run_requested(self, mode: str) -> None:
        if mode == ProjectMode.PINTEREST.value:
            self.start()

    def _refresh_fal_cost(self) -> tuple[float, str]:
        runtime_settings = self.runtime_settings_provider()
        if not isinstance(runtime_settings, Mapping):
            raise ClipartFlowError("Настройки запуска повреждены")
        api_key = str(runtime_settings.get("fal_api_key") or "").strip()
        if not api_key:
            raise ClipartFlowError("Добавьте Fal.ai API Key в настройках API")
        quantities = fal_endpoint_quantities(self.adapter_state)
        if not quantities:
            raise ClipartFlowError("В текущем запуске нет операций Fal.ai")
        return estimate_fal_cost(api_key, quantities)

    def start(self) -> ClipartRunRequest | None:
        if self.shell.another_run_is_active(self):
            message = _pinterest_text("regeneration_another_run_active", locale=self.locale)
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        if self.worker is not None and self.runtime_adapter.is_running(self.worker):
            message = _pinterest_text("regeneration_already_running", locale=self.locale)
            self.review_page.set_run_status(message, error=True)
            self.error.emit(message)
            return None
        try:
            runtime_settings = self.runtime_settings_provider()
            if not isinstance(runtime_settings, Mapping):
                raise ClipartFlowError(_pinterest_text("error.runtime_settings", locale=self.locale))
            runtime_settings = dict(runtime_settings)
            runtime_settings["fal_cost_confirmed"] = self.review_page.fal_cost_confirmed()
            request = self._request(runtime_settings)
            self._runtime_settings = runtime_settings
            missing = missing_runtime_requirements(request)
            if missing:
                raise ClipartFlowError(
                    "Укажите в настройках: " + ", ".join(missing)
                )
            self.authorization_provider()
            worker = self.runtime_adapter.create_worker(**request.worker_kwargs())
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
        message = "Запуск передан существующему pipeline 2.0"
        self.review_page.set_run_status(message)
        self.started.emit(request)
        return request

    def regenerate_variant(self, variant_id: str) -> PinterestPinRunRequest | None:
        """Start one selected Pinterest slot without resetting the six-slot preview."""
        if self.shell.another_run_is_active(self):
            self.error.emit(
                _pinterest_text(
                    "regeneration_another_run_active",
                    locale=self.locale,
                )
            )
            return None
        if self.worker is not None and self.runtime_adapter.is_running(self.worker):
            self.error.emit(
                _pinterest_text(
                    "regeneration_already_running",
                    locale=self.locale,
                )
            )
            return None
        preview = self.pages[StepId.RESULTS]
        if not isinstance(preview, PinterestPinPreviewPage):
            raise RuntimeError("Pinterest preview page is not installed")
        result = preview._find_result(variant_id)
        try:
            runtime_settings = self.runtime_settings_provider()
            if not isinstance(runtime_settings, Mapping):
                raise ClipartFlowError(_pinterest_text("error.runtime_settings", locale=self.locale))
            request = self._request(runtime_settings)
            cached_product = self._product_layer
            if cached_product is not None and cached_product.source_path != request.product_path:
                cached_product = None
            request = replace(
                request,
                queue_items=(
                    {
                        "variant_id": result.variant_id,
                        "variant_kind": result.variant_kind,
                    },
                ),
                product_layer=cached_product,
            )
            self._runtime_settings = runtime_settings
            self.authorization_provider()
            worker = self.create_worker_for_request(request)
        except (ClipartFlowError, LicenseError, OSError, TypeError, ValueError) as error:
            self.error.emit(_safe_runtime_error(error, locals().get("runtime_settings")))
            return None

        preview._mark_variant_for_regeneration(variant_id)
        self.worker = worker
        self.run_queue.start_new(request)
        self.run_queue.connect_worker(worker)
        self.runtime_adapter.start(worker)
        self.review_page.set_run_status(
            _pinterest_text("regeneration_started", locale=self.locale)
        )
        self.started.emit(request)
        return request

    def _reset_preview_results_for_new_run(self) -> None:
        """Discard result-bound state only after a replacement run can start."""
        preview = self.pages[StepId.RESULTS]
        if not isinstance(preview, PinterestPinPreviewPage):
            raise RuntimeError("Pinterest preview page is not installed")
        preview.refresh_from_state()
        for result in preview.results:
            result.status = "pending"
            result.retryable = False
            result.accepted = False
            result.output_path = ""
            result.product_layer_digest = ""
            result.export_status = "not_exported"
            result.error_code = ""
            result.error_message = ""
        preview.refresh_from_state()

    def stop(self) -> None:
        if self.worker is not None:
            self.runtime_adapter.stop(self.worker)

    def _sync_preview_results_from_queue(self) -> None:
        """Project the dedicated Pinterest queue into its fixed result slots."""
        session = self.run_queue.session
        if session is None:
            return
        preview = self.pages[StepId.RESULTS]
        if not isinstance(preview, PinterestPinPreviewPage):
            raise RuntimeError("Pinterest preview page is not installed")
        preview.refresh_from_state()
        from v3_run_queue import RunItemStatus

        variants = (
            self.worker.variants
            if isinstance(self.worker, PinterestPinWorkerAdapter)
            else ()
        )
        if isinstance(self.worker, PinterestPinWorkerAdapter):
            product_layer = self.worker.product_layer
            if product_layer is not None:
                self._product_layer = product_layer
        variants_by_id = {variant.variant_id: variant for variant in variants}
        requested_variant_ids = {
            str(item.get("variant_id") or "").strip()
            for item in (
                self.worker.request.queue_items
                if isinstance(self.worker, PinterestPinWorkerAdapter)
                else ()
            )
            if isinstance(item, Mapping)
        }
        output_paths = (
            self.worker.output_paths
            if isinstance(self.worker, PinterestPinWorkerAdapter)
            else {}
        )
        items_by_variant_id = {
            str(item.payload.get("variant_id") or ""): item
            for item in session.items
            if isinstance(item.payload, dict)
        }
        for result in preview.results:
            if result.variant_id not in requested_variant_ids:
                continue
            item = items_by_variant_id.get(result.variant_id)
            variant = variants_by_id.get(result.variant_id)
            if variant is not None:
                result.variant_id = variant.variant_id
                result.variant_kind = variant.variant_kind
                result.source_product_path = variant.source_product_path
                result.product_layer_digest = variant.product_layer_digest
            if (
                item is not None
                and item.status is RunItemStatus.SUCCEEDED
                and variant is not None
                and variant.status == "success"
            ):
                result.status = "success"
                result.output_path = output_paths.get(variant.variant_id, item.output_path)
                result.retryable = False
                result.export_status = "not_exported"
                result.error_code = ""
                result.error_message = ""
                continue
            result.status = "failed"
            result.output_path = ""
            result.accepted = False
            result.retryable = True
            result.export_status = "not_exported"
            result.error_code = (
                variant.error_code
                if variant is not None and variant.error_code
                else "pin_generation_failed"
            )
            result.error_message = PinterestPinResultData(error_code=result.error_code).error_message
        preview.refresh_from_state()
        self.shell.mark_dirty()

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
    provider_capabilities_provider: Callable[[], Mapping[str, object]] | None = None,
    locale: str = "ru",
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
        provider_capabilities_provider=provider_capabilities_provider,
        locale=locale,
    )
    shell.pinterest_flow_controller = controller
    return controller
