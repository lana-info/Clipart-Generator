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

from PyQt6.QtCore import QObject, QSize, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QImageReader, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
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
from v3_project_state import ProjectMode, ProjectState
from v3_runtime_adapter import LEGACY_STAGE_PREFIXES, legacy_progress_stage
from run_lifecycle import RunLifecycle


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


class RunQueueError(ValueError):
    pass


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


def _request_items(request: Any, mode: ProjectMode) -> list[RunItem]:
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
        requested_output = str(
            (getattr(request, "settings", {}) or {}).get("output_dir") or ""
        ).strip()
        self.output_dir = (
            Path(requested_output).resolve(strict=False)
            if requested_output
            else self.work_dir / "output"
        )
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
        self._event("run_started", count=len(self.items))

    def _event(self, name: str, **fields: Any) -> None:
        if len(self._technical_events) >= MAX_TECHNICAL_EVENTS:
            return
        parts = [f"event={name}"]
        for key, value in fields.items():
            if isinstance(value, (bool, int)) or (
                isinstance(value, str)
                and re.fullmatch(r"[a-z0-9_.-]{1,80}", value)
            ):
                parts.append(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
        self._technical_events.append(" ".join(parts))
        if self._diagnostic_journal is not None:
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
                ("attempt", "attempt"),
                ("reason", "reason"),
                ("stage", "stage"),
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

    @property
    def technical_log(self) -> str:
        return "\n".join(self._technical_events)

    @property
    def progress_percent(self) -> int:
        terminal = sum(
            item.status
            in {
                RunItemStatus.SUCCEEDED,
                RunItemStatus.FAILED,
                RunItemStatus.CANCELLED,
            }
            for item in self.items
        )
        completed = round((terminal / len(self.items)) * 100) if self.items else 0
        active = 0
        if self.current_index is not None:
            active = self._item_progress.get(self.current_index, 0)
            if active:
                active = round(active / max(len(self.items), 1))
        value = max(completed, completed + active)
        self._last_progress = max(self._last_progress, min(100, value))
        return self._last_progress

    @property
    def failed_indices(self) -> list[int]:
        return [
            index
            for index, item in enumerate(self.items)
            if item.status is RunItemStatus.FAILED
        ]

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
    def _active_item(self, local_index: int) -> RunItem | None:
        if local_index < 1 or local_index > len(self.active_order):
            return None
        global_index = self.active_order[local_index - 1]
        return self.items[global_index]

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
            )
        if isinstance(message, ProgressEvent):
            if message.percent is not None:
                self.handle_progress_value(message.percent)
            if message.stage:
                self.current_stage = message.stage
            self.activity_indeterminate = message.indeterminate
            if message.message:
                message = message.message
            else:
                message = ""
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
            self._event("run_cancelled")
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
            # The worker's current intermediate-file contract is
            # ``<output_dir>/.run``.  Trusting the legacy ``work_dir/raw``
            # location makes valid generated paths look missing to the UI.
            trusted = _trusted_worker_path(raw, self.output_dir / ".run")
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
                self._close_running_stages(item, "complete")
                item.stage_statuses["export"] = "complete"
                item.status = RunItemStatus.SUCCEEDED
                item.short_message = "Результат сохранён."
                self._event("item_succeeded", item=item.index)
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
            code, user_message = _failure_reason(text[len(_ERROR_PREFIX) :])
            self._close_running_stages(item, "failed")
            item.status = RunItemStatus.FAILED
            item.short_message = user_message
            self._event("item_failed", item=item.index, reason=code)
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
            self._event("run_cancelled")

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
        current = (
            self.items[self.current_index]
            if self.current_index is not None
            and 0 <= self.current_index < len(self.items)
            else None
        )
        if current is not None and current.status is RunItemStatus.RUNNING:
            if native_after_current is not None:
                native_after_current()
            else:
                self._deferred_stop = immediate_stop
        else:
            immediate_stop()
            self._cancel_pending()
            self.running = False
            self.finished_at = time.monotonic()
            self._event("run_cancelled")
        self.changed.emit()
        return True

    def handle_finished(self) -> None:
        if not self.running and self.finished_at is not None:
            return
        for item in self.items:
            if item.status in {RunItemStatus.PENDING, RunItemStatus.RUNNING}:
                self._close_running_stages(item, "failed")
                item.status = RunItemStatus.FAILED
                item.short_message = "Worker не подтвердил сохранение результата."
                self._event(
                    "item_failed",
                    item=item.index,
                    reason="missing_completion",
                )
        incomplete = any(item.status is RunItemStatus.FAILED for item in self.items)
        self.lifecycle.finish(error_code="missing_completion" if incomplete else "")
        self.current_index = None
        self.running = False
        self.finished_at = time.monotonic()
        self._event("run_failed" if incomplete else "run_finished", reason="missing_completion" if incomplete else "")
        self.changed.emit()

    def handle_fatal_error(self, message: Any) -> None:
        if not self.running and self.finished_at is not None:
            return
        code, user_message = _failure_reason(str(message or ""))
        for item in self.items:
            if item.status in {RunItemStatus.PENDING, RunItemStatus.RUNNING}:
                self._close_running_stages(item, "failed")
                item.status = RunItemStatus.FAILED
                item.short_message = user_message
                self._event("item_failed", item=item.index, reason=code)
        self.lifecycle.finish(error_code=code)
        self.current_index = None
        self.running = False
        self.finished_at = time.monotonic()
        self._event("run_failed", reason=code)
        self.changed.emit()

    def prepare_retry(self) -> Any | None:
        failed = self.failed_indices
        if self.running or not failed:
            return None
        self.active_order = list(failed)
        for index in failed:
            item = self.items[index]
            item.status = RunItemStatus.PENDING
            item.short_message = "Ожидает повторного запуска."
            item.output_path = ""
            item.stage_statuses.clear()
            if isinstance(item.payload, dict):
                item.source_path = ""
            item.attempts += 1
        generated = list(getattr(self.request, "generated_prompts", []) or [])
        if generated:
            retry_request = replace(
                self.request,
                generated_prompts=[
                    {
                        "prompt": str(self.items[index].payload.get("prompt") or ""),
                        "references": list(
                            self.items[index].payload.get("references") or []
                        ),
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
        self.current_index = None
        self.running = True
        self.stop_after_current_requested = False
        self._deferred_stop = None
        self._event("retry_started", count=len(failed))
        self.changed.emit()
        return retry_request


def build_safe_run_report(session: RunQueueSession) -> dict[str, Any]:
    if not isinstance(session, RunQueueSession):
        raise TypeError("session must be a RunQueueSession")
    return {
        "schema_version": 1,
        "mode": session.mode.value,
        "summary": session.counts(),
        "items": [
            {
                "index": item.index,
                "display_name": item.display_name[:260],
                "processing": item.status.value,
                "attempts": item.attempts,
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

    def refresh_items(self, items: list[RunItem]) -> None:
        selected = self.currentRow()
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


class RunResultsPage(QWidget):
    stop_requested = pyqtSignal()
    retry_requested = pyqtSignal()
    process_more_requested = pyqtSignal()

    def __init__(
        self,
        state: ProjectState,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__()
        self.state = state
        self.session: RunQueueSession | None = None
        self._log_dialog: QDialog | None = None
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
        self.queue.setMinimumHeight(160)
        self.queue.currentRowChanged.connect(self._selection_changed)
        self.viewer = BeforeAfterViewer()

        self.processing_label = QLabel()
        self.stages_label = QLabel()
        self.file_hints_label = QLabel()
        self.pixel_evidence_label = QLabel()
        self.handoff_label = QLabel()
        self.technical_note = QLabel("Подробности этапов и проверки доступны в «Техническом логе».")
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
        utility_secondary = QWidget()
        utility_secondary_layout = QHBoxLayout(utility_secondary)
        utility_secondary_layout.setContentsMargins(0, 0, 0, 0)
        self.stop_button = V3Button(
            "Остановить после текущего файла",
            ButtonVariant.SECONDARY,
        )
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.retry_button = V3Button(
            "Повторить ошибки",
            ButtonVariant.SECONDARY,
        )
        self.retry_button.clicked.connect(self.retry_requested.emit)
        self.process_more_button = V3Button(
            "Обработать ещё файлы",
            ButtonVariant.SECONDARY,
        )
        self.process_more_button.clicked.connect(self.process_more_requested.emit)
        self.open_folder_button = V3Button(
            "Открыть папку с результатами",
            ButtonVariant.PRIMARY,
        )
        self.open_folder_button.clicked.connect(self._open_folder)
        self.log_button = V3Button(
            "Технический лог",
            ButtonVariant.GHOST,
        )
        self.log_button.clicked.connect(self._show_log)
        self.export_button = V3Button(
            "Экспортировать отчёт",
            ButtonVariant.GHOST,
        )
        self.export_button.clicked.connect(self._choose_report_path)
        for button in (
            self.stop_button,
            self.retry_button,
            self.process_more_button,
        ):
            workflow_layout.addWidget(button)
        workflow_layout.addStretch()
        utility_primary_layout.addWidget(self.open_folder_button)
        utility_primary_layout.addStretch()
        for button in (self.log_button, self.export_button):
            utility_secondary_layout.addWidget(button)
        utility_secondary_layout.addStretch()
        utility_layout.addWidget(utility_primary)
        utility_layout.addWidget(utility_secondary)
        actions_layout.addWidget(workflow_actions)
        actions_layout.addWidget(utility_actions)
        self.workflow_actions = workflow_actions
        self.utility_actions = utility_actions

        for widget in (
            self.summary_label,
            self.progress_bar,
            self.current_label,
            self.queue,
            self.viewer,
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
        session.changed.connect(self.refresh_from_state)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        session = self.session
        if session is None:
            self.stop_button.hide()
            self.retry_button.hide()
            self.process_more_button.hide()
            self.open_folder_button.setEnabled(False)
            self.log_button.setEnabled(False)
            self.export_button.setEnabled(False)
            self._selection_changed(-1)
            return
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
        retry_visible = not session.running and bool(session.failed_indices)
        process_more_visible = not session.running
        self.stop_button.setVisible(stop_visible)
        self.retry_button.setVisible(retry_visible)
        self.process_more_button.setVisible(process_more_visible)
        self.workflow_actions.setVisible(
            stop_visible or retry_visible or process_more_visible
        )
        self.utility_actions.setVisible(True)
        self.stop_button.setEnabled(stop_visible)
        self.retry_button.setEnabled(retry_visible)
        self.open_folder_button.setEnabled(session.output_dir.is_dir())
        self.log_button.setEnabled(True)
        self.export_button.setEnabled(True)
        self._selection_changed(self.queue.currentRow())

    @staticmethod
    def _stage_label(stage: str) -> str:
        return {
            "processing": "идёт обработка",
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
            f"⏱ Время: {session.elapsed_seconds} с"
        )

    def _selected_item(self, row: int) -> RunItem | None:
        if (
            self.session is None
            or row < 0
            or row >= len(self.session.items)
        ):
            return None
        return self.session.items[row]

    def _selection_changed(self, row: int) -> None:
        item = self._selected_item(row)
        if item is None:
            self.viewer.set_paths("", "")
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
        self.viewer.set_paths(item.source_path, item.output_path)
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
        record = next(
            (
                candidate
                for candidate in self.state.processing.verification_records
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

    def _show_log(self) -> None:
        if self.session is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Технический лог")
        dialog.resize(720, 420)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(self.session.technical_log)
        layout.addWidget(text)
        close_button = V3Button("Закрыть", ButtonVariant.SECONDARY)
        close_button.clicked.connect(dialog.close)
        layout.addWidget(close_button)
        self._log_dialog = dialog
        dialog.show()

    def _choose_report_path(self) -> None:
        if self.session is None:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Экспортировать отчёт выполнения",
            "run-report.json",
            "JSON (*.json)",
        )
        if not destination:
            return
        try:
            export_safe_run_report(self.session, destination)
        except (OSError, RunQueueError) as error:
            self.summary_label.setText(
                f"Не удалось экспортировать отчёт: {error}"
            )
            return
        self.summary_label.setText("Отчёт выполнения сохранён.")

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
    def __init__(self, controller: Any, mode: ProjectMode) -> None:
        self.controller = controller
        self.mode = mode
        self.session: RunQueueSession | None = None
        self._worker_generation = 0
        self._active_worker: Any | None = None
        self.page = RunResultsPage(
            controller.shell.state,
            tokens=controller.shell.tokens,
        )
        self.page.stop_requested.connect(self.stop_after_current)
        self.page.retry_requested.connect(self.retry_failed)
        self.page.process_more_requested.connect(self.process_more)

    def process_more(self) -> None:
        if self.session is not None and self.session.running:
            return
        self.session = None
        self.page.session = None
        self.page.refresh_from_state()
        self.controller.start_processing_again()

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
        if hasattr(worker, "finished"):
            worker.finished.connect(
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
        if self.session is not None:
            self.session.handle_progress(message)
        self.controller.progress.emit(_safe_progress_text(message))

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

    def retry_failed(self) -> Any | None:
        if self.session is None:
            return None
        worker = getattr(self.controller, "worker", None)
        if worker is not None and bool(worker.isRunning()):
            return None
        if not self.session.failed_indices:
            return None
        try:
            authorization_provider = getattr(
                self.controller,
                "authorization_provider",
                None,
            )
            if not callable(authorization_provider):
                raise RunQueueError("Лицензионный сервис не настроен")
            authorization_provider()
        except Exception as error:
            self.controller._error(str(error))
            return None
        request = self.session.prepare_retry()
        if request is None:
            return None
        try:
            worker = self.controller.worker_factory(**request.worker_kwargs())
        except Exception as error:
            self.controller._error(str(error))
            return None
        self.controller.worker = worker
        self.connect_worker(worker)
        worker.start()
        self.controller.started.emit(request)
        return request
