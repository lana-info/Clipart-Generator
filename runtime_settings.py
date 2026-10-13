"""Construction of the immutable settings snapshot passed to a worker."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROVIDER_CONCURRENCY_CHOICES = (1, 2, 3)
DEFAULT_PROVIDER_CONCURRENCY = 3
API_CONCURRENCY_CHOICES = (1, 2, 3, 4, 5)
DEFAULT_API_CONCURRENCY = 3

# Compatibility names for existing KIE-only callers.
KIE_CONCURRENCY_CHOICES = PROVIDER_CONCURRENCY_CHOICES
DEFAULT_KIE_CONCURRENCY = DEFAULT_PROVIDER_CONCURRENCY


def normalize_provider_concurrency(
    value: Any,
    *,
    legacy_value: Any = None,
) -> int:
    candidate = legacy_value if value in (None, "") else value
    try:
        normalized = int(candidate)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_PROVIDER_CONCURRENCY
    if normalized not in PROVIDER_CONCURRENCY_CHOICES:
        return DEFAULT_PROVIDER_CONCURRENCY
    return normalized


def normalize_api_concurrency(value: Any, *, legacy_value: Any = None) -> int:
    candidate = legacy_value if value in (None, "") else value
    try:
        normalized = int(candidate)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_API_CONCURRENCY
    return normalized if normalized in API_CONCURRENCY_CHOICES else DEFAULT_API_CONCURRENCY


normalize_kie_concurrency = normalize_provider_concurrency


def build_runtime_settings(
    config: Mapping[str, Any],
    secrets: Mapping[str, Any],
    *,
    visible_mark_confirmed_regions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(config)
    for key in (
        "kie_api_key",
        "openrouter_api_key",
        "photoroom_api_key",
        "fal_api_key",
        "atlascloud_api_key",
        "piapi_api_key",
        "runpod_api_key",
        "runpod_endpoint_id",
    ):
        settings[key] = str(secrets.get(key, config.get(key, "")) or "").strip()
    if visible_mark_confirmed_regions is not None:
        settings["visible_mark_confirmed_regions"] = dict(visible_mark_confirmed_regions)
    if "api_concurrency" in settings:
        settings["api_concurrency"] = normalize_api_concurrency(settings["api_concurrency"])
    settings["kie_concurrency"] = normalize_provider_concurrency(
        settings.get("kie_concurrency"),
        legacy_value=settings.get("generation_concurrency"),
    )
    settings["photoroom_concurrency"] = normalize_provider_concurrency(
        settings.get("photoroom_concurrency")
    )
    settings["fal_concurrency"] = normalize_provider_concurrency(
        settings.get("fal_concurrency")
    )
    return settings
