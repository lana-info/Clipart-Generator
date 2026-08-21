from worker_runtime import launch_worker, wire_worker_signals
from v3_runtime_adapter import LEGACY_STAGE_PREFIXES, LegacyWorkerRuntimeAdapter, legacy_progress_stage


class Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class Worker:
    def __init__(self):
        self.progress = Signal()
        self.progress_value = Signal()
        self.finished = Signal()
        self.error = Signal()

    def start(self):
        self.started = True


def test_wire_worker_signals_connects_all_signals():
    worker = Worker()
    callbacks = [lambda *_: None for _ in range(4)]
    wire_worker_signals(
        worker,
        on_progress=callbacks[0],
        on_progress_value=callbacks[1],
        on_finished=callbacks[2],
        on_error=callbacks[3],
    )
    assert worker.progress.callbacks == [callbacks[0]]
    assert worker.progress_value.callbacks == [callbacks[1]]
    assert worker.finished.callbacks == [callbacks[2]]
    assert worker.error.callbacks == [callbacks[3]]


def test_launch_worker_constructs_wires_and_starts():
    created = {}
    def factory(**kwargs):
        created.update(kwargs)
        return Worker()
    callbacks = [lambda *_: None for _ in range(4)]
    worker = launch_worker(
        factory,
        mode="mode2_process",
        work_dir="work",
        settings={},
        selected_files=[],
        generated_prompts=[],
        on_progress=callbacks[0],
        on_progress_value=callbacks[1],
        on_finished=callbacks[2],
        on_error=callbacks[3],
    )
    assert created["mode"] == "mode2_process"
    assert worker.started is True


def test_legacy_runtime_adapter_translates_stage_and_keeps_fake_runtime_injected():
    for prefix, stage in LEGACY_STAGE_PREFIXES:
        expected = "failed" if "Не удалось" in prefix else "running"
        assert legacy_progress_stage(prefix + "...") == (stage, expected)
        complete_expected = "failed" if "Не удалось" in prefix else "complete"
        assert legacy_progress_stage(prefix + " готово") == (stage, complete_expected)
    assert legacy_progress_stage("Удаление фона: пропущено") == ("background_removal", "skipped")
    assert legacy_progress_stage("Удаление фона: ошибка") == ("background_removal", "failed")
    assert legacy_progress_stage("неизвестное сообщение") is None
    adapter = LegacyWorkerRuntimeAdapter()
    assert adapter.name == "legacy_worker"
