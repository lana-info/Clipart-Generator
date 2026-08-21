from __future__ import annotations

from dataclasses import dataclass
from typing import Final


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
        ("PhotoRoom", "photoroom"),
        ("Local rembg", "local_rembg"),
    ),
}

KIE_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Topaz", "topaz/upscale"),
    ("Recraft Crisp", "recraft/crisp-upscale"),
)
KIE_REMOVE_BG_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Recraft Remove Background", "recraft/remove-background"),
)
LOCAL_REMBG_PROFILE_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("Клипарт", "clipart"),
    ("Люди", "people"),
    ("Аниме", "anime"),
    ("Запасной", "fallback"),
)
LOCAL_REMBG_MODEL_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    ("BiRefNet — общий", "birefnet-general"),
    ("BiRefNet — портрет", "birefnet-portrait"),
    ("IS-Net — аниме", "isnet-anime"),
    ("IS-Net — общий", "isnet-general-use"),
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
