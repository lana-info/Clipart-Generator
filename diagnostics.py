"""Bounded, privacy-safe diagnostic journal for the V3 desktop application."""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import tempfile
import threading
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping

from security_redaction import redact_text


DEFAULT_SESSION_MAX_BYTES = 4 * 1024 * 1024
DEFAULT_TOTAL_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_EVENT_MAX_BYTES = 16 * 1024
MAX_SESSIONS = 3

_ALLOWED_DETAILS = {
    "api_key",
    "attempt",
    "available_version",
    "configured",
    "correlation_id",
    "counts",
    "current_version",
    "decision",
    "downloaded_bytes",
    "error_code",
    "error_message",
    "filename",
    "folder_name",
    "folder_role",
    "http_status",
    "item_index",
    "item_total",
    "license_key",
    "mode",
    "model",
    "operation_type",
    "provider",
    "reason",
    "stage",
    "status",
    "task",
    "total_bytes",
}
_SECRET_KEYS = {"api_key", "license_key", "token", "proof", "password", "secret"}
_PROHIBITED_KEYS = {"prompt", "image", "raw_response", "environment", "device_private_key"}
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
    re.compile(r"\bCG-[A-Z2-7]{8,}\b", re.IGNORECASE),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{8,}"),
)
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\r\n,;]+")
_POSIX_PATH = re.compile(r"(?<![:/])/(?:[^/\s]+/)+([^/\s]+)")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any, limit: int = 512) -> str:
    text = redact_text(value, limit=limit)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[СКРЫТО]", text)
    home = str(Path.home())
    if home and home not in {"/", "."}:
        text = text.replace(home, "<путь>")
    text = _WINDOWS_PATH.sub("<путь>", text)
    text = _POSIX_PATH.sub(lambda match: f"<путь>/{match.group(1)}", text)
    return text[:limit]


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    if "\\" in text:
        text = PureWindowsPath(text).name
    else:
        text = Path(text).name
    return _safe_text(text, 200)


class DiagnosticJournal:
    def __init__(
        self,
        app_data_root: str | Path,
        *,
        app_version: str,
        now: Callable[[], datetime] | None = None,
        session_id: str | None = None,
        session_max_bytes: int = DEFAULT_SESSION_MAX_BYTES,
        total_max_bytes: int = DEFAULT_TOTAL_MAX_BYTES,
        event_max_bytes: int = DEFAULT_EVENT_MAX_BYTES,
    ) -> None:
        self.app_version = _safe_text(app_version, 64)
        self.directory = Path(app_data_root) / "diagnostics"
        self._now = now or _utc_now
        self.session_id = _safe_text(session_id or uuid.uuid4().hex, 64)
        self.session_max_bytes = max(512, int(session_max_bytes))
        self.total_max_bytes = max(self.session_max_bytes, int(total_max_bytes))
        self.event_max_bytes = max(512, min(int(event_max_bytes), self.session_max_bytes))
        timestamp = self._now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.session_path: Path | None = self.directory / f"{timestamp}-{self.session_id}.jsonl"
        self._lock = threading.RLock()
        self._truncated = False
        self._dropped_events = 0
        self._memory_fallback: list[dict[str, Any]] = []
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self.session_path.touch(exist_ok=False)
            self._prune()
        except OSError:
            self.session_path = None

    def record(
        self,
        event: str,
        summary: str,
        *,
        severity: str = "info",
        operation_id: str | None = None,
        screen: str | None = None,
        outcome: str | None = None,
        retry: str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = {
            "schema_version": 1,
            "timestamp": self._now().astimezone(timezone.utc).isoformat(),
            "severity": severity if severity in {"debug", "info", "warning", "error"} else "info",
            "event": _safe_text(event, 96),
            "summary": _safe_text(summary),
            "session_id": self.session_id,
            "app_version": self.app_version,
            "platform": _safe_text(f"{platform.system()} {platform.release()}", 120),
        }
        for name, value in (
            ("operation_id", operation_id),
            ("screen", screen),
            ("outcome", outcome),
            ("retry", retry),
        ):
            if value not in (None, ""):
                item[name] = _safe_text(value, 160)
        safe_details = self._sanitize_details(details or {})
        if safe_details:
            item["details"] = safe_details
        encoded = self._encode_bounded(item)
        with self._lock:
            if self.session_path is None:
                self._memory_fallback.append(item)
                self._memory_fallback = self._memory_fallback[-200:]
                return item
            try:
                current_size = self.session_path.stat().st_size
                if current_size + len(encoded) > self.session_max_bytes:
                    self._dropped_events += 1
                    self._write_truncated_marker(current_size)
                    return item
                with self.session_path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                self._prune()
            except OSError:
                self._memory_fallback.append(item)
                self._memory_fallback = self._memory_fallback[-200:]
        return item

    def _sanitize_details(self, details: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for raw_name, value in details.items():
            name = str(raw_name).strip().lower()
            if name in _PROHIBITED_KEYS or name not in _ALLOWED_DETAILS:
                continue
            if name in _SECRET_KEYS:
                result[name] = "[СКРЫТО]"
            elif name == "filename":
                result[name] = _safe_filename(value)
            elif isinstance(value, bool) or value is None:
                result[name] = value
            elif isinstance(value, (int, float)):
                result[name] = value
            elif isinstance(value, Mapping):
                result[name] = {
                    _safe_text(key, 64): number
                    for key, number in list(value.items())[:20]
                    if isinstance(number, (int, float, bool)) or number is None
                }
            elif isinstance(value, (list, tuple)):
                result[name] = [_safe_text(item, 160) for item in value[:20]]
            else:
                result[name] = _safe_text(value)
        return result

    def _encode_bounded(self, item: dict[str, Any]) -> bytes:
        encoded = (json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) <= self.event_max_bytes:
            return encoded
        compact = dict(item)
        compact["summary"] = _safe_text(item.get("summary"), 120)
        compact["details"] = {"status": "truncated"}
        encoded = (json.dumps(compact, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
        if len(encoded) <= self.event_max_bytes:
            return encoded
        minimal = {
            "schema_version": 1,
            "timestamp": item.get("timestamp"),
            "severity": item.get("severity"),
            "event": _safe_text(item.get("event"), 48),
            "summary": _safe_text(item.get("summary"), 60),
            "session_id": self.session_id,
        }
        return (json.dumps(minimal, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    def _write_truncated_marker(self, current_size: int) -> None:
        if self._truncated:
            return
        self._truncated = True
        marker = {
            "schema_version": 1,
            "timestamp": self._now().astimezone(timezone.utc).isoformat(),
            "severity": "warning",
            "event": "log_truncated",
            "summary": "Журнал достиг ограничения размера; повторяющиеся записи пропущены.",
            "session_id": self.session_id,
            "app_version": self.app_version,
            "platform": _safe_text(f"{platform.system()} {platform.release()}", 120),
        }
        encoded = self._encode_bounded(marker)
        if current_size + len(encoded) <= self.session_max_bytes:
            with self.session_path.open("ab") as handle:
                handle.write(encoded)

    def _prune(self) -> None:
        if self.session_path is None or not self.directory.is_dir():
            return
        files = sorted(
            self.directory.glob("*.jsonl"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
            reverse=True,
        )
        for stale in files[MAX_SESSIONS:]:
            if stale != self.session_path:
                stale.unlink(missing_ok=True)
        files = sorted(
            self.directory.glob("*.jsonl"),
            key=lambda path: (path.stat().st_mtime_ns, path.name),
        )
        total = sum(path.stat().st_size for path in files)
        for stale in files:
            if total <= self.total_max_bytes:
                break
            if stale == self.session_path:
                continue
            size = stale.stat().st_size
            stale.unlink(missing_ok=True)
            total -= size

    def read_events(self) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        paths = sorted(self.directory.glob("*.jsonl"), reverse=True) if self.directory.is_dir() else []
        for path in paths[:MAX_SESSIONS]:
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            item = json.loads(line)
                        except (ValueError, UnicodeError):
                            continue
                        if isinstance(item, dict) and item.get("schema_version") == 1:
                            events.append(item)
            except OSError:
                continue
        events.extend(self._memory_fallback)
        return sorted(events, key=lambda item: str(item.get("timestamp", "")), reverse=True)

    @staticmethod
    def format_event(event: Mapping[str, Any]) -> str:
        lines = [
            f"Время: {event.get('timestamp', '—')}",
            f"Уровень: {event.get('severity', '—')}",
            f"Событие: {event.get('event', '—')}",
            f"Описание: {event.get('summary', '—')}",
        ]
        for key, value in (event.get("details") or {}).items():
            lines.append(f"{key}: {value}")
        return "\n".join(lines)

    def export_zip(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        events = self.read_events()
        text = "\n\n".join(self.format_event(item) for item in events) + "\n"
        system = {
            "schema_version": 1,
            "app_version": self.app_version,
            "platform": platform.system(),
            "platform_release": platform.release(),
            "python": platform.python_version(),
            "session_count": len(list(self.directory.glob("*.jsonl"))) if self.directory.is_dir() else 0,
            "event_count": len(events),
        }
        fd, temporary = tempfile.mkstemp(dir=str(target.parent), prefix=".diagnostics-", suffix=".zip")
        os.close(fd)
        try:
            with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("diagnostics.txt", text)
                archive.writestr(
                    "diagnostics.json",
                    json.dumps({"schema_version": 1, "events": events}, ensure_ascii=False, indent=2),
                )
                archive.writestr("system.json", json.dumps(system, ensure_ascii=False, indent=2))
                archive.writestr(
                    "README.txt",
                    "Пакет диагностики Vibix Images. Ключи, промпты, изображения и полные личные пути не включены.\n",
                )
            os.replace(temporary, target)
        except Exception:
            Path(temporary).unlink(missing_ok=True)
            raise
        return target

    def close(self) -> None:
        if self._dropped_events:
            self.record(
                "session_summary",
                "Часть повторяющихся записей была пропущена из-за ограничения размера.",
                severity="warning",
                details={"counts": {"dropped_events": self._dropped_events}},
            )
