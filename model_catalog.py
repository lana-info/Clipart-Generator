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
    ("gpt4o-image", "GPT‑4o Image", "text_to_image"),
    ("gpt-image/1.5-text-to-image", "GPT Image 1.5 (Text→Image)", "text_to_image"),
    ("gpt-image-2", "GPT Image 2", "text_to_image"),
    ("nano-banana-2", "Nano Banana 2", "text_to_image"),
    ("z-image", "Z-Image", "text_to_image"),
    ("google/imagen4", "Google Imagen 4", "text_to_image"),
    ("google/imagen4-fast", "Google Imagen 4 Fast", "text_to_image"),
    ("google/imagen4-ultra", "Google Imagen 4 Ultra", "text_to_image"),
    ("google/nano-banana", "Google Nano Banana", "text_to_image"),
    ("qwen-image-2", "Qwen Image 2.0", "text_to_image"),
    ("flux-2/flex-text-to-image", "FLUX.2 Flex (Text→Image)", "text_to_image"),
    ("flux-2/pro-text-to-image", "FLUX.2 Pro (Text→Image)", "text_to_image"),
    ("grok-imagine/text-to-image", "Grok Imagine (Text→Image)", "text_to_image"),
    ("qwen/text-to-image", "Qwen (Text→Image)", "text_to_image"),
    ("nano-banana-pro", "Google Nano Banana Pro", "image_to_image"),
    ("gpt-image-2", "GPT Image 2", "image_to_image"),
    ("nano-banana-2", "Nano Banana 2", "image_to_image"),
    ("flux-2/pro-image-to-image", "FLUX.2 Pro (Image→Image)", "image_to_image"),
    ("flux-2/flex-image-to-image", "FLUX.2 Flex (Image→Image)", "image_to_image"),
    ("qwen-image-2", "Qwen Image 2.0", "edit"),
    ("grok-imagine/image-to-image", "Grok Imagine (Image→Image)", "image_to_image"),
    ("gpt-image/1.5-image-to-image", "GPT Image 1.5 (Image→Image)", "image_to_image"),
    ("qwen/image-to-image", "Qwen (Image→Image)", "image_to_image"),
    ("google/nano-banana-edit", "Google Nano Banana Edit", "edit"),
    ("qwen/image-edit", "Qwen Image Edit", "edit"),
)

_CAPABILITIES = {
    "gpt-image/1.5-text-to-image": {"ratios": {"1:1", "2:3", "3:2"}, "qualities": {"medium", "high"}, "pricing": "4 / 22 credits ($0.02 / $0.11)"},
    "gpt-image/1.5-image-to-image": {"ratios": {"1:1", "2:3", "3:2"}, "qualities": {"medium", "high"}, "pricing": "4 / 22 credits ($0.02 / $0.11)"},
    "gpt-image-2": {"ratios": {"auto", "1:1", "9:16", "16:9", "4:3", "3:4"}, "resolutions": {"1K", "2K", "4K"}, "pricing": {"1K": "6 credits / $0.03", "2K": "10 credits / $0.05", "4K": "16 credits / $0.08"}, "reference_compatible_text": True},
    "nano-banana-2": {"ratios": {"auto", "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"}, "resolutions": {"1K", "2K", "4K"}, "pricing": {"1K": "8 credits / $0.04", "2K": "12 credits / $0.06", "4K": "18 credits / $0.09"}, "reference_compatible_text": True},
    "nano-banana-pro": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9"}, "resolutions": {"1K", "2K", "4K"}, "pricing": {"1K": "18 credits / $0.09", "2K": "18 credits / $0.09", "4K": "24 credits / $0.12"}, "reference_compatible_text": True},
    "qwen-image-2": {"ratios": {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"}, "pricing": "6 credits / $0.03", "reference_compatible_text": True},
    "flux-2/flex-text-to-image": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"}},
    "flux-2/pro-text-to-image": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"}},
    "flux-2/flex-image-to-image": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "14 credits / $0.07", "2K": "24 credits / $0.12"}},
    "flux-2/pro-image-to-image": {"ratios": {"auto", "1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9"}, "resolutions": {"1K", "2K"}, "pricing": {"1K": "5 credits / $0.025", "2K": "7 credits / $0.035"}},
}

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
VISIBLE_GENERATION_MODEL_IDS = frozenset({"gpt-image/1.5-text-to-image", "gpt-image-2", "nano-banana-2", "nano-banana-pro", "qwen-image-2", "flux-2/pro-text-to-image", "flux-2/flex-text-to-image", "gpt-image/1.5-image-to-image", "flux-2/pro-image-to-image", "flux-2/flex-image-to-image"})
REFERENCE_MODEL_SHORTLIST = frozenset({"gpt-image/1.5-image-to-image", "gpt-image-2", "nano-banana-2", "nano-banana-pro", "qwen-image-2", "flux-2/pro-image-to-image", "flux-2/flex-image-to-image"})
PROCESSING_PRICING = MappingProxyType({"topaz/image-upscale": "40 credits / $0.20", "recraft/crisp-upscale": "0.5 credits / $0.0025", "recraft/remove-background": "1 credit / $0.005"})


def model_spec(model_id: str) -> ModelSpec:
    try:
        return MODEL_SPECS[model_id]
    except KeyError as error:
        raise KeyError(f"Unknown generation model: {model_id}") from error


def resolve_generation_endpoint(model_id: str, has_references: bool = False) -> str:
    model_spec(model_id)
    if model_id == "gpt-image-2":
        return "gpt-image-2-image-to-image" if has_references else "gpt-image-2-text-to-image"
    return model_id
