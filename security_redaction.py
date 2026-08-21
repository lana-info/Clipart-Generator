"""Small, dependency-free redaction primitive for logs and user-facing errors."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


SECRET_KEY_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|authorization|bearer|credential|license[_-]?key|nonce|password|private[_-]?key|proof|secret|token)"
)
SECRET_VALUE_PATTERNS = (
    re.compile(r"(?i)sk-[a-z0-9_-]{8,}"),
    re.compile(r"(?i)(bearer\s+)[^\s,;]+"),
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|authorization|x-api-key|license[_-]?key|nonce|password|private[_-]?key|proof|secret|token)['\"]?\s*[:=]\s*['\"]?)[^&\s,;\"'}]+"
    ),
    re.compile(r"-----BEGIN [A-Z ]+-----[\s\S]*?-----END [A-Z ]+-----"),
)


def redact_text(value: Any, secrets: tuple[Any, ...] = (), limit: int = 500) -> str:
    text = str(value or "").replace("\x00", "").strip()
    for secret in secrets:
        marker = str(secret or "")
        if marker:
            text = text.replace(marker, "[hidden]")
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}[hidden]" if match.lastindex else "[hidden]", text)
    return text[:limit]


def redact_value(value: Any, secrets: tuple[Any, ...] = (), *, key: str | None = None) -> Any:
    if key and SECRET_KEY_PATTERN.search(key):
        return "[hidden]"
    if isinstance(value, Mapping):
        return {str(name): redact_value(item, secrets, key=str(name)) for name, item in value.items()}
    if isinstance(value, list):
        return [redact_value(item, secrets) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item, secrets) for item in value)
    if isinstance(value, (str, bytes, bytearray)):
        return redact_text(value.decode("utf-8", "replace") if isinstance(value, bytes) else value, secrets)
    return value
