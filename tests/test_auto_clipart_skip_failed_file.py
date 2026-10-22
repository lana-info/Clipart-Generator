"""One failed provider file is skipped; a batch stops only after a streak."""
from __future__ import annotations

import ast
import threading
import types
from pathlib import Path
from unittest.mock import Mock

from PIL import Image

from studio_auto_clipart_state import AutoClipartStateExtension
from tests.test_v3_run_queue import generation_request
from v3_project_state import ProjectMode
from v3_run_queue import ProgressEvent, RunItemStatus, RunQueueSession

ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = 3


class _Cancelled(RuntimeError):
    pass


class _ItemError(RuntimeError):
    def __init__(self, message, **_details):
        super().__init__(message)


def _worker_method(name):
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "WorkerThread")
    func = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    env = {
        "ProcessingCancelled": _Cancelled,
        "ItemExecutionError": _ItemError,
        "PROVIDER_FAILURE_STOP_THRESHOLD": THRESHOLD,
        "PROVIDER_FAILURE_STOP_PROVIDERS": frozenset({"piapi", "atlascloud"}),
        "_item_error_known_paths": lambda *_: (),
        "sanitize_item_error_paths": lambda text, **_: text,
    }
    module = ast.fix_missing_locations(ast.Module(body=[func], type_ignores=[]))
    exec(compile(module, "main.py", "exec"), env)
    return env[name]


def _worker(provider="piapi"):
    worker = types.SimpleNamespace(
        _consecutive_provider_failures=0,
        _shared_state_lock=threading.Lock(),
        _diagnostic_context=types.SimpleNamespace(provider=provider, stage="generation", model="m"),
        _item_context=threading.local(),
        progress=Mock(),
        stop_requested=0,
        _safe_error_text=lambda error, limit=0: str(error),
    )
    worker.request_stop_after_current = lambda: setattr(worker, "stop_requested", worker.stop_requested + 1)
    for name in ("_execute_item_entry", "_note_provider_failure"):
        setattr(worker, name, types.MethodType(_worker_method(name), worker))
    return worker


def _fail():
    raise RuntimeError("piapi: generation failed")


def _run(worker, ok):
    try:
        return worker._execute_item_entry((lambda: "out") if ok else _fail)
    except _ItemError:
        return None


def test_single_provider_failure_does_not_stop_the_batch():
    worker = _worker()
    assert _run(worker, ok=False) is None
    assert worker.stop_requested == 0
    assert _run(worker, ok=True) == "out"
    assert worker._consecutive_provider_failures == 0


def test_failures_separated_by_success_never_reach_threshold():
    worker = _worker()
    for ok in (False, False, True, False, False, True, False):
        _run(worker, ok)
    assert worker.stop_requested == 0


def test_consecutive_failures_stop_once_with_explanation():
    worker = _worker()
    for _ in range(THRESHOLD + 2):
        _run(worker, ok=False)
    assert worker.stop_requested == 1
    worker.progress.emit.assert_called_once()
    text = worker.progress.emit.call_args.args[0]
    assert text.startswith("Остановлено после текущего файла")
    assert str(THRESHOLD) in text and "повторите" in text


def test_non_provider_failures_never_stop_the_batch():
    worker = _worker(provider="")
    for _ in range(THRESHOLD + 2):
        _run(worker, ok=False)
    assert worker.stop_requested == 0


def _feed(session, index, total, status, **kw):
    session.handle_item_progress(ProgressEvent(item_index=index, total_items=total, stage="generation", status=status, **kw))


def test_failed_file_is_marked_and_remaining_files_finish(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=4), ProjectMode.CLIPART)
    for index in (1, 2, 3, 4):
        _feed(session, index, 4, "running")
        if index == 2:
            _feed(session, index, 4, "failed", message="piapi: generation failed")
        else:
            ready = session.output_dir / f"gen_{index}_ready.png"
            ready.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (8, 8), "white").save(ready)
            session.handle_item_progress(ProgressEvent(
                item_index=index, total_items=4, stage="export", status="succeeded", output_path=str(ready)))
    session.handle_finished()
    statuses = [item.status for item in session.items]
    assert statuses.count(RunItemStatus.FAILED) == 1 and session.items[1].status is RunItemStatus.FAILED
    assert [s for i, s in enumerate(statuses) if i != 1] == [RunItemStatus.SUCCEEDED] * 3
    assert session.retry_indices == [1]


def test_failed_cancelled_succeeded_statuses_survive_save_and_restore(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=3), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(session.output_dir / "kept_ready.png")
    session.items[1].status = RunItemStatus.FAILED
    session.items[2].status = RunItemStatus.CANCELLED
    session.handle_finished()
    rows = [
        {"status": item.status.value, "output_path": item.output_path or "", "attempts": item.attempts,
         "editor_output_path": "", "paid_completed_stages": list(item.paid_history_stages()),
         "stage_statuses": item.saved_stages(), "source_path": ""}
        for item in session.items
    ]
    state = {"clipart": {"automatic": {"run": rows}}}
    AutoClipartStateExtension().normalize_state(state)
    assert [r["status"] for r in state["clipart"]["automatic"]["run"]] == ["succeeded", "failed", "cancelled"]


def test_skipped_files_are_not_reported_as_missing_completion(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=2), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[1].status = RunItemStatus.FAILED
    events = []
    session._event = lambda name, **fields: events.append((name, fields))
    session.handle_finished()
    assert ("run_failed", ) == (events[-1][0],) and events[-1][1]["reason"] == "item_failures"

    session = RunQueueSession(generation_request(tmp_path, count=2), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    events = []
    session._event = lambda name, **fields: events.append((name, fields))
    session.handle_finished()
    assert events[-1][1]["reason"] == "missing_completion"


def test_autosave_stops_timer_when_workflow_capability_is_gone():
    from studio_auto_clipart_flow import AutoClipartFlowController

    class Gone:
        @property
        def is_active(self):
            raise RuntimeError("Workflow capability is unavailable")

    controller = types.SimpleNamespace(shell=types.SimpleNamespace(state=Gone()), save_timer=Mock(), is_busy=lambda: False)
    AutoClipartFlowController._autosave(controller)
    controller.save_timer.stop.assert_called_once()


def test_failure_counted_at_provider_site_is_not_counted_twice():
    worker = _worker()

    def failing_poll():
        worker._note_provider_failure()
        raise RuntimeError("piapi: generation failed")

    for _ in range(THRESHOLD - 1):
        try:
            worker._execute_item_entry(failing_poll)
        except _ItemError:
            pass
    assert worker._consecutive_provider_failures == THRESHOLD - 1
    assert worker.stop_requested == 0
