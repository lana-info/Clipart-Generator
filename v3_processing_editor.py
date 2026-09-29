from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from v3_project_state import ImageOperationData, ProjectMode, ProjectState
from v3_image_processing_ui import (
    CLEANUP_OPERATION_LABELS, ProcessingPipelineEditor, RunPlanBuilder,
    UPSCALE_AFTER_UI_ENABLED, configure_unavailable_synthid, processing_pipeline_steps,
)

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
    "sharp_cutout": ProcessingRecipe(
        key="sharp_cutout",
        title="Удалить фон с чёткими краями",
        description="Локально, без апскейла и обрезки.",
        operations=_operations(
            remove_background=True,
            remove_background_provider="local_rembg",
            local_rembg_model="u2net",
            local_rembg_edge_quality="cutout",
        ),
    ),
    "prepare_clipart": ProcessingRecipe(
        key="prepare_clipart",
        title="Подготовить клипарт",
        description="Подготовка прозрачного фона, очистка края и trim.",
        operations=_operations(
            upscale_before=True,
            remove_background=True,
            remove_background_provider="local_rembg",
            edge_shrink=True,
            trim=True,
            export_300_dpi=True,
        ),
    ),
    "metadata_cleanup": ProcessingRecipe(
        key="metadata_cleanup",
        title="Очистить служебные метаданные",
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
    "export_300_dpi": ProcessingRecipe(
        key="export_300_dpi",
        title="Экспорт 300 DPI",
        description="Сохранить изображение с параметрами для печати 300 DPI.",
        operations=_operations(export_300_dpi=True),
    ),
    "custom": ProcessingRecipe(
        key="custom",
        title="Свой рецепт",
        description="Настройки не меняются; операции выбираются вручную.",
        operations=None,
    ),
}

def _processing_data(state: Any):
    scope = getattr(state, "scope", None)
    if scope is not None:
        if scope is not ProjectMode.PROCESSING:
            raise ValueError("Processing recipe state is outside processing scope")
        return state.data
    try:
        return state.processing
    except AttributeError as exc:
        raise TypeError("state must expose processing workflow data") from exc


def apply_processing_recipe(state: Any, recipe: str) -> None:
    if recipe == "check_cleanup":
        recipe = "metadata_cleanup"
    if recipe not in PROCESSING_RECIPES:
        raise ValueError("Неизвестный рецепт обработки")
    data = _processing_data(state)
    data.recipe = recipe
    preset = PROCESSING_RECIPES[recipe].operations
    if preset is None:
        return
    current = data.operations
    for name in ImageOperationData.__dataclass_fields__:
        setattr(current, name, getattr(preset, name))
