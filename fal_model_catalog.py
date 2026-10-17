"""Explicit Fal.ai endpoint capabilities used by provider selection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class FalEndpointProfile:
    model_id: str
    operation: str
    supports_references: bool
    preserves_alpha: bool | None
    output_formats: tuple[str, ...]
    price_note: str
    parameter_names: tuple[str, ...] = ()


FAL_ENDPOINT_PROFILES: Final[tuple[FalEndpointProfile, ...]] = (
    FalEndpointProfile(
        model_id="fal-ai/flux/schnell",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("png", "jpeg"),
        price_note="model pricing must be refreshed before live use",
    ),
    FalEndpointProfile(
        model_id="fal-ai/ideogram/v3",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("png", "jpeg", "webp"),
        price_note="Ideogram V3 price tier is selected by request parameters",
        parameter_names=("prompt", "aspect_ratio", "rendering_speed", "num_images", "seed"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/ideogram/v3/generate-transparent",
        operation="generation",
        supports_references=False,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="Ideogram Transparent price tier is selected by request parameters",
        parameter_names=("prompt", "aspect_ratio", "rendering_speed", "num_images", "seed"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/recraft/v4/text-to-image",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("webp",),
        price_note="$0.04 per image",
        parameter_names=("prompt", "image_size"),
    ),
    FalEndpointProfile(
        model_id="ideogram/v4/fast",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("png", "jpeg"),
        price_note="priced per megapixel and rendering speed",
        parameter_names=("prompt", "image_size"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/flux-2/klein/4b",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("png", "jpeg"),
        price_note="$0.005 per megapixel",
        parameter_names=("prompt", "image_size"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/kling-image/o3/text-to-image",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("png", "jpeg", "webp"),
        price_note="$0.028 per image at 1K/2K; 4K is double",
        parameter_names=("prompt", "aspect_ratio", "resolution"),
    ),
    FalEndpointProfile(
        model_id="bria/fibo-gen-1.5/text-to-image",
        operation="generation",
        supports_references=False,
        preserves_alpha=False,
        output_formats=("png",),
        price_note="$0.04 per image",
        parameter_names=("prompt", "aspect_ratio", "resolution"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/bria/background/remove",
        operation="remove_background",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="model pricing must be refreshed before live use",
        parameter_names=("sync_mode",),
    ),
    FalEndpointProfile(
        model_id="fal-ai/birefnet/v2",
        operation="remove_background",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png", "webp", "gif"),
        price_note="model pricing must be refreshed before live use",
        parameter_names=(
            "model",
            "operating_resolution",
            "refine_foreground",
            "output_mask",
            "output_format",
            "sync_mode",
        ),
    ),
    FalEndpointProfile(
        model_id="fal-ai/imageutils/rembg",
        operation="remove_background",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="model pricing must be refreshed before live use",
        parameter_names=("crop_to_bbox", "sync_mode"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/ideogram/remove-background",
        operation="remove_background",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="model pricing must be refreshed before live use",
    ),
    FalEndpointProfile(
        model_id="fal-ai/pixelcut/background-removal",
        operation="remove_background",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="model pricing must be refreshed before live use",
    ),
    FalEndpointProfile(
        model_id="bria/upscale/creative",
        operation="upscale",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="$0.04 per image; refresh before live use",
        parameter_names=("preserve_alpha",),
    ),
    FalEndpointProfile(
        model_id="bria/increase-resolution",
        operation="upscale",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="model pricing must be refreshed before live use",
        parameter_names=("desired_increase", "preserve_alpha", "output_type"),
    ),
    FalEndpointProfile(
        model_id="topaz/upscale/image/precision",
        operation="upscale",
        supports_references=True,
        preserves_alpha=False,
        output_formats=("png", "jpeg"),
        price_note="$0.08 per started 24 MP of output; refresh before live use",
        parameter_names=("model", "upscale_factor", "output_format"),
    ),
    FalEndpointProfile(
        model_id="topaz/upscale/image/transparent",
        operation="upscale",
        supports_references=True,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="model pricing must be refreshed before live use",
        parameter_names=("output_format",),
    ),
    FalEndpointProfile(
        model_id="fal-ai/recraft/upscale/crisp",
        operation="upscale",
        supports_references=True,
        preserves_alpha=False,
        output_formats=("png",),
        price_note="$0.004 per image; refresh before live use",
    ),
)


def fal_endpoint_profiles(operation: str | None = None) -> tuple[FalEndpointProfile, ...]:
    if operation is None:
        return FAL_ENDPOINT_PROFILES
    return tuple(profile for profile in FAL_ENDPOINT_PROFILES if profile.operation == operation)


def fal_endpoint_profile(model_id: str, operation: str) -> FalEndpointProfile:
    for profile in FAL_ENDPOINT_PROFILES:
        if profile.model_id == model_id and profile.operation == operation:
            return profile
    raise KeyError(f"Unknown Fal.ai endpoint profile: {model_id}/{operation}")


def is_fal_generation_model(model_id: object) -> bool:
    value = str(model_id or "").strip()
    return any(
        profile.model_id == value
        for profile in fal_endpoint_profiles("generation")
    )


def is_fal_model_id(model_id: object) -> bool:
    value = str(model_id or "").strip()
    return any(profile.model_id == value for profile in FAL_ENDPOINT_PROFILES)


_IMAGE_SIZE_BY_RATIO: Final[dict[str, str]] = {
    "1:1": "square_hd",
    "3:4": "portrait_4_3",
    "4:3": "landscape_4_3",
    "9:16": "portrait_16_9",
    "16:9": "landscape_16_9",
}


def fal_generation_payload(
    model_id: str,
    prompt: str,
    ratio: str,
    resolution: str,
) -> dict[str, str]:
    """Translate shared generation controls into an endpoint-safe Fal payload."""

    profile = fal_endpoint_profile(model_id, "generation")
    from model_catalog import validate_generation_contract
    validate_generation_contract(
        model_id, has_references=False, ratio=ratio,
        resolution=resolution, prompt=prompt,
    )
    payload = {"prompt": str(prompt or "")}
    if "aspect_ratio" in profile.parameter_names:
        payload["aspect_ratio"] = str(ratio or "1:1")
    if "image_size" in profile.parameter_names:
        payload["image_size"] = _IMAGE_SIZE_BY_RATIO.get(
            str(ratio or ""), "square_hd"
        )
    if "resolution" in profile.parameter_names:
        payload["resolution"] = str(resolution or "1K")
    return payload


__all__ = [
    "FAL_ENDPOINT_PROFILES",
    "FalEndpointProfile",
    "fal_endpoint_profile",
    "fal_endpoint_profiles",
    "fal_generation_payload",
    "is_fal_generation_model",
    "is_fal_model_id",
]
