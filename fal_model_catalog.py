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
        parameter_names=("prompt", "image_size", "rendering_speed", "num_images", "seed"),
    ),
    FalEndpointProfile(
        model_id="fal-ai/ideogram/v3/generate-transparent",
        operation="generation",
        supports_references=False,
        preserves_alpha=True,
        output_formats=("png",),
        price_note="Ideogram Transparent price tier is selected by request parameters",
        parameter_names=("prompt", "image_size", "rendering_speed", "num_images", "seed"),
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
        model_id="fal-ai/esrgan",
        operation="upscale",
        supports_references=True,
        preserves_alpha=None,
        output_formats=("png", "jpeg"),
        price_note="model pricing must be refreshed before live use",
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


__all__ = [
    "FAL_ENDPOINT_PROFILES",
    "FalEndpointProfile",
    "fal_endpoint_profile",
    "fal_endpoint_profiles",
]
