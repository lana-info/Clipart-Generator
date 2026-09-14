"""Dependency-free shared upscale identifiers and normalization rules."""
from __future__ import annotations

from typing import Final

KIE_TOPAZ_MODEL_ID: Final = "topaz/image-upscale"
FAL_BRIA_UPSCALE_MODEL_ID: Final = "bria/upscale/creative"
FAL_TOPAZ_PRECISION_MODEL_ID: Final = "topaz/upscale/image/precision"
FAL_RECRAFT_CRISP_MODEL_ID: Final = "fal-ai/recraft/upscale/crisp"
FAL_UPSCALE_MODEL_IDS: Final = frozenset({
    FAL_BRIA_UPSCALE_MODEL_ID, FAL_TOPAZ_PRECISION_MODEL_ID, FAL_RECRAFT_CRISP_MODEL_ID,
})
LEGACY_FAL_UPSCALE_MODEL_IDS: Final = frozenset({"fal-ai/esrgan"})
LEGACY_KIE_TOPAZ_MODEL_IDS: Final = frozenset({"topaz/upscale"})
TOPAZ_UPSCALE_FACTORS: Final = (2, 4)
TOPAZ_MAX_FILE_BYTES: Final = 10_000_000
TOPAZ_MAX_OUTPUT_SIDE: Final = 20_000


def normalize_kie_upscale_model(model_id: object) -> str:
    value = str(model_id or "").strip()
    if not value or value in LEGACY_KIE_TOPAZ_MODEL_IDS:
        return KIE_TOPAZ_MODEL_ID
    return value


def normalize_fal_upscale_model(model_id: object) -> str:
    value = str(model_id or "").strip()
    if not value or value in LEGACY_FAL_UPSCALE_MODEL_IDS:
        return FAL_BRIA_UPSCALE_MODEL_ID
    if value in FAL_UPSCALE_MODEL_IDS:
        return value
    return FAL_BRIA_UPSCALE_MODEL_ID


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


def normalize_fal_upscale_factor(model_id: object, value: object) -> int:
    model_id = normalize_fal_upscale_model(model_id)
    if model_id == FAL_BRIA_UPSCALE_MODEL_ID:
        return 2
    if model_id == FAL_RECRAFT_CRISP_MODEL_ID:
        return 4
    return normalize_topaz_upscale_factor(value)
