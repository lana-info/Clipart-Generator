"""Pure, versioned persistence boundary for user preferences."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping


PREFERENCES_SCHEMA_VERSION = 1
PREFERENCES_DEFAULTS: dict[str, Any] = {
    "schema_version": PREFERENCES_SCHEMA_VERSION,
    "last_work_dir": "",
    "last_output_dir": "",
    "clipart": {},
    "pinterest": {},
    "processing": {},
}
_MODE_KEYS = frozenset({"clipart", "pinterest", "processing"})
_SECRET_KEYS = frozenset({
    "api_key", "kie_api_key", "photoroom_api_key", "runpod_api_key",
    "license_key", "token", "access_token", "private_key",
})
LEGACY_PREFERENCE_KEYS = {
    "work_dir": "last_work_dir",
    "last_work_directory": "last_work_dir",
    "output_dir": "last_output_dir",
}


def _clean_mode(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return _strip_secrets(dict(value))


def _strip_secrets(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip_secrets(item)
            for key, item in value.items()
            if str(key).casefold() not in _SECRET_KEYS
        }
    if isinstance(value, list):
        return [_strip_secrets(item) for item in value]
    return value


def migrate_preferences(value: Any) -> dict[str, Any]:
    """Migrate old preference payloads without QApplication or user paths."""
    source = dict(value) if isinstance(value, Mapping) else {}
    if source.get("schema_version", 0) not in (0, PREFERENCES_SCHEMA_VERSION):
        source = {}
    result = dict(PREFERENCES_DEFAULTS)
    for legacy_key, current_key in LEGACY_PREFERENCE_KEYS.items():
        if current_key not in source and isinstance(source.get(legacy_key), str):
            source[current_key] = source[legacy_key]
    result["last_work_dir"] = source.get("last_work_dir", "") if isinstance(source.get("last_work_dir", ""), str) else ""
    result["last_output_dir"] = source.get("last_output_dir", "") if isinstance(source.get("last_output_dir", ""), str) else ""
    for key in _MODE_KEYS:
        result[key] = _clean_mode(source.get(key))
    result["schema_version"] = PREFERENCES_SCHEMA_VERSION
    return result


def load_preferences(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return migrate_preferences({})
    try:
        raw = Path(path).read_text(encoding="utf-8")
        return migrate_preferences(json.loads(raw))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return migrate_preferences({})


def save_preferences_atomic(path: str | Path, value: Mapping[str, Any]) -> None:
    """Persist only the schema fields, replacing the file atomically."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = migrate_preferences(value)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def resolve_output_directory(work_dir: str | Path, configured: str | Path | None) -> Path:
    """Choose a writable output directory without trusting an invalid path."""
    work = Path(work_dir).expanduser()
    candidate = Path(configured).expanduser() if str(configured or "").strip() else work / "output"
    if candidate.is_dir() and os.access(candidate, os.W_OK):
        return candidate
    fallback = work / "output"
    if fallback.is_dir() and os.access(fallback, os.W_OK):
        return fallback
    return fallback
