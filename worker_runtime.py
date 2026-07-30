"""Helpers for wiring worker signals to UI callbacks."""

from __future__ import annotations

from collections.abc import Callable


def wire_worker_signals(
    worker,
    *,
    on_progress: Callable[[str], None],
    on_progress_value: Callable[[int], None],
    on_finished: Callable[[str], None],
    on_error: Callable[[str], None],
) -> None:
    worker.progress.connect(on_progress)
    worker.progress_value.connect(on_progress_value)
    worker.finished.connect(on_finished)
    worker.error.connect(on_error)
