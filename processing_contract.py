"""Pure processing orchestration primitives shared by UI and worker code."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol

from security_redaction import redact_text


class CancellationToken(Protocol):
    def is_cancelled(self) -> bool: ...


class EventSink(Protocol):
    def __call__(self, event: str, details: Mapping[str, Any] | None = None) -> None: ...


class ProcessingProvider(Protocol):
    def apply(self, context: "ProcessingContext", input_path: Path) -> Path: ...


@dataclass(frozen=True)
class ProcessingContext:
    source_path: Path
    workspace: Path
    output_dir: Path
    settings: Mapping[str, Any]
    cancellation: CancellationToken | None = None
    event_sink: EventSink | None = None


@dataclass(frozen=True)
class ProcessingFailure:
    kind: str
    message: str
    recoverable: bool = False


def pipeline_steps(operations: Any) -> tuple[str, ...]:
    steps: list[str] = []
    if operations.visible_mark_cleanup:
        steps.append("Удаление видимой метки")
    if operations.upscale_before:
        steps.append("Апскейл до удаления фона")
    if operations.unsharp:
        steps.append("Unsharp Mask")
    if operations.remove_background:
        steps.append("Удаление фона")
    if operations.upscale_after and operations.trim:
        steps.append("Trim перед апскейлом")
    if operations.upscale_after:
        steps.append("Апскейл после удаления фона")
    if operations.edge_shrink:
        steps.append("Очистка края alpha")
    if operations.trim:
        steps.append("Trim")
        if getattr(operations, "trim_padding_percent", 0):
            steps.append("Прозрачное поле 1%")
    if any(getattr(operations, name, False) for name in (
        "remove_exif", "remove_xmp", "remove_iptc", "remove_comments_text",
        "remove_embedded_thumbnail", "remove_generator_fields", "remove_embedded_c2pa",
    )):
        steps.append("Очистка данных файла")
    if operations.export_300_dpi:
        steps.append("Экспорт 300 DPI")
    if steps:
        steps.append("Экспорт нового PNG")
    return tuple(steps)


def classify_failure(error: BaseException, *, cancelled: bool = False) -> ProcessingFailure:
    if cancelled:
        return ProcessingFailure("cancelled", "Обработка отменена")
    if isinstance(error, (FileNotFoundError, PermissionError)):
        return ProcessingFailure("workspace", redact_text(str(error)), recoverable=True)
    return ProcessingFailure("failed", redact_text(str(error)))


def output_path(source_path: str | Path, output_dir: str | Path) -> Path:
    return Path(output_dir) / f"{Path(source_path).stem}.png"


def run_workspace(output_dir: str | Path, run_id: str | None = None) -> Path:
    """Return the transient root or one isolated run directory below it."""
    transient_root = Path(output_dir) / ".run"
    normalized_run_id = str(run_id or "").strip()
    return transient_root / normalized_run_id if normalized_run_id else transient_root


def publish_atomic(
    source_path: str | Path,
    output_path_value: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    """Copy a completed result into its final path without partial output."""
    source = Path(source_path)
    target = Path(output_path_value)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    os.close(fd)
    try:
        shutil.copy2(source, temporary_name)
        if overwrite:
            os.replace(temporary_name, target)
        elif sys.platform == "win32":
            # Windows rename is atomic and refuses to replace an existing file.
            os.rename(temporary_name, target)
        else:
            os.link(temporary_name, target)
            try:
                os.unlink(temporary_name)
            except OSError:
                # The target is already a complete hard link to the staged data.
                pass
        return target
    except BaseException:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise
