from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from studio_job_services import CoreWorkerJobHandle
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode


class RawWorker(QObject):
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    diagnostic = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.started = False
        self.stop_after = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def request_stop_after_current(self):
        self.stop_after = True

    def isRunning(self):
        return self.started


def test_core_worker_handle_forwards_only_narrow_lifecycle_and_events():
    raw = RawWorker()
    handle = CoreWorkerJobHandle(raw)
    assert handle.parent() is None
    assert not hasattr(handle, "worker")
    assert not hasattr(handle, "raw_worker")
    seen = []
    handle.progress.connect(seen.append)
    raw.progress.emit("working")
    assert seen == ["working"]
    handle.start()
    assert raw.started is True and handle.isRunning() is True
    handle.request_stop_after_current()
    assert raw.stop_after is True
    handle.stop()
    assert raw.started is False


def test_application_core_wraps_worker_before_builtin_workflow_receives_it():
    app = QApplication.instance() or QApplication([])
    raw = RawWorker()
    view = V3ApplicationView(worker_factory=lambda **_kwargs: raw)
    view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
    handle = view._create_project_worker(
        view.shell, mode="mode1_generate_only", work_dir=".", settings={}
    )
    assert isinstance(handle, CoreWorkerJobHandle)
    assert handle is not raw
    view.close()
    app.processEvents()
