from __future__ import annotations

import json
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from PyQt6.QtCore import QEvent, QObject, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from v3_components import (
    DEFAULT_TOKENS,
    ButtonVariant,
    FormCard,
    V3Button,
    V3DesignTokens,
)
from security_redaction import redact_text
from provider_diagnostics import build_provider_event
from provider_error_messages import friendly_provider_error
from fal_model_catalog import is_fal_generation_model
from v3_provider_registry import normalize_fal_upscale_factor
from v3_project_state import ProjectMode, ProjectState
from v3_runtime_adapter import LEGACY_STAGE_PREFIXES, legacy_progress_stage
from run_lifecycle import RunLifecycle
from v3_transparency_preview import ClipartTransparencyPreview
from studio_run_results_extension import RunResultsExtension


MAX_RUN_ITEMS = 10_000
MAX_TECHNICAL_EVENTS = 50_000
MAX_REPORT_BYTES = 4 * 1024 * 1024
MAX_PREVIEW_BYTES = 64 * 1024 * 1024
MAX_PREVIEW_PIXELS = 100_000_000

_ITEM_START = re.compile(
    r"^\[(?P<index>\d+)/(?P<total>\d+)\] "
    r"(?:Генерация|Обработка файла:)"
)
_GENERATED_PREFIX = "Сгенерировано:"
_OUTPUT_PREFIX = "Итог сохранён:"
_ERROR_PREFIX = "Ошибка:"
_MISSING_PREFIX = "Файл не найден:"
_STOP_MARKERS = (
    "Остановлено пользователем",
    "Остановлено после текущего файла",
)
_LOG_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\r\n,;]+")
_LOG_POSIX_PATH = re.compile(r"(?<![:/])/(?:[^/\s;]+/)+([^/\s;]+)")
_READY_OUTPUT_NAME = re.compile(r"_ready(?:_\d+)?\.png$", re.IGNORECASE)


class RunQueueError(ValueError):
    pass


def format_elapsed_duration(seconds: int | float) -> str:
    total = max(0, int(round(float(seconds))))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} ч {minutes} мин {secs} сек"
    if minutes:
        return f"{minutes} мин {secs} сек"
    return f"{secs} секунд"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    """Stable progress contract; legacy worker text is adapted into this shape."""

    item_index: int | None = None
    total_items: int | None = None
    stage: str = ""
    status: str = "running"
    message: str = ""
    percent: int | None = None
    indeterminate: bool = False
    source_path: str = ""
    output_path: str = ""


class RunItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


STATUS_LABELS: dict[RunItemStatus, str] = {
    RunItemStatus.PENDING: "ожидает",
    RunItemStatus.RUNNING: "выполняется",
    RunItemStatus.SUCCEEDED: "готово",
    RunItemStatus.FAILED: "ошибка",
    RunItemStatus.CANCELLED: "отменено",
}


@dataclass
class RunItem:
    index: int
    display_name: str
    status: RunItemStatus = RunItemStatus.PENDING
    short_message: str = "Ожидает запуска."
    attempts: int = 1
    stage_statuses: dict[str, str] = field(default_factory=dict)
    source_path: str = field(default="", repr=False)
    output_path: str = field(default="", repr=False)
    payload: Any = field(default=None, repr=False)
    # Explicit editor save, distinct from a worker-supplied external path.
    editor_output_path: str = field(default="", repr=False)
    # Stages embodied by the retained input while a recovery attempt is active.
    recovery_input_stages: dict[str, str] | None = field(default=None, repr=False)
    paid_completed_stages: tuple[str, ...] = field(default=(), repr=False)

    def paid_history_stages(self) -> tuple[str, ...]:
        stages = {"upscale_before", "upscale_after", "background_removal"}
        return tuple(sorted(set(self.paid_completed_stages) | {
            name for name, status in self.stage_statuses.items()
            if name in stages and status == "complete"
        }))

    def saved_stages(self) -> dict[str, str]:
        return dict(self.recovery_input_stages if self.recovery_input_stages is not None
                    else self.stage_statuses)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        return False
    return True


def _trusted_worker_path(value: str, root: Path) -> str:
    candidate = Path(str(value).strip())
    if not candidate.is_absolute() or not _is_within(candidate, root):
        return ""
    resolved = candidate.resolve(strict=False)
    try:
        if not resolved.is_file() or resolved.stat().st_size > MAX_PREVIEW_BYTES:
            return ""
    except OSError:
        return ""
    reader = QImageReader(str(resolved))
    reader.setDecideFormatFromContent(True)
    size = reader.size()
    if (
        not size.isValid()
        or size.width() * size.height() > MAX_PREVIEW_PIXELS
        or not reader.canRead()
    ):
        return ""
    if reader.read().isNull():
        return ""
    return str(resolved)


def _stage_update(message: str) -> tuple[str, str] | None:
    return legacy_progress_stage(message)


def _failure_reason(message: str) -> tuple[str, str]:
    classified = friendly_provider_error(message)
    if classified is not None:
        return classified
    lowered = str(message).casefold()
    if "timeout" in lowered or "timed out" in lowered:
        return "timeout", "Внешний сервис не ответил вовремя."
    if "api key" in lowered or "ключ" in lowered:
        return "configuration", "Не хватает обязательной настройки запуска."
    if "not found" in lowered or "не найден" in lowered:
        return "file_unavailable", "Исходный файл недоступен."
    if "invalid" in lowered or "повреж" in lowered:
        return "invalid_image", "Файл не удалось прочитать как изображение."
    if "http" in lowered or "provider" in lowered or "сервис" in lowered:
        return "provider_error", "Внешний сервис завершил операцию с ошибкой."
    return "processing_error", "Не удалось завершить обработку файла."


def _provider_error_details(message: Any) -> dict[str, str]:
    """Extract bounded, non-secret provider diagnostics from a worker error."""
    text = redact_text(message, limit=800)
    details: dict[str, str] = {}
    for field, pattern in (
        ("task", r"(?:taskId|task_id)=([A-Za-z0-9_.:-]{1,128})"),
        ("error_code", r"(?:errorCode|error_code|code)=([A-Za-z0-9_.:-]{1,64})"),
        ("http_status", r"(?:http_status|HTTP status)=([0-9]{3})"),
    ):
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            details[field] = match.group(1)
    message_match = re.search(r"(?:message|failMsg|error_message)=([^;\]]+)", text, flags=re.IGNORECASE)
    if message_match:
        details["error_message"] = redact_text(message_match.group(1).strip(" ;"), limit=300)
    return details


def _safe_technical_error_details(message: Any) -> tuple[str, dict[str, str]]:
    technical_message = redact_text(message, limit=500)
    details = _provider_error_details(technical_message)
    details.setdefault("error_message", technical_message)
    return technical_message, details


def _safe_technical_log_text(value: Any) -> str:
    text = redact_text(value, limit=500)
    text = _LOG_WINDOWS_PATH.sub(
        lambda match: "<path>/" + match.group(0).replace("\\", "/").rsplit("/", 1)[-1],
        text,
    )
    return _LOG_POSIX_PATH.sub(lambda match: f"<path>/{match.group(1)}", text)


def _enabled_run_stages(settings: Any, mode: ProjectMode) -> list[str]:
    source = settings if isinstance(settings, dict) else dict(settings or {})
    stages: list[str] = []
    if mode is not ProjectMode.PROCESSING:
        stages.append("generation")
    for enabled, stage in (
        (source.get("visible_mark_cleanup_enabled"), "visible_mark_cleanup"),
        (source.get("invisible_watermark_cleanup_enabled"), "invisible_watermark_cleanup"),
        (source.get("upscale"), "upscale_before"),
        (source.get("unsharp_enabled"), "unsharp"),
        (source.get("remove_bg"), "background_removal"),
        (source.get("upscale_after"), "upscale_after"),
        (source.get("edge_shrink_enabled"), "edge_cleanup"),
        (source.get("trim_enabled"), "trim"),
        (
            any(
                source.get(name)
                for name in (
                    "cleanup_remove_exif",
                    "cleanup_remove_xmp",
                    "cleanup_remove_iptc",
                    "cleanup_remove_comments_text",
                    "cleanup_remove_embedded_thumbnail",
                    "cleanup_remove_generator_fields",
                    "cleanup_remove_embedded_c2pa",
                )
            ),
            "metadata_cleanup",
        ),
        (source.get("export_300_dpi"), "export_300_dpi"),
    ):
        if enabled:
            stages.append(stage)
    stages.append("export")
    return stages


def _provider_model_routes(
    settings: Any,
    mode: ProjectMode,
    items: list[RunItem] | None = None,
) -> tuple[list[str], list[str]]:
    source = settings if isinstance(settings, dict) else dict(settings or {})
    providers: list[str] = []
    models: list[str] = []
    if mode is not ProjectMode.PROCESSING:
        generation_models: list[str] = []
        for item in items or ():
            payload = item.payload if isinstance(item.payload, dict) else {}
            model_key = (
                "reference_generation_model"
                if payload.get("references")
                else "text_generation_model"
            )
            model = str(source.get(model_key) or "").strip()
            if model and model not in generation_models:
                generation_models.append(model)
        if not generation_models:
            fallback_model = str(source.get("text_generation_model") or "").strip()
            if fallback_model:
                generation_models.append(fallback_model)
        for model in generation_models:
            route = f"generation:{'fal' if is_fal_generation_model(model) else 'kie'}"
            if route not in providers:
                providers.append(route)
        for route, key in (
            ("text_generation", "text_generation_model"),
            ("reference_generation", "reference_generation_model"),
        ):
            model = str(source.get(key) or "").strip()
            if model:
                models.append(f"{route}:{model}")
    for enabled_key, stage, provider_key in (
        ("upscale", "upscale_before", "upscale_provider"),
        ("remove_bg", "background_removal", "remove_bg_provider"),
        ("upscale_after", "upscale_after", "upscale_after_provider"),
    ):
        if not source.get(enabled_key):
            continue
        provider = str(source.get(provider_key) or "unknown").strip()
        providers.append(f"{stage}:{provider}")
        if stage == "background_removal":
            model_key = (
                "kie_remove_bg_model"
                if provider == "kie"
                else "local_rembg_model"
                if provider == "local_rembg"
                else ""
            )
        elif stage == "upscale_after":
            model_key = (
                "kie_upscale_after_model"
                if provider == "kie"
                else "fal_upscale_after_model"
                if provider == "fal"
                else "local_realesrgan_after_scale"
                if provider == "local_realesrgan"
                else ""
            )
        else:
            model_key = (
                "kie_upscale_model"
                if provider == "kie"
                else "fal_upscale_model"
                if provider == "fal"
                else "local_realesrgan_profile"
                if provider == "local_realesrgan"
                else ""
            )
        model = str(source.get(model_key) or "").strip() if model_key else ""
        if provider == "local_realesrgan":
            profile = str(source.get("local_realesrgan_profile") or "clipart").strip()
            scale_key = (
                "local_realesrgan_after_scale"
                if stage == "upscale_after"
                else "local_realesrgan_scale"
            )
            scale = str(source.get(scale_key) or "").strip()
            model = f"{profile}-{scale}x" if scale else profile
        elif provider == "fal" and stage in {"upscale_before", "upscale_after"}:
            scale_key = (
                "fal_upscale_after_scale"
                if stage == "upscale_after"
                else "fal_upscale_scale"
            )
            scale = str(
                normalize_fal_upscale_factor(model, source.get(scale_key, 4))
            )
            model = f"{model}-{scale}x" if model and scale else model
        if model:
            models.append(f"{stage}:{model}")
    return providers, models


def _request_items(request: Any, mode: ProjectMode) -> list[RunItem]:
    queue_items = tuple(getattr(request, "queue_items", ()) or ())
    if queue_items:
        if len(queue_items) > MAX_RUN_ITEMS:
            raise RunQueueError("Run queue exceeds the supported item limit")
        items: list[RunItem] = []
        for index, payload in enumerate(queue_items, start=1):
            if not isinstance(payload, dict):
                raise RunQueueError("Run queue item has an invalid payload")
            variant_id = str(payload.get("variant_id") or "").strip()
            if not variant_id:
                raise RunQueueError("Run queue item has no identifier")
            items.append(
                RunItem(
                    index=index,
                    display_name=variant_id,
                    payload=dict(payload),
                )
            )
        return items
    generated = list(getattr(request, "generated_prompts", []) or [])
    selected = list(getattr(request, "selected_files", []) or [])
    if generated:
        if len(generated) > MAX_RUN_ITEMS:
            raise RunQueueError("Run queue exceeds the supported item limit")
        return [
            RunItem(
                index=index,
                display_name=f"Изображение {index}",
                payload={
                    "prompt": str(entry.get("prompt") or ""),
                    "references": list(entry.get("references") or []),
                    "chroma_key_color": str(entry.get("chroma_key_color") or ""),
                    "result_kind": entry.get("result_kind", "legacy"),
                    **({"object_id": str(entry.get("object_id") or "")}
                       if str(entry.get("object_id") or "") else {}),
                },
            )
            for index, entry in enumerate(generated, start=1)
        ]
    if selected:
        if len(selected) > MAX_RUN_ITEMS:
            raise RunQueueError("Run queue exceeds the supported item limit")
        return [
            RunItem(
                index=index,
                display_name=Path(path).name or f"Файл {index}",
                source_path=str(path),
                payload=str(path),
            )
            for index, path in enumerate(selected, start=1)
        ]
    raise RunQueueError(f"No runnable items for mode {mode.value}")


class RunQueueSession(QObject):
    changed = pyqtSignal()

    def __init__(
        self,
        request: Any,
        mode: ProjectMode,
        parent: QObject | None = None,
        diagnostic_journal: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self.request = request
        self.mode = mode
        self.work_dir = Path(str(getattr(request, "work_dir", ""))).resolve(
            strict=False
        )
        settings = getattr(request, "settings", {}) or {}
        requested_output = str(
            settings.get("output_dir") or ""
        ).strip()
        self.output_dir = (
            Path(requested_output).resolve(strict=False)
            if requested_output
            else self.work_dir / "output"
        )
        requested_workspace = str(settings.get("workspace_root") or "").strip()
        self.workspace_root = (
            Path(requested_workspace).resolve(strict=False)
            if requested_workspace
            else self.output_dir.parent
        )
        self.transient_dir = self.workspace_root / ".run"
        self.items = _request_items(request, mode)
        self.active_order = list(range(len(self.items)))
        self.current_index: int | None = None
        self.current_stage = ""
        self.activity_indeterminate = False
        self._item_progress: dict[int, int] = {}
        self._last_progress = 0
        self.running = True
        self.lifecycle = RunLifecycle()
        self.lifecycle.start()
        self.started_at = time.monotonic()
        self.finished_at: float | None = None
        self.stop_after_current_requested = False
        self._deferred_stop: Callable[[], None] | None = None
        self._technical_events: list[str] = []
        self._diagnostic_journal = diagnostic_journal
        self.operation_id = uuid.uuid4().hex
        provider_routes, model_routes = _provider_model_routes(
            settings,
            mode,
            self.items,
        )
        self._event(
            "run_started",
            count=len(self.items),
            operation_type=str(getattr(request, "mode", "") or ""),
            enabled_stages=_enabled_run_stages(settings, mode),
            provider_routes=provider_routes,
            model_routes=model_routes,
            trim_mode=(
                str(settings.get("trim_mode") or "")
                if settings.get("trim_enabled")
                else ""
            ),
        )

    def _event(self, name: str, _record_journal: bool = True, **fields: Any) -> None:
        if len(self._technical_events) >= MAX_TECHNICAL_EVENTS:
            return
        elapsed_ms = max(0, round((time.monotonic() - self.started_at) * 1000))
        parts = [
            f"seq={len(self._technical_events) + 1}",
            f"elapsed_ms={elapsed_ms}",
            f"operation_id={self.operation_id}",
            f"mode={self.mode.value}",
            f"event={name}",
        ]
        for key, value in fields.items():
            if key == "elapsed_ms" or value is None or value == "" or value == [] or value == {}:
                continue
            if key == "error_message":
                parts.append(
                    f"error_message={json.dumps(_safe_technical_log_text(value), ensure_ascii=False)}"
                )
            elif key == "filename":
                parts.append(
                    f"filename={json.dumps(_safe_technical_log_text(Path(str(value)).name), ensure_ascii=False)}"
                )
            elif isinstance(value, (bool, int)) or (
                isinstance(value, str)
                and re.fullmatch(r"[a-z0-9_.-]{1,80}", value)
            ):
                parts.append(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
            elif isinstance(value, (list, tuple)) and all(
                isinstance(item, str)
                and re.fullmatch(r"[a-z0-9_./:-]{1,160}", item)
                for item in value
            ):
                parts.append(f"{key}={','.join(value)}")
            elif isinstance(value, dict) and all(
                isinstance(item_key, str)
                and re.fullmatch(r"[a-z0-9_.-]{1,80}", item_key)
                and isinstance(item_value, (bool, int))
                for item_key, item_value in value.items()
            ):
                compact = ",".join(
                    f"{item_key}:{str(item_value).lower() if isinstance(item_value, bool) else item_value}"
                    for item_key, item_value in sorted(value.items())
                )
                parts.append(f"{key}={compact}")
        self._technical_events.append(" ".join(parts))
        if self._diagnostic_journal is not None and _record_journal:
            summaries = {
                "run_started": "Запущена обработка пакета.",
                "item_started": "Начата обработка файла.",
                "item_succeeded": "Файл обработан успешно.",
                "item_failed": "Файл завершён с ошибкой.",
                "item_cancelled": "Обработка файла отменена.",
                "run_finished": "Обработка пакета завершена.",
                "run_failed": "Обработка пакета завершена с ошибкой.",
                "run_cancelled": "Обработка пакета отменена.",
                "retry_started": "Запущен повтор ошибочных файлов.",
                "stop_after_current_requested": "Запрошена остановка после текущего файла.",
            }
            details = {"mode": self.mode.value}
            for source, target in (
                ("item", "item_index"),
                ("count", "item_total"),
                ("operation_type", "operation_type"),
                ("attempt", "attempt"),
                ("reason", "reason"),
                ("stage", "stage"),
                ("status", "status"),
                ("task", "task"),
                ("error_code", "error_code"),
                ("error_message", "error_message"),
                ("http_status", "http_status"),
                ("enabled_stages", "enabled_stages"),
                ("trim_mode", "trim_mode"),
                ("provider_routes", "provider_routes"),
                ("model_routes", "model_routes"),
                ("filename", "filename"),
                ("output_bytes", "output_bytes"),
                ("counts", "counts"),
                ("elapsed_ms", "elapsed_ms"),
            ):
                if source in fields:
                    details[target] = fields[source]
            severity = "error" if "failed" in name else "warning" if "cancel" in name or "stop" in name else "info"
            self._diagnostic_journal.record(
                name,
                summaries.get(name, "Изменилось состояние обработки."),
                severity=severity,
                operation_id=self.operation_id,
                screen="results",
                outcome=(
                    "failed" if "failed" in name else
                    "cancelled" if "cancel" in name else
                    "success" if "succeeded" in name or name == "run_finished" else None
                ),
                retry="started" if name == "retry_started" else None,
                details=details,
            )

    def handle_diagnostic(self, event: Any) -> None:
        """Correlate one worker/provider event without trusting private input."""
        try:
            source = dict(event) if isinstance(event, dict) else {}
            name = str(source.pop("event", "") or "")
            safe = build_provider_event(name, **source)
            safe_name = str(safe.pop("event"))
            safe.pop("severity", None)
            safe.pop("summary", None)

            try:
                local_index = int(safe.get("item_index", 0) or 0)
            except (TypeError, ValueError, OverflowError):
                local_index = 0
            active_item = self._active_item(local_index)
            if active_item is not None:
                # Keep completed processing stages even when indexed progress
                # suppresses the legacy text stream (parallel generation).
                stage = str(safe.get("stage") or "")
                outcome = str(safe.get("outcome") or "")
                if safe_name == "provider_task_succeeded" and stage in {
                    "upscale_before", "upscale_after", "background_removal"
                }:
                    paid = tuple(sorted(set(active_item.paid_completed_stages) | {stage}))
                    if paid != active_item.paid_completed_stages:
                        active_item.paid_completed_stages = paid
                        self.changed.emit()
                if safe_name == "stage_finished" and stage:
                    if outcome == "succeeded" or (outcome == "skipped" and safe.get("status") == "already_alpha"):
                        active_item.stage_statuses[stage] = "complete"
                    elif outcome == "failed":
                        active_item.stage_statuses[stage] = "failed"
                requested_index = active_item.index
            else:
                requested_index = (
                    self.current_index + 1 if self.current_index is not None else 1
                )
                requested_index = min(
                    max(1, requested_index),
                    max(1, len(self.items)),
                )
            safe["item_index"] = requested_index
            safe["item_total"] = len(self.items)
            if self.items:
                safe["attempt"] = self.items[requested_index - 1].attempts

            self._event(safe_name, _record_journal=False, **safe)
            if self._diagnostic_journal is not None:
                recorder = getattr(self._diagnostic_journal, "record_structured", None)
                if callable(recorder):
                    recorder(
                        {"event": safe_name, **safe},
                        operation_id=self.operation_id,
                    )
            if (
                safe_name == "run_finished"
                and str(safe.get("outcome") or "").lower() == "cancelled"
            ):
                self.handle_cancelled_terminal()
        except Exception:
            self._event(
                "diagnostic_parse_failed",
                _record_journal=False,
                status="rejected",
            )

    @property
    def technical_log(self) -> str:
        return "\n".join(self._technical_events)

    @property
    def progress_percent(self) -> int:
        total = len(self.active_order)
        if not total:
            return 0
        terminal_statuses = {
            RunItemStatus.SUCCEEDED,
            RunItemStatus.FAILED,
            RunItemStatus.CANCELLED,
        }
        accumulated = 0
        for index in self.active_order:
            item = self.items[index]
            if item.status in terminal_statuses:
                accumulated += 100
            elif item.status is RunItemStatus.RUNNING:
                accumulated += self._item_progress.get(index, 0)
        value = round(accumulated / total)
        self._last_progress = max(self._last_progress, min(100, value))
        return self._last_progress

    @property
    def failed_indices(self) -> list[int]:
        return [
            index
            for index, item in enumerate(self.items)
            if item.status is RunItemStatus.FAILED
        ]

    @property
    def retry_indices(self) -> list[int]:
        """Explicit continuation includes cancelled work, never ready outputs."""
        return [index for index, item in enumerate(self.items)
                if item.status in {RunItemStatus.FAILED, RunItemStatus.CANCELLED}]

    def counts(self) -> dict[str, int]:
        return {
            status.value: sum(item.status is status for item in self.items)
            for status in RunItemStatus
        }

    @property
    def elapsed_seconds(self) -> int:
        end = self.finished_at if self.finished_at is not None else time.monotonic()
        return max(0, round(end - self.started_at))

    @staticmethod
    def _close_running_stages(item: RunItem, status: str) -> None:
        for stage, current in tuple(item.stage_statuses.items()):
            if current == "running":
                item.stage_statuses[stage] = status

    @staticmethod
    def _successful_item_message(item: RunItem) -> str:
        return "Результат сохранён."
    def _active_item(self, local_index: int) -> RunItem | None:
        if local_index < 1 or local_index > len(self.active_order):
            return None
        global_index = self.active_order[local_index - 1]
        return self.items[global_index]

    def handle_item_progress(self, event: Any) -> None:
        """Apply one indexed lifecycle event without a shared item cursor."""
        if isinstance(event, dict):
            event = ProgressEvent(
                item_index=event.get("item_index"),
                total_items=event.get("total_items"),
                stage=str(event.get("stage") or ""),
                status=str(event.get("status") or "running"),
                message=str(event.get("message") or ""),
                percent=event.get("percent"),
                indeterminate=bool(event.get("indeterminate", False)),
                source_path=str(event.get("source_path") or ""),
                output_path=str(event.get("output_path") or ""),
            )
        if not isinstance(event, ProgressEvent):
            self._event("worker_progress_rejected", reason="invalid_event")
            return
        try:
            local_index = int(event.item_index or 0)
            total_items = int(event.total_items or 0)
        except (TypeError, ValueError, OverflowError):
            self._event("worker_progress_rejected", reason="invalid_index")
            return
        item = self._active_item(local_index)
        if item is None or total_items != len(self.active_order):
            self._event("worker_progress_rejected", reason="index_mismatch")
            return

        global_index = item.index - 1
        status = str(event.status or "running").strip().lower()
        stage = str(event.stage or "").strip()
        self.current_index = global_index
        if stage:
            self.current_stage = stage
        self.activity_indeterminate = bool(event.indeterminate)
        if event.percent is not None:
            try:
                numeric = max(0, min(100, int(event.percent)))
            except (TypeError, ValueError, OverflowError):
                numeric = None
            if numeric is not None:
                self._item_progress[global_index] = max(
                    self._item_progress.get(global_index, 0), numeric
                )
                self.activity_indeterminate = event.indeterminate or numeric <= 0

        if status == "running":
            was_pending = item.status is RunItemStatus.PENDING
            item.status = RunItemStatus.RUNNING
            item.short_message = "Выполняется."
            if stage:
                item.stage_statuses[stage] = "running"
            if was_pending:
                self._event("item_started", item=item.index, attempt=item.attempts)
        elif status in {"stage_complete", "generated"}:
            item.status = RunItemStatus.RUNNING
            if stage:
                item.stage_statuses[stage] = "complete"
            if event.source_path:
                trusted = _trusted_worker_path(event.source_path, self.transient_dir)
                if trusted:
                    item.source_path = trusted
                else:
                    self._event(
                        "worker_path_rejected",
                        item=item.index,
                        kind="generated",
                    )
        elif status in {"stage_skipped", "stage_failed"}:
            item.status = RunItemStatus.RUNNING
            if stage:
                item.stage_statuses[stage] = "failed" if status == "stage_failed" else "skipped"
            self._event(
                "stage_updated",
                item=item.index,
                stage=stage,
                status=item.stage_statuses.get(stage, "skipped"),
            )
        elif status == "succeeded":
            trusted = _trusted_worker_path(event.output_path, self.output_dir)
            if not trusted:
                self._close_running_stages(item, "failed")
                item.status = RunItemStatus.FAILED
                item.short_message = "Worker вернул недопустимый путь результата."
                self._event(
                    "item_failed",
                    item=item.index,
                    reason="output_path_rejected",
                )
            else:
                item.output_path = trusted
                item.recovery_input_stages = None
                if item.editor_output_path != trusted:
                    item.editor_output_path = ""
                self._close_running_stages(item, "complete")
                item.stage_statuses[stage or "export"] = "complete"
                failed_stage = next(
                    (
                        name
                        for name, stage_status in item.stage_statuses.items()
                        if stage_status in {"failed", "skipped"}
                    ),
                    "",
                )
                if failed_stage:
                    item.status = RunItemStatus.FAILED
                    item.short_message = (
                        "Файл сохранён для коррекции. Обработка не завершена; файл не готов к экспорту."
                    )
                    self._event(
                        "item_failed",
                        item=item.index,
                        reason="stage_failed",
                        stage=failed_stage,
                        filename=Path(trusted).name,
                    )
                else:
                    item.status = RunItemStatus.SUCCEEDED
                    item.short_message = self._successful_item_message(item)
                    self._event(
                        "item_succeeded",
                        item=item.index,
                        filename=Path(trusted).name,
                    )
            self._after_terminal_item()
        elif status == "failed":
            technical_message, technical_details = _safe_technical_error_details(
                event.message
            )
            code, user_message = _failure_reason(technical_message)
            self._close_running_stages(item, "failed")
            if stage:
                item.stage_statuses[stage] = "failed"
            item.status = RunItemStatus.FAILED
            item.short_message = user_message
            self._event(
                "item_failed",
                item=item.index,
                reason=code,
                **technical_details,
            )
            self._after_terminal_item()
        elif status == "cancelled":
            self._close_running_stages(item, "cancelled")
            if stage:
                item.stage_statuses[stage] = "cancelled"
            item.status = RunItemStatus.CANCELLED
            item.short_message = "Операция отменена безопасно."
            self._event("item_cancelled", item=item.index)
        else:
            self._event("worker_progress_rejected", reason="invalid_status")
            return
        self.changed.emit()

    def handle_progress(self, message: Any) -> None:
        if isinstance(message, dict):
            message = ProgressEvent(
                item_index=message.get("item_index"),
                total_items=message.get("total_items"),
                stage=str(message.get("stage") or ""),
                status=str(message.get("status") or "running"),
                message=str(message.get("message") or ""),
                percent=message.get("percent"),
                indeterminate=bool(message.get("indeterminate", False)),
                source_path=str(message.get("source_path") or ""),
                output_path=str(message.get("output_path") or ""),
            )
        if isinstance(message, ProgressEvent):
            self.handle_item_progress(message)
            return
        text = str(message or "").strip()
        match = _ITEM_START.match(text)
        if match:
            local_index = int(match.group("index"))
            total = int(match.group("total"))
            item = self._active_item(local_index)
            if item is None or total != len(self.active_order):
                self._event("worker_progress_rejected", reason="index_mismatch")
                return
            self.current_index = item.index - 1
            # A legacy worker emits a generic item-start message for every
            # mode. Processing must never be presented as image generation.
            self.current_stage = (
                "processing"
                if self.mode is ProjectMode.PROCESSING
                else "generation"
            )
            self.activity_indeterminate = True
            item.status = RunItemStatus.RUNNING
            item.short_message = "Выполняется."
            if isinstance(item.payload, dict):
                item.stage_statuses[self.current_stage] = "running"
            self._event(
                "item_started",
                item=item.index,
                attempt=item.attempts,
            )
            self.changed.emit()
            return

        item = (
            self.items[self.current_index]
            if self.current_index is not None
            and 0 <= self.current_index < len(self.items)
            else None
        )
        # A native stop-after-current request can emit the worker's stop
        # marker after the current item has already reported its output.  The
        # marker must therefore be handled before the terminal-item guard;
        # otherwise the session remains running with pending items.
        if any(marker in text for marker in _STOP_MARKERS):
            if self.finished_at is not None:
                return
            if item is not None and item.status is RunItemStatus.RUNNING:
                self._close_running_stages(item, "cancelled")
                item.status = RunItemStatus.CANCELLED
                item.short_message = "Операция отменена безопасно."
                self._event("item_cancelled", item=item.index)
            self._cancel_pending()
            self.running = False
            self.finished_at = time.monotonic()
            self._record_run_cancelled()
            self.changed.emit()
            return

        if item is not None and item.status in {
            RunItemStatus.SUCCEEDED, RunItemStatus.FAILED, RunItemStatus.CANCELLED
        }:
            return
        stage_update = _stage_update(text)
        if stage_update is not None and item is not None:
            stage, status = stage_update
            item.stage_statuses[stage] = status
            self._event(
                "stage_updated",
                item=item.index,
                stage=stage,
                status=status,
            )
            self.changed.emit()
            return

        if text.startswith(_GENERATED_PREFIX) and item is not None:
            raw = text[len(_GENERATED_PREFIX) :].strip()
            trusted = _trusted_worker_path(raw, self.transient_dir)
            if trusted:
                item.source_path = trusted
                item.stage_statuses["generation"] = "complete"
            else:
                self._event(
                    "worker_path_rejected",
                    item=item.index,
                    kind="generated",
                )
            self.changed.emit()
            return

        if text.startswith(_OUTPUT_PREFIX) and item is not None:
            raw = text[len(_OUTPUT_PREFIX) :].strip()
            trusted = _trusted_worker_path(raw, self.output_dir)
            if trusted:
                item.output_path = trusted
                item.recovery_input_stages = None
                if item.editor_output_path != trusted:
                    item.editor_output_path = ""
                try:
                    output_bytes = Path(trusted).stat().st_size
                except OSError:
                    output_bytes = 0
                failed_stage = next(
                    (
                        stage
                        for stage, status in item.stage_statuses.items()
                        if status in {"failed", "skipped"}
                    ),
                    "",
                )
                if failed_stage:
                    self._close_running_stages(item, "failed")
                    item.stage_statuses["export"] = "complete"
                    item.status = RunItemStatus.FAILED
                    item.short_message = (
                        "Файл сохранён для коррекции. Обработка не завершена; файл не готов к экспорту."
                    )
                    self._event(
                        "item_failed",
                        item=item.index,
                        reason="stage_failed",
                        stage=failed_stage,
                        filename=Path(trusted).name,
                        output_bytes=output_bytes,
                    )
                else:
                    self._close_running_stages(item, "complete")
                    item.stage_statuses["export"] = "complete"
                    item.status = RunItemStatus.SUCCEEDED
                    item.short_message = self._successful_item_message(item)
                    self._event(
                        "item_succeeded",
                        item=item.index,
                        filename=Path(trusted).name,
                        output_bytes=output_bytes,
                    )
            else:
                self._close_running_stages(item, "failed")
                item.status = RunItemStatus.FAILED
                item.short_message = "Worker вернул недопустимый путь результата."
                self._event(
                    "item_failed",
                    item=item.index,
                    reason="output_path_rejected",
                )
            self._after_terminal_item()
            self.changed.emit()
            return

        if text.startswith(_ERROR_PREFIX) and item is not None:
            technical_message, technical_details = _safe_technical_error_details(
                text[len(_ERROR_PREFIX) :].strip()
            )
            code, user_message = _failure_reason(technical_message)
            self._close_running_stages(item, "failed")
            item.status = RunItemStatus.FAILED
            item.short_message = user_message
            self._event(
                "item_failed",
                item=item.index,
                reason=code,
                **technical_details,
            )
            self._after_terminal_item()
            self.changed.emit()
            return

        if text.startswith(_MISSING_PREFIX) and item is not None:
            self._close_running_stages(item, "failed")
            item.status = RunItemStatus.FAILED
            item.short_message = "Исходный файл недоступен."
            self._event(
                "item_failed",
                item=item.index,
                reason="file_unavailable",
            )
            self._after_terminal_item()
            self.changed.emit()
            return

    def handle_progress_value(self, value: Any) -> None:
        if self.current_index is None:
            return
        try:
            numeric = max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return
        self._item_progress[self.current_index] = max(
            self._item_progress.get(self.current_index, 0), numeric
        )
        self.activity_indeterminate = numeric <= 0
        self.changed.emit()

    def _after_terminal_item(self) -> None:
        if self.stop_after_current_requested and self._deferred_stop is not None:
            callback = self._deferred_stop
            self._deferred_stop = None
            callback()
            self._cancel_pending()
            self.running = False
            self.finished_at = time.monotonic()
            self._record_run_cancelled()

    def _record_run_cancelled(self) -> None:
        if self.finished_at is None:
            self.finished_at = time.monotonic()
        self._event(
            "run_cancelled",
            counts=self.counts(),
            elapsed_ms=round((self.finished_at - self.started_at) * 1000),
        )

    def _cancel_pending(self) -> None:
        for item in self.items:
            if item.status is RunItemStatus.PENDING:
                item.status = RunItemStatus.CANCELLED
                item.short_message = "Не запускался после остановки."

    def request_stop_after_current(
        self,
        *,
        immediate_stop: Callable[[], None],
        native_after_current: Callable[[], None] | None = None,
    ) -> bool:
        if not self.running or self.stop_after_current_requested:
            return False
        self.stop_after_current_requested = True
        self._event("stop_after_current_requested")
        active_items = [
            item for item in self.items if item.status is RunItemStatus.RUNNING
        ]
        if active_items:
            if native_after_current is not None:
                native_after_current()
            else:
                self._deferred_stop = immediate_stop
        else:
            immediate_stop()
            self._cancel_pending()
            self.running = False
            self.finished_at = time.monotonic()
            self._record_run_cancelled()
        self.changed.emit()
        return True

    def request_immediate_stop(self, *, immediate_stop: Callable[[], None]) -> bool:
        """Interrupt the active worker and close the run immediately."""
        if not self.running:
            return False
        self._event("immediate_stop_requested")
        for item in self.items:
            if item.status is RunItemStatus.RUNNING:
                self._close_running_stages(item, "cancelled")
                item.status = RunItemStatus.CANCELLED
                item.short_message = "Операция прервана пользователем."
        self._cancel_pending()
        self.running = False
        self.finished_at = time.monotonic()
        self._record_run_cancelled()
        self.changed.emit()
        immediate_stop()
        return True

    def handle_cancelled_terminal(self) -> None:
        """Close every still-active row after a structured worker cancellation."""
        if not self.running and self.finished_at is not None:
            return
        for item in self.items:
            if item.status in {RunItemStatus.PENDING, RunItemStatus.RUNNING}:
                self._close_running_stages(item, "cancelled")
                item.status = RunItemStatus.CANCELLED
                item.short_message = "Не выполнялся после остановки."
        self.current_index = None
        self.running = False
        self.finished_at = time.monotonic()
        self._record_run_cancelled()
        self.changed.emit()

    def handle_finished(self) -> None:
        if not self.running and self.finished_at is not None:
            return
        missing_completion = False
        for item in self.items:
            if item.status in {RunItemStatus.PENDING, RunItemStatus.RUNNING}:
                missing_completion = True
                self._close_running_stages(item, "failed")
                item.status = RunItemStatus.FAILED
                item.short_message = "Worker не подтвердил сохранение результата."
                self._event(
                    "item_failed",
                    item=item.index,
                    reason="missing_completion",
                )
        incomplete = any(item.status is RunItemStatus.FAILED for item in self.items)
        # Skipped (failed) files are a normal outcome; only unfinished items
        # mean the worker never reported completion.
        reason = "missing_completion" if missing_completion else "item_failures" if incomplete else ""
        self.lifecycle.finish(error_code=reason)
        self.current_index = None
        self.running = False
        self.finished_at = time.monotonic()
        self._event(
            "run_failed" if incomplete else "run_finished",
            reason=reason,
            counts=self.counts(),
            elapsed_ms=round((self.finished_at - self.started_at) * 1000),
        )
        self.changed.emit()

    def handle_fatal_error(self, message: Any) -> None:
        if not self.running and self.finished_at is not None:
            return
        technical_message, provider_details = _safe_technical_error_details(message)
        code, user_message = _failure_reason(technical_message)
        for item in self.items:
            if item.status in {RunItemStatus.PENDING, RunItemStatus.RUNNING}:
                self._close_running_stages(item, "failed")
                item.status = RunItemStatus.FAILED
                item.short_message = user_message
                self._event(
                    "item_failed",
                    item=item.index,
                    reason=code,
                    **provider_details,
                )
        self.lifecycle.finish(error_code=code)
        self.current_index = None
        self.running = False
        self.finished_at = time.monotonic()
        self._event(
            "run_failed",
            reason=code,
            counts=self.counts(),
            elapsed_ms=round((self.finished_at - self.started_at) * 1000),
        )
        self.changed.emit()

    def _recovery_retry(self):
        """Process saved pixels first; keep generation retries separate."""
        if (getattr(self.request, "queue_items", None)
                or not getattr(self.request, "generated_prompts", None)):
            return None
        candidates = []
        for index in self.retry_indices:
            item = self.items[index]
            path = item.output_path or item.source_path
            if not path:
                continue
            candidate = Path(path)
            trusted = (path == item.editor_output_path or
                       _is_within(candidate, self.output_dir) or
                       _is_within(candidate, self.transient_dir))
            if not trusted or candidate.is_symlink() or not candidate.is_file():
                continue
            settings = dict(self.request.settings)
            saved_stages = item.saved_stages() if item.output_path else {}
            for stage, flag in (("upscale_before", "upscale"), ("upscale_after", "upscale_after"),
                                ("unsharp", "unsharp_enabled"), ("edge_cleanup", "edge_shrink_enabled")):
                if saved_stages.get(stage) == "complete":
                    settings[flag] = False
            settings["skip_remover_for_alpha"] = True
            settings["overwrite_existing"] = False
            settings["publish_recovered_source"] = True
            settings["recovery_completed_stages"] = list(item.paid_history_stages())
            # Keep the requested remover and its model. Raw generation metadata
            # restores the per-item key colour; existing alpha is preserved by
            # skip_remover_for_alpha during a manual-fix publication pass.
            if not candidates or settings == candidates[0][2]:
                candidates.append((index, str(candidate.resolve()), settings))
        if not candidates:
            return None
        settings = candidates[0][2]
        settings["task_item_indices"] = self._retry_task_indices([row[0] for row in candidates])
        request = replace(self.request, mode="mode2_process", generated_prompts=[],
                          selected_files=[row[1] for row in candidates], settings=settings)
        return [row[0] for row in candidates], request

    def _retry_task_indices(self, indices):
        original = self.request.settings.get("task_item_indices")
        return [original[index] if original is not None else index + 1 for index in indices]

    def preview_retry(self) -> Any | None:
        failed = self.retry_indices
        if self.running or not failed:
            return None
        recovery = self._recovery_retry()
        if recovery is not None:
            return recovery[1]
        queue_items = tuple(getattr(self.request, "queue_items", ()) or ())
        generated = list(getattr(self.request, "generated_prompts", []) or [])
        if queue_items:
            retry_request = replace(
                self.request,
                queue_items=tuple(
                    dict(self.items[index].payload)
                    for index in failed
                ),
            )
        elif generated:
            failed = [index for index in failed
                      if not (self.items[index].output_path or self.items[index].source_path)]
            if not failed:
                return None  # A missing saved PNG must never trigger paid regeneration.
            retry_request = replace(
                self.request,
                generated_prompts=[
                    {
                        "prompt": str(self.items[index].payload.get("prompt") or ""),
                        "references": list(
                            self.items[index].payload.get("references") or []
                        ),
                        "chroma_key_color": str(
                            self.items[index].payload.get("chroma_key_color") or ""
                        ),
                        "result_kind": self.items[index].payload.get("result_kind", "legacy"),
                        **({"object_id": str(self.items[index].payload.get("object_id") or "")}
                           if str(self.items[index].payload.get("object_id") or "") else {}),
                    }
                    for index in failed
                ],
                selected_files=[],
            )
        else:
            retry_request = replace(
                self.request,
                selected_files=[
                    str(self.items[index].payload) for index in failed
                ],
                generated_prompts=[],
            )
        if not queue_items:
            settings = dict(retry_request.settings)
            settings["task_item_indices"] = self._retry_task_indices(failed)
            retry_request = replace(retry_request, settings=settings)
        return retry_request

    def regenerable_indices(self, indices) -> list[int]:
        """Items that can be generated again from their saved prompt (not running, not file queues)."""
        if (self.running or getattr(self.request, "queue_items", None)
                or not getattr(self.request, "generated_prompts", None)):
            return []
        return sorted({
            index for index in indices
            if 0 <= index < len(self.items)
            and self.items[index].status in {
                RunItemStatus.SUCCEEDED, RunItemStatus.FAILED, RunItemStatus.CANCELLED}
            and isinstance(self.items[index].payload, dict)
            and str(self.items[index].payload.get("prompt") or "").strip()
        })

    def preview_regenerate(self, indices) -> Any | None:
        chosen = self.regenerable_indices(indices)
        if not chosen:
            return None
        entries = []
        for index in chosen:
            payload = self.items[index].payload
            entries.append({
                "prompt": str(payload.get("prompt") or ""),
                "references": list(payload.get("references") or []),
                "chroma_key_color": str(payload.get("chroma_key_color") or ""),
                "result_kind": payload.get("result_kind", "legacy"),
                **({"object_id": str(payload.get("object_id") or "")}
                   if str(payload.get("object_id") or "") else {}),
            })
        settings = dict(self.request.settings)
        settings["task_item_indices"] = self._retry_task_indices(chosen)
        settings["overwrite_existing"] = True  # the new picture replaces the chosen one
        return replace(self.request, generated_prompts=entries, selected_files=[], settings=settings)

    def prepare_regenerate(self, indices) -> Any | None:
        request = self.preview_regenerate(indices)
        if request is None:
            return None
        chosen = self.regenerable_indices(indices)
        self.active_order = list(chosen)
        for index in chosen:
            item = self.items[index]
            item.status = RunItemStatus.PENDING
            item.short_message = "Ожидает повторной генерации."
            item.output_path = ""
            item.editor_output_path = ""
            item.stage_statuses.clear()
            item.paid_completed_stages = ()
            item.recovery_input_stages = None
            item.attempts += 1
        self.current_index = None
        self._item_progress.clear()
        self._last_progress = 0
        self.running = True
        self.stop_after_current_requested = False
        self._deferred_stop = None
        self._event("regenerate_started", count=len(chosen))
        self.changed.emit()
        return request

    def prepare_retry(self) -> Any | None:
        retry_request = self.preview_retry()
        if retry_request is None:
            return None
        recovery = self._recovery_retry()
        failed = recovery[0] if recovery is not None else self.retry_indices
        if recovery is None and getattr(self.request, "generated_prompts", None):
            failed = [index for index in failed
                      if not (self.items[index].output_path or self.items[index].source_path)]
        self.active_order = list(failed)
        for index in failed:
            item = self.items[index]
            item.status = RunItemStatus.PENDING
            item.short_message = "Ожидает повторного запуска."
            if recovery is None:
                item.output_path = ""
                item.editor_output_path = ""
                item.stage_statuses.clear()
                if isinstance(item.payload, dict):
                    item.source_path = ""
            else:
                item.paid_completed_stages = item.paid_history_stages()
                item.recovery_input_stages = item.saved_stages() if item.output_path else {}
                item.stage_statuses = {key: value for key, value in item.recovery_input_stages.items()
                                       if value == "complete"}
            item.attempts += 1
        self.current_index = None
        self._item_progress.clear()
        self._last_progress = 0
        self.running = True
        self.stop_after_current_requested = False
        self._deferred_stop = None
        self._event("retry_started", count=len(failed))
        self.changed.emit()
        return retry_request


def build_safe_run_report(session: RunQueueSession) -> dict[str, Any]:
    if not isinstance(session, RunQueueSession):
        raise TypeError("session must be a RunQueueSession")
    settings = getattr(session.request, "settings", {}) or {}
    diagnostic_settings = {
        key: redact_text(str(settings[key]), limit=160)
        for key in (
            "run_mode",
            "text_generation_model",
            "reference_generation_model",
            "upscale_provider",
            "upscale_after_provider",
            "remove_bg_provider",
            "kie_upscale_model",
            "kie_upscale_after_model",
            "fal_upscale_model",
            "fal_upscale_scale",
            "kie_remove_bg_model",
        )
        if key in settings and settings[key] not in (None, "")
    }
    if diagnostic_settings.get("fal_upscale_model"):
        diagnostic_settings["fal_upscale_scale"] = str(
            normalize_fal_upscale_factor(
                diagnostic_settings["fal_upscale_model"],
                settings.get("fal_upscale_scale"),
            )
        )
    return {
        "schema_version": 1,
        "mode": session.mode.value,
        "operation_id": session.operation_id,
        "summary": session.counts(),
        "elapsed_seconds": session.elapsed_seconds,
        "settings": diagnostic_settings,
        "technical_log": redact_text(session.technical_log, limit=MAX_TECHNICAL_EVENTS * 160),
        "items": [
            {
                "index": item.index,
                "display_name": item.display_name[:260],
                "processing": item.status.value,
                "attempts": item.attempts,
                "message": redact_text(item.short_message, limit=500),
                "stages": dict(sorted(item.stage_statuses.items())),
                "file_hints": "not_inferred",
                "pixel_evidence": "not_inferred",
                "verification_handoff": "not_inferred",
            }
            for item in session.items
        ],
    }


def export_safe_run_report(
    session: RunQueueSession,
    destination: str | os.PathLike[str],
) -> Path:
    path = Path(destination)
    if path.suffix.casefold() != ".json":
        raise RunQueueError("Run report must use the .json extension")
    payload = json.dumps(
        build_safe_run_report(session),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if len(payload) > MAX_REPORT_BYTES:
        raise RunQueueError("Run report exceeds the supported size")
    parent = path.parent.resolve(strict=False)
    if not parent.is_dir():
        raise RunQueueError("Run report parent directory must already exist")
    path = parent / path.name
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(parent),
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return path


class RunQueue(QListWidget):
    def __init__(self, *, tokens: V3DesignTokens = DEFAULT_TOKENS) -> None:
        super().__init__()
        self.tokens = tokens
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def selected_rows(self) -> list[int]:
        return sorted({self.row(row) for row in self.selectedItems()})

    def refresh_items(self, items: list[RunItem]) -> None:
        selected = self.currentRow()
        chosen = self.selected_rows()
        self.clear()
        for item in items:
            label = (
                f"{item.index}. {item.display_name} — "
                f"{STATUS_LABELS[item.status]}"
            )
            row = QListWidgetItem(label)
            row.setData(Qt.ItemDataRole.UserRole, item.index - 1)
            row.setToolTip(item.short_message)
            status_colors = {
                RunItemStatus.RUNNING: self.tokens.accent_soft,
                RunItemStatus.SUCCEEDED: self.tokens.accent_soft,
                RunItemStatus.FAILED: self.tokens.error_soft,
                RunItemStatus.CANCELLED: self.tokens.warning_soft,
            }
            color = status_colors.get(item.status)
            if color:
                row.setBackground(QColor(color))
            self.addItem(row)
        if items:
            self.setCurrentRow(
                selected if 0 <= selected < len(items) else 0
            )
            for row in chosen:
                if 0 <= row < len(items):
                    self.item(row).setSelected(True)


class BeforeAfterViewer(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setProperty("v3Card", True)
        layout = QHBoxLayout(self)
        self.before = self._column(layout, "До")
        self.after = self._column(layout, "После")

    @staticmethod
    def _column(layout: QHBoxLayout, title: str) -> QLabel:
        frame = QWidget()
        column = QVBoxLayout(frame)
        label = QLabel(title)
        label.setProperty("v3Status", True)
        preview = QLabel("Нет изображения")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumSize(220, 180)
        preview.setWordWrap(True)
        preview.setAccessibleName(f"{title} изображение")
        column.addWidget(label)
        column.addWidget(preview, 1)
        layout.addWidget(frame, 1)
        return preview

    @staticmethod
    def _pixmap(path: str) -> QPixmap | None:
        if not path:
            return None
        source = Path(path)
        try:
            if not source.is_file() or source.stat().st_size > MAX_PREVIEW_BYTES:
                return None
        except OSError:
            return None
        reader = QImageReader(str(source))
        size = reader.size()
        if (
            not size.isValid()
            or size.width() * size.height() > MAX_PREVIEW_PIXELS
        ):
            return None
        target = size.scaled(
            QSize(360, 260),
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        reader.setScaledSize(target)
        image = reader.read()
        return QPixmap.fromImage(image) if not image.isNull() else None

    def set_paths(self, before: str, after: str) -> None:
        for label, path, empty in (
            (self.before, before, "Исходник недоступен"),
            (self.after, after, "Результат ещё не создан"),
        ):
            pixmap = self._pixmap(path)
            label.setPixmap(pixmap if pixmap is not None else QPixmap())
            label.setText("" if pixmap is not None else empty)


class RunCompletionDialog(QDialog):
    def __init__(self, page: "RunResultsPage", session: RunQueueSession) -> None:
        super().__init__(page)
        self.page = page
        self.setWindowTitle("Задание выполнено")
        self.setModal(False)
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        title = QLabel("Задание выполнено")
        title.setProperty("v3Title", True)
        counts = session.counts()
        self.summary_label = QLabel(
            f"Обработано: {counts['succeeded']}\n"
            f"С ошибками: {counts['failed']}\n"
            f"Пропущено: {counts['cancelled']}\n"
            f"Время: {format_elapsed_duration(session.elapsed_seconds)}"
        )
        self.summary_label.setWordWrap(True)
        folder_label = QLabel(f"Папка результата: {session.output_dir}")
        folder_label.setWordWrap(True)
        actions = QHBoxLayout()
        self.open_folder_button = V3Button(
            "Открыть папку с результатами",
            ButtonVariant.PRIMARY,
        )
        self.open_folder_button.setEnabled(session.output_dir.is_dir())
        self.open_folder_button.clicked.connect(page._open_folder)
        self.close_button = V3Button("Закрыть", ButtonVariant.SECONDARY)
        self.close_button.clicked.connect(self.close)
        actions.addWidget(self.open_folder_button)
        actions.addWidget(self.close_button)
        layout.addWidget(title)
        layout.addWidget(self.summary_label)
        layout.addWidget(folder_label)
        layout.addLayout(actions)


def transparency_candidate_paths(session: RunQueueSession) -> list[Path]:
    """Return editable final PNGs without exposing transient workspace files."""
    candidates: list[Path] = []
    seen: set[Path] = set()
    output_root = session.output_dir.resolve(strict=False)

    def add(path: str | Path, *, editor_copy: bool = False) -> None:
        candidate = Path(path)
        canonical = candidate.resolve(strict=False)
        if (
            (not editor_copy and not _READY_OUTPUT_NAME.search(candidate.name))
            or candidate.suffix.lower() != '.png'
            or candidate.is_symlink()
            or (not editor_copy and not _is_within(canonical, output_root))
            or canonical in seen
            or not candidate.is_file()
        ):
            return
        seen.add(canonical)
        candidates.append(candidate)

    for item in session.items:
        if item.status in {RunItemStatus.SUCCEEDED, RunItemStatus.FAILED} and item.output_path:
            add(item.output_path, editor_copy=item.output_path == item.editor_output_path)
    try:
        ready_outputs = sorted(
            (
                path
                for path in session.output_dir.iterdir()
                if _READY_OUTPUT_NAME.search(path.name)
            ),
            key=lambda path: path.name.casefold(),
        )
    except OSError:
        ready_outputs = []
    for path in ready_outputs:
        add(path)
    return candidates


class RunResultsPage(QWidget):
    # The alpha/brush editor is implemented but intentionally hidden in the
    # stable client release. It will return in the dedicated image-processing
    # version after a separate product review.
    SHOW_TRANSPARENCY_EDITOR = False
    # Set by RunQueueSupport when the owning controller can confirm a paid regeneration.
    regenerate_supported = False

    stop_requested = pyqtSignal()
    immediate_stop_requested = pyqtSignal()
    retry_requested = pyqtSignal()
    process_more_requested = pyqtSignal()
    regenerate_requested = pyqtSignal(object)
    finish_requested = pyqtSignal()
    transparency_requested = pyqtSignal(int)
    membership_changed = pyqtSignal()
    processing_requested = pyqtSignal(object)

    def __init__(
        self,
        state: ProjectState,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
        results_extension: RunResultsExtension | None = None,
    ) -> None:
        super().__init__()
        self.state = state
        self.results_extension = results_extension
        self.session: RunQueueSession | None = None
        self._completion_dialog: RunCompletionDialog | None = None
        self._completion_shown_at: float | None = None
        self._preview_item_index: int | None = None
        self._transparency_paths: list[Path] = []
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        page_layout.addWidget(self.scroll_area, 1)
        self.card = FormCard(
            "Выполнение и результаты",
            "Очередь, общий прогресс и результаты каждого файла.",
            tokens=tokens,
        )
        self.scroll_area.setWidget(self.card)
        self.setAccessibleName("Выполнение и результаты")

        self.summary_label = QLabel("Запуск ещё не начат.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("v3Status", True)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMaximumWidth(520)
        self.current_label = QLabel("Текущий файл: —")
        self.current_label.setWordWrap(True)
        self.queue = RunQueue(tokens=tokens)
        self.queue.setAccessibleName("Очередь выполнения")
        self.queue.setMinimumHeight(360)
        self.queue.currentRowChanged.connect(self._selection_changed)
        self.queue.itemSelectionChanged.connect(self._update_regenerate_button)
        self.queue.itemDoubleClicked.connect(self._open_transparency_item)
        self.viewer = BeforeAfterViewer()
        self.viewer.hide()
        self.transparency_preview = ClipartTransparencyPreview()
        self.transparency_preview.hide()
        self.preview_popup = QLabel(self, flags=Qt.WindowType.ToolTip)
        self.preview_popup.setWindowTitle("Предпросмотр")
        self.preview_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_popup.setMinimumSize(280, 220)
        self.preview_popup.setStyleSheet(
            "QLabel { background: #172133; border: 1px solid #5f728e; "
            "padding: 8px; color: #eaf1fb; }"
        )
        self.preview_popup.hide()
        self.queue.setMouseTracking(True)
        self.queue.viewport().setMouseTracking(True)
        self.queue.itemEntered.connect(self._show_item_preview)
        self.queue.viewport().installEventFilter(self)
        self.queue.installEventFilter(self)
        self.installEventFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.applicationStateChanged.connect(self._application_state_changed)

        self.processing_label = QLabel()
        self.stages_label = QLabel()
        self.file_hints_label = QLabel()
        self.pixel_evidence_label = QLabel()
        self.handoff_label = QLabel()
        self.technical_note = QLabel(
            "Подробности текущего и предыдущих запусков доступны по кнопке "
            "«Диагностика» в правом верхнем углу."
        )
        self.technical_note.setWordWrap(True)
        self.technical_note.setProperty("v3Small", True)
        for label in (
            self.processing_label,
            self.stages_label,
            self.file_hints_label,
            self.pixel_evidence_label,
            self.handoff_label,
        ):
            label.setWordWrap(True)
            label.setProperty("v3Small", True)

        for label in (self.stages_label, self.file_hints_label, self.pixel_evidence_label, self.handoff_label):
            label.hide()
        actions = QWidget()
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(6)
        workflow_actions = QWidget()
        workflow_layout = QHBoxLayout(workflow_actions)
        workflow_layout.setContentsMargins(0, 0, 0, 0)
        utility_actions = QWidget()
        utility_layout = QVBoxLayout(utility_actions)
        utility_layout.setContentsMargins(0, 0, 0, 0)
        utility_primary = QWidget()
        utility_primary_layout = QHBoxLayout(utility_primary)
        utility_primary_layout.setContentsMargins(0, 0, 0, 0)
        self.stop_button = V3Button(
            "Остановить после текущего файла",
            ButtonVariant.SECONDARY,
        )
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.immediate_stop_button = V3Button(
            "Прервать сейчас",
            ButtonVariant.DESTRUCTIVE,
        )
        self.immediate_stop_button.clicked.connect(self.immediate_stop_requested.emit)
        self.retry_button = V3Button(
            "Повторить ошибки",
            ButtonVariant.SECONDARY,
        )
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.process_more_button = V3Button(
            "Начать заново в этом режиме",
            ButtonVariant.SECONDARY,
        )
        self.process_more_button.clicked.connect(self.process_more_requested.emit)
        self.regenerate_button = V3Button(
            "Сгенерировать выбранные заново", ButtonVariant.SECONDARY,
        )
        self.regenerate_button.setToolTip(
            "Создать новые изображения для выбранных строк списка (Ctrl или Shift для нескольких). "
            "Платная операция: цена и подтверждение покажутся перед запуском")
        self.regenerate_button.hide()
        self.regenerate_button.clicked.connect(
            lambda: self.regenerate_requested.emit(self.queue.selected_rows()))
        self.send_to_processing_button = V3Button(
            "Обработать выбранное", ButtonVariant.SECONDARY,
        )
        self.send_to_processing_button.hide()
        self.send_to_processing_button.clicked.connect(self._send_to_processing)
        self.finish_button = V3Button(
            "Завершить и на главную",
            ButtonVariant.SECONDARY,
        )
        self.finish_button.clicked.connect(self.finish_requested.emit)
        self.open_folder_button = V3Button(
            "Открыть папку с результатами",
            ButtonVariant.PRIMARY,
        )
        self.open_folder_button.clicked.connect(self._open_folder)
        export_label = str(
            getattr(self.results_extension, "export_action_label", "") or ""
        ).strip()
        self.export_sets_button = V3Button(
            export_label or "Дополнительный экспорт", ButtonVariant.SECONDARY
        )
        self.export_sets_button.clicked.connect(self._export_sets)
        self.check_transparency_button = V3Button(
            "Проверить прозрачность",
            ButtonVariant.SECONDARY,
        )
        self.check_transparency_button.clicked.connect(
            self._request_selected_transparency
        )
        self.check_transparency_button.setToolTip(
            "Проверить прозрачность выбранного изображения и при необходимости исправить фон")
        self.retry_button.setToolTip(
            "Запустить только то, что не получилось или было отменено; готовые файлы не трогаются")
        self.process_more_button.setToolTip(
            "Очистить экран выполнения и вернуться к запуску нового прогона; файлы на диске остаются")
        self.send_to_processing_button.setToolTip(
            "Отправить выбранные готовые изображения в модуль «Обработка изображений»")
        self.check_transparency_button.hide()
        self.save_corrected_button = V3Button(
            "Сохранить исправленный PNG",
            ButtonVariant.PRIMARY,
        )
        self.save_corrected_button.clicked.connect(self._save_corrected_png)
        self.save_corrected_button.hide()
        self.save_mask_button = V3Button(
            "Сохранить alpha-маску",
            ButtonVariant.SECONDARY,
        )
        self.save_mask_button.clicked.connect(self._save_mask)
        self.save_mask_button.hide()
        for button in (
            self.stop_button,
            self.immediate_stop_button,
            self.retry_button,
            self.process_more_button,
            self.regenerate_button,
            self.send_to_processing_button,
        ):
            workflow_layout.addWidget(button)
        self.finish_button.hide()
        workflow_layout.addStretch()
        utility_primary_layout.addWidget(self.open_folder_button)
        utility_primary_layout.addWidget(self.export_sets_button)
        utility_primary_layout.addWidget(self.check_transparency_button)
        utility_primary_layout.addWidget(self.save_corrected_button)
        utility_primary_layout.addWidget(self.save_mask_button)
        utility_primary_layout.addStretch()
        utility_layout.addWidget(utility_primary)
        actions_layout.addWidget(workflow_actions)
        actions_layout.addWidget(utility_actions)
        self.workflow_actions = workflow_actions
        self.utility_actions = utility_actions

        for widget in (
            self.summary_label,
            self.progress_bar,
            self.current_label,
            self.queue,
            self.transparency_preview,
            self.processing_label,
            self.stages_label,
            self.file_hints_label,
            self.pixel_evidence_label,
            self.handoff_label,
            self.technical_note,
        ):
            self.card.add_widget(widget)
        self.action_bar = actions
        page_layout.addWidget(self.action_bar, 0)
        self.refresh_from_state()

    def set_session(self, session: RunQueueSession) -> None:
        if not isinstance(session, RunQueueSession):
            raise TypeError("session must be a RunQueueSession")
        self.session = session
        self._completion_shown_at = None
        session.changed.connect(self.refresh_from_state)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        session = self.session
        export_supported = bool(
            self.results_extension is not None
            and str(getattr(self.results_extension, "export_action_label", "") or "").strip()
        )
        self.export_sets_button.setVisible(export_supported)
        self.export_sets_button.setEnabled(
            bool(export_supported and session and not session.running and self._export_paths())
        )
        if session is None:
            self._transparency_paths = []
            self.stop_button.hide()
            self.immediate_stop_button.hide()
            self.retry_button.hide()
            self.process_more_button.hide()
            self.finish_button.hide()
            self.open_folder_button.setEnabled(False)
            self.check_transparency_button.hide()
            self.save_corrected_button.hide()
            self.save_mask_button.hide()
            self._selection_changed(-1)
            return
        self._transparency_paths = (
            transparency_candidate_paths(session) if not session.running else []
        )
        counts = session.counts()
        self.summary_label.setText(self._summary_text(session, counts))
        summary_state = "error" if counts["failed"] else "warning" if counts["cancelled"] else ""
        self.summary_label.setProperty("state", summary_state)
        self.summary_label.style().unpolish(self.summary_label)
        self.summary_label.style().polish(self.summary_label)
        self.progress_bar.setRange(0, 0 if session.running and session.activity_indeterminate else 100)
        if not (session.running and session.activity_indeterminate):
            self.progress_bar.setValue(session.progress_percent)
        current = (
            session.items[session.current_index]
            if session.current_index is not None
            and 0 <= session.current_index < len(session.items)
            else None
        )
        self.current_label.setText(
            f"Текущий файл: {current.display_name} · {self._stage_label(session.current_stage)}"
            if current is not None and session.running
            else "Текущий файл: —"
        )
        row = self.queue.currentRow()
        self.queue.refresh_items(session.items)
        if row >= 0:
            self.queue.setCurrentRow(min(row, len(session.items) - 1))
        stop_visible = session.running and not session.stop_after_current_requested
        immediate_stop_visible = session.running
        retry_visible = not session.running and bool(session.retry_indices)
        remaining = len(session.retry_indices)
        self.retry_button.setText(
            f'Доделать оставшиеся ({remaining})'
            if any(item.status is RunItemStatus.CANCELLED for item in session.items)
            else f'Повторить ошибки ({remaining})'
        )
        # Clipart: a new set starts from the project step / home, so "start again" is not offered.
        process_more_visible = not session.running and self.state.mode is not ProjectMode.CLIPART
        finish_visible = False
        self.stop_button.setVisible(stop_visible)
        self.immediate_stop_button.setVisible(immediate_stop_visible)
        self.retry_button.setVisible(retry_visible)
        self.process_more_button.setVisible(process_more_visible)
        self.finish_button.setVisible(finish_visible)
        self.workflow_actions.setVisible(
            stop_visible
            or immediate_stop_visible
            or retry_visible
            or process_more_visible
            or finish_visible
        )
        self.utility_actions.setVisible(True)
        self.stop_button.setEnabled(stop_visible)
        self.immediate_stop_button.setEnabled(immediate_stop_visible)
        self.retry_button.setEnabled(retry_visible)
        self.finish_button.setEnabled(finish_visible)
        self.open_folder_button.setEnabled(session.output_dir.is_dir())
        self._selection_changed(self.queue.currentRow())
        self._show_completion_if_needed(session)

    def _export_paths(self):
        """Only final outputs recorded by this session, never a folder scan."""
        if self.session is None or self.session.running:
            return []
        paths, seen = [], set()
        for item in self.session.items:
            if item.status is not RunItemStatus.SUCCEEDED or not item.output_path:
                continue
            path = Path(item.output_path)
            if (path.suffix.lower() != '.png' or path.is_symlink()
                    or not path.is_file() or (not _is_within(path, self.session.output_dir)
                                             and item.output_path != item.editor_output_path)):
                continue
            resolved = path.resolve()
            if resolved not in seen:
                paths.append(resolved)
                seen.add(resolved)
        return paths

    def use_edited_output(self, source, destination):
        """Adopt an editor copy without turning incomplete processing into success."""
        source, destination = Path(source), Path(destination)
        if (self.session is None or self.session.running
                or source.resolve() not in (self._export_paths() + transparency_candidate_paths(self.session))
                or destination.is_symlink()
                or not destination.is_file() or destination.suffix.lower() != '.png'):
            return
        destination = destination.resolve()
        for item in self.session.items:
            if (item.status in {RunItemStatus.SUCCEEDED, RunItemStatus.FAILED} and item.output_path
                    and Path(item.output_path).resolve() == source.resolve()):
                if self.results_extension is not None:
                    self.results_extension.on_edited_output(
                        self.state,
                        (item.output_path, str(source.resolve())),
                        destination,
                    )
                    workspace = getattr(self.session, 'workspace_root', None)
                    if workspace is not None:
                        from studio_working_files import link_edited_output
                        try:
                            link_edited_output(workspace, (item.output_path,), destination)
                        except (OSError, ValueError):
                            self.summary_label.setText(
                                'PNG сохранён; автоматическая очистка его рабочих файлов недоступна.'
                            )
                item.output_path = str(destination)
                item.editor_output_path = str(destination)
        self.membership_changed.emit()
        self.session.changed.emit()

    def _seed_bundle_membership(self):
        if self.results_extension is None or self.session is None:
            return False
        changed = bool(self.results_extension.seed_membership(
            self.state, self.session, self._export_paths()
        ))
        if changed:
            self.membership_changed.emit()
        return changed

    def _bundle_export_issues(self):
        if self.results_extension is None or self.session is None:
            return []
        return list(self.results_extension.export_issues(
            self.state, self.session, self._export_paths()
        ))

    def _alpha_qc_reports(self, paths=None):
        if self.results_extension is None or self.session is None:
            return []
        requested = None
        export_paths = ()
        if paths is not None:
            requested = []
            for path in paths:
                try:
                    requested.append(Path(path).resolve())
                except OSError:
                    continue
        else:
            export_paths = tuple(self._export_paths())
        return list(self.results_extension.quality_reports(
            self.state, self.session, export_paths, requested
        ))

    def _request_quality_fix(self, path):
        if self.session is None:
            return
        try:
            target = Path(path).resolve()
        except OSError:
            return
        for index, item in enumerate(self.session.items):
            if item.status is not RunItemStatus.SUCCEEDED or not item.output_path:
                continue
            try:
                candidate = Path(item.output_path).resolve()
            except OSError:
                continue
            if candidate == target:
                self.transparency_requested.emit(index)
                return

    def _export_sets(self):
        if self.results_extension is None:
            return
        self._seed_bundle_membership()
        paths = self._export_paths()
        if not paths:
            return
        self.results_extension.open_export_dialog(
            self,
            self.state,
            paths,
            review_issues=self._bundle_export_issues(),
            quality_reports=self._alpha_qc_reports(paths),
            on_membership_saved=self._save_export_membership,
            on_fix_requested=self._request_quality_fix,
        )

    def _save_export_membership(self, membership):
        if self.results_extension is None:
            return
        self.results_extension.save_membership(self.state, membership)
        self.membership_changed.emit()

    @staticmethod
    def _stage_label(stage: str) -> str:
        return {
            "processing": "идёт обработка",
            "background_removal": "удаляется фон",
            "upscale": "увеличивается изображение",
            "unsharp": "повышается резкость",
            "edge_cleanup": "очищается край",
            "metadata_cleanup": "очищаются метаданные",
            "export_300_dpi": "сохраняется PNG",
            "generation": "создаётся изображение",
            "export": "сохраняется результат",
            "trim": "подготавливается изображение",
        }.get(stage, "подготовка")

    @staticmethod
    def _summary_text(session: RunQueueSession, counts: dict[str, int]) -> str:
        if session.running:
            heading = "Обработка выполняется"
        elif counts["failed"]:
            heading = "Обработка завершена с ошибками"
        elif counts["cancelled"]:
            heading = "Обработка завершена не полностью"
        else:
            heading = "Обработка завершена успешно"
        return (
            f"{heading}\n"
            f"✓ Обработано: {counts['succeeded']}   "
            f"⚠ Ошибки: {counts['failed']}   "
            f"⏭ Пропущено: {counts['cancelled']}   "
            f"Всего: {len(session.items)}\n"
            f"📁 Папка результата: {session.output_dir}\n"
            f"⏱ Время: {format_elapsed_duration(session.elapsed_seconds)}"
        )

    def _selected_item(self, row: int) -> RunItem | None:
        if (
            self.session is None
            or row < 0
            or row >= len(self.session.items)
        ):
            return None
        return self.session.items[row]

    def _open_transparency_item(self, row: QListWidgetItem) -> None:
        if self.state.mode not in {ProjectMode.CLIPART, ProjectMode.PROCESSING}:
            return
        item_index = row.data(Qt.ItemDataRole.UserRole)
        item = self._selected_item(item_index)
        if (
            item is None
            or item.status not in {RunItemStatus.SUCCEEDED, RunItemStatus.FAILED}
            or not item.output_path
        ):
            return
        self.transparency_requested.emit(int(item_index))

    def _request_selected_transparency(self) -> None:
        row = self.queue.currentRow()
        if (
            self.state.mode not in {ProjectMode.CLIPART, ProjectMode.PROCESSING}
            or self.session is None
            or self.session.running
            or not self._transparency_paths
        ):
            return
        self.transparency_requested.emit(row)

    def processing_selection(self) -> list[str]:
        if self.session is None or self.session.running:
            return []
        item = self._selected_item(self.queue.currentRow())
        if item is None:
            return []
        if item.status not in {RunItemStatus.SUCCEEDED, RunItemStatus.FAILED}:
            return []
        path = item.output_path
        if not path or Path(path).is_symlink():
            return []
        root = Path(path).parent if path == item.editor_output_path else self.session.output_dir
        trusted = _trusted_worker_path(path, root)
        return [trusted] if trusted else []

    def _send_to_processing(self) -> None:
        paths = self.processing_selection()
        if paths:
            self.processing_requested.emit(paths)

    def _update_regenerate_button(self) -> None:
        session = self.session
        visible = bool(
            session is not None and self.regenerate_supported
            and self.state.mode is ProjectMode.CLIPART
            and session.regenerable_indices(self.queue.selected_rows()))
        self.regenerate_button.setVisible(visible)
        self.regenerate_button.setEnabled(visible)
        self.workflow_actions.setVisible(
            visible or any(button.isVisibleTo(self.workflow_actions) for button in (
                self.stop_button, self.immediate_stop_button, self.retry_button,
                self.process_more_button)))

    def _selection_changed(self, row: int) -> None:
        self._update_regenerate_button()
        self.send_to_processing_button.setEnabled(bool(self.processing_selection()))
        item = self._selected_item(row)
        if item is None:
            self.preview_popup.hide()
            self.transparency_preview.hide()
            self.check_transparency_button.hide()
            self.save_corrected_button.hide()
            self._set_status_label(
                self.processing_label,
                "Ожидание запуска",
                RunItemStatus.PENDING,
            )
            self.stages_label.setText("Этапы: ещё не начаты")
            self.file_hints_label.setText("Дополнительные сведения доступны в центре проверки")
            self.pixel_evidence_label.setText("Проверка пикселей: не выполнялась")
            self.handoff_label.setText("Передача на проверку: не выполнялась")
            return
        self.preview_popup.hide()
        if self.SHOW_TRANSPARENCY_EDITOR and self.state.mode is ProjectMode.CLIPART:
            preview_path = (
                item.output_path
                if item.status is RunItemStatus.SUCCEEDED
                else item.source_path
            )
            self.transparency_preview.set_path(preview_path)
            self.transparency_preview.show()
            self.save_corrected_button.setVisible(
                item.status is RunItemStatus.SUCCEEDED
                and bool(item.output_path)
            )
            self.save_mask_button.setVisible(
                item.status is RunItemStatus.SUCCEEDED
                and bool(item.output_path)
            )
        else:
            self.transparency_preview.hide()
            self.save_corrected_button.hide()
            self.save_mask_button.hide()
        self.check_transparency_button.setVisible(
            self.state.mode in {ProjectMode.CLIPART, ProjectMode.PROCESSING}
            and self.session is not None
            and not self.session.running
            and bool(self._transparency_paths)
        )
        # Transparency check is the key next step: it is the highlighted button while
        # shown; "Открыть папку" is then an ordinary one.
        # One main button by situation: unfinished work first, then the transparency check.
        retry_main = self.retry_button.isVisibleTo(self)
        check_main = self.check_transparency_button.isVisibleTo(self) and not retry_main
        self.retry_button.set_variant(ButtonVariant.PRIMARY if retry_main else ButtonVariant.SECONDARY)
        self.check_transparency_button.set_variant(
            ButtonVariant.PRIMARY if check_main else ButtonVariant.SECONDARY)
        self.open_folder_button.set_variant(
            ButtonVariant.SECONDARY if retry_main or check_main else ButtonVariant.PRIMARY)
        status_titles = {
            RunItemStatus.PENDING: ("Ожидает запуска", "•"),
            RunItemStatus.RUNNING: ("Обработка выполняется", "●"),
            RunItemStatus.SUCCEEDED: ("Файл обработан", "✓"),
            RunItemStatus.FAILED: ("Файл не обработан", "⚠"),
            RunItemStatus.CANCELLED: ("Файл пропущен", "—"),
        }
        title, icon = status_titles[item.status]
        detail = item.short_message
        self._set_status_label(
            self.processing_label,
            f"{icon} {title}\n{detail}",
            item.status,
        )
        stage_text = ", ".join(
            f"{name}={status}"
            for name, status in sorted(item.stage_statuses.items())
        ) or "not_started"
        self.stages_label.setText(f"Этапы обработки: {stage_text}")
        verification_records = ()
        if self.state.mode is ProjectMode.PROCESSING:
            mode_data = getattr(self.state, "data", None)
            if mode_data is None:
                mode_data = getattr(self.state, "processing", None)
            verification_records = getattr(mode_data, "verification_records", ())
        record = next(
            (
                candidate
                for candidate in verification_records
                if candidate.file_path == item.source_path
            ),
            None,
        )
        self.file_hints_label.setText("Дополнительные сведения доступны в центре проверки")
        self.pixel_evidence_label.setText(
            "Проверка пикселей: "
            + (record.synthid_status if record is not None else "не выполнялась")
        )
        self.handoff_label.setText(
            "Передача на проверку: "
            + (record.openai_status if record is not None else "не выполнялась")
        )

    def _show_item_preview(self, row: QListWidgetItem | None) -> None:
        if row is None or self.session is None:
            self._hide_item_preview()
            return
        item_index = row.data(Qt.ItemDataRole.UserRole)
        item = self._selected_item(item_index)
        if item is None:
            self._hide_item_preview()
            return
        self._preview_item_index = item_index
        path = item.output_path or item.source_path
        pixmap = BeforeAfterViewer._pixmap(path)
        self.preview_popup.clear()
        if pixmap is None:
            self.preview_popup.setText("Предпросмотр недоступен")
        else:
            self.preview_popup.setPixmap(
                pixmap.scaled(
                    QSize(360, 280),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        rect = self.queue.visualItemRect(row)
        point = self.queue.viewport().mapToGlobal(rect.topRight())
        self.preview_popup.adjustSize()
        self.preview_popup.move(point.x() - self.preview_popup.width(), point.y())
        self.preview_popup.show()

    def _hide_item_preview(self) -> None:
        self._preview_item_index = None
        self.preview_popup.hide()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        event_type = event.type()
        if (
            watched is self.queue.viewport()
            and event_type == QEvent.Type.MouseMove
        ):
            hovered = self.queue.itemAt(event.position().toPoint())
            if hovered is None:
                self._hide_item_preview()
            else:
                hovered_index = hovered.data(Qt.ItemDataRole.UserRole)
                if hovered_index != self._preview_item_index:
                    self._show_item_preview(hovered)
        if event_type in {
            QEvent.Type.Leave,
            QEvent.Type.WindowDeactivate,
            QEvent.Type.ApplicationDeactivate,
        }:
            self._hide_item_preview()
        elif (
            event_type is QEvent.Type.KeyPress
            and getattr(event, "key", lambda: None)() == Qt.Key.Key_Escape
        ):
            self._hide_item_preview()
        return super().eventFilter(watched, event)

    def _application_state_changed(self, state: Qt.ApplicationState) -> None:
        if state is not Qt.ApplicationState.ApplicationActive:
            self._hide_item_preview()

    def reset_transient_ui(self) -> None:
        self._hide_item_preview()
        if self._completion_dialog is not None:
            self._completion_dialog.close()
            self._completion_dialog.deleteLater()
            self._completion_dialog = None
        self._completion_shown_at = None

    def hideEvent(self, event: Any) -> None:
        self.reset_transient_ui()
        super().hideEvent(event)

    def _show_completion_if_needed(self, session: RunQueueSession) -> None:
        if session.running:
            if self._completion_dialog is not None:
                self._completion_dialog.close()
                self._completion_dialog.deleteLater()
                self._completion_dialog = None
            return
        if session.finished_at is None:
            return
        if self._completion_shown_at == session.finished_at:
            return
        self._completion_shown_at = session.finished_at
        if self._completion_dialog is not None:
            self._completion_dialog.close()
        self._completion_dialog = RunCompletionDialog(self, session)
        self._completion_dialog.show()

    @staticmethod
    def _set_status_label(
        label: QLabel,
        text: str,
        status: RunItemStatus,
    ) -> None:
        state = {
            RunItemStatus.FAILED: "error",
            RunItemStatus.CANCELLED: "warning",
            RunItemStatus.RUNNING: "warning",
        }.get(status, "")
        label.setText(text)
        label.setProperty("state", state)
        label.style().unpolish(label)
        label.style().polish(label)

    def _open_folder(self) -> None:
        if self.session is None or not self.session.output_dir.is_dir():
            self.summary_label.setText("Папка результата ещё не создана.")
            return
        if not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.session.output_dir))
        ):
            self.summary_label.setText("Не удалось открыть папку результата.")

    def _save_corrected_png(self) -> None:
        if self.session is None or self.state.mode is not ProjectMode.CLIPART:
            return
        item = self._selected_item(self.queue.currentRow())
        if item is None or item.status is not RunItemStatus.SUCCEEDED:
            return
        source = Path(item.output_path)
        default = self.session.output_dir / f"{source.stem}_corrected.png"
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить исправленный PNG",
            str(default),
            "PNG (*.png)",
        )
        if not destination:
            return
        try:
            self.transparency_preview.save_corrected_png(destination)
            self.summary_label.setText(
                f"Исправленный PNG сохранён: {Path(destination).name}"
            )
        except (OSError, ValueError) as error:
            self.summary_label.setText(f"Не удалось сохранить PNG: {error}")

    def _save_mask(self) -> None:
        if self.session is None or self.state.mode is not ProjectMode.CLIPART:
            return
        item = self._selected_item(self.queue.currentRow())
        if item is None or item.status is not RunItemStatus.SUCCEEDED:
            return
        source = Path(item.output_path)
        default = self.session.output_dir / f"{source.stem}_mask.png"
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить alpha-маску",
            str(default),
            "PNG (*.png)",
        )
        if not destination:
            return
        try:
            self.transparency_preview.save_mask(destination)
            self.summary_label.setText(
                f"Alpha-маска сохранена: {Path(destination).name}"
            )
        except (OSError, ValueError) as error:
            self.summary_label.setText(f"Не удалось сохранить alpha-маску: {error}")

def _safe_progress_text(message: Any) -> str:
    text = str(message or "").strip()
    match = _ITEM_START.match(text)
    if match:
        return (
            f"Элемент {int(match.group('index'))}/"
            f"{int(match.group('total'))}: выполняется"
        )
    if text.startswith(_OUTPUT_PREFIX):
        return "Результат элемента сохранён."
    if text.startswith(_GENERATED_PREFIX):
        return "Изображение создано; выполняется обработка."
    if text.startswith(_ERROR_PREFIX):
        return _failure_reason(text[len(_ERROR_PREFIX) :])[1]
    if text.startswith(_MISSING_PREFIX):
        return "Исходный файл недоступен."
    if any(marker in text for marker in _STOP_MARKERS):
        return "Выполнение безопасно остановлено."
    return "Выполнение продолжается."


class RunQueueSupport:
    def __init__(
        self, controller: Any, mode: ProjectMode, *,
        results_extension: RunResultsExtension | None = None,
    ) -> None:
        self.controller = controller
        self.mode = mode
        self.session: RunQueueSession | None = None
        self._worker_generation = 0
        self._active_worker: Any | None = None
        self._structured_progress_generation: int | None = None
        self.page = RunResultsPage(
            controller.shell.state,
            tokens=controller.shell.tokens,
            results_extension=results_extension,
        )
        self.page.stop_requested.connect(self.stop_after_current)
        self.page.immediate_stop_requested.connect(self.stop_now)
        self.page.retry_requested.connect(self.retry_failed)
        self.page.process_more_requested.connect(self.process_more)
        self.page.regenerate_supported = callable(getattr(controller, 'confirm_retry_request', None))
        self.page.regenerate_requested.connect(self.regenerate_selected)
        self.page.finish_requested.connect(self.finish_workflow)
        self.page.membership_changed.connect(controller.shell.state_changed.emit)

    def finish_workflow(self) -> None:
        if self.session is None or self.session.running:
            return
        self.controller.shell.finish_requested.emit(self.mode.value)

    def process_more(self) -> None:
        if self.session is not None and self.session.running:
            return
        self.reset_for_new_workflow()
        self.controller.start_processing_again()

    def reset_for_new_workflow(self) -> bool:
        if self.session is not None and self.session.running:
            return False
        self.page.reset_transient_ui()
        self.session = None
        self.page.session = None
        self.page.refresh_from_state()
        return True

    def start_new(self, request: Any) -> RunQueueSession:
        session = RunQueueSession(
            request,
            self.mode,
            diagnostic_journal=getattr(
                self.controller.shell,
                "diagnostic_journal",
                None,
            ),
        )
        self.session = session
        self.page.set_session(session)
        return session

    def connect_worker(self, worker: Any) -> None:
        self._worker_generation += 1
        generation = self._worker_generation
        self._active_worker = worker
        self._structured_progress_generation = None
        if hasattr(worker, "item_progress"):
            worker.item_progress.connect(
                lambda event, source=worker, token=generation: self._item_progress_event(
                    source,
                    token,
                    event,
                )
            )
        if hasattr(worker, "progress"):
            worker.progress.connect(
                lambda message, source=worker, token=generation: self._progress(
                    source,
                    token,
                    message,
                )
            )
        if hasattr(worker, "progress_value"):
            worker.progress_value.connect(
                lambda value, source=worker, token=generation: self._progress_value(
                    source,
                    token,
                    value,
                )
            )
        if hasattr(worker, "diagnostic"):
            worker.diagnostic.connect(
                lambda event, source=worker, token=generation: self._diagnostic(
                    source,
                    token,
                    event,
                )
            )
        completion_signal = getattr(worker, "completed", None)
        if completion_signal is None:
            completion_signal = getattr(worker, "finished", None)
        if completion_signal is not None:
            completion_signal.connect(
                lambda message, source=worker, token=generation: self._dispatch_finished(
                    source,
                    token,
                    message,
                )
            )
        if hasattr(worker, "error"):
            worker.error.connect(
                lambda message, source=worker, token=generation: self._dispatch_error(
                    source,
                    token,
                    message,
                )
            )

    def _is_active(self, worker: Any, generation: int) -> bool:
        return (
            worker is self._active_worker
            and generation == self._worker_generation
        )

    def _progress(
        self,
        worker: Any,
        generation: int,
        message: Any,
    ) -> None:
        if not self._is_active(worker, generation):
            return
        if (
            self.session is not None
            and self._structured_progress_generation != generation
        ):
            self.session.handle_progress(message)
        self.controller.progress.emit(_safe_progress_text(message))

    def _item_progress_event(
        self,
        worker: Any,
        generation: int,
        event: Any,
    ) -> None:
        if not self._is_active(worker, generation) or self.session is None:
            return
        self._structured_progress_generation = generation
        self.session.handle_item_progress(event)
        self.controller.progress.emit(_safe_progress_text(getattr(event, "message", "")))
        self.controller.progress_value.emit(self.session.progress_percent)

    def _diagnostic(
        self,
        worker: Any,
        generation: int,
        event: Any,
    ) -> None:
        if not self._is_active(worker, generation) or self.session is None:
            return
        self.session.handle_diagnostic(event)

    def _progress_value(
        self,
        worker: Any,
        generation: int,
        _value: Any,
    ) -> None:
        if not self._is_active(worker, generation):
            return
        if self.session is None:
            self.controller.progress_value.emit(0)
            return
        if self._structured_progress_generation == generation:
            self.controller.progress_value.emit(self.session.progress_percent)
            return
        total_items = max(len(self.session.items), 1)
        current_index = self.session.current_index
        if current_index is None:
            self.controller.progress_value.emit(self.session.progress_percent)
            return
        try:
            local_value = int(_value)
        except (TypeError, ValueError):
            local_value = 0
        if local_value < 0:
            local_value = 0
        elif local_value > 100:
            local_value = 100

        self.session.handle_progress_value(local_value)

        base = (current_index / total_items) * 100
        overall = int(base + local_value / total_items)
        terminal = self.session.progress_percent
        if overall < terminal:
            overall = terminal
        self.controller.progress_value.emit(overall)

    def _dispatch_finished(
        self,
        worker: Any,
        generation: int,
        message: Any,
    ) -> None:
        if not self._is_active(worker, generation):
            return
        self._active_worker = None
        self.controller._finished(str(message or ""))

    def _dispatch_error(
        self,
        worker: Any,
        generation: int,
        message: Any,
    ) -> None:
        if not self._is_active(worker, generation):
            return
        self._active_worker = None
        self.controller._error(str(message or ""))

    def finished(self) -> None:
        if self.session is not None:
            self.session.handle_finished()
            self.controller.progress_value.emit(self.session.progress_percent)

    def fatal_error(self, message: Any) -> None:
        if self.session is not None:
            self.session.handle_fatal_error(message)
            self.controller.progress_value.emit(self.session.progress_percent)

    def stop_after_current(self) -> bool:
        worker = getattr(self.controller, "worker", None)
        if (
            self.session is None
            or worker is None
            or worker is not self._active_worker
        ):
            return False
        immediate = getattr(worker, "stop", None)
        if not callable(immediate):
            return False
        native = getattr(worker, "request_stop_after_current", None)
        return self.session.request_stop_after_current(
            immediate_stop=immediate,
            native_after_current=native if callable(native) else None,
        )

    def stop_now(self) -> bool:
        worker = getattr(self.controller, "worker", None)
        if (
            self.session is None
            or worker is None
            or worker is not self._active_worker
        ):
            return False
        immediate = getattr(worker, "stop", None)
        if not callable(immediate):
            return False
        return self.session.request_immediate_stop(immediate_stop=immediate)

    def regenerate_selected(self, indices) -> Any | None:
        """Generate the chosen items again: paid, so only after cost and confirmation."""
        if self.session is None:
            return None
        busy = getattr(self.controller, "is_busy", None)
        if callable(busy) and busy():
            return None
        worker = getattr(self.controller, "worker", None)
        if worker is not None and bool(worker.isRunning()):
            return None
        preview = self.session.preview_regenerate(indices)
        if preview is None:
            return None
        confirm = getattr(self.controller, "confirm_retry_request", None)
        if not callable(confirm) or not confirm(preview, regenerate=True):
            return None
        if self.session.preview_regenerate(indices) != preview:
            return None
        request = self.session.prepare_regenerate(indices)
        if request is None:
            return None
        try:
            create_worker = getattr(self.controller, "create_worker_for_request", None)
            if not callable(create_worker):
                raise RunQueueError("Core retry service is unavailable")
            worker = create_worker(request)
        except Exception as error:
            self.controller._error(str(error))
            return None
        self.controller.worker = worker
        self.connect_worker(worker)
        worker.start()
        self.controller.started.emit(request)
        return request

    def retry_failed(self) -> Any | None:
        if self.session is None:
            return None
        busy = getattr(self.controller, "is_busy", None)
        if callable(busy) and busy():
            return None
        worker = getattr(self.controller, "worker", None)
        if worker is not None and bool(worker.isRunning()):
            return None
        if not self.session.retry_indices:
            return None
        confirm = getattr(self.controller, "confirm_retry_request", None)
        if callable(confirm):
            preview = self.session.preview_retry()
            if preview is None:
                self.page.summary_label.setText(
                    "Сохранённый PNG недоступен. Верните файл в прежнюю папку; повторная генерация не запущена."
                )
                return None
            if not confirm(preview):
                return None
            if self.session.preview_retry() != preview:
                return None
        request = self.session.prepare_retry()
        if request is None:
            return None
        try:
            create_worker = getattr(self.controller, "create_worker_for_request", None)
            if not callable(create_worker):
                raise RunQueueError("Core retry service is unavailable")
            worker = create_worker(request)
        except Exception as error:
            self.controller._error(str(error))
            return None
        self.controller.worker = worker
        self.connect_worker(worker)
        worker.start()
        self.controller.started.emit(request)
        return request
