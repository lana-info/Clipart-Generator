"""Core-owned storage and dispatch for legacy desktop workers."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _WorkerCapability:
    worker: Any


_WORKERS: dict[str, _WorkerCapability] = {}


def _resolve(capability_id: str):
    entry = _WORKERS.get(str(capability_id))
    if entry is None:
        raise RuntimeError("Core worker capability is unavailable")
    return entry.worker


def release_worker(capability_id: str) -> None:
    _WORKERS.pop(str(capability_id), None)


def _bridge(worker, name: str, emit) -> None:
    signal = getattr(worker, name, None)
    if signal is not None and hasattr(signal, "connect"):
        signal.connect(emit)


def register_worker(worker: Any, handle: Any) -> str:
    if worker is None:
        raise TypeError("worker is required")
    token = uuid.uuid4().hex
    _WORKERS[token] = _WorkerCapability(worker)
    destroyed = getattr(handle, "destroyed", None)
    if destroyed is not None and hasattr(destroyed, "connect"):
        destroyed.connect(lambda *_args, capability_id=token: release_worker(capability_id))
    _bridge(worker, "progress", handle.progress.emit)
    _bridge(worker, "item_progress", handle.item_progress.emit)
    _bridge(worker, "progress_value", handle.progress_value.emit)
    _bridge(worker, "diagnostic", handle.diagnostic.emit)
    _bridge(worker, "error", handle.error.emit)
    completed = getattr(worker, "completed", None)
    finished = getattr(worker, "finished", None)
    has_completed = completed is not None and hasattr(completed, "connect")
    has_finished = finished is not None and hasattr(finished, "connect")
    if has_completed:
        if has_finished:
            completed.connect(
                lambda message="": handle.completed.emit(str(message or ""))
            )
        else:
            def terminal_completed(message="", *, capability_id=token) -> None:
                handle.completed.emit(str(message or ""))
                release_worker(capability_id)

            completed.connect(terminal_completed)
    elif has_finished:
        def terminal_finished(*args, capability_id=token) -> None:
            handle.completed.emit(str(args[0] if args else ""))
            release_worker(capability_id)

        finished.connect(terminal_finished)
    if has_completed and has_finished:
        finished.connect(lambda *_args, capability_id=token: release_worker(capability_id))
    return token


def worker_start(capability_id: str) -> None:
    worker = _resolve(capability_id)
    start = getattr(worker, "start", None)
    if not callable(start):
        raise RuntimeError("Core worker cannot be started")
    start()


def worker_stop(capability_id: str) -> None:
    entry = _WORKERS.get(str(capability_id))
    if entry is None:
        return
    worker = entry.worker
    stop = getattr(worker, "stop", None)
    if callable(stop):
        stop()


def worker_request_stop_after_current(capability_id: str) -> None:
    entry = _WORKERS.get(str(capability_id))
    if entry is None:
        return
    worker = entry.worker
    request = getattr(worker, "request_stop_after_current", None)
    if callable(request):
        request()
        return
    stop = getattr(worker, "stop", None)
    if callable(stop):
        stop()


def worker_is_running(capability_id: str) -> bool:
    entry = _WORKERS.get(str(capability_id))
    if entry is None:
        return False
    worker = entry.worker
    running = getattr(worker, "isRunning", None)
    return bool(running()) if callable(running) else False
