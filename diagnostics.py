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
from collections import deque
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Mapping

from security_redaction import redact_absolute_paths, redact_text
from provider_diagnostics import build_provider_event


DIAGNOSTIC_SCHEMA_VERSION = 2
DEFAULT_SESSION_MAX_BYTES = 8 * 1024 * 1024
DEFAULT_TOTAL_MAX_BYTES = 24 * 1024 * 1024
DEFAULT_EVENT_MAX_BYTES = 16 * 1024
DEFAULT_SESSION_MAX_EVENTS = 5_000
DEFAULT_PRIORITY_EVENT_RESERVE = 1_024
MAX_SESSIONS = 3
DEFAULT_STACK_SNAPSHOT_FILENAME = "startup-timeout-stacks.txt"

_TERMINAL_EVENTS = frozenset(
    {
        "application_exit",
        "run_cancelled",
        "run_failed",
        "run_finished",
        "session_summary",
        "unhandled_exception",
    }
)

_ALLOWED_DETAILS = {
    "api_key",
    "attempt",
    "available_version",
    "configured",
    "correlation_id",
    "response_schema",
    "expected_field",
    "retry_risk",
    "counts",
    "current_version",
    "decision",
    "downloaded_bytes",
    "duration_ms",
    "color_mode",
    "elapsed_ms",
    "enabled_stages",
    "error_code",
    "error_message",
    "filename",
    "has_alpha",
    "height",
    "image_format",
    "input_bytes",
    "folder_name",
    "folder_role",
    "http_status",
    "item_index",
    "item_total",
    "license_key",
    "mode",
    "model",
    "model_routes",
    "modules",
    "operation_type",
    "parameters",
    "poll_attempt",
    "prompt_chars",
    "prompt_index",
    "output_bytes",
    "provider",
    "provider_state",
    "provider_routes",
    "reason",
    "reference_count",
    "result_count",
    "result_index",
    "stage",
    "status",
    "task",
    "timed_out",
    "total_bytes",
    "trim_mode",
    "uploaded_bytes",
    "visible",
    "width",
}
_SECRET_KEYS = {"api_key", "license_key", "token", "proof", "password", "secret"}
_PROHIBITED_KEYS = {"prompt", "image", "raw_response", "environment", "device_private_key"}
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
    re.compile(r"\bCG-[A-Z2-7]{8,}\b", re.IGNORECASE),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]{8,}"),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any, limit: int = 512) -> str:
    text = redact_text(value, limit=limit)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[СКРЫТО]", text)
    home = str(Path.home())
    if home and home not in {"/", "."}:
        text = text.replace(home, "<путь>")
    return redact_absolute_paths(text, limit=limit).replace("<path>", "<путь>")


def _safe_filename(value: Any) -> str:
    text = str(value or "").strip()
    if "\\" in text:
        text = PureWindowsPath(text).name
    else:
        text = Path(text).name
    return _safe_text(text, 200)


def _event_sequence(item: Mapping[str, Any]) -> int:
    try:
        return max(0, int(item.get("sequence", 0) or 0))
    except (TypeError, ValueError):
        return 0


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
        session_max_events: int = DEFAULT_SESSION_MAX_EVENTS,
        priority_event_reserve: int = DEFAULT_PRIORITY_EVENT_RESERVE,
    ) -> None:
        self.app_version = _safe_text(app_version, 64)
        self.directory = Path(app_data_root) / "diagnostics"
        self._now = now or _utc_now
        self.session_id = _safe_text(session_id or uuid.uuid4().hex, 64)
        self.session_max_bytes = max(512, int(session_max_bytes))
        self.total_max_bytes = max(self.session_max_bytes, int(total_max_bytes))
        self.event_max_bytes = max(512, min(int(event_max_bytes), self.session_max_bytes))
        self.session_max_events = max(4, int(session_max_events))
        self.priority_event_reserve = min(
            max(1, int(priority_event_reserve)),
            self.session_max_events - 2,
        )
        self._normal_event_limit = (
            self.session_max_events - self.priority_event_reserve - 1
        )
        self._priority_byte_reserve = min(
            512 * 1024,
            self.session_max_bytes // 8,
        )
        timestamp = self._now().astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.session_path: Path | None = self.directory / f"{timestamp}-{self.session_id}.jsonl"
        self._lock = threading.RLock()
        self._truncated = False
        self._dropped_events = 0
        self._sequence = 0
        self._persisted_events = 0
        self._poll_states: dict[tuple[str, ...], str] = {}
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
        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        item = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "timestamp": self._now().astimezone(timezone.utc).isoformat(),
            "sequence": sequence,
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
            if not self._should_persist_event(item):
                return item
            if self.session_path is None:
                self._memory_fallback.append(item)
                self._memory_fallback = self._memory_fallback[-200:]
                return item
            try:
                current_size = self.session_path.stat().st_size
                priority = self._is_priority_event(item)
                marker_reserve = 0 if self._truncated else len(self._truncated_marker_bytes())
                normal_capacity_reached = (
                    not priority
                    and (
                        self._persisted_events >= self._normal_event_limit
                        or current_size
                        + len(encoded)
                        + marker_reserve
                        + self._priority_byte_reserve
                        > self.session_max_bytes
                    )
                )
                absolute_capacity_reached = (
                    self._persisted_events + (0 if self._truncated else 1)
                    >= self.session_max_events
                    or current_size + len(encoded) + marker_reserve
                    > self.session_max_bytes
                )
                if normal_capacity_reached or absolute_capacity_reached:
                    self._dropped_events += 1
                    self._write_truncated_marker(current_size)
                    return item
                with self.session_path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                self._persisted_events += 1
                self._prune()
            except OSError:
                self._memory_fallback.append(item)
                self._memory_fallback = self._memory_fallback[-200:]
        return item

    @staticmethod
    def _is_priority_event(item: Mapping[str, Any]) -> bool:
        return (
            str(item.get("severity") or "") in {"warning", "error"}
            or str(item.get("outcome") or "") in {"failed", "cancelled"}
            or str(item.get("event") or "") in _TERMINAL_EVENTS
        )

    def _should_persist_event(self, item: Mapping[str, Any]) -> bool:
        if item.get("event") != "provider_task_polled":
            return True
        details = item.get("details")
        if not isinstance(details, Mapping):
            return True
        key = tuple(
            str(value or "")
            for value in (
                item.get("operation_id"),
                details.get("provider"),
                details.get("task"),
                details.get("item_index"),
                details.get("stage"),
                details.get("model"),
            )
        )
        state = str(details.get("provider_state") or details.get("status") or "")
        previous_state = self._poll_states.get(key)
        self._poll_states[key] = state
        try:
            attempt = int(details.get("poll_attempt") or 0)
        except (TypeError, ValueError, OverflowError):
            attempt = 0
        return (
            previous_state is None
            or previous_state != state
            or attempt <= 1
            or attempt % 10 == 0
        )

    def record_structured(
        self,
        event: Mapping[str, Any],
        *,
        operation_id: str | None = None,
        screen: str = "results",
    ) -> dict[str, Any]:
        """Persist one already bounded provider/run event defensively."""
        try:
            source = dict(event) if isinstance(event, Mapping) else {}
            event_name = str(source.pop("event", "") or "")
            safe = build_provider_event(event_name, **source)
            name = str(safe.pop("event"))
            severity = str(safe.pop("severity", "info") or "info")
            summary = str(
                safe.pop("summary", "")
                or {
                    "item_input_inspected": "Проверены параметры исходного изображения.",
                    "stage_started": "Начат этап обработки изображения.",
                    "stage_finished": "Завершён этап обработки изображения.",
                    "provider_upload_started": "Начата загрузка изображения провайдеру.",
                    "provider_upload_finished": "Загрузка изображения провайдеру завершена.",
                    "provider_task_submitted": "Задача передана внешнему сервису.",
                    "provider_task_polled": "Получено состояние задачи внешнего сервиса.",
                    "provider_task_recovery_deferred": "Восстановление задачи внешнего сервиса временно отложено.",
                    "provider_task_succeeded": "Внешний сервис успешно завершил задачу.",
                    "provider_task_failed": "Внешний сервис завершил задачу с ошибкой.",
                    "provider_result_downloaded": "Результат внешнего сервиса загружен.",
                    "item_finished": "Обработка изображения завершена.",
                    "run_finished": "Обработка пакета завершена.",
                    "diagnostic_parse_failed": "Некорректная диагностическая запись отклонена.",
                }.get(name, "Записано техническое событие.")
            )
            outcome = safe.get("outcome")
            return self.record(
                name,
                summary,
                severity=severity,
                operation_id=operation_id,
                screen=screen,
                outcome=str(outcome) if outcome not in (None, "") else None,
                details=safe,
            )
        except Exception:
            return self.record(
                "diagnostic_parse_failed",
                "Некорректная диагностическая запись отклонена.",
                severity="warning",
                operation_id=operation_id,
                screen=screen,
                details={"status": "rejected"},
            )

    def _sanitize_details(self, details: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for raw_name, value in details.items():
            name = str(raw_name).strip().lower()
            if name in _PROHIBITED_KEYS or name not in _ALLOWED_DETAILS:
                continue
            if name in _SECRET_KEYS:
                result[name] = "[СКРЫТО]"
            elif (
                name == "task"
                and isinstance(value, str)
                and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value.strip())
                and not value.strip().casefold().startswith("sk-")
            ):
                result[name] = value.strip()
            elif name == "filename":
                result[name] = _safe_filename(value)
            elif isinstance(value, bool) or value is None:
                result[name] = value
            elif isinstance(value, (int, float)):
                result[name] = value
            elif isinstance(value, Mapping):
                nested: dict[str, Any] = {}
                for key, nested_value in list(value.items())[:20]:
                    safe_key = _safe_text(key, 64)
                    if isinstance(nested_value, bool) or nested_value is None:
                        nested[safe_key] = nested_value
                    elif isinstance(nested_value, (int, float)):
                        nested[safe_key] = nested_value
                    elif name == "parameters" and isinstance(nested_value, str):
                        nested[safe_key] = _safe_text(nested_value, 160)
                result[name] = nested
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
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
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
        encoded = self._truncated_marker_bytes()
        if (
            self._persisted_events < self.session_max_events
            and current_size + len(encoded) <= self.session_max_bytes
        ):
            with self.session_path.open("ab") as handle:
                handle.write(encoded)
            self._persisted_events += 1

    def _truncated_marker_bytes(self) -> bytes:
        marker = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
            "timestamp": self._now().astimezone(timezone.utc).isoformat(),
            "severity": "warning",
            "event": "log_truncated",
            "summary": "Журнал достиг ограничения размера; повторяющиеся записи пропущены.",
            "session_id": self.session_id,
            "app_version": self.app_version,
            "platform": _safe_text(f"{platform.system()} {platform.release()}", 120),
        }
        return self._encode_bounded(marker)

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
            recent: deque[dict[str, Any]] = deque(maxlen=self.session_max_events)
            try:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            item = json.loads(line)
                        except (ValueError, UnicodeError):
                            continue
                        if isinstance(item, dict) and item.get("schema_version") in {1, 2}:
                            recent.append(item)
            except OSError:
                continue
            events.extend(recent)
        events.extend(self._memory_fallback)
        return sorted(
            events,
            key=lambda item: (
                str(item.get("timestamp", "")),
                str(item.get("session_id", "")),
                _event_sequence(item),
            ),
            reverse=True,
        )[: self.session_max_events * MAX_SESSIONS]

    @staticmethod
    def format_event(event: Mapping[str, Any]) -> str:
        severity_labels = {
            "debug": "техническое",
            "info": "информация",
            "warning": "предупреждение",
            "error": "ошибка",
        }
        lines = [
            f"Время: {event.get('timestamp', '—')}",
            f"Уровень: {severity_labels.get(str(event.get('severity')), event.get('severity', '—'))}",
            f"Событие: {event.get('event', '—')}",
            f"Описание: {event.get('summary', '—')}",
        ]
        details = event.get("details") or {}
        if not isinstance(details, Mapping):
            return "\n".join(lines)
        labels = {
            "attempt": "Попытка",
            "color_mode": "Цветовой режим",
            "elapsed_ms": "Длительность",
            "error_code": "Код ошибки",
            "error_message": "Сообщение ошибки",
            "filename": "Файл",
            "has_alpha": "Alpha-канал",
            "http_status": "HTTP-статус",
            "image_format": "Формат",
            "input_bytes": "Размер входного файла",
            "item_index": "Номер изображения",
            "item_total": "Изображений всего",
            "model": "Модель",
            "operation_type": "Операция",
            "outcome": "Результат",
            "output_bytes": "Размер результата",
            "parameters": "Параметры",
            "poll_attempt": "Номер проверки статуса",
            "prompt_chars": "Длина промпта",
            "prompt_index": "Номер промпта",
            "provider": "Провайдер",
            "provider_state": "Состояние провайдера",
            "reference_count": "Количество референсов",
            "result_count": "Количество результатов",
            "result_index": "Номер результата",
            "stage": "Этап",
            "status": "Статус",
            "task": "Идентификатор задачи",
            "uploaded_bytes": "Загружено байт",
            "downloaded_bytes": "Скачано байт",
        }
        width = details.get("width")
        height = details.get("height")
        if width not in (None, "") and height not in (None, ""):
            lines.append(f"Размер изображения: {width} × {height}")
        for key, value in details.items():
            if key in {"width", "height", "mode"}:
                continue
            label = labels.get(str(key), str(key))
            if key == "elapsed_ms":
                value = f"{value} мс"
            elif key == "has_alpha":
                value = "есть" if value else "нет"
            lines.append(f"{label}: {value}")
        return "\n".join(lines)

    def export_zip(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        events = self.read_events()
        text = "\n\n".join(self.format_event(item) for item in events) + "\n"
        system = {
            "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
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
                    json.dumps(
                        {"schema_version": DIAGNOSTIC_SCHEMA_VERSION, "events": events},
                        ensure_ascii=False,
                        indent=2,
                    ),
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

    def save_thread_stacks(self, filename: str = DEFAULT_STACK_SNAPSHOT_FILENAME) -> str | None:
        """Save every Python thread's stack next to the journal; never raise.

        A startup or verification timeout cannot be diagnosed by the journal alone:
        the interface thread's last Python frame names the call it is stuck in.
        Returns the saved file name, or None when stacks cannot be written.
        """
        safe_name = Path(str(filename)).name[:64]
        if not re.fullmatch(r"[a-z0-9._-]{1,64}", safe_name):
            return None
        try:
            import faulthandler

            self.directory.mkdir(parents=True, exist_ok=True)
            target = self.directory / safe_name
            with target.open("w", encoding="utf-8") as handle:
                faulthandler.dump_traceback(file=handle, all_threads=True)
            return safe_name
        except Exception:
            return None

    def close(self) -> None:
        if self._dropped_events:
            self.record(
                "session_summary",
                "Часть повторяющихся записей была пропущена из-за ограничения размера.",
                severity="warning",
                details={"counts": {"dropped_events": self._dropped_events}},
            )
