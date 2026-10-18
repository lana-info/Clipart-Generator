from types import SimpleNamespace
import pytest
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
from studio_auto_clipart_shell import AutoClipartShell
from v3_project_state import ProjectMode, StepId

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])

@pytest.mark.parametrize("active", [True, False])
@pytest.mark.parametrize("fail", [True, False])
def test_confirmation_keeps_run_permission_and_restores_timer(app, active, fail):
    timer = QTimer()
    timer.setInterval(10)
    shell = SimpleNamespace(state=SimpleNamespace(mode=ProjectMode.CLIPART, current_step=StepId.REVIEW_RUN), module_id="auto-clipart", _run_request_key=None)
    ticks = []
    def autosave():
        ticks.append(True)
        shell._run_request_key = None
    timer.timeout.connect(autosave)
    if active:
        timer.start()
    def navigate(direction):
        assert direction == 1
        loop = QEventLoop()
        QTimer.singleShot(100, loop.quit)
        loop.exec()
        assert shell._run_request_key == (ProjectMode.CLIPART, StepId.REVIEW_RUN)
        assert not ticks
        if fail:
            raise RuntimeError("Injected cancellation/error")
    controller = SimpleNamespace(save_timer=timer, navigate=navigate)
    shell.workflow_controller = lambda module_id: controller
    try:
        if fail:
            with pytest.raises(RuntimeError, match="Injected"):
                AutoClipartShell.go_next(shell)
        else:
            assert AutoClipartShell.go_next(shell) is StepId.REVIEW_RUN
        assert shell._run_request_key is None
        assert timer.isActive() is active
    finally:
        timer.stop()
