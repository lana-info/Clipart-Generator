"""Construction of the immutable settings snapshot passed to a worker."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


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
    return settings
