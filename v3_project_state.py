from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field, fields as dataclass_fields
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_STATE_SCHEMA_VERSION = 1
MAX_DRAFT_BYTES = 2 * 1024 * 1024
MAX_PROMPT_ENTRIES = 5000
MAX_REFERENCES_PER_PROMPT = 5
MAX_PROMPT_GENERATOR_ITEMS = 500
MAX_PROMPT_GENERATOR_TEXT_LENGTH = 4000
MAX_PROMPT_SERIES_COUNT = 500
MAX_SELECTED_FILES = 10000
MAX_TEXT_LENGTH = 20000


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


ROUTES: dict[ProjectMode, tuple[StepId, ...]] = {
    ProjectMode.CLIPART: (
        StepId.PROJECT,
        StepId.PROMPTS,
        StepId.GENERATION,
        StepId.PROCESSING_OPTIONS,
        StepId.REVIEW_RUN,
        StepId.RESULTS,
    ),
    ProjectMode.PINTEREST: (
        StepId.PROJECT,
        StepId.PROMPTS,
        StepId.PIN_FORMAT_MODEL,
        StepId.PROCESSING_OPTIONS,
        StepId.REVIEW_RUN,
        StepId.RESULTS,
    ),
    ProjectMode.PROCESSING: (
        StepId.FILES,
        StepId.GOAL,
        StepId.PIPELINE,
        StepId.EVIDENCE,
        StepId.REVIEW_RUN,
        StepId.RESULTS,
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
    style: str = ""
    palette: str = ""
    composition: str = ""
    background: str = ""
    restrictions: list[str] = field(default_factory=list)
    count: int = 12

    def __post_init__(self) -> None:
        self.theme = _text(self.theme, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        self.subjects = _string_list(
            self.subjects,
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
        self.restrictions = _string_list(
            self.restrictions,
            limit=MAX_PROMPT_GENERATOR_ITEMS,
        )
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
            "style": self.style,
            "palette": self.palette,
            "composition": self.composition,
            "background": self.background,
            "restrictions": list(self.restrictions),
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
            style=data.get("style", base.style),
            palette=data.get("palette", base.palette),
            composition=data.get("composition", base.composition),
            background=data.get("background", base.background),
            restrictions=data.get("restrictions", base.restrictions),
            count=data.get("count", base.count),
        )


def clipart_prompt_generator_defaults() -> PromptGeneratorData:
    return PromptGeneratorData(
        style="cohesive professional clipart illustration",
        palette="a consistent harmonious palette across the full series",
        composition=(
            "one isolated subject, centered, fully visible, clear silhouette"
        ),
        background="pure solid white background, no environment or ground",
        restrictions=[
            "no text",
            "no logo",
            "no watermark",
            "no frame",
            "no cropped parts",
            "no cast or contact shadow",
        ],
    )


def pinterest_prompt_generator_defaults() -> PromptGeneratorData:
    return PromptGeneratorData(
        style="polished editorial social media image",
        palette="a consistent harmonious palette across the full series",
        composition=(
            "vertical composition, clear focal point, balanced negative space, "
            "safe zones near the edges"
        ),
        background="cohesive full-frame background supporting the main subject",
        restrictions=[
            "no watermark",
            "no logo",
            "no mandatory text overlay",
            "no collage or editable layer layout",
        ],
    )


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

    def __post_init__(self) -> None:
        self.project_name = _text(self.project_name, limit=200)
        self.work_dir = _text(self.work_dir)
        self.output_dir = _text(self.output_dir)

    def to_dict(self) -> dict[str, str]:
        return {
            "project_name": self.project_name,
            "work_dir": self.work_dir,
            "output_dir": self.output_dir,
        }

    @classmethod
    def from_dict(cls, value: Any) -> CommonProjectData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            project_name=data.get("project_name", ""),
            work_dir=data.get("work_dir", ""),
            output_dir=data.get("output_dir", ""),
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
    upscale_after_provider: str = "local_realesrgan"
    upscale_factor: int = 4
    kie_upscale_model: str = "topaz/upscale"
    kie_upscale_after_model: str = "topaz/upscale"
    local_realesrgan_profile: str = "clipart"
    local_realesrgan_scale: int = 4
    local_realesrgan_after_scale: int = 4
    remove_background: bool = True
    remove_background_provider: str = "kie"
    kie_remove_bg_model: str = "recraft/remove-background"
    local_rembg_profile: str = "clipart"
    local_rembg_model: str = "birefnet-general"
    local_rembg_edge_quality: str = "normal"
    local_ben2_refine_foreground: bool = False
    local_ben2_alpha_threshold: int = 24
    local_ben2_edge_softness: int = 0
    local_ben2_corner_radius: int = 0
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
        self.upscale_after_provider = _text(
            self.upscale_after_provider,
            limit=100,
        ) or "local_realesrgan"
        self.upscale_factor = _bounded_int(
            self.upscale_factor,
            default=4,
            minimum=1,
            maximum=16,
        )
        self.kie_upscale_model = _text(self.kie_upscale_model, limit=200) or "topaz/upscale"
        self.kie_upscale_after_model = _text(
            self.kie_upscale_after_model,
            limit=200,
        ) or "topaz/upscale"
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
        self.kie_remove_bg_model = _text(
            self.kie_remove_bg_model,
            limit=200,
        ) or "recraft/remove-background"
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
            kie_upscale_model=config.get("kie_upscale_model", "topaz/upscale"),
            kie_upscale_after_model=config.get(
                "kie_upscale_after_model",
                config.get("kie_upscale_model", "topaz/upscale"),
            ),
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
class PinterestModeData:
    prompts: list[PromptEntry] = field(default_factory=list)
    prompt_generator: PromptGeneratorData = field(
        default_factory=pinterest_prompt_generator_defaults
    )
    generation: GenerationData = field(
        default_factory=lambda: GenerationData(
            model="gpt-image-2",
            ratio="9:16",
            resolution="1K",
            reference_model="gpt-image-2",
            reference_ratio="9:16",
            reference_resolution="1K",
        )
    )
    operations: ImageOperationData = field(
        default_factory=lambda: ImageOperationData(
            upscale_before=False,
            remove_background=False,
        )
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompts": [entry.to_dict() for entry in self.prompts],
            "prompt_generator": self.prompt_generator.to_dict(),
            "generation": self.generation.to_dict(),
            "operations": self.operations.to_dict(),
        }

    @classmethod
    def from_dict(cls, value: Any) -> PinterestModeData:
        data = value if isinstance(value, Mapping) else {}
        return cls(
            prompts=_prompt_entries(data.get("prompts", [])),
            prompt_generator=PromptGeneratorData.from_dict(
                data.get("prompt_generator", {}),
                defaults=pinterest_prompt_generator_defaults(),
            ),
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
            operations=ImageOperationData.from_dict(
                data.get("operations", {})
                if isinstance(data.get("operations"), Mapping)
                else {}
            ),
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


def _validate_scalar_fields(section: Mapping[str, Any], model: Any, name: str) -> None:
    defaults = model()
    definitions = dataclass_fields(defaults)
    _reject_unknown_fields(section, [item.name for item in definitions], name)
    for definition in definitions:
        field_name = definition.name
        if field_name not in section:
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
            "style",
            "palette",
            "composition",
            "background",
            "restrictions",
            "count",
        ),
        name,
    )
    for key in (
        "theme",
        "style",
        "palette",
        "composition",
        "background",
    ):
        value = section.get(key)
        if not isinstance(value, str):
            raise ProjectStateError(
                f"Project draft field {name}.{key} must be a string"
            )
        if len(value) > MAX_PROMPT_GENERATOR_TEXT_LENGTH:
            raise ProjectStateError(
                f"Project draft field {name}.{key} is too long"
            )
    for key in ("subjects", "restrictions"):
        values = section.get(key)
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
        ("project_name", "work_dir", "output_dir"),
        "common",
    )
    for key in ("project_name", "work_dir", "output_dir"):
        if not isinstance(common.get(key), str):
            raise ProjectStateError(f"Project draft field common.{key} must be a string")

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
    )

    pinterest = _draft_object(value, "pinterest")
    _reject_unknown_fields(
        pinterest,
        ("prompts", "prompt_generator", "generation", "operations"),
        "pinterest",
    )
    _validate_prompt_section(pinterest, "pinterest")
    if "prompt_generator" in pinterest:
        _validate_prompt_generator_section(
            _draft_object(pinterest, "prompt_generator"),
            "pinterest.prompt_generator",
        )
    _validate_scalar_fields(
        _draft_object(pinterest, "generation"),
        GenerationData,
        "pinterest.generation",
    )
    _validate_scalar_fields(
        _draft_object(pinterest, "operations"),
        ImageOperationData,
        "pinterest.operations",
    )

    processing = _draft_object(value, "processing")
    _reject_unknown_fields(
        processing,
        (
            "selected_files",
            "recipe",
            "overwrite_existing",
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
    _validate_verification_records(processing)
    _validate_scalar_fields(
        _draft_object(processing, "operations"),
        ImageOperationData,
        "processing.operations",
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
    processing: ProcessingModeData = field(default_factory=ProcessingModeData)
    current_step_by_mode: dict[ProjectMode, StepId] = field(
        default_factory=_initial_steps
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, ProjectMode):
            try:
                self.mode = ProjectMode(self.mode)
            except (TypeError, ValueError) as error:
                raise ProjectStateError(f"Unsupported project mode: {self.mode!r}") from error

        normalized_steps = _initial_steps()
        for mode, step in dict(self.current_step_by_mode).items():
            try:
                normalized_mode = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
                normalized_step = step if isinstance(step, StepId) else StepId(step)
            except (TypeError, ValueError):
                continue
            if (
                normalized_step is StepId.PROMPT_REVIEW
                and normalized_mode in {ProjectMode.CLIPART, ProjectMode.PINTEREST}
            ):
                normalized_step = StepId.PROMPTS
            if normalized_step in ROUTES[normalized_mode]:
                normalized_steps[normalized_mode] = normalized_step
        self.current_step_by_mode = normalized_steps

    @property
    def route(self) -> tuple[StepId, ...]:
        return ROUTES[self.mode]

    @property
    def current_step(self) -> StepId:
        return self.current_step_by_mode[self.mode]

    def switch_mode(self, mode: ProjectMode | str) -> StepId:
        normalized = mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
        self.mode = normalized
        return self.current_step

    def set_step(self, step: StepId | str) -> StepId:
        try:
            normalized = step if isinstance(step, StepId) else StepId(step)
        except (TypeError, ValueError) as error:
            raise ProjectStateError(f"Unsupported step: {step!r}") from error
        if (
            normalized is StepId.PROMPT_REVIEW
            and self.mode in {ProjectMode.CLIPART, ProjectMode.PINTEREST}
        ):
            normalized = StepId.PROMPTS
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
            prompts = (
                self.clipart.prompts
                if self.mode is ProjectMode.CLIPART
                else self.pinterest.prompts
            )
            generation = (
                self.clipart.generation
                if self.mode is ProjectMode.CLIPART
                else self.pinterest.generation
            )
            if target in {StepId.PROJECT, StepId.REVIEW_RUN} and not self.common.work_dir:
                issues.append("work_dir_required")
            if target in {StepId.PROMPTS, StepId.REVIEW_RUN}:
                if not prompts:
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
        return {
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
        return cls(
            mode=value.get("mode", ProjectMode.CLIPART.value),
            common=CommonProjectData.from_dict(value.get("common", {})),
            runtime=RuntimeData.from_dict(value.get("runtime", {})),
            clipart=ClipartModeData.from_dict(value.get("clipart", {})),
            pinterest=PinterestModeData.from_dict(value.get("pinterest", {})),
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

    payload = json.dumps(
        state.to_dict(),
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
