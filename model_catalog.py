"""Single immutable catalog for generation models and pure routing lookups."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (set, frozenset)):
        return frozenset(value)
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    label: str
    model_type: str
    ratios: frozenset[str] = frozenset()
    resolutions: frozenset[str] = frozenset()
    qualities: frozenset[str] = frozenset()
    pricing: str | Mapping[str, str] | None = None
    reference_compatible_text: bool = False


_MODEL_ROWS = (
    ("fal-ai/flux/schnell", "Fal.ai — FLUX Schnell", "text_to_image"),
    ("fal-ai/ideogram/v3", "Fal.ai — Ideogram V3", "text_to_image"),
    ("fal-ai/ideogram/v3/generate-transparent", "Fal.ai — Ideogram V3 Transparent", "text_to_image"),
    ("fal-ai/recraft/v4/text-to-image", "Fal.ai — Recraft V4", "text_to_image"),
    ("ideogram/v4/fast", "Fal.ai — Ideogram V4 Fast", "text_to_image"),
    ("fal-ai/flux-2/klein/4b", "Fal.ai — FLUX.2 Klein 4B", "text_to_image"),
    ("fal-ai/kling-image/o3/text-to-image", "Fal.ai — Kling O3 Image", "text_to_image"),
    ("bria/fibo-gen-1.5/text-to-image", "Fal.ai — Bria Fibo Gen 1.5", "text_to_image"),
    ("atlascloud/gpt-image-2.5-flare", "AtlasCloud — GPT Image 2.5 Flare", "text_to_image"),
    ("piapi/gpt-image-2.5-flare", "PiAPI — GPT Image 2.5 Flare", "text_to_image"),
    ("atlascloud/gpt-image-2.5-sunburst", "AtlasCloud — GPT Image 2.5 Sunburst", "text_to_image"),
    ("piapi/gpt-image-2.5-sunburst", "PiAPI — GPT Image 2.5 Sunburst", "text_to_image"),
    ("piapi/gpt-image-2.5", "PiAPI — GPT Image 2.5 (бюджетный, авторазмер)", "text_to_image"),
    ("gpt4o-image", "KIE — GPT‑4o Image", "text_to_image"),
    ("gpt-image/1.5-text-to-image", "KIE — GPT Image 1.5 (Text→Image)", "text_to_image"),
    ("gpt-image-2", "KIE — GPT Image 2", "text_to_image"),
    ("nano-banana-2", "KIE — Nano Banana 2", "text_to_image"),
    ("z-image", "KIE — Z-Image", "text_to_image"),
    ("google/imagen4", "KIE — Google Imagen 4", "text_to_image"),
    ("google/imagen4-fast", "KIE — Google Imagen 4 Fast", "text_to_image"),
    ("google/imagen4-ultra", "KIE — Google Imagen 4 Ultra", "text_to_image"),
    ("google/nano-banana", "KIE — Google Nano Banana", "text_to_image"),
    ("qwen-image-2", "KIE — Qwen Image 2.0", "text_to_image"),
    ("flux-2/flex-text-to-image", "KIE — FLUX.2 Flex (Text→Image)", "text_to_image"),
    ("flux-2/pro-text-to-image", "KIE — FLUX.2 Pro (Text→Image)", "text_to_image"),
    ("grok-imagine/text-to-image", "KIE — Grok Imagine (Text→Image)", "text_to_image"),
    ("qwen/text-to-image", "KIE — Qwen (Text→Image)", "text_to_image"),
    ("nano-banana-pro", "KIE — Google Nano Banana Pro", "image_to_image"),
    ("gpt-image-2", "KIE — GPT Image 2", "image_to_image"),
    ("nano-banana-2", "KIE — Nano Banana 2", "image_to_image"),
    ("flux-2/pro-image-to-image", "KIE — FLUX.2 Pro (Image→Image)", "image_to_image"),
    ("flux-2/flex-image-to-image", "KIE — FLUX.2 Flex (Image→Image)", "image_to_image"),
    ("qwen-image-2", "KIE — Qwen Image 2.0", "edit"),
    ("grok-imagine/image-to-image", "KIE — Grok Imagine (Image→Image)", "image_to_image"),
    ("gpt-image/1.5-image-to-image", "KIE — GPT Image 1.5 (Image→Image)", "image_to_image"),
    ("qwen/image-to-image", "KIE — Qwen (Image→Image)", "image_to_image"),
    ("google/nano-banana-edit", "KIE — Google Nano Banana Edit", "edit"),
    ("qwen/image-edit", "KIE — Qwen Image Edit", "edit"),
)

_CAPABILITIES = {
    # Fal pricing and endpoint-specific image-size capabilities are resolved
    # separately; leaving these fields open prevents fabricated estimates.
    "fal-ai/flux/schnell": {"reference_compatible_text": False},
    "atlascloud/gpt-image-2.5-flare": {"ratios": {"1:1", "2:3", "3:2"}, "resolutions": {"1K"}},
    "piapi/gpt-image-2.5-flare": {"ratios": {"1:1", "2:3", "3:2"}, "resolutions": {"1K"}},
    "atlascloud/gpt-image-2.5-sunburst": {"ratios": {"1:1", "2:3", "3:2"}, "resolutions": {"1K"}},
    "piapi/gpt-image-2.5-sunburst": {"ratios": {"1:1", "2:3", "3:2"}, "resolutions": {"1K"}},
    "piapi/gpt-image-2.5": {"ratios": {"auto"}, "resolutions": {"auto"}},
    "fal-ai/ideogram/v3": {
        "ratios": {"1:1", "3:4", "4:3", "9:16", "16:9"},
        "pricing": "Turbo $0.03 / Balanced $0.06 / Quality $0.09",
    },
    "fal-ai/ideogram/v3/generate-transparent": {
        "ratios": {"1:1", "3:4", "4:3", "9:16", "16:9"},
        "pricing": "Turbo $0.03 / Balanced $0.06 / Quality $0.09",
    },
    "fal-ai/recraft/v4/text-to-image": {
        "ratios": {"1:1", "3:4", "4:3", "9:16", "16:9"},
        "pricing": "$0.04 / image",
    },
    "ideogram/v4/fast": {
        "ratios": {"1:1", "3:4", "4:3", "9:16", "16:9"},
        "pricing": "Turbo $0.00525 / MP; Balanced $0.0105 / MP; Quality $0.0175 / MP",
    },
    "fal-ai/flux-2/klein/4b": {
        "ratios": {"1:1", "3:4", "4:3", "9:16", "16:9"},
        "pricing": "$0.005 / MP",
    },
    "fal-ai/kling-image/o3/text-to-image": {
        "ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"},
        "resolutions": {"1K", "2K", "4K"},
        "pricing": {"1K": "$0.028 / image", "2K": "$0.028 / image", "4K": "$0.056 / image"},
    },
    "bria/fibo-gen-1.5/text-to-image": {
        "ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9"},
        "resolutions": {"1MP", "4MP"},
        "pricing": "$0.04 / image",
    },
    "gpt-image/1.5-text-to-image": {"ratios": {"1:1", "2:3", "3:2"}, "qualities": {"medium", "high"}, "pricing": "4 / 22 credits ($0.02 / $0.11)"},
    "gpt-image/1.5-image-to-image": {"ratios": {"1:1", "2:3", "3:2"}, "qualities": {"medium", "high"}, "pricing": "4 / 22 credits ($0.02 / $0.11)"},
    "gpt-image-2": {"ratios": {"auto", "1:1", "3:2", "2:3", "4:3", "3:4", "5:4", "4:5", "16:9", "9:16", "2:1", "1:2", "3:1", "1:3", "21:9", "9:21"}, "resolutions": {"1K", "2K", "4K"}, "pricing": {"1K": "6 credits / $0.03", "2K": "10 credits / $0.05", "4K": "16 credits / $0.08"}, "reference_compatible_text": True},
    "nano-banana-2": {"ratios": {"auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"}, "resolutions": {"1K", "2K", "4K"}, "pricing": {"1K": "8 credits / $0.04", "2K": "12 credits / $0.06", "4K": "18 credits / $0.09"}, "reference_compatible_text": True},
    "nano-banana-pro": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}, "resolutions": {"1K", "2K", "4K"}, "pricing": {"1K": "18 credits / $0.09", "2K": "18 credits / $0.09", "4K": "24 credits / $0.12"}, "reference_compatible_text": True},
    "qwen-image-2": {"ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}, "pricing": "6 credits / $0.03", "reference_compatible_text": True},
    "flux-2/flex-text-to-image": {"ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"}},
    "flux-2/pro-text-to-image": {"ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"}},
    "flux-2/flex-image-to-image": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"}},
    "flux-2/pro-image-to-image": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"}},
}

_MODE_RATIOS = MappingProxyType({
    "qwen-image-2": MappingProxyType({
        False: frozenset({"1:1", "3:4", "4:3", "9:16", "16:9"}),
        True: frozenset({"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}),
    }),
    "flux-2/flex-image-to-image": MappingProxyType({
        True: frozenset({"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}),
    }),
    "flux-2/pro-image-to-image": MappingProxyType({
        True: frozenset({"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}),
    }),
})

_REFERENCE_LIMITS = MappingProxyType({
    "gpt-image/1.5-image-to-image": (16, 10 * 1024 * 1024),
    "gpt-image-2": (16, 30 * 1024 * 1024),
    "nano-banana-2": (14, 30 * 1024 * 1024),
    "nano-banana-pro": (8, 30 * 1024 * 1024),
    "qwen-image-2": (1, 10 * 1024 * 1024),
    "flux-2/flex-image-to-image": (8, 10 * 1024 * 1024),
    "flux-2/pro-image-to-image": (8, 10 * 1024 * 1024),
})

_PROMPT_LIMITS = MappingProxyType({
    "gpt-image-2": (1, 20_000),
    "flux-2/flex-text-to-image": (3, 5_000),
    "flux-2/pro-text-to-image": (3, 5_000),
    "flux-2/flex-image-to-image": (3, 5_000),
    "flux-2/pro-image-to-image": (3, 5_000),
})

_first_rows: dict[str, tuple[str, str]] = {}
for _model_id, _label, _model_type in _MODEL_ROWS:
    _first_rows.setdefault(_model_id, (_label, _model_type))

MODEL_SPECS = MappingProxyType({
    model_id: ModelSpec(
        model_id=model_id,
        label=label,
        model_type=model_type,
        ratios=frozenset(_CAPABILITIES.get(model_id, {}).get("ratios", ())),
        resolutions=frozenset(_CAPABILITIES.get(model_id, {}).get("resolutions", ())),
        qualities=frozenset(_CAPABILITIES.get(model_id, {}).get("qualities", ())),
        pricing=_freeze(_CAPABILITIES.get(model_id, {}).get("pricing")),
        reference_compatible_text=bool(_CAPABILITIES.get(model_id, {}).get("reference_compatible_text", False)),
    ) for model_id, (label, model_type) in _first_rows.items()
})

GENERATION_MODELS = tuple(MappingProxyType({"id": i, "label": l, "type": t}) for i, l, t in _MODEL_ROWS)
GENERATION_MODEL_META = MappingProxyType({model_id: next(row for row in GENERATION_MODELS if row["id"] == model_id) for model_id in MODEL_SPECS})
SUPPORTED_GENERATION_MODEL_IDS = frozenset(row[0] for row in _MODEL_ROWS)
VISIBLE_GENERATION_MODEL_IDS = frozenset({"atlascloud/gpt-image-2.5-sunburst", "piapi/gpt-image-2.5-sunburst", "piapi/gpt-image-2.5", "atlascloud/gpt-image-2.5-flare", "piapi/gpt-image-2.5-flare", "fal-ai/flux/schnell", "fal-ai/ideogram/v3", "fal-ai/ideogram/v3/generate-transparent", "fal-ai/recraft/v4/text-to-image", "ideogram/v4/fast", "fal-ai/flux-2/klein/4b", "fal-ai/kling-image/o3/text-to-image", "bria/fibo-gen-1.5/text-to-image", "gpt-image/1.5-text-to-image", "gpt-image-2", "nano-banana-2", "nano-banana-pro", "qwen-image-2", "flux-2/pro-text-to-image", "flux-2/flex-text-to-image", "gpt-image/1.5-image-to-image", "flux-2/pro-image-to-image", "flux-2/flex-image-to-image"})
REFERENCE_MODEL_SHORTLIST = frozenset({"gpt-image/1.5-image-to-image", "gpt-image-2", "nano-banana-2", "nano-banana-pro", "qwen-image-2", "flux-2/pro-image-to-image", "flux-2/flex-image-to-image"})
PROCESSING_PRICING = MappingProxyType({"topaz/image-upscale": "40 credits / $0.20", "recraft/crisp-upscale": "0.5 credits / $0.0025", "recraft/remove-background": "1 credit / $0.005"})


def generation_provider_id(model_id: str) -> str:
    """Select a generation provider without conflating every non-Fal model with KIE."""
    from fal_model_catalog import is_fal_generation_model
    from gpt25_provider import provider_for_model

    direct = provider_for_model(model_id)
    return direct if direct else "fal" if is_fal_generation_model(model_id) else "kie"


def model_spec(model_id: str) -> ModelSpec:
    try:
        return MODEL_SPECS[model_id]
    except KeyError as error:
        raise KeyError(f"Unknown generation model: {model_id}") from error


def resolve_generation_endpoint(model_id: str, has_references: bool = False) -> str:
    model_spec(model_id)
    if model_id == "gpt-image-2":
        return "gpt-image-2-image-to-image" if has_references else "gpt-image-2-text-to-image"
    if model_id == "qwen-image-2":
        return "qwen2/image-edit" if has_references else "qwen2/text-to-image"
    return model_id


def ratios_for_mode(model_id: str, has_references: bool = False) -> frozenset[str]:
    spec = model_spec(model_id)
    modes = _MODE_RATIOS.get(model_id)
    if modes and bool(has_references) in modes:
        return modes[bool(has_references)]
    return spec.ratios


def reference_limits(model_id: str) -> tuple[int | None, int | None]:
    model_spec(model_id)
    return _REFERENCE_LIMITS.get(model_id, (None, None))


def validate_generation_contract(
    model_id: str,
    *,
    has_references: bool,
    ratio: str,
    resolution: str,
    prompt: str,
    reference_count: int = 0,
    reference_sizes: tuple[int, ...] = (),
) -> None:
    spec = model_spec(model_id)
    allowed_ratios = ratios_for_mode(model_id, has_references)
    if allowed_ratios and ratio not in allowed_ratios:
        raise ValueError(f"Пропорция {ratio} недоступна для модели {spec.label}")
    if spec.resolutions and resolution not in spec.resolutions:
        raise ValueError(f"Разрешение {resolution} недоступно для модели {spec.label}")

    minimum, maximum = _PROMPT_LIMITS.get(model_id, (1, None))
    prompt_length = len(str(prompt or ""))
    if prompt_length < minimum or (maximum is not None and prompt_length > maximum):
        upper = maximum if maximum is not None else "без ограничения"
        raise ValueError(f"Промпт для {spec.label} должен содержать от {minimum} до {upper} символов")

    if model_id == "gpt-image-2":
        if ratio == "auto" and resolution != "1K":
            raise ValueError("GPT Image 2: пропорция auto поддерживает только разрешение 1K")
        if ratio == "1:1" and resolution == "4K":
            raise ValueError("GPT Image 2: пропорция 1:1 недоступна в разрешении 4K")
        if has_references:
            if ratio in {"5:4", "4:5"} and resolution != "1K":
                raise ValueError(f"GPT Image 2: пропорция {ratio} поддерживает только 1K с референсами")
        elif resolution in {"2K", "4K"} and ratio in {"5:4", "4:5", "3:1", "1:3", "9:21"}:
            raise ValueError(f"GPT Image 2: пропорция {ratio} недоступна в разрешении {resolution}")

    max_references, max_reference_bytes = reference_limits(model_id)
    if has_references and max_references is not None and reference_count > max_references:
        reference_word = "референс" if max_references == 1 else "референса"
        raise ValueError(f"Модель {spec.label} поддерживает максимум {max_references} {reference_word}")
    if has_references and max_reference_bytes is not None:
        for size in reference_sizes:
            if size > max_reference_bytes:
                limit_mb = max_reference_bytes // (1024 * 1024)
                raise ValueError(f"Референс для {spec.label} превышает {limit_mb} МБ")
