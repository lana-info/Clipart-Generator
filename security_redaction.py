"""Small, dependency-free redaction primitive for logs and user-facing errors."""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import PurePosixPath, PureWindowsPath
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

_QUOTED_ABSOLUTE_PATH = re.compile(
    r"(?P<quote>['\"])(?P<path>(?:[A-Za-z]:[\\/]|\\{2,}|/)[^'\"\r\n]+)(?P=quote)"
)
_WINDOWS_ABSOLUTE_FILE_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])"
    r"(?:[A-Z]:[\\/]|\\{2,}[^\\/\r\n,;:'\"<>|?*]+[\\/]"
    r"[^\\/\r\n,;:'\"<>|?*]+[\\/])"
    r"(?:[^\\/\r\n,;:'\"<>|?*]+[\\/])*"
    r"[^\\/\r\n,;:'\"<>|?*]+?\.[A-Z0-9]{1,10}"
    r"(?=$|[\s,;:'\"<>\]\)}])"
)
_POSIX_ABSOLUTE_FILE_PATH = re.compile(
    r"(?i)(?<![:/A-Za-z0-9_])/"
    r"(?:[^/\r\n,;:'\"<>]+/)+"
    r"[^/\r\n,;:'\"<>]+?\.[A-Z0-9]{1,10}"
    r"(?=$|[\s,;:'\"<>\]\)}])"
)
_WINDOWS_ABSOLUTE_PATH = re.compile(
    r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/](?:[^\\/\s,;:'\"<>|?*]+[\\/])*[^\\/\s,;:'\"<>|?*]+"
)
_POSIX_ABSOLUTE_PATH = re.compile(
    r"(?<![:/A-Za-z0-9_])/(?:[^/\s,;:'\"<>]+/)+[^/\s,;:'\"<>]+"
)


def redact_absolute_paths(value: Any, known_paths: tuple[Any, ...] = (), limit: int = 500) -> str:
    """Redact absolute drive, UNC and POSIX paths while preserving basenames."""

    def replacement(raw_path: str) -> str:
        candidate = str(raw_path or "").strip()
        is_windows = PureWindowsPath(candidate).is_absolute()
        basename = (
            PureWindowsPath(candidate).name
            if is_windows
            else PurePosixPath(candidate).name
        )
        separator = "\\" if is_windows else "/"
        return f"<path>{separator}{basename}" if basename else "<path>"

    text = str(value or "")
    for raw_path in sorted(
        {str(path) for path in known_paths if str(path or "")},
        key=len,
        reverse=True,
    ):
        for variant in sorted({raw_path, repr(raw_path)[1:-1]}, key=len, reverse=True):
            text = text.replace(variant, replacement(raw_path))
    text = _QUOTED_ABSOLUTE_PATH.sub(
        lambda match: (
            f"{match.group('quote')}{replacement(match.group('path'))}"
            f"{match.group('quote')}"
        ),
        text,
    )
    for pattern in (
        _WINDOWS_ABSOLUTE_FILE_PATH,
        _POSIX_ABSOLUTE_FILE_PATH,
        _WINDOWS_ABSOLUTE_PATH,
        _POSIX_ABSOLUTE_PATH,
    ):
        text = pattern.sub(lambda match: replacement(match.group(0)), text)
    return text[: max(0, int(limit))]


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
