"""Neutral compatibility builder for the existing image WorkerThread settings snapshot."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from provider_upscale_contract import normalize_fal_upscale_factor


def build_image_worker_settings(
    runtime: Any,
    generation: Any,
    operations: Any,
    runtime_settings: Mapping[str, Any] | None,
    *,
    run_mode: str,
) -> dict[str, Any]:
    source = runtime_settings or {}
    settings = {
        name: value
        for name in ("kie_api_key", "photoroom_api_key", "fal_api_key", "local_realesrgan_dir")
        if isinstance((value := source.get(name)), str)
    }
    settings.update(dict(runtime.to_dict()))
    settings.update({
        "run_mode": run_mode,
        "text_generation_model": generation.model,
        "text_generation_ratio": generation.ratio,
        "text_generation_resolution": generation.resolution,
        "reference_generation_model": generation.reference_model,
        "reference_generation_ratio": generation.reference_ratio,
        "reference_generation_resolution": generation.reference_resolution,
        "visible_mark_cleanup_enabled": operations.visible_mark_cleanup,
        "visible_mark_cleanup_mode": operations.visible_mark_cleanup_mode,
        "invisible_watermark_cleanup_enabled": operations.invisible_watermark_cleanup,
        "upscale": operations.upscale_before,
        "upscale_provider": operations.upscale_before_provider,
        "upscale_after": operations.upscale_after,
        "upscale_after_provider": operations.upscale_after_provider,
        "upscale_factor": operations.upscale_factor,
        "kie_upscale_model": operations.kie_upscale_model,
        "kie_upscale_after_model": operations.kie_upscale_after_model,
        "fal_upscale_model": operations.fal_upscale_model,
        "fal_upscale_after_model": operations.fal_upscale_after_model,
        "fal_upscale_scale": normalize_fal_upscale_factor(operations.fal_upscale_model, operations.fal_upscale_scale),
        "fal_upscale_after_scale": operations.fal_upscale_after_scale,
        "local_realesrgan_profile": operations.local_realesrgan_profile,
        "local_realesrgan_scale": operations.local_realesrgan_scale,
        "local_realesrgan_after_scale": operations.local_realesrgan_after_scale,
        "remove_bg": operations.remove_background,
        "skip_remover_for_alpha": True,
        "remove_bg_provider": operations.remove_background_provider,
        "kie_remove_bg_model": operations.kie_remove_bg_model,
        "fal_remove_bg_model": operations.fal_remove_bg_model,
        "fal_birefnet_model": operations.fal_birefnet_model,
        "fal_birefnet_resolution": operations.fal_birefnet_resolution,
        "fal_birefnet_refine_foreground": operations.fal_birefnet_refine_foreground,
        "fal_rembg_crop_to_bbox": operations.fal_rembg_crop_to_bbox,
        "local_rembg_profile": operations.local_rembg_profile,
        "local_rembg_model": operations.local_rembg_model,
        "local_rembg_edge_quality": operations.local_rembg_edge_quality,
        "local_ben2_refine_foreground": operations.local_ben2_refine_foreground,
        "local_ben2_alpha_threshold": operations.local_ben2_alpha_threshold,
        "local_ben2_edge_softness": operations.local_ben2_edge_softness,
        "local_ben2_corner_radius": operations.local_ben2_corner_radius,
        "chroma_key_color": operations.chroma_key_color,
        "unsharp_enabled": operations.unsharp,
        "unsharp_amount": operations.unsharp_amount,
        "unsharp_radius": operations.unsharp_radius,
        "unsharp_threshold": operations.unsharp_threshold,
        "edge_shrink_enabled": operations.edge_shrink,
        "edge_shrink_pixels": operations.edge_shrink_pixels,
        "trim_enabled": operations.trim,
        "trim_mode": operations.trim_mode,
        "export_300_dpi": operations.export_300_dpi,
        "cleanup_remove_exif": operations.remove_exif,
        "cleanup_remove_xmp": operations.remove_xmp,
        "cleanup_remove_iptc": operations.remove_iptc,
        "cleanup_remove_comments_text": operations.remove_comments_text,
        "cleanup_remove_embedded_thumbnail": operations.remove_embedded_thumbnail,
        "cleanup_remove_generator_fields": operations.remove_generator_fields,
        "cleanup_remove_embedded_c2pa": operations.remove_embedded_c2pa,
        "cleanup_preserve_icc": operations.preserve_icc,
        "cleanup_preserve_dpi": operations.preserve_dpi,
    })
    return settings
