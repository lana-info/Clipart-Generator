from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from chroma_key import KEY_COLORS


KIE_TOPAZ_MODEL_ID: Final = "topaz/image-upscale"
LEGACY_KIE_TOPAZ_MODEL_IDS: Final = frozenset({"topaz/upscale"})
TOPAZ_UPSCALE_FACTORS: Final = (2, 4)
TOPAZ_MAX_FILE_BYTES: Final = 10_000_000
TOPAZ_MAX_OUTPUT_SIDE: Final = 20_000
CHROMA_KEY_COLOR_OPTIONS: Final = tuple(
    ({"blue": "Синий", "red": "Красный", "green": "Зелёный"}[name], name)
    for name in KEY_COLORS
)


def normalize_kie_upscale_model(model_id: object) -> str:
    value = str(model_id or "").strip()
    if not value or value in LEGACY_KIE_TOPAZ_MODEL_IDS:
        return KIE_TOPAZ_MODEL_ID
    return value


def normalize_topaz_upscale_factor(value: object) -> int:
    if isinstance(value, bool):
        return 4
    if isinstance(value, float) and not value.is_integer():
        return 4
    try:
        factor = int(value)
    except (TypeError, ValueError):
        return 4
    if factor == 1:
        return 2
    return factor if factor in TOPAZ_UPSCALE_FACTORS else 4


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    provider_id: str
    label: str
    operations: tuple[str, ...]
    requires_network: bool
    requires_cost: bool
    preserves_alpha: bool
    requires_api_key: bool
    visible_controls: tuple[str, ...]


PROVIDER_SPECS: Final[dict[str, ProviderSpec]] = {
    "fal": ProviderSpec(
        provider_id="fal",
        label="Fal.ai",
        operations=("remove_background",),
        requires_network=True,
        requires_cost=True,
        preserves_alpha=False,
        requires_api_key=True,
        visible_controls=(
            "fal_remove_bg_model",
            "fal_birefnet_model",
            "fal_birefnet_resolution",
            "fal_birefnet_refine_foreground",
            "fal_rembg_crop_to_bbox",
        ),
    ),
    "kie": ProviderSpec(
        provider_id="kie",
        label="KIE",
        operations=("upscale_before", "upscale_after", "remove_background"),
        requires_network=True,
        requires_cost=True,
        preserves_alpha=True,
        requires_api_key=True,
        visible_controls=(
            "kie_upscale_model",
            "kie_upscale_after_model",
            "kie_remove_bg_model",
        ),
    ),
    "photoroom": ProviderSpec(
        provider_id="photoroom",
        label="PhotoRoom",
        operations=("remove_background",),
        requires_network=True,
        requires_cost=True,
        preserves_alpha=True,
        requires_api_key=True,
        visible_controls=(),
    ),
    "local_rembg": ProviderSpec(
        provider_id="local_rembg",
        label="Local rembg",
        operations=("remove_background",),
        requires_network=False,
        requires_cost=False,
        preserves_alpha=True,
        requires_api_key=False,
        visible_controls=(
            "local_rembg_profile",
            "local_rembg_model",
            "local_rembg_edge_quality",
        ),
    ),
    "local_ben2": ProviderSpec(
        provider_id="local_ben2",
        label="Local BEN2",
        operations=("remove_background",),
        requires_network=False,
        requires_cost=False,
        preserves_alpha=True,
        requires_api_key=False,
        visible_controls=(
            "local_ben2_alpha_threshold",
            "local_ben2_edge_softness",
            "local_ben2_corner_radius",
        ),
    ),
    "local_chroma_key": ProviderSpec(
        provider_id="local_chroma_key",
        label="Local Chroma Key",
        operations=("remove_background",),
        requires_network=False,
        requires_cost=False,
        preserves_alpha=True,
        requires_api_key=False,
        visible_controls=("chroma_key_color",),
    ),
    "local_realesrgan": ProviderSpec(
        provider_id="local_realesrgan",
        label="Local Real-ESRGAN",
        operations=("upscale_before", "upscale_after"),
        requires_network=False,
        requires_cost=False,
        preserves_alpha=True,
        requires_api_key=False,
        visible_controls=(
            "local_realesrgan_profile",
            "local_realesrgan_scale",
            "local_realesrgan_after_scale",
        ),
    ),
}

PROVIDER_FIELD_OPTIONS: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "upscale_before_provider": (
        ("KIE", "kie"),
        ("Local Real-ESRGAN", "local_realesrgan"),
    ),
    "upscale_after_provider": (
        ("KIE", "kie"),
        ("Local Real-ESRGAN", "local_realesrgan"),
    ),
    "remove_background_provider": (
        ("KIE", "kie"),
        ("Fal.ai", "fal"),
        ("PhotoRoom", "photoroom"),
        ("Local rembg", "local_rembg"),
        ("Local BEN2", "local_ben2"),
        ("Local Chroma Key", "local_chroma_key"),
    ),
}

KIE_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Topaz", KIE_TOPAZ_MODEL_ID),
    ("Recraft Crisp", "recraft/crisp-upscale"),
)
KIE_REMOVE_BG_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Recraft Remove Background", "recraft/remove-background"),
)
FAL_REMOVE_BG_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Bria RMBG 2.0", "fal-ai/bria/background/remove"),
    ("BiRefNet v2", "fal-ai/birefnet/v2"),
    ("Ideogram Remove Background", "fal-ai/ideogram/remove-background"),
    ("Pixelcut Background Removal", "fal-ai/pixelcut/background-removal"),
    ("rembg", "fal-ai/imageutils/rembg"),
)
FAL_UPSCALE_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("ESRGAN", "fal-ai/esrgan"),
)
FAL_BIREFNET_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Общая — Light", "General Use (Light)"),
    ("Общая — Light 2K", "General Use (Light 2K)"),
    ("Общая — Heavy", "General Use (Heavy)"),
    ("Matting", "Matting"),
    ("Портрет", "Portrait"),
    ("Общая — Dynamic", "General Use (Dynamic)"),
)
FAL_BIREFNET_RESOLUTION_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("1024×1024", "1024x1024"),
    ("2048×2048", "2048x2048"),
    ("2304×2304 (Dynamic)", "2304x2304"),
)
LOCAL_REMBG_PROFILE_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Клипарт", "clipart"),
    ("Люди", "people"),
    ("Аниме", "anime"),
    ("Запасной", "fallback"),
)
LOCAL_REMBG_PROFILE_MODELS: Final[dict[str, str]] = {
    "clipart": "birefnet-general",
    "people": "birefnet-portrait",
    "anime": "isnet-anime",
    "fallback": "isnet-general-use",
}
LOCAL_REMBG_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("BiRefNet — общий (~928 МБ при первом запуске)", "birefnet-general"),
    ("BiRefNet — портрет (~928 МБ при первом запуске)", "birefnet-portrait"),
    ("IS-Net — аниме (~168 МБ при первом запуске)", "isnet-anime"),
    ("IS-Net — общий (~170 МБ при первом запуске)", "isnet-general-use"),
)


def provider_spec(provider_id: str) -> ProviderSpec:
    try:
        return PROVIDER_SPECS[provider_id]
    except KeyError as error:
        raise KeyError(f"Unknown processing provider: {provider_id}") from error


def known_provider_ids() -> tuple[str, ...]:
    return tuple(PROVIDER_SPECS)


def processing_provider_options(field_name: str) -> tuple[tuple[str, str], ...]:
    try:
        return PROVIDER_FIELD_OPTIONS[field_name]
    except KeyError as error:
        raise KeyError(f"Unknown provider field: {field_name}") from error


def provider_supports_operation(provider_id: str, operation: str) -> bool:
    return operation in provider_spec(provider_id).operations


def provider_requires_api_key(provider_id: str) -> bool:
    return provider_spec(provider_id).requires_api_key


def provider_requires_network(provider_id: str) -> bool:
    return provider_spec(provider_id).requires_network


def provider_requires_cost(provider_id: str) -> bool:
    return provider_spec(provider_id).requires_cost


def provider_preserves_alpha(provider_id: str) -> bool:
    return provider_spec(provider_id).preserves_alpha


def upscale_model_preserves_alpha(provider_id: str, model_id: str) -> bool:
    """Return whether a selected upscale model can receive transparent input."""
    if provider_id == "kie" and model_id == "recraft/crisp-upscale":
        return False
    return provider_preserves_alpha(provider_id)


def provider_visible_controls(provider_id: str) -> tuple[str, ...]:
    return provider_spec(provider_id).visible_controls


def provider_label(provider_id: str) -> str:
    return provider_spec(provider_id).label
