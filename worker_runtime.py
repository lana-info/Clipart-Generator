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
    completion_signal = getattr(worker, "completed", None)
    if completion_signal is None:
        completion_signal = worker.finished
    completion_signal.connect(on_finished)
    worker.error.connect(on_error)


def launch_worker(
    worker_factory: Callable[..., object],
    *,
    mode: str,
    work_dir: str,
    settings: dict,
    selected_files: list[str],
    generated_prompts: list[dict],
    on_progress: Callable[[str], None],
    on_progress_value: Callable[[int], None],
    on_finished: Callable[[str], None],
    on_error: Callable[[str], None],
):
    worker = worker_factory(
        mode=mode,
        work_dir=work_dir,
        settings=settings,
        selected_files=selected_files,
        generated_prompts=generated_prompts,
    )
    wire_worker_signals(
        worker,
        on_progress=on_progress,
        on_progress_value=on_progress_value,
        on_finished=on_finished,
        on_error=on_error,
    )
    worker.start()
    return worker
