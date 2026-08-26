"""Construction of the immutable settings snapshot passed to a worker."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

KIE_CONCURRENCY_CHOICES = (1, 2, 3, 5, 10)
DEFAULT_KIE_CONCURRENCY = 3


def normalize_kie_concurrency(
    value: Any,
    *,
    legacy_value: Any = None,
) -> int:
    candidate = legacy_value if value in (None, "") else value
    try:
        normalized = int(candidate)
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_KIE_CONCURRENCY
    if normalized not in KIE_CONCURRENCY_CHOICES:
        return DEFAULT_KIE_CONCURRENCY
    return normalized


def build_runtime_settings(
    config: Mapping[str, Any],
    secrets: Mapping[str, Any],
    *,
    visible_mark_confirmed_regions: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    settings = dict(config)
    for key in (
        "kie_api_key",
        "photoroom_api_key",
        "runpod_api_key",
        "runpod_endpoint_id",
    ):
        settings[key] = str(secrets.get(key, config.get(key, "")) or "").strip()
    if visible_mark_confirmed_regions is not None:
        settings["visible_mark_confirmed_regions"] = dict(visible_mark_confirmed_regions)
    settings["kie_concurrency"] = normalize_kie_concurrency(
        settings.get("kie_concurrency"),
        legacy_value=settings.get("generation_concurrency"),
    )
    return settings
