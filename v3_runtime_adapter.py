"""Narrow runtime protocol and the temporary legacy WorkerThread adapter."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol


LEGACY_STAGE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Экспериментальная очистка невидимого watermark", "invisible_watermark_cleanup"),
    ("Видимая метка:", "visible_mark_cleanup"),
    ("Локальный апскейл", "upscale"),
    ("Апскейл через", "upscale"),
    ("Кратность апскейла:", "upscale"),
    ("Удаление фона", "background_removal"),
    ("Промежуточный локальный без фона:", "background_removal"),
    ("Промежуточный BEN2 без фона:", "background_removal"),
    ("Промежуточный PhotoRoom без фона:", "background_removal"),
    ("Промежуточный без фона:", "background_removal"),
    ("Промежуточный локальный апскейл:", "upscale"),
    ("Промежуточный апскейл:", "upscale"),
    ("Промежуточная резкость:", "unsharp"),
    ("Удаление контура:", "edge_cleanup"),
    ("Промежуточный без контура:", "edge_cleanup"),
    ("Trim ", "trim"),
    ("Очистка файла:", "metadata_cleanup"),
)


class RuntimeAdapter(Protocol):
    name: str

    def read_settings(self) -> Mapping[str, Any]: ...

    def create_worker(self, **kwargs: Any) -> Any: ...

    def start(self, worker: Any) -> None: ...

    def stop(self, worker: Any) -> None: ...

    def is_running(self, worker: Any) -> bool: ...


def legacy_progress_stage(message: str) -> tuple[str, str] | None:
    text = str(message or "").strip()
    for prefix, stage in LEGACY_STAGE_PREFIXES:
        if not text.startswith(prefix):
            continue
        lowered = text.casefold()
        if "ошибка" in lowered:
            status = "failed"
        elif any(marker in lowered for marker in ("пропущ", "не потребовал", "не найден", "не требуется")):
            status = "skipped"
        elif text.endswith("..."):
            status = "running"
        else:
            status = "complete"
        return stage, status
    return None


class LegacyWorkerRuntimeAdapter:
    name = "legacy_worker"

    def read_settings(self) -> Mapping[str, Any]:
        import main

        path = Path(main.CONFIG_FILE)
        if not path.is_file():
            return {}
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                return {}
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, Mapping) else {}

    def create_worker(self, **kwargs: Any) -> Any:
        from main import WorkerThread

        return WorkerThread(**kwargs)

    def start(self, worker: Any) -> None:
        worker.start()

    def stop(self, worker: Any) -> None:
        if hasattr(worker, "stop"):
            worker.stop()

    def is_running(self, worker: Any) -> bool:
        return bool(getattr(worker, "isRunning", lambda: False)())


DEFAULT_LEGACY_RUNTIME_ADAPTER = LegacyWorkerRuntimeAdapter()


def runtime_adapter_for(
    runtime_settings_provider: Callable[[], Mapping[str, Any]] | None,
    worker_factory: Callable[..., Any] | None,
) -> RuntimeAdapter:
    if runtime_settings_provider is None and worker_factory is None:
        return DEFAULT_LEGACY_RUNTIME_ADAPTER
    return _InjectedRuntimeAdapter(runtime_settings_provider, worker_factory)


class _InjectedRuntimeAdapter:
    name = "injected"

    def __init__(self, settings_provider, worker_factory) -> None:
        self._settings_provider = settings_provider or DEFAULT_LEGACY_RUNTIME_ADAPTER.read_settings
        self._worker_factory = worker_factory or DEFAULT_LEGACY_RUNTIME_ADAPTER.create_worker

    def read_settings(self) -> Mapping[str, Any]:
        return self._settings_provider()

    def create_worker(self, **kwargs: Any) -> Any:
        return self._worker_factory(**kwargs)

    def start(self, worker: Any) -> None:
        worker.start()

    def stop(self, worker: Any) -> None:
        if hasattr(worker, "stop"):
            worker.stop()

    def is_running(self, worker: Any) -> bool:
        return bool(getattr(worker, "isRunning", lambda: False)())
