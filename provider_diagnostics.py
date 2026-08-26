"""Privacy-safe structured diagnostics for image providers and local stages."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path, PureWindowsPath
from typing import Any

from PIL import Image

from security_redaction import redact_text


_EVENTS = frozenset(
    {
        "item_input_inspected",
        "stage_started",
        "stage_finished",
        "provider_upload_started",
        "provider_upload_finished",
        "provider_task_submitted",
        "provider_task_polled",
        "provider_task_succeeded",
        "provider_task_failed",
        "provider_result_downloaded",
        "item_finished",
        "run_finished",
        "diagnostic_parse_failed",
    }
)
_FIELDS = frozenset(
    {
        "attempt",
        "color_mode",
        "elapsed_ms",
        "error_code",
        "error_message",
        "filename",
        "has_alpha",
        "height",
        "http_status",
        "image_format",
        "input_bytes",
        "item_index",
        "item_total",
        "model",
        "operation_type",
        "outcome",
        "output_bytes",
        "parameters",
        "poll_attempt",
        "prompt_chars",
        "prompt_index",
        "provider",
        "provider_state",
        "reference_count",
        "result_count",
        "result_index",
        "severity",
        "stage",
        "status",
        "summary",
        "task",
        "uploaded_bytes",
        "downloaded_bytes",
        "width",
    }
)
_PARAMETER_FIELDS = frozenset(
    {
        "amount",
        "aspect_ratio",
        "edge_pixels",
        "output_format",
        "quality",
        "radius",
        "resolution",
        "scale",
        "threshold",
        "upscale_factor",
    }
)
_STRING_FIELDS = frozenset(
    {
        "color_mode",
        "error_code",
        "error_message",
        "filename",
        "image_format",
        "model",
        "operation_type",
        "outcome",
        "provider",
        "provider_state",
        "severity",
        "stage",
        "status",
        "summary",
        "task",
    }
)
_INTEGER_FIELDS = frozenset(
    {
        "attempt",
        "elapsed_ms",
        "height",
        "http_status",
        "input_bytes",
        "item_index",
        "item_total",
        "output_bytes",
        "poll_attempt",
        "prompt_chars",
        "prompt_index",
        "reference_count",
        "result_count",
        "result_index",
        "uploaded_bytes",
        "downloaded_bytes",
        "width",
    }
)
_URL = re.compile(r"(?i)\b(?:https?|ftp)://[^\s,;]+")
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\r\n,;]+")
_POSIX_PATH = re.compile(r"(?<![:/])/(?:[^/\s]+/)+[^/\s]+")


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    name = PureWindowsPath(text).name if "\\" in text else Path(text).name
    return safe_provider_message(name)[:200]


def safe_provider_message(value: Any) -> str:
    """Return a bounded provider message with secrets, paths and URLs removed."""
    text = redact_text(value, limit=500)
    text = _URL.sub("<url>", text)
    text = _WINDOWS_PATH.sub("<path>", text)
    text = _POSIX_PATH.sub("<path>", text)
    return text[:500]


def inspect_image_metadata(path: str | Path) -> dict[str, object]:
    """Read non-content image metadata without returning the private path."""
    source = Path(path)
    result: dict[str, object] = {"filename": _safe_filename(source.name)}
    try:
        result["input_bytes"] = max(0, int(source.stat().st_size))
        with Image.open(source) as image:
            result.update(
                {
                    "image_format": safe_provider_message(image.format or "unknown")[:32],
                    "width": max(0, int(image.width)),
                    "height": max(0, int(image.height)),
                    "color_mode": safe_provider_message(image.mode or "unknown")[:32],
                    "has_alpha": "A" in image.getbands() or "transparency" in image.info,
                }
            )
    except (OSError, ValueError, TypeError):
        result["status"] = "unreadable"
    return result


def _safe_parameter_map(value: Any) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, object] = {}
    for raw_name, raw_value in value.items():
        name = str(raw_name).strip().lower()
        if name not in _PARAMETER_FIELDS:
            continue
        if isinstance(raw_value, bool) or raw_value is None:
            result[name] = raw_value
        elif isinstance(raw_value, (int, float)):
            result[name] = raw_value
        elif isinstance(raw_value, str):
            result[name] = safe_provider_message(raw_value)[:80]
    return result


def build_provider_event(event: str, **values: object) -> dict[str, object]:
    """Build an allowlisted event safe for signals, logs and persistence."""
    event_name = str(event or "").strip()
    if event_name not in _EVENTS:
        return {
            "event": "diagnostic_parse_failed",
            "severity": "warning",
            "summary": "Неизвестное диагностическое событие было отклонено.",
        }
    result: dict[str, object] = {"event": event_name}
    for raw_name, value in values.items():
        name = str(raw_name).strip().lower()
        if name not in _FIELDS or value is None:
            continue
        if name == "parameters":
            parameters = _safe_parameter_map(value)
            if parameters:
                result[name] = parameters
        elif name == "filename":
            result[name] = _safe_filename(value)
        elif name == "has_alpha":
            result[name] = bool(value)
        elif name in _INTEGER_FIELDS:
            try:
                result[name] = max(0, int(value))
            except (TypeError, ValueError, OverflowError):
                continue
        elif name in _STRING_FIELDS:
            limit = 500 if name == "error_message" else 200
            safe = safe_provider_message(value)[:limit]
            if safe:
                result[name] = safe
    if "severity" not in result:
        result["severity"] = "error" if event_name.endswith("_failed") else "info"
    return result


def count_provider_results(value: object) -> int:
    """Count provider result entries without returning or retaining their URLs."""
    parsed: object = value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return 0
    if isinstance(parsed, Mapping):
        for key in ("resultUrls", "result_urls", "urls", "images", "results"):
            candidate = parsed.get(key)
            if isinstance(candidate, (list, tuple)):
                return len(candidate)
        for key in ("result", "data", "output"):
            if key in parsed:
                count = count_provider_results(parsed.get(key))
                if count:
                    return count
    if isinstance(parsed, (list, tuple)):
        return len(parsed)
    return 0


__all__ = [
    "build_provider_event",
    "count_provider_results",
    "inspect_image_metadata",
    "safe_provider_message",
]
