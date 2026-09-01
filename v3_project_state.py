from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field, fields as dataclass_fields
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from chroma_key import KEY_COLORS
from v3_provider_registry import (
    FAL_BRIA_UPSCALE_MODEL_ID,
    FAL_TOPAZ_TRANSPARENT_MODEL_ID,
    KIE_TOPAZ_MODEL_ID,
    normalize_fal_upscale_model,
    normalize_fal_upscale_factor,
    normalize_kie_upscale_model,
    normalize_topaz_upscale_factor,
    upscale_model_preserves_alpha,
)


PROJECT_STATE_SCHEMA_VERSION = 1
MAX_DRAFT_BYTES = 2 * 1024 * 1024
MAX_PROMPT_ENTRIES = 5000
MAX_REFERENCES_PER_PROMPT = 5
MAX_PROMPT_GENERATOR_ITEMS = 500
MAX_PROMPT_GENERATOR_TEXT_LENGTH = 4000
MAX_PROMPT_SERIES_COUNT = 500
MAX_CHROMA_KEY_MATERIALS = 3
MAX_SELECTED_FILES = 10000
MAX_TEXT_LENGTH = 20000
PINTEREST_CANVAS_WIDTH = 1000
PINTEREST_CANVAS_HEIGHT = 1500
PINTEREST_TEMPLATE_COUNT = 3
PINTEREST_AI_SCENE_COUNT = 3
MAX_PIN_RESULTS = PINTEREST_TEMPLATE_COUNT + PINTEREST_AI_SCENE_COUNT
_CHROMA_KEY_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")


class ProjectStateError(ValueError):
    pass


class ProjectStateValidationError(ProjectStateError):
    pass


class ProjectMode(str, Enum):
    CLIPART = "clipart"
    PINTEREST = "pinterest"
    PROCESSING = "processing"


class StepId(str, Enum):
    PROJECT = "project"
    PROMPTS = "prompts"
    PROMPT_REVIEW = "prompt_review"
    GENERATION = "generation"
    PROCESSING_OPTIONS = "processing_options"
    PIN_FORMAT_MODEL = "pin_format_model"
    FILES = "files"
    GOAL = "goal"
    PIPELINE = "pipeline"
    EVIDENCE = "evidence"
    REVIEW_RUN = "review_run"
    RESULTS = "results"
    TRANSPARENCY = "transparency"


ROUTES: dict[ProjectMode, tuple[StepId, ...]] = {
    ProjectMode.CLIPART: (
        StepId.PROJECT,
        StepId.PROMPTS,
        StepId.PROMPT_REVIEW,
        StepId.GENERATION,
        StepId.PROCESSING_OPTIONS,
        StepId.REVIEW_RUN,
        StepId.RESULTS,
        StepId.TRANSPARENCY,
    ),
    ProjectMode.PINTEREST: (
        StepId.PROJECT,
        StepId.PROMPTS,
        StepId.PROMPT_REVIEW,
        StepId.PIN_FORMAT_MODEL,
        StepId.REVIEW_RUN,
        StepId.RESULTS,
    ),
    ProjectMode.PROCESSING: (
        StepId.FILES,
        StepId.GOAL,
        StepId.PIPELINE,
        StepId.REVIEW_RUN,
        StepId.RESULTS,
        StepId.TRANSPARENCY,
    ),
}


def route_for_mode(mode: ProjectMode | str) -> tuple[StepId, ...]:
    try:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    except (TypeError, ValueError) as error:
        raise ProjectStateError(f"Unsupported project mode: {mode!r}") from error
    return ROUTES[normalized]


def _text(value: Any, *, limit: int = MAX_TEXT_LENGTH) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        return ""
    return str(value).strip()[:limit]


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, result))


def _bounded_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, result))


def _boolean(value: Any, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    return default


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[str] = []
    for item in value:
        normalized = _text(item)
        if normalized:
            result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _references(value: Any) -> list[str]:
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                decoded = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                decoded = None
            if isinstance(decoded, list):
                value = decoded
            else:
                value = [raw]
        else:
            value = [raw]
    return _string_list(value, limit=MAX_REFERENCES_PER_PROMPT)


@dataclass
class PromptEntry:
    prompt: str = ""
    references: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.prompt = _text(self.prompt)
        self.references = _references(self.references)

    def to_dict(self) -> dict[str, Any]:
        return {"prompt": self.prompt, "references": list(self.references)}

    @classmethod
    def from_value(cls, value: Any) -> PromptEntry | None:
        if isinstance(value, str):
            prompt = _text(value)
            return cls(prompt=prompt) if prompt else None
        if not isinstance(value, Mapping):
            return None
        entry = cls(
            prompt=value.get("prompt", ""),
            references=_references(value.get("references", [])),
        )
        return entry if entry.prompt or entry.references else None


@dataclass
class PromptGeneratorData:
    theme: str = ""
    subjects: list[str] = field(default_factory=list)
    variations: list[str] = field(default_factory=list)
    style: str = ""
    palette: str = ""
    composition: str = ""
    background: str = ""
    consistency: str = ""
    restrictions: list[str] = field(default_factory=list)
    chroma_key_enabled: bool = False
    chroma_key_color: str = "blue"
    chroma_key_custom_color: str = "#0000FF"
    chroma_key_materials: list[str] = field(default_factory=list)
    # Kept in the draft schema for backward compatibility with 3.0.5 files.
    # New prompt series use the object × variation combinations instead.
    count: int = 12

    def __post_init__(self) -> None:
        self.theme = _text(self.theme, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        self.subjects = _string_list(
            self.subjects,
            limit=MAX_PROMPT_GENERATOR_ITEMS,
        )
        self.variations = _string_list(
            self.variations,
            limit=MAX_PROMPT_GENERATOR_ITEMS,
        )
        self.style = _text(self.style, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        self.palette = _text(
            self.palette, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH
        )
        self.composition = _text(
            self.composition, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH
        )
        self.background = _text(
            self.background, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH
        )
        self.consistency = _text(
            self.consistency, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH
        )
        self.restrictions = _string_list(
            self.restrictions,
            limit=MAX_PROMPT_GENERATOR_ITEMS,
        )
        self.chroma_key_enabled = _boolean(self.chroma_key_enabled, default=False)
        self.chroma_key_color = _text(self.chroma_key_color, limit=20).lower()
        if self.chroma_key_color not in KEY_COLORS:
            self.chroma_key_color = "blue"
        self.chroma_key_custom_color = _text(self.chroma_key_custom_color, limit=20) or "#0000FF"
        allowed_materials = {
            "watercolor", "thin_leaves", "conifer_needles", "metal",
            "ribbon_satin",
        }
        self.chroma_key_materials = [
            material for material in _string_list(self.chroma_key_materials, limit=7)
            if material in allowed_materials
        ][:MAX_CHROMA_KEY_MATERIALS]
        self.count = _bounded_int(
            self.count,
            default=12,
            minimum=1,
            maximum=MAX_PROMPT_SERIES_COUNT,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "subjects": list(self.subjects),
            "variations": list(self.variations),
            "style": self.style,
            "palette": self.palette,
            "composition": self.composition,
            "background": self.background,
            "consistency": self.consistency,
            "restrictions": list(self.restrictions),
            "chroma_key_enabled": self.chroma_key_enabled,
            "chroma_key_color": self.chroma_key_color,
            "chroma_key_custom_color": self.chroma_key_custom_color,
            "chroma_key_materials": list(self.chroma_key_materials),
            "count": self.count,
        }

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        defaults: PromptGeneratorData | None = None,
    ) -> PromptGeneratorData:
        data = value if isinstance(value, Mapping) else {}
        base = defaults if defaults is not None else cls()
        return cls(
            theme=data.get("theme", base.theme),
            subjects=data.get("subjects", base.subjects),
            variations=data.get("variations", base.variations),
            style=data.get("style", base.style),
            palette=data.get("palette", base.palette),
            composition=data.get("composition", base.composition),
            background=data.get("background", base.background),
            consistency=data.get("consistency", base.consistency),
            restrictions=data.get("restrictions", base.restrictions),
            chroma_key_enabled=data.get("chroma_key_enabled", base.chroma_key_enabled),
            chroma_key_color=data.get("chroma_key_color", base.chroma_key_color),
            chroma_key_custom_color=data.get("chroma_key_custom_color", base.chroma_key_custom_color),
            chroma_key_materials=data.get("chroma_key_materials", base.chroma_key_materials),
            count=data.get("count", base.count),
        )


def clipart_prompt_generator_defaults() -> PromptGeneratorData:
    return PromptGeneratorData()


def pinterest_prompt_generator_defaults() -> PromptGeneratorData:
    return PromptGeneratorData()


def _prompt_entries(value: Any) -> list[PromptEntry]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    result: list[PromptEntry] = []
    for item in value:
        entry = PromptEntry.from_value(item)
        if entry is not None:
            result.append(entry)
        if len(result) >= MAX_PROMPT_ENTRIES:
            break
    return result

@dataclass
class RuntimeData:
    retries: int = 3
    timeout: int = 60
    generation_wait_timeout: int = 300
    status_poll_interval: float = 20.0
    kie_upload_path: str = "clipart-generator"

    def __post_init__(self) -> None:
        self.retries = _bounded_int(self.retries, default=3, minimum=0, maximum=10)
        self.timeout = _bounded_int(self.timeout, default=60, minimum=10, maximum=600)
        self.generation_wait_timeout = _bounded_int(
            self.generation_wait_timeout,
            default=300,
            minimum=120,
            maximum=3600,
        )
        self.status_poll_interval = _bounded_float(
            self.status_poll_interval,
            default=20.0,
            minimum=5.0,
            maximum=60.0,
        )
        self.kie_upload_path = _text(
            self.kie_upload_path,
            limit=500,
        ) or "clipart-generator"

    def to_dict(self) -> dict[str, Any]:
        return {
            "retries": self.retries,
            "timeout": self.timeout,
            "generation_wait_timeout": self.generation_wait_timeout,
            "status_poll_interval": self.status_poll_interval,
            "kie_upload_path": self.kie_upload_path,
        }

    @classmethod
    def from_dict(cls, value: Any) -> RuntimeData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            retries=data.get("retries", 3),
            timeout=data.get("timeout", 60),
            generation_wait_timeout=data.get("generation_wait_timeout", 300),
            status_poll_interval=data.get("status_poll_interval", 20.0),
            kie_upload_path=data.get("kie_upload_path", "clipart-generator"),
        )


@dataclass
class CommonProjectData:
    project_name: str = ""
    work_dir: str = ""
    output_dir: str = ""
    output_dirs: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.project_name = _text(self.project_name, limit=200)
        self.work_dir = _text(self.work_dir)
        self.output_dir = _text(self.output_dir)
        self.output_dirs = {
            str(key): _text(value)
            for key, value in (self.output_dirs or {}).items()
            if str(key) in {mode.value for mode in ProjectMode}
        }

    def to_dict(self) -> dict[str, str]:
        return {
            "project_name": self.project_name,
            "work_dir": self.work_dir,
            "output_dir": self.output_dir,
            "output_dirs": dict(self.output_dirs),
        }

    @classmethod
    def from_dict(cls, value: Any) -> CommonProjectData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            project_name=data.get("project_name", ""),
            work_dir=data.get("work_dir", ""),
            output_dir=data.get("output_dir", ""),
            output_dirs=data.get("output_dirs", {}),
        )


@dataclass
class GenerationData:
    model: str = "gpt-image/1.5-text-to-image"
    ratio: str = "1:1"
    resolution: str = "1K"
    reference_model: str = "gpt-image/1.5-image-to-image"
    reference_ratio: str = "1:1"
    reference_resolution: str = "1K"
    variants: int = 1

    def __post_init__(self) -> None:
        self.model = _text(self.model, limit=200)
        self.ratio = _text(self.ratio, limit=20)
        self.resolution = _text(self.resolution, limit=20)
        self.reference_model = _text(self.reference_model, limit=200)
        self.reference_ratio = _text(self.reference_ratio, limit=20)
        self.reference_resolution = _text(self.reference_resolution, limit=20)
        self.variants = _bounded_int(
            self.variants,
            default=1,
            minimum=1,
            maximum=100,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "ratio": self.ratio,
            "resolution": self.resolution,
            "reference_model": self.reference_model,
            "reference_ratio": self.reference_ratio,
            "reference_resolution": self.reference_resolution,
            "variants": self.variants,
        }

    @classmethod
    def from_dict(
        cls,
        value: Any,
        *,
        default_ratio: str = "1:1",
    ) -> GenerationData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            model=data.get("model", "gpt-image/1.5-text-to-image"),
            ratio=data.get("ratio", default_ratio),
            resolution=data.get("resolution", "1K"),
            reference_model=data.get(
                "reference_model",
                "gpt-image/1.5-image-to-image",
            ),
            reference_ratio=data.get("reference_ratio", "1:1"),
            reference_resolution=data.get("reference_resolution", "1K"),
            variants=data.get("variants", 1),
        )

@dataclass
class ImageOperationData:
    visible_mark_cleanup: bool = False
    visible_mark_cleanup_mode: str = "gemini_auto"
    invisible_watermark_cleanup: bool = False
    upscale_before: bool = True
    upscale_before_provider: str = "kie"
    upscale_after: bool = False
    upscale_after_provider: str = "fal"
    upscale_factor: int = 4
    kie_upscale_model: str = KIE_TOPAZ_MODEL_ID
    kie_upscale_after_model: str = KIE_TOPAZ_MODEL_ID
    fal_upscale_model: str = FAL_BRIA_UPSCALE_MODEL_ID
    fal_upscale_after_model: str = FAL_TOPAZ_TRANSPARENT_MODEL_ID
    fal_upscale_scale: int = 4
    fal_upscale_after_scale: int = 4
    local_realesrgan_profile: str = "clipart"
    local_realesrgan_scale: int = 4
    local_realesrgan_after_scale: int = 4
    remove_background: bool = True
    remove_background_provider: str = "kie"
    kie_remove_bg_model: str = "recraft/remove-background"
    fal_remove_bg_model: str = "fal-ai/bria/background/remove"
    fal_birefnet_model: str = "General Use (Light)"
    fal_birefnet_resolution: str = "1024x1024"
    fal_birefnet_refine_foreground: bool = True
    fal_rembg_crop_to_bbox: bool = False
    local_rembg_profile: str = "clipart"
    local_rembg_model: str = "birefnet-general"
    local_rembg_edge_quality: str = "normal"
    local_ben2_refine_foreground: bool = False
    local_ben2_alpha_threshold: int = 24
    local_ben2_edge_softness: int = 0
    local_ben2_corner_radius: int = 0
    chroma_key_color: str = "blue"
    # Retained only so older drafts round-trip safely. Automatic chroma removal
    # ignores custom colors and the two former numeric controls.
    chroma_key_custom_color: str = "#0000FF"
    chroma_key_tolerance: int = 32
    chroma_key_softness: int = 8
    unsharp: bool = False
    unsharp_amount: int = 30
    unsharp_radius: float = 100.0
    unsharp_threshold: int = 0
    edge_shrink: bool = False
    edge_shrink_pixels: int = 1
    trim: bool = False
    trim_mode: str = "alpha"
    export_300_dpi: bool = False
    remove_exif: bool = False
    remove_xmp: bool = False
    remove_iptc: bool = False
    remove_comments_text: bool = False
    remove_embedded_thumbnail: bool = False
    remove_generator_fields: bool = False
    remove_embedded_c2pa: bool = False
    preserve_icc: bool = True
    preserve_dpi: bool = True

    def __post_init__(self) -> None:
        self.visible_mark_cleanup_mode = _text(
            self.visible_mark_cleanup_mode,
            limit=50,
        ) or "gemini_auto"
        self.upscale_before_provider = _text(
            self.upscale_before_provider,
            limit=100,
        ) or "kie"
        requested_after_provider = _text(
            self.upscale_after_provider,
            limit=100,
        ) or "fal"
        requested_after_model = _text(self.fal_upscale_after_model, limit=200)
        alpha_safe_after = (
            requested_after_provider == "fal"
            and upscale_model_preserves_alpha(
                requested_after_provider,
                requested_after_model,
            )
        )
        if self.upscale_after and not alpha_safe_after:
            self.upscale_after = False
        self.upscale_after_provider = "fal"
        self.upscale_factor = normalize_topaz_upscale_factor(self.upscale_factor)
        self.kie_upscale_model = normalize_kie_upscale_model(
            _text(self.kie_upscale_model, limit=200)
        )
        self.kie_upscale_after_model = normalize_kie_upscale_model(
            _text(self.kie_upscale_after_model, limit=200)
        )
        self.fal_upscale_model = normalize_fal_upscale_model(
            _text(self.fal_upscale_model, limit=200)
        )
        self.fal_upscale_after_model = normalize_fal_upscale_model(
            requested_after_model or FAL_TOPAZ_TRANSPARENT_MODEL_ID
        )
        self.fal_upscale_scale = normalize_fal_upscale_factor(
            self.fal_upscale_model,
            self.fal_upscale_scale,
        )
        self.fal_upscale_after_scale = normalize_fal_upscale_factor(
            self.fal_upscale_after_model,
            self.fal_upscale_after_scale,
        )
        self.local_realesrgan_profile = _text(
            self.local_realesrgan_profile,
            limit=100,
        ) or "clipart"
        self.local_realesrgan_scale = self._realesrgan_scale(
            self.local_realesrgan_scale
        )
        self.local_realesrgan_after_scale = self._realesrgan_scale(
            self.local_realesrgan_after_scale
        )
        self.remove_background_provider = _text(
            self.remove_background_provider,
            limit=100,
        ) or "kie"
        if self.remove_background_provider == "local_ben2":
            self.remove_background_provider = "local_rembg"
        self.kie_remove_bg_model = _text(
            self.kie_remove_bg_model,
            limit=200,
        ) or "recraft/remove-background"
        if self.kie_remove_bg_model != "recraft/remove-background":
            self.kie_remove_bg_model = "recraft/remove-background"
        self.fal_remove_bg_model = _text(self.fal_remove_bg_model, limit=200) or "fal-ai/bria/background/remove"
        if self.fal_remove_bg_model == "fal-ai/birefnet":
            self.fal_remove_bg_model = "fal-ai/birefnet/v2"
        self.fal_birefnet_model = _text(self.fal_birefnet_model, limit=100) or "General Use (Light)"
        self.fal_birefnet_resolution = _text(self.fal_birefnet_resolution, limit=30) or "1024x1024"
        self.local_rembg_profile = _text(self.local_rembg_profile, limit=100) or "clipart"
        self.local_rembg_model = _text(
            self.local_rembg_model,
            limit=200,
        ) or "birefnet-general"
        edge_quality = _text(self.local_rembg_edge_quality, limit=20).lower()
        self.local_rembg_edge_quality = (
            edge_quality if edge_quality in {"soft", "normal", "sharp"} else "normal"
        )
        self.local_ben2_alpha_threshold = _bounded_int(
            self.local_ben2_alpha_threshold,
            default=24,
            minimum=0,
            maximum=255,
        )
        self.local_ben2_edge_softness = _bounded_int(
            self.local_ben2_edge_softness,
            default=0,
            minimum=0,
            maximum=3,
        )
        self.local_ben2_corner_radius = _bounded_int(
            self.local_ben2_corner_radius,
            default=0,
            minimum=0,
            maximum=3,
        )
        self.chroma_key_color = _text(self.chroma_key_color, limit=20).lower()
        if self.chroma_key_color not in KEY_COLORS:
            self.chroma_key_color = "blue"
        self.chroma_key_custom_color = _text(self.chroma_key_custom_color, limit=20) or "#0000FF"
        self.chroma_key_tolerance = _bounded_int(
            self.chroma_key_tolerance, default=32, minimum=0, maximum=255
        )
        self.chroma_key_softness = _bounded_int(
            self.chroma_key_softness, default=8, minimum=0, maximum=255
        )
        self.unsharp_amount = _bounded_int(
            self.unsharp_amount,
            default=30,
            minimum=0,
            maximum=500,
        )
        self.unsharp_radius = _bounded_float(
            self.unsharp_radius,
            default=100.0,
            minimum=0.1,
            maximum=200.0,
        )
        self.unsharp_threshold = _bounded_int(
            self.unsharp_threshold,
            default=0,
            minimum=0,
            maximum=255,
        )
        self.edge_shrink_pixels = _bounded_int(
            self.edge_shrink_pixels,
            default=1,
            minimum=1,
            maximum=3,
        )
        trim_mode = _text(self.trim_mode, limit=20).lower()
        self.trim_mode = trim_mode if trim_mode in {"alpha", "white", "black"} else "alpha"

    @staticmethod
    def _realesrgan_scale(value: Any) -> int:
        normalized = _bounded_int(value, default=4, minimum=2, maximum=4)
        return normalized if normalized in {2, 4} else 4

    def to_dict(self) -> dict[str, Any]:
        return {
            definition.name: getattr(self, definition.name)
            for definition in dataclass_fields(self)
        }

    @classmethod
    def from_dict(cls, value: Any) -> ImageOperationData:
        data = value if isinstance(value, Mapping) else {}
        defaults = cls()
        values: dict[str, Any] = {}
        for definition in dataclass_fields(defaults):
            default = getattr(defaults, definition.name)
            raw = data.get(definition.name, default)
            values[definition.name] = (
                _boolean(raw, default=default) if isinstance(default, bool) else raw
            )
        return cls(**values)

    @classmethod
    def from_v2_config(cls, config: Mapping[str, Any]) -> ImageOperationData:
        remove_all = _boolean(config.get("cleanup_remove_all"), default=False)
        return cls(
            visible_mark_cleanup=_boolean(
                config.get("visible_mark_cleanup_enabled"),
                default=False,
            ),
            visible_mark_cleanup_mode=config.get(
                "visible_mark_cleanup_mode",
                "gemini_auto",
            ),
            upscale_before=_boolean(config.get("upscale"), default=True),
            upscale_before_provider=config.get("upscale_provider", "kie"),
            upscale_after=_boolean(config.get("upscale_after"), default=False),
            upscale_after_provider=config.get(
                "upscale_after_provider",
                "local_realesrgan",
            ),
            upscale_factor=config.get("upscale_factor", 4),
            kie_upscale_model=config.get("kie_upscale_model", KIE_TOPAZ_MODEL_ID),
            kie_upscale_after_model=config.get(
                "kie_upscale_after_model",
                config.get("kie_upscale_model", KIE_TOPAZ_MODEL_ID),
            ),
            fal_upscale_model=config.get(
                "fal_upscale_model", FAL_BRIA_UPSCALE_MODEL_ID
            ),
            fal_upscale_after_model=config.get(
                "fal_upscale_after_model", FAL_BRIA_UPSCALE_MODEL_ID
            ),
            fal_upscale_scale=config.get("fal_upscale_scale", 4),
            fal_upscale_after_scale=config.get("fal_upscale_after_scale", 4),
            local_realesrgan_profile=config.get(
                "local_realesrgan_profile",
                "clipart",
            ),
            local_realesrgan_scale=config.get("local_realesrgan_scale", 4),
            local_realesrgan_after_scale=config.get(
                "local_realesrgan_after_scale",
                config.get("local_realesrgan_scale", 4),
            ),
            remove_background=_boolean(config.get("remove_bg"), default=True),
            remove_background_provider=config.get("remove_bg_provider", "kie"),
            kie_remove_bg_model=config.get(
                "kie_remove_bg_model",
                "recraft/remove-background",
            ),
            fal_remove_bg_model=(
                "fal-ai/birefnet/v2"
                if config.get("fal_remove_bg_model") == "fal-ai/birefnet"
                else config.get("fal_remove_bg_model", "fal-ai/bria/background/remove")
            ),
            fal_birefnet_model=config.get("fal_birefnet_model", "General Use (Light)"),
            fal_birefnet_resolution=config.get("fal_birefnet_resolution", "1024x1024"),
            fal_birefnet_refine_foreground=_boolean(config.get("fal_birefnet_refine_foreground"), default=True),
            fal_rembg_crop_to_bbox=_boolean(config.get("fal_rembg_crop_to_bbox"), default=False),
            local_rembg_profile=config.get("local_rembg_profile", "clipart"),
            local_rembg_model=config.get("local_rembg_model", "birefnet-general"),
            local_rembg_edge_quality=config.get(
                "local_rembg_edge_quality",
                "normal",
            ),
            local_ben2_refine_foreground=_boolean(
                config.get("local_ben2_refine_foreground"),
                default=False,
            ),
            local_ben2_alpha_threshold=config.get("local_ben2_alpha_threshold", 24),
            local_ben2_edge_softness=config.get("local_ben2_edge_softness", 0),
            local_ben2_corner_radius=config.get("local_ben2_corner_radius", 0),
            chroma_key_color=config.get("chroma_key_color", "blue"),
            chroma_key_custom_color=config.get("chroma_key_custom_color", "#0000FF"),
            chroma_key_tolerance=config.get("chroma_key_tolerance", 32),
            chroma_key_softness=config.get("chroma_key_softness", 8),
            unsharp=_boolean(config.get("unsharp_enabled"), default=False),
            unsharp_amount=config.get("unsharp_amount", 30),
            unsharp_radius=config.get("unsharp_radius", 100),
            unsharp_threshold=config.get("unsharp_threshold", 0),
            edge_shrink=_boolean(config.get("edge_shrink_enabled"), default=False),
            edge_shrink_pixels=config.get("edge_shrink_pixels", 1),
            trim=_boolean(config.get("trim_enabled"), default=False),
            trim_mode=config.get("trim_mode", "alpha"),
            export_300_dpi=_boolean(config.get("export_300_dpi"), default=False),
            remove_exif=remove_all
            or _boolean(config.get("cleanup_remove_exif"), default=False),
            remove_xmp=remove_all
            or _boolean(config.get("cleanup_remove_xmp"), default=False),
            remove_iptc=remove_all
            or _boolean(config.get("cleanup_remove_iptc"), default=False),
            remove_comments_text=remove_all
            or _boolean(config.get("cleanup_remove_comments_text"), default=False),
            remove_embedded_thumbnail=remove_all
            or _boolean(
                config.get("cleanup_remove_embedded_thumbnail"),
                default=False,
            ),
            remove_generator_fields=remove_all
            or _boolean(
                config.get("cleanup_remove_generator_fields"),
                default=False,
            ),
            remove_embedded_c2pa=remove_all
            or _boolean(config.get("cleanup_remove_embedded_c2pa"), default=False),
            preserve_icc=_boolean(config.get("cleanup_preserve_icc"), default=True),
            preserve_dpi=_boolean(config.get("cleanup_preserve_dpi"), default=True),
        )


@dataclass(slots=True)
class PinterestOperationData:
    """Persist only operations that the Pinterest workflow can expose."""

    upscale_before: bool = False
    upscale_before_provider: str = "kie"
    upscale_after: bool = False
    upscale_after_provider: str = "local_realesrgan"
    upscale_factor: int = 4
    kie_upscale_model: str = KIE_TOPAZ_MODEL_ID
    kie_upscale_after_model: str = KIE_TOPAZ_MODEL_ID
    local_realesrgan_profile: str = "clipart"
    local_realesrgan_scale: int = 4
    local_realesrgan_after_scale: int = 4
    unsharp: bool = False
    unsharp_amount: int = 30
    unsharp_radius: float = 100.0
    unsharp_threshold: int = 0

    def __post_init__(self) -> None:
        normalized = ImageOperationData(
            upscale_before=self.upscale_before,
            upscale_before_provider=self.upscale_before_provider,
            upscale_after=self.upscale_after,
            upscale_after_provider=self.upscale_after_provider,
            upscale_factor=self.upscale_factor,
            kie_upscale_model=self.kie_upscale_model,
            kie_upscale_after_model=self.kie_upscale_after_model,
            local_realesrgan_profile=self.local_realesrgan_profile,
            local_realesrgan_scale=self.local_realesrgan_scale,
            local_realesrgan_after_scale=self.local_realesrgan_after_scale,
            unsharp=self.unsharp,
            unsharp_amount=self.unsharp_amount,
            unsharp_radius=self.unsharp_radius,
            unsharp_threshold=self.unsharp_threshold,
            remove_background=False,
        )
        for definition in dataclass_fields(self):
            setattr(self, definition.name, getattr(normalized, definition.name))

    def to_dict(self) -> dict[str, Any]:
        return {
            definition.name: getattr(self, definition.name)
            for definition in dataclass_fields(self)
        }

    @classmethod
    def from_dict(cls, value: Any) -> PinterestOperationData:
        source = value if isinstance(value, Mapping) else {}
        return cls(**{
            definition.name: source.get(definition.name, definition.default)
            for definition in dataclass_fields(cls)
        })

    @classmethod
    def from_image_operations(cls, value: ImageOperationData) -> PinterestOperationData:
        return cls(**{
            definition.name: getattr(value, definition.name)
            for definition in dataclass_fields(cls)
        })

    def as_image_operations(self) -> ImageOperationData:
        return ImageOperationData(
            **self.to_dict(),
            remove_background=False,
            visible_mark_cleanup=False,
            invisible_watermark_cleanup=False,
            edge_shrink=False,
            trim=False,
            export_300_dpi=False,
            remove_exif=False,
            remove_xmp=False,
            remove_iptc=False,
            remove_comments_text=False,
            remove_embedded_thumbnail=False,
            remove_generator_fields=False,
            remove_embedded_c2pa=False,
        )


def clipart_operation_defaults() -> ImageOperationData:
    return ImageOperationData(
        upscale_before=True,
        remove_background=True,
        trim=True,
        export_300_dpi=True,
    )

@dataclass
class ClipartModeData:
    prompts: list[PromptEntry] = field(default_factory=list)
    prompt_generator: PromptGeneratorData = field(
        default_factory=clipart_prompt_generator_defaults
    )
    generation: GenerationData = field(default_factory=GenerationData)
    operations: ImageOperationData = field(default_factory=clipart_operation_defaults)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompts": [entry.to_dict() for entry in self.prompts],
            "prompt_generator": self.prompt_generator.to_dict(),
            "generation": self.generation.to_dict(),
            "operations": self.operations.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> ClipartModeData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            prompts=_prompt_entries(data.get("prompts", [])),
            prompt_generator=PromptGeneratorData.from_dict(
                data.get("prompt_generator", {}),
                defaults=clipart_prompt_generator_defaults(),
            ),
            generation=GenerationData.from_dict(data.get("generation", {})),
            operations=ImageOperationData.from_dict(
                {
                    **clipart_operation_defaults().to_dict(),
                    **(
                        data.get("operations", {})
                        if isinstance(data.get("operations"), Mapping)
                        else {}
                    ),
                }
            ),
        )


@dataclass
class PinterestPinData:
    canvas_width: int = PINTEREST_CANVAS_WIDTH
    canvas_height: int = PINTEREST_CANVAS_HEIGHT
    template_count: int = PINTEREST_TEMPLATE_COUNT
    ai_scene_count: int = PINTEREST_AI_SCENE_COUNT
    product_paths: list[str] = field(default_factory=list)
    selected_product_index: int = 0
    pin_title: str = ""
    pin_subtitle: str = ""
    pin_cta: str = ""
    style: str = ""
    background_description: str = ""
    color_palette: str = ""

    def __post_init__(self) -> None:
        self.canvas_width = _bounded_int(
            self.canvas_width,
            default=PINTEREST_CANVAS_WIDTH,
            minimum=PINTEREST_CANVAS_WIDTH,
            maximum=PINTEREST_CANVAS_WIDTH,
        )
        self.canvas_height = _bounded_int(
            self.canvas_height,
            default=PINTEREST_CANVAS_HEIGHT,
            minimum=PINTEREST_CANVAS_HEIGHT,
            maximum=PINTEREST_CANVAS_HEIGHT,
        )
        self.template_count = _bounded_int(
            self.template_count,
            default=PINTEREST_TEMPLATE_COUNT,
            minimum=PINTEREST_TEMPLATE_COUNT,
            maximum=PINTEREST_TEMPLATE_COUNT,
        )
        self.ai_scene_count = _bounded_int(
            self.ai_scene_count,
            default=PINTEREST_AI_SCENE_COUNT,
            minimum=PINTEREST_AI_SCENE_COUNT,
            maximum=PINTEREST_AI_SCENE_COUNT,
        )
        self.product_paths = _string_list(self.product_paths, limit=MAX_SELECTED_FILES)
        self.selected_product_index = _bounded_int(
            self.selected_product_index,
            default=0,
            minimum=0,
            maximum=max(0, len(self.product_paths) - 1),
        )
        for name in (
            "pin_title",
            "pin_subtitle",
            "pin_cta",
            "style",
            "background_description",
            "color_palette",
        ):
            setattr(self, name, _text(getattr(self, name)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "canvas_width": self.canvas_width,
            "canvas_height": self.canvas_height,
            "template_count": self.template_count,
            "ai_scene_count": self.ai_scene_count,
            "product_paths": list(self.product_paths),
            "selected_product_index": self.selected_product_index,
            "pin_title": self.pin_title,
            "pin_subtitle": self.pin_subtitle,
            "pin_cta": self.pin_cta,
            "style": self.style,
            "background_description": self.background_description,
            "color_palette": self.color_palette,
        }

    @classmethod
    def from_dict(cls, value: Any) -> PinterestPinData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            canvas_width=data.get("canvas_width", PINTEREST_CANVAS_WIDTH),
            canvas_height=data.get("canvas_height", PINTEREST_CANVAS_HEIGHT),
            template_count=data.get("template_count", PINTEREST_TEMPLATE_COUNT),
            ai_scene_count=data.get("ai_scene_count", PINTEREST_AI_SCENE_COUNT),
            product_paths=data.get("product_paths", []),
            selected_product_index=data.get("selected_product_index", 0),
            pin_title=data.get("pin_title", ""),
            pin_subtitle=data.get("pin_subtitle", ""),
            pin_cta=data.get("pin_cta", ""),
            style=data.get("style", ""),
            background_description=data.get("background_description", ""),
            color_palette=data.get("color_palette", ""),
        )


_PINTEREST_VARIANT_KINDS = frozenset({"template", "ai_scene"})
_PINTEREST_RESULT_STATUSES = frozenset({"pending", "success", "failed"})
_PINTEREST_EXPORT_STATUSES = frozenset({"not_exported", "exported", "failed"})
_PINTEREST_ERROR_MESSAGES = {
    "": "",
    "background_generation_failed": "Не удалось создать фон. Повторите попытку.",
    "pin_generation_failed": "Не удалось создать вариант пина. Повторите попытку.",
}


@dataclass
class PinterestPinResultData:
    variant_id: str = ""
    variant_kind: str = "template"
    source_product_path: str = ""
    output_path: str = ""
    accepted: bool = False
    status: str = "pending"
    retryable: bool = False
    product_layer_digest: str = ""
    export_status: str = "not_exported"
    error_code: str = ""
    error_message: str = ""

    def __post_init__(self) -> None:
        self.variant_id = _text(self.variant_id, limit=200)
        self.variant_kind = _text(self.variant_kind, limit=30)
        if self.variant_kind not in _PINTEREST_VARIANT_KINDS:
            self.variant_kind = "template"
        self.source_product_path = _text(self.source_product_path)
        self.output_path = _text(self.output_path)
        self.accepted = _boolean(self.accepted, default=False)
        self.status = _text(self.status, limit=30)
        if self.status not in _PINTEREST_RESULT_STATUSES:
            self.status = "pending"
        self.retryable = _boolean(self.retryable, default=False)
        self.product_layer_digest = _text(self.product_layer_digest, limit=200)
        self.export_status = _text(self.export_status, limit=30)
        if self.export_status not in _PINTEREST_EXPORT_STATUSES:
            self.export_status = "not_exported"
        self.error_code = _text(self.error_code, limit=100)
        if self.error_code not in _PINTEREST_ERROR_MESSAGES:
            self.error_code = "pin_generation_failed"
        self.error_message = _PINTEREST_ERROR_MESSAGES[self.error_code]

    def to_dict(self) -> dict[str, Any]:
        return {
            "variant_id": self.variant_id,
            "variant_kind": self.variant_kind,
            "source_product_path": self.source_product_path,
            "output_path": self.output_path,
            "accepted": self.accepted,
            "status": self.status,
            "retryable": self.retryable,
            "product_layer_digest": self.product_layer_digest,
            "export_status": self.export_status,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, value: Any) -> PinterestPinResultData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            **{
                item.name: data.get(item.name, item.default)
                for item in dataclass_fields(cls)
            }
        )


def _pinterest_pin_results(value: Any) -> list[PinterestPinResultData]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [
        PinterestPinResultData.from_dict(item)
        for item in value[:MAX_PIN_RESULTS]
        if isinstance(item, Mapping)
    ]


@dataclass
class PinterestModeData:
    prompts: list[PromptEntry] = field(default_factory=list)
    generation: GenerationData = field(
        default_factory=lambda: GenerationData(
            model="gpt-image-2",
            ratio="2:3",
            resolution="1K",
            reference_model="gpt-image-2",
            reference_ratio="2:3",
            reference_resolution="1K",
        )
    )
    pin: PinterestPinData = field(default_factory=PinterestPinData)
    results: list[PinterestPinResultData] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompts": [entry.to_dict() for entry in self.prompts],
            "generation": self.generation.to_dict(),
            "pin": self.pin.to_dict(),
            "results": [result.to_dict() for result in self.results],
        }

    @classmethod
    def from_dict(cls, value: Any) -> PinterestModeData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            prompts=_prompt_entries(data.get("prompts", [])),
            generation=GenerationData.from_dict(
                {
                    **cls().generation.to_dict(),
                    **(
                        data.get("generation", {})
                        if isinstance(data.get("generation"), Mapping)
                        else {}
                    ),
                },
                default_ratio="9:16",
            ),
            pin=PinterestPinData.from_dict(data.get("pin", {})),
            results=_pinterest_pin_results(data.get("results", [])),
        )


@dataclass
class PinterestLegacyData:
    """Read-only archive of pre-Task-7 Pinterest fields during draft migration."""

    prompts: list[PromptEntry] = field(default_factory=list)
    prompt_generator: PromptGeneratorData = field(
        default_factory=pinterest_prompt_generator_defaults
    )
    operations: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompts": [entry.to_dict() for entry in self.prompts],
            "prompt_generator": self.prompt_generator.to_dict(),
            "operations": dict(self.operations),
        }

    @classmethod
    def from_dict(cls, value: Any) -> PinterestLegacyData:
        data = value if isinstance(value, Mapping) else {}
        operations = data.get("operations", {})
        return cls(
            prompts=_prompt_entries(data.get("prompts", [])),
            prompt_generator=PromptGeneratorData.from_dict(
                data.get("prompt_generator", {}),
                defaults=pinterest_prompt_generator_defaults(),
            ),
            operations=dict(operations) if isinstance(operations, Mapping) else {},
        )


_EVIDENCE_STATUSES = frozenset(
    {"detected", "not_detected", "not_verified", "unsupported"}
)
_EVIDENCE_STAGES = frozenset({"not_checked", "input", "output"})


@dataclass
class VerificationRecordData:
    file_path: str = ""
    synthid_status: str = "not_verified"
    synthid_stage: str = "not_checked"
    openai_status: str = "not_verified"
    openai_stage: str = "not_checked"

    def __post_init__(self) -> None:
        self.file_path = _text(self.file_path, limit=MAX_TEXT_LENGTH)
        self.synthid_status = self._status(self.synthid_status)
        self.openai_status = self._status(self.openai_status)
        self.synthid_stage = self._stage(self.synthid_stage, self.synthid_status)
        self.openai_stage = self._stage(self.openai_stage, self.openai_status)

    @staticmethod
    def _status(value: Any) -> str:
        normalized = _text(value, limit=30).lower()
        return normalized if normalized in _EVIDENCE_STATUSES else "not_verified"

    @staticmethod
    def _stage(value: Any, status: str) -> str:
        normalized = _text(value, limit=30).lower()
        if status not in {"detected", "not_detected"}:
            return "not_checked"
        return normalized if normalized in {"input", "output"} else "input"

    def to_dict(self) -> dict[str, str]:
        return {
            "file_path": self.file_path,
            "synthid_status": self.synthid_status,
            "synthid_stage": self.synthid_stage,
            "openai_status": self.openai_status,
            "openai_stage": self.openai_stage,
        }

    @classmethod
    def from_dict(cls, value: Any) -> VerificationRecordData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            file_path=data.get("file_path", ""),
            synthid_status=data.get("synthid_status", "not_verified"),
            synthid_stage=data.get("synthid_stage", "not_checked"),
            openai_status=data.get("openai_status", "not_verified"),
            openai_stage=data.get("openai_stage", "not_checked"),
        )


def _verification_records(value: Any) -> list[VerificationRecordData]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    records: list[VerificationRecordData] = []
    seen: set[str] = set()
    for item in value:
        record = (
            item
            if isinstance(item, VerificationRecordData)
            else VerificationRecordData.from_dict(item)
        )
        if not record.file_path or record.file_path in seen:
            continue
        records.append(record)
        seen.add(record.file_path)
        if len(records) >= MAX_SELECTED_FILES:
            break
    return records

@dataclass
class ProcessingModeData:
    selected_files: list[str] = field(default_factory=list)
    recipe: str = "custom"
    overwrite_existing: bool = False
    deep_watermark_consent: bool = False
    operations: ImageOperationData = field(default_factory=ImageOperationData)
    verification_records: list[VerificationRecordData] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.selected_files = _string_list(
            self.selected_files,
            limit=MAX_SELECTED_FILES,
        )
        self.recipe = _text(self.recipe, limit=100) or "custom"
        self.verification_records = _verification_records(self.verification_records)

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_files": list(self.selected_files),
            "recipe": self.recipe,
            "overwrite_existing": self.overwrite_existing,
            "deep_watermark_consent": self.deep_watermark_consent,
            "operations": self.operations.to_dict(),
            "verification_records": [
                record.to_dict() for record in self.verification_records
            ],
        }

    @classmethod
    def from_dict(cls, value: Any) -> ProcessingModeData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            selected_files=_string_list(
                data.get("selected_files", []),
                limit=MAX_SELECTED_FILES,
            ),
            recipe=data.get("recipe", "custom"),
            overwrite_existing=bool(data.get("overwrite_existing", False)),
            deep_watermark_consent=bool(data.get("deep_watermark_consent", False)),
            operations=ImageOperationData.from_dict(data.get("operations", {})),
            verification_records=_verification_records(
                data.get("verification_records", [])
            ),
        )

def _reject_unknown_fields(
    section: Mapping[str, Any],
    allowed: Sequence[str],
    name: str,
) -> None:
    unknown = sorted(set(section) - set(allowed))
    if unknown:
        raise ProjectStateError(
            f"Project draft field {name!r} contains unknown keys: {', '.join(unknown)}"
        )


def _draft_object(container: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = container.get(key)
    if not isinstance(value, Mapping):
        raise ProjectStateError(f"Project draft field {key!r} must be an object")
    return value


def _validate_scalar_fields(
    section: Mapping[str, Any],
    model: Any,
    name: str,
    *,
    allow_missing: bool = False,
) -> None:
    defaults = model()
    definitions = dataclass_fields(defaults)
    _reject_unknown_fields(section, [item.name for item in definitions], name)
    for definition in definitions:
        field_name = definition.name
        if field_name not in section:
            if allow_missing:
                continue
            raise ProjectStateError(
                f"Project draft field {name}.{field_name} is required"
            )
        value = section[field_name]
        default = getattr(defaults, field_name)
        valid = False
        if isinstance(default, bool):
            valid = isinstance(value, bool)
        elif isinstance(default, int):
            valid = type(value) is int
        elif isinstance(default, float):
            valid = isinstance(value, (int, float)) and not isinstance(value, bool)
        elif isinstance(default, str):
            valid = isinstance(value, str)
        if not valid:
            raise ProjectStateError(
                f"Project draft field {name}.{field_name} has an invalid type"
            )


def _validate_prompt_section(section: Mapping[str, Any], name: str) -> None:
    prompts = section.get("prompts")
    if not isinstance(prompts, list):
        raise ProjectStateError(f"Project draft field {name}.prompts must be a list")
    for entry in prompts:
        if not isinstance(entry, Mapping):
            raise ProjectStateError(f"Project draft {name} prompt must be an object")
        _reject_unknown_fields(entry, ("prompt", "references"), f"{name}.prompt")
        if not isinstance(entry.get("prompt"), str):
            raise ProjectStateError(f"Project draft {name} prompt text must be a string")
        references = entry.get("references")
        if not isinstance(references, list) or not all(
            isinstance(reference, str) for reference in references
        ):
            raise ProjectStateError(
                f"Project draft {name} prompt references must be a string list"
            )


def _validate_prompt_generator_section(
    section: Mapping[str, Any],
    name: str,
) -> None:
    _reject_unknown_fields(
        section,
        (
            "theme",
            "subjects",
            "variations",
            "style",
            "palette",
            "composition",
            "background",
            "consistency",
            "restrictions",
            "count",
            "chroma_key_enabled",
            "chroma_key_color",
            "chroma_key_custom_color",
            "chroma_key_materials",
        ),
        name,
    )
    for key in (
        "theme",
        "style",
        "palette",
        "composition",
        "background",
        "consistency",
    ):
        value = section.get(key)
        if key in {"consistency"} and value is None:
            continue
        if not isinstance(value, str):
            raise ProjectStateError(
                f"Project draft field {name}.{key} must be a string"
            )
        if len(value) > MAX_PROMPT_GENERATOR_TEXT_LENGTH:
            raise ProjectStateError(
                f"Project draft field {name}.{key} is too long"
            )
    for key in ("subjects", "variations", "restrictions"):
        values = section.get(key)
        if key == "variations" and values is None:
            continue
        if not isinstance(values, list) or not all(
            isinstance(value, str) for value in values
        ):
            raise ProjectStateError(
                f"Project draft field {name}.{key} must be a string list"
            )
        if len(values) > MAX_PROMPT_GENERATOR_ITEMS:
            raise ProjectStateError(
                f"Project draft field {name}.{key} has too many items"
            )
        if any(len(value) > MAX_TEXT_LENGTH for value in values):
            raise ProjectStateError(
                f"Project draft field {name}.{key} contains a long item"
            )
    count = section.get("count")
    if type(count) is not int:
        raise ProjectStateError(
            f"Project draft field {name}.count must be an integer"
        )
    if not 1 <= count <= MAX_PROMPT_SERIES_COUNT:
        raise ProjectStateError(
            f"Project draft field {name}.count is out of range"
        )
    if type(section.get("chroma_key_enabled", False)) is not bool:
        raise ProjectStateError(
            f"Project draft field {name}.chroma_key_enabled must be a boolean"
        )
    key_color = section.get("chroma_key_color", "blue")
    if not isinstance(key_color, str) or len(key_color) > 20 or not (
        key_color.casefold() in KEY_COLORS
        or _CHROMA_KEY_COLOR_PATTERN.fullmatch(key_color.strip())
    ):
        raise ProjectStateError(
            f"Project draft field {name}.chroma_key_color is invalid"
        )
    custom_color = section.get("chroma_key_custom_color", "#0000FF")
    if not isinstance(custom_color, str) or not _CHROMA_KEY_COLOR_PATTERN.fullmatch(custom_color.strip()):
        raise ProjectStateError(
            f"Project draft field {name}.chroma_key_custom_color is invalid"
        )
    materials = section.get("chroma_key_materials", [])
    if not isinstance(materials, list) or not all(isinstance(value, str) for value in materials):
        raise ProjectStateError(f"Project draft field {name}.chroma_key_materials must be a string list")


def _validate_verification_records(processing: Mapping[str, Any]) -> None:
    if "verification_records" not in processing:
        return
    records = processing.get("verification_records")
    if not isinstance(records, list) or len(records) > MAX_SELECTED_FILES:
        raise ProjectStateError(
            "Project draft field processing.verification_records must be a bounded list"
        )
    allowed = (
        "file_path",
        "synthid_status",
        "synthid_stage",
        "openai_status",
        "openai_stage",
    )
    selected_files = processing.get("selected_files", [])
    seen_paths: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ProjectStateError(
                "Project draft verification record must be an object"
            )
        name = f"processing.verification_records[{index}]"
        _reject_unknown_fields(record, allowed, name)
        if set(record) != set(allowed):
            raise ProjectStateError(f"Project draft field {name} is incomplete")
        if not all(isinstance(record[field], str) for field in allowed):
            raise ProjectStateError(f"Project draft field {name} has an invalid type")
        file_path = record["file_path"]
        if not file_path or len(file_path) > MAX_TEXT_LENGTH:
            raise ProjectStateError(f"Project draft field {name}.file_path is invalid")
        if file_path not in selected_files or file_path in seen_paths:
            raise ProjectStateError(
                f"Project draft field {name}.file_path is not a unique selected file"
            )
        seen_paths.add(file_path)
        for prefix in ("synthid", "openai"):
            status = record[f"{prefix}_status"]
            stage = record[f"{prefix}_stage"]
            if status not in _EVIDENCE_STATUSES or stage not in _EVIDENCE_STAGES:
                raise ProjectStateError(f"Project draft field {name} has an invalid status")
            checked = status in {"detected", "not_detected"}
            if checked != (stage in {"input", "output"}):
                raise ProjectStateError(
                    f"Project draft field {name} has an inconsistent evidence stage"
                )


def _validate_pinterest_pin_data(pinterest: Mapping[str, Any]) -> None:
    if "pin" not in pinterest:
        return
    pin = _draft_object(pinterest, "pin")
    allowed = tuple(item.name for item in dataclass_fields(PinterestPinData))
    _reject_unknown_fields(pin, allowed, "pinterest.pin")
    if set(pin) != set(allowed):
        raise ProjectStateError("Project draft field pinterest.pin is incomplete")
    for key in (
        "canvas_width",
        "canvas_height",
        "template_count",
        "ai_scene_count",
        "selected_product_index",
    ):
        if type(pin[key]) is not int:
            raise ProjectStateError(
                f"Project draft field pinterest.pin.{key} must be an integer"
            )
    for key in (
        "pin_title",
        "pin_subtitle",
        "pin_cta",
        "style",
        "background_description",
        "color_palette",
    ):
        if not isinstance(pin[key], str):
            raise ProjectStateError(
                f"Project draft field pinterest.pin.{key} must be a string"
            )
    if not isinstance(pin["product_paths"], list) or not all(
        isinstance(path, str) for path in pin["product_paths"]
    ):
        raise ProjectStateError(
            "Project draft field pinterest.pin.product_paths must be a string list"
        )
    if len(pin["product_paths"]) > MAX_SELECTED_FILES:
        raise ProjectStateError(
            "Project draft field pinterest.pin.product_paths has too many items"
        )
    if pin["canvas_width"] != PINTEREST_CANVAS_WIDTH:
        raise ProjectStateError(
            "Project draft field pinterest.pin.canvas_width is unsupported"
        )
    if pin["canvas_height"] != PINTEREST_CANVAS_HEIGHT:
        raise ProjectStateError(
            "Project draft field pinterest.pin.canvas_height is unsupported"
        )
    if pin["template_count"] != PINTEREST_TEMPLATE_COUNT:
        raise ProjectStateError(
            "Project draft field pinterest.pin.template_count is unsupported"
        )
    if pin["ai_scene_count"] != PINTEREST_AI_SCENE_COUNT:
        raise ProjectStateError(
            "Project draft field pinterest.pin.ai_scene_count is unsupported"
        )
    if not 0 <= pin["selected_product_index"] < max(1, len(pin["product_paths"])):
        raise ProjectStateError(
            "Project draft field pinterest.pin.selected_product_index is out of range"
        )


def _validate_pinterest_results(pinterest: Mapping[str, Any]) -> None:
    if "results" not in pinterest:
        return
    results = pinterest["results"]
    if not isinstance(results, list) or len(results) > MAX_PIN_RESULTS:
        raise ProjectStateError(
            "Project draft field pinterest.results must be a bounded list"
        )
    allowed = tuple(item.name for item in dataclass_fields(PinterestPinResultData))
    for index, result in enumerate(results):
        name = f"pinterest.results[{index}]"
        if not isinstance(result, Mapping):
            raise ProjectStateError(f"Project draft field {name} must be an object")
        _reject_unknown_fields(result, allowed, name)
        if set(result) != set(allowed):
            raise ProjectStateError(f"Project draft field {name} is incomplete")
        for key in ("accepted", "retryable"):
            if not isinstance(result[key], bool):
                raise ProjectStateError(
                    f"Project draft field {name}.{key} must be boolean"
                )
        for key in set(allowed) - {"accepted", "retryable"}:
            if not isinstance(result[key], str):
                raise ProjectStateError(
                    f"Project draft field {name}.{key} must be a string"
                )
        if result["variant_kind"] not in _PINTEREST_VARIANT_KINDS:
            raise ProjectStateError(
                f"Project draft field {name}.variant_kind is unsupported"
            )
        if result["status"] not in _PINTEREST_RESULT_STATUSES:
            raise ProjectStateError(
                f"Project draft field {name}.status is unsupported"
            )
        if result["export_status"] not in _PINTEREST_EXPORT_STATUSES:
            raise ProjectStateError(
                f"Project draft field {name}.export_status is unsupported"
            )
        if result["error_code"] not in _PINTEREST_ERROR_MESSAGES:
            raise ProjectStateError(
                f"Project draft field {name}.error_code is unsupported"
            )
        if result["error_message"] != _PINTEREST_ERROR_MESSAGES[result["error_code"]]:
            raise ProjectStateError(
                f"Project draft field {name}.error_message is unsafe"
            )


def _validate_pinterest_legacy_data(
    legacy: Mapping[str, Any],
    *,
    name: str,
) -> None:
    _reject_unknown_fields(
        legacy,
        ("prompts", "prompt_generator", "operations"),
        name,
    )
    if "prompts" in legacy:
        _validate_prompt_section(legacy, name)
    if "prompt_generator" in legacy:
        _validate_prompt_generator_section(
            _draft_object(legacy, "prompt_generator"),
            f"{name}.prompt_generator",
        )
    if "operations" not in legacy:
        return
    pinterest_operations = _draft_object(legacy, "operations")
    pinterest_operation_fields = tuple(
        definition.name for definition in dataclass_fields(PinterestOperationData)
    )
    legacy_operation_fields = tuple(
        definition.name for definition in dataclass_fields(ImageOperationData)
    )
    _reject_unknown_fields(
        pinterest_operations,
        (*pinterest_operation_fields, *legacy_operation_fields),
        f"{name}.operations",
    )


def _validate_project_draft_shape(value: Mapping[str, Any]) -> None:
    _reject_unknown_fields(
        value,
        (
            "schema_version",
            "mode",
            "common",
            "runtime",
            "clipart",
            "pinterest",
            "pinterest_legacy",
            "processing",
            "current_step_by_mode",
        ),
        "root",
    )
    if not isinstance(value.get("mode"), str):
        raise ProjectStateError("Project draft mode must be a string")
    try:
        active_mode = ProjectMode(value["mode"])
    except ValueError as error:
        raise ProjectStateError("Project draft mode is unsupported") from error

    common = _draft_object(value, "common")
    _reject_unknown_fields(
        common,
        ("project_name", "work_dir", "output_dir", "output_dirs"),
        "common",
    )
    for key in ("project_name", "work_dir", "output_dir"):
        if not isinstance(common.get(key), str):
            raise ProjectStateError(f"Project draft field common.{key} must be a string")
    if not isinstance(common.get("output_dirs", {}), Mapping):
        raise ProjectStateError("Project draft field common.output_dirs must be an object")
    for key, output_value in common.get("output_dirs", {}).items():
        if key not in {mode.value for mode in ProjectMode} or not isinstance(output_value, str):
            raise ProjectStateError("Project draft field common.output_dirs is invalid")

    runtime = _draft_object(value, "runtime")
    _validate_scalar_fields(runtime, RuntimeData, "runtime")

    clipart = _draft_object(value, "clipart")
    _reject_unknown_fields(
        clipart,
        ("prompts", "prompt_generator", "generation", "operations"),
        "clipart",
    )
    _validate_prompt_section(clipart, "clipart")
    if "prompt_generator" in clipart:
        _validate_prompt_generator_section(
            _draft_object(clipart, "prompt_generator"),
            "clipart.prompt_generator",
        )
    _validate_scalar_fields(
        _draft_object(clipart, "generation"),
        GenerationData,
        "clipart.generation",
    )
    _validate_scalar_fields(
        _draft_object(clipart, "operations"),
        ImageOperationData,
        "clipart.operations",
        allow_missing=True,
    )

    pinterest = _draft_object(value, "pinterest")
    _reject_unknown_fields(
        pinterest,
        (
            "generation",
            "pin",
            "results",
            "prompts",
            "prompt_generator",
            "operations",
        ),
        "pinterest",
    )
    _validate_scalar_fields(
        _draft_object(pinterest, "generation"),
        GenerationData,
        "pinterest.generation",
    )
    legacy_pinterest_fields = {
        key: pinterest[key]
        for key in ("prompts", "prompt_generator", "operations")
        if key in pinterest
    }
    if legacy_pinterest_fields:
        _validate_pinterest_legacy_data(
            legacy_pinterest_fields,
            name="pinterest",
        )
    _validate_pinterest_pin_data(pinterest)
    _validate_pinterest_results(pinterest)
    if "pinterest_legacy" in value:
        _validate_pinterest_legacy_data(
            _draft_object(value, "pinterest_legacy"),
            name="pinterest_legacy",
        )

    processing = _draft_object(value, "processing")
    _reject_unknown_fields(
        processing,
        (
            "selected_files",
            "recipe",
            "overwrite_existing",
            "deep_watermark_consent",
            "operations",
            "verification_records",
        ),
        "processing",
    )
    selected_files = processing.get("selected_files")
    if not isinstance(selected_files, list) or not all(
        isinstance(selected_file, str) for selected_file in selected_files
    ):
        raise ProjectStateError(
            "Project draft field processing.selected_files must be a string list"
        )
    if not isinstance(processing.get("recipe"), str):
        raise ProjectStateError("Project draft field processing.recipe must be a string")
    if not isinstance(processing.get("deep_watermark_consent", False), bool):
        raise ProjectStateError("Project draft field processing.deep_watermark_consent must be boolean")
    _validate_verification_records(processing)
    _validate_scalar_fields(
        _draft_object(processing, "operations"),
        ImageOperationData,
        "processing.operations",
        allow_missing=True,
    )

    steps = _draft_object(value, "current_step_by_mode")
    _reject_unknown_fields(
        steps,
        tuple(mode.value for mode in ProjectMode),
        "current_step_by_mode",
    )
    for mode in ProjectMode:
        raw_step = steps.get(mode.value)
        if not isinstance(raw_step, str):
            raise ProjectStateError(
                f"Project draft current step for {mode.value!r} must be a string"
            )
        try:
            step = StepId(raw_step)
        except ValueError as error:
            raise ProjectStateError(
                f"Project draft current step for {mode.value!r} is unsupported"
            ) from error
        if step not in ROUTES[mode]:
            raise ProjectStateError(
                f"Project draft current step for {mode.value!r} is outside its route"
            )
    if StepId(steps[active_mode.value]) not in ROUTES[active_mode]:
        raise ProjectStateError("Project draft active step is outside its route")


def _initial_steps() -> dict[ProjectMode, StepId]:
    return {mode: route[0] for mode, route in ROUTES.items()}


@dataclass
class ProjectState:
    mode: ProjectMode = ProjectMode.CLIPART
    common: CommonProjectData = field(default_factory=CommonProjectData)
    runtime: RuntimeData = field(default_factory=RuntimeData)
    clipart: ClipartModeData = field(default_factory=ClipartModeData)
    pinterest: PinterestModeData = field(default_factory=PinterestModeData)
    pinterest_legacy: PinterestLegacyData | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    processing: ProcessingModeData = field(default_factory=ProcessingModeData)
    current_step_by_mode: dict[ProjectMode, StepId] = field(
        default_factory=_initial_steps
    )
    workflow_routes: dict[ProjectMode, tuple[StepId, ...]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ProjectMode):
            try:
                self.mode = ProjectMode(self.mode)
            except (TypeError, ValueError) as error:
                raise ProjectStateError(f"Unsupported project mode: {self.mode!r}") from error
        if self.pinterest_legacy is not None and not isinstance(
            self.pinterest_legacy, PinterestLegacyData
        ):
            self.pinterest_legacy = PinterestLegacyData.from_dict(self.pinterest_legacy)

        normalized_steps = _initial_steps()
        for mode, step in dict(self.current_step_by_mode).items():
            try:
                normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
                normalized_step = step if isinstance(step, StepId) else StepId(step)
            except (TypeError, ValueError):
                continue
            if (
                normalized_mode is ProjectMode.PINTEREST
                and normalized_step is StepId.PROCESSING_OPTIONS
            ):
                normalized_step = StepId.REVIEW_RUN
            if normalized_step in ROUTES[normalized_mode]:
                normalized_steps[normalized_mode] = normalized_step
        self.current_step_by_mode = normalized_steps
        normalized_routes: dict[ProjectMode, tuple[StepId, ...]] = dict(ROUTES)
        for mode, route in dict(self.workflow_routes).items():
            try:
                normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
                normalized_route = tuple(
                    step if isinstance(step, StepId) else StepId(step)
                    for step in route
                )
            except (TypeError, ValueError):
                continue
            if normalized_route and len(normalized_route) == len(set(normalized_route)):
                normalized_routes[normalized_mode] = normalized_route
                if self.current_step_by_mode[normalized_mode] not in normalized_route:
                    self.current_step_by_mode[normalized_mode] = normalized_route[0]
        self.workflow_routes = normalized_routes

    @property
    def route(self) -> tuple[StepId, ...]:
        return self.workflow_routes[self.mode]

    def set_workflow_route(
        self,
        mode: ProjectMode | str,
        route: tuple[StepId, ...] | list[StepId],
    ) -> None:
        normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        normalized_route = tuple(
            step if isinstance(step, StepId) else StepId(step) for step in route
        )
        if not normalized_route or len(normalized_route) != len(set(normalized_route)):
            raise ProjectStateError("Workflow route must contain unique steps")
        self.workflow_routes[normalized_mode] = normalized_route
        if self.current_step_by_mode[normalized_mode] not in normalized_route:
            self.current_step_by_mode[normalized_mode] = normalized_route[0]

    @property
    def current_step(self) -> StepId:
        return self.current_step_by_mode[self.mode]

    def switch_mode(self, mode: ProjectMode | str) -> StepId:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        self.mode = normalized
        return self.current_step

    def output_dir_for_mode(self, mode: ProjectMode | str | None = None) -> str:
        selected = mode if isinstance(mode, ProjectMode) else ProjectMode(mode or self.mode)
        return self.common.output_dirs.get(selected.value, self.common.output_dir)

    def set_output_dir_for_mode(self, value: str, mode: ProjectMode | str | None = None) -> None:
        selected = mode if isinstance(mode, ProjectMode) else ProjectMode(mode or self.mode)
        normalized = _text(value)
        self.common.output_dirs[selected.value] = normalized
        self.common.output_dir = normalized

    def set_step(self, step: StepId | str) -> StepId:
        try:
            normalized = step if isinstance(step, StepId) else StepId(step)
        except (TypeError, ValueError) as error:
            raise ProjectStateError(f"Unsupported step: {step!r}") from error
        if normalized not in self.route:
            raise ProjectStateError(
                f"Step {normalized.value!r} is not part of {self.mode.value!r} route"
            )
        self.current_step_by_mode[self.mode] = normalized
        return normalized

    def validation_issues(self, step: StepId | None = None) -> tuple[str, ...]:
        target = step or self.current_step
        if target not in self.route:
            raise ProjectStateError(
                f"Step {target.value!r} is not part of {self.mode.value!r} route"
            )

        issues: list[str] = []
        if self.mode in {ProjectMode.CLIPART, ProjectMode.PINTEREST}:
            generation = self.clipart.generation if self.mode is ProjectMode.CLIPART else self.pinterest.generation
            if target in {StepId.PROJECT, StepId.REVIEW_RUN} and not self.common.work_dir:
                issues.append("work_dir_required")
            if self.mode is ProjectMode.CLIPART and target in {StepId.PROMPTS, StepId.PROMPT_REVIEW, StepId.REVIEW_RUN} and not self.clipart.prompts:
                issues.append("prompts_required")
            if self.mode is ProjectMode.PINTEREST and target in {
                StepId.PROMPT_REVIEW,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
            } and not self.pinterest.prompts:
                issues.append("prompts_required")
            if target in {
                StepId.GENERATION,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
            }:
                if not generation.model:
                    issues.append("generation_model_required")
                if not generation.ratio:
                    issues.append("generation_ratio_required")
                if not generation.resolution:
                    issues.append("generation_resolution_required")
        elif target in {StepId.FILES, StepId.REVIEW_RUN}:
            if not self.processing.selected_files:
                issues.append("selected_files_required")
        return tuple(issues)

    def next_step(self, *, require_valid: bool = True) -> StepId:
        if require_valid:
            issues = self.validation_issues()
            if issues:
                raise ProjectStateValidationError(
                    "Current step is incomplete: " + ", ".join(issues)
                )
        index = self.route.index(self.current_step)
        if index < len(self.route) - 1:
            self.current_step_by_mode[self.mode] = self.route[index + 1]
        return self.current_step

    def previous_step(self) -> StepId:
        index = self.route.index(self.current_step)
        if index > 0:
            self.current_step_by_mode[self.mode] = self.route[index - 1]
        return self.current_step

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": PROJECT_STATE_SCHEMA_VERSION,
            "mode": self.mode.value,
            "common": self.common.to_dict(),
            "runtime": self.runtime.to_dict(),
            "clipart": self.clipart.to_dict(),
            "pinterest": self.pinterest.to_dict(),
            "processing": self.processing.to_dict(),
            "current_step_by_mode": {
                mode.value: self.current_step_by_mode[mode].value for mode in ProjectMode
            },
        }
        if self.pinterest_legacy is not None:
            result["pinterest_legacy"] = self.pinterest_legacy.to_dict()
        return result

    @classmethod
    def from_dict(cls, value: Any) -> ProjectState:
        if not isinstance(value, Mapping):
            raise ProjectStateError("Project draft root must be an object")
        schema_version = value.get("schema_version")
        if type(schema_version) is not int or schema_version != PROJECT_STATE_SCHEMA_VERSION:
            raise ProjectStateError("Unsupported project draft schema")
        _validate_project_draft_shape(value)
        raw_steps = value.get("current_step_by_mode", {})
        steps = dict(raw_steps) if isinstance(raw_steps, Mapping) else {}
        for mode in (ProjectMode.CLIPART, ProjectMode.PROCESSING):
            if steps.get(mode.value) == StepId.TRANSPARENCY.value:
                # The editor depends on the live run queue, which is intentionally
                # not persisted in project drafts. Reopen the durable results page.
                steps[mode.value] = StepId.RESULTS.value
        pinterest_data = value.get("pinterest", {})
        legacy_source = value.get("pinterest_legacy")
        if legacy_source is None and isinstance(pinterest_data, Mapping):
            legacy_fields = {
                key: pinterest_data[key]
                for key in ("prompt_generator", "operations")
                if key in pinterest_data
            }
            legacy_source = legacy_fields or None
        return cls(
            mode=value.get("mode", ProjectMode.CLIPART.value),
            common=CommonProjectData.from_dict(value.get("common", {})),
            runtime=RuntimeData.from_dict(value.get("runtime", {})),
            clipart=ClipartModeData.from_dict(value.get("clipart", {})),
            pinterest=PinterestModeData.from_dict(pinterest_data),
            pinterest_legacy=(
                PinterestLegacyData.from_dict(legacy_source)
                if legacy_source is not None
                else None
            ),
            processing=ProcessingModeData.from_dict(value.get("processing", {})),
            current_step_by_mode=steps,
        )


def migrate_v2_config(
    config: Mapping[str, Any],
    *,
    prompts: Sequence[Any] | None = None,
) -> ProjectState:
    if not isinstance(config, Mapping):
        raise ProjectStateError("Version 2 config must be an object")

    run_mode = _text(config.get("run_mode", "generate_only"), limit=50)
    mode = (
        ProjectMode.PROCESSING
        if run_mode == "process_only"
        else ProjectMode.CLIPART
    )
    work_dir = _text(config.get("last_work_dir", ""))
    generation_model = _text(
        config.get(
            "text_generation_model",
            config.get("generation_model", "gpt-image/1.5-text-to-image"),
        ),
        limit=200,
    )
    generation_ratio = _text(
        config.get(
            "text_generation_ratio",
            config.get("generation_size", "1:1"),
        ),
        limit=20,
    )
    generation_resolution = _text(
        config.get("text_generation_resolution", "1K"),
        limit=20,
    )
    reference_model = _text(
        config.get(
            "reference_generation_model",
            "gpt-image/1.5-image-to-image",
        ),
        limit=200,
    )
    reference_ratio = _text(
        config.get("reference_generation_ratio", generation_ratio or "1:1"),
        limit=20,
    )
    reference_resolution = _text(
        config.get("reference_generation_resolution", "1K"),
        limit=20,
    )
    operations = ImageOperationData.from_v2_config(config)
    migrated_prompts = _prompt_entries(prompts or [])

    return ProjectState(
        mode=mode,
        common=CommonProjectData(
            project_name=_text(config.get("project_name", ""), limit=200),
            work_dir=work_dir,
            output_dir=str(Path(work_dir) / "output") if work_dir else "",
        ),
        runtime=RuntimeData(
            retries=config.get("retries", 3),
            timeout=config.get("timeout", 60),
            generation_wait_timeout=config.get("generation_wait_timeout", 300),
            status_poll_interval=config.get("status_poll_interval", 20),
            kie_upload_path=config.get("kie_upload_path", "clipart-generator"),
        ),
        clipart=ClipartModeData(
            prompts=migrated_prompts,
            generation=GenerationData(
                model=generation_model or "gpt-image/1.5-text-to-image",
                ratio=generation_ratio or "1:1",
                resolution=generation_resolution or "1K",
                reference_model=reference_model or "gpt-image/1.5-image-to-image",
                reference_ratio=reference_ratio or "1:1",
                reference_resolution=reference_resolution or "1K",
            ),
            operations=operations,
        ),
        pinterest=PinterestModeData(),
        processing=ProcessingModeData(
            selected_files=[],
            recipe="custom",
            operations=ImageOperationData.from_v2_config(config),
        ),
    )


def save_project_draft(state: ProjectState, path: str | os.PathLike[str]) -> None:
    if not isinstance(state, ProjectState):
        raise ProjectStateError("state must be a ProjectState")
    destination = Path(path)
    parent = destination.parent
    if not parent.is_dir():
        raise ProjectStateError("Project draft directory does not exist")

    draft = state.to_dict()
    _validate_project_draft_shape(draft)
    payload = json.dumps(
        draft,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if len(payload) > MAX_DRAFT_BYTES:
        raise ProjectStateError("Project draft exceeds the size limit")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise ProjectStateError("Could not save project draft") from error


def load_project_draft(path: str | os.PathLike[str]) -> ProjectState:
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as error:
        raise ProjectStateError("Could not read project draft") from error
    if size > MAX_DRAFT_BYTES:
        raise ProjectStateError("Project draft exceeds the size limit")
    try:
        with source.open("rb") as stream:
            raw = stream.read(MAX_DRAFT_BYTES + 1)
        if len(raw) > MAX_DRAFT_BYTES:
            raise ProjectStateError("Project draft exceeds the size limit")
        data = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ProjectStateError("Project draft is not valid UTF-8 JSON") from error
    return ProjectState.from_dict(data)
