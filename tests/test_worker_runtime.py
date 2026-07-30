from worker_runtime import wire_worker_signals


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
