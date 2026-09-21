import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QObject, pyqtSignal

from license_client import LicenseAuthorization, ModuleEntitlement
from v3_mode_selection import V3ApplicationView
from v3_project_state import StepId


class FixtureWorker(QObject):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    item_progress = pyqtSignal(object)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__()
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def isRunning(self):
        return self.running


@pytest.fixture(scope="module", autouse=True)
def app():
    app = QApplication.instance() or QApplication([])
    yield app


def authorization(module="auto-clipart"):
    now = datetime.now(timezone.utc)
    return LicenseAuthorization("fixture", "clipart-generator", "device", now,
        now + timedelta(minutes=5), module_entitlements=(
            ModuleEntitlement(module, now, now + timedelta(days=1)),))


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    gate = Mock(status_text="Test", verification_text="Test")
    gate.current_authorization = authorization()
    gate.authorize_run.return_value = gate.current_authorization
    worker = Mock()
    view = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate,
        worker_factory=worker, runtime_settings_provider=lambda: {"kie_api_key": "fixture-only"})
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: pytest.fail(str(args[-1])))
    view._handle_module_action("auto-clipart", "open")
    controller = view.shell.workflow_controller("auto-clipart")
    controller.brief.directory.setText(str(tmp_path))
    controller.brief.theme.setText("Winter flowers")
    controller.brief.total.setValue(1)
    yield view, controller, gate, worker
    controller.save_timer.stop()
    if controller.run_queue.session:
        controller.run_queue.session.running = False
    view.close()
    view.deleteLater()


def prepare_launch(controller):
    for _ in range(4):
        controller.navigate(1)
    assert controller.shell.state.current_step is StepId.PROCESSING_OPTIONS
    for item in controller.brief.object_editor.items:
        item["name"] = "Winter flower"
    controller.brief.object_editor.refresh()
    controller.navigate(1)
    assert controller.shell.state.current_step is StepId.REVIEW_RUN


def test_eight_steps_prepare_prompts_without_paid_work(workspace):
    view, controller, gate, worker = workspace
    assert len(view.shell.step_labels) == 8
    assert view.shell.module_id == "auto-clipart"
    prepare_launch(controller)
    assert len(view.project_state.clipart.prompts) == 1
    assert view.project_state.clipart.prompts[0].result_kind == "clipart"
    assert view.project_state.clipart.prompts[0].object_id
    assert view.project_state.clipart.operations.remove_background
    assert view.project_state.clipart.operations.remove_background_provider == "local_chroma_key"
    assert not view.project_state.clipart.operations.upscale_before
    assert view.project_state.clipart.operations.upscale_after
    worker.assert_not_called()
    record = view._project_store.load(view._active_project_id)
    assert record.module_id == "auto-clipart"


def test_auto_project_resumes_its_route_not_ordinary_generation(workspace):
    view, controller, gate, worker = workspace
    prepare_launch(controller)
    project_id = view._active_project_id
    controller.save_timer.stop()
    assert view.continue_saved_project(project_id)
    resumed = view.shell.workflow_controller("auto-clipart")
    assert resumed is not None
    assert view.shell.workflow_controller("clipart") is None
    assert view.project_state.current_step is StepId.REVIEW_RUN
    assert resumed.brief.theme.text() == "Winter flowers"
    worker.assert_not_called()
    resumed.save_timer.stop()


def test_cancelled_confirmation_does_not_create_worker(workspace, monkeypatch):
    view, controller, gate, worker = workspace
    prepare_launch(controller)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    controller.navigate(1)
    worker.assert_not_called()
    assert view.project_state.current_step is StepId.REVIEW_RUN


def test_upscale_selection_survives_reopen_and_builds_one_alpha_safe_pass(workspace):
    from v3_clipart_flow import build_clipart_run_request, fal_endpoint_quantities

    view, controller, gate, worker = workspace
    prepare_launch(controller)
    controller.upscale_provider.setCurrentIndex(controller.upscale_provider.findData("fal"))
    assert controller.upscale_model.findData("topaz/upscale/image/precision") == -1
    controller.upscale_model.setCurrentIndex(controller.upscale_model.findData("bria/increase-resolution"))
    controller.upscale_scale.setCurrentIndex(controller.upscale_scale.findData(4))
    request = build_clipart_run_request(controller.shell.state)
    assert request.settings["upscale"] is False
    assert request.settings["upscale_after"] is True
    assert request.settings["fal_upscale_after_model"] == "bria/increase-resolution"
    assert request.settings["fal_upscale_after_scale"] == 4
    assert fal_endpoint_quantities(controller.shell.state) == {"bria/increase-resolution": 1}
    project_id = view._active_project_id
    controller.save_timer.stop()
    assert view.continue_saved_project(project_id)
    resumed = view.shell.workflow_controller("auto-clipart")
    resumed.save_timer.stop()
    assert resumed.upscale_provider.currentData() == "fal"
    assert resumed.upscale_model.currentData() == "bria/increase-resolution"
    assert resumed.upscale_scale.currentData() == 4
    resumed.upscale_model.setCurrentIndex(resumed.upscale_model.findData("topaz/upscale/image/transparent"))
    assert resumed.upscale_scale.currentData() == 4
    assert not resumed.upscale_scale.isEnabled()
    build_clipart_run_request(resumed.shell.state)
    worker.assert_not_called()


def test_ordinary_generator_does_not_install_automatic_controller(workspace):
    view, controller, gate, worker = workspace
    controller.save_timer.stop()
    view._handle_mode_selected("clipart")
    assert not hasattr(view.shell, "module_id")
    assert view.shell.workflow_controller("clipart") is not None
    assert view.shell.workflow_controller("auto-clipart") is None
    worker.assert_not_called()


def test_confirmed_run_progress_results_export_and_resume(workspace, monkeypatch, tmp_path):
    from pathlib import Path
    from zipfile import ZipFile
    from PIL import Image, ImageDraw
    from studio_set_export import export_clipart_sets
    from v3_run_queue import RunItemStatus

    view, controller, gate, worker = workspace
    raw_worker = FixtureWorker()
    worker.return_value = raw_worker
    prepare_launch(controller)
    controller.upscale_provider.setCurrentIndex(controller.upscale_provider.findData("kie"))
    errors = []
    controller.error.connect(errors.append)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    view.shell.go_next()
    assert not errors, errors
    worker.assert_called_once()
    assert view.project_state.current_step is StepId.RESULTS
    session = controller.run_queue.session
    assert session.running
    session.handle_item_progress(dict(item_index=1, total_items=1, stage="generation",
                                      status="running", percent=40))
    assert not view.shell.next_button.isEnabled()
    output = Path(view.project_state.common.output_dir) / "flower.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    png = Image.new("RGBA", (128, 128))
    ImageDraw.Draw(png).ellipse((32, 32, 96, 96), fill=(220, 90, 140, 255))
    png.save(output)
    session.handle_item_progress(dict(item_index=1, total_items=1, stage="complete",
                                      status="succeeded", percent=100, output_path=str(output)))
    controller.worker.stop()
    raw_worker.finished.emit("Done")
    assert session.items[0].status is RunItemStatus.SUCCEEDED
    assert not session.running
    controller.navigate(1)
    assert view.project_state.current_step is StepId.TRANSPARENCY
    assert view.shell.next_button.isEnabled()
    paths = controller.run_queue.page._export_paths()
    assert paths == [output] or paths == (output,)
    extension = controller.run_queue.page.results_extension
    extension.seed_membership(controller.shell.state, session, paths)
    assert not extension.export_issues(controller.shell.state, session, paths)
    archives = export_clipart_sets([dict(title="Winter flowers", images=paths)], tmp_path)
    with ZipFile(archives[0]) as archive:
        assert "overview.pdf" in archive.namelist()
        assert "manifest.json" not in archive.namelist()
        assert any(name.endswith(".png") for name in archive.namelist())
    edited = tmp_path / "edited-flower.png"
    png.save(edited)
    controller.run_queue.page.use_edited_output(output, edited)
    controller._save_run()
    project_id = view._active_project_id
    controller.save_timer.stop()
    assert view.continue_saved_project(project_id)
    resumed = view.shell.workflow_controller("auto-clipart")
    resumed.save_timer.stop()
    assert view.project_state.current_step is StepId.TRANSPARENCY
    assert not resumed.run_queue.session.running
    assert resumed.run_queue.session.items[0].status is RunItemStatus.SUCCEEDED
    assert edited in resumed.run_queue.page._export_paths()
    worker.assert_called_once()


def test_manual_prompt_survives_back_and_forward(workspace):
    view, controller, gate, worker = workspace
    prepare_launch(controller)
    entry = view.project_state.clipart.prompts[0]
    entry.prompt = "My manual prompt"
    controller.navigate(-1)
    controller.navigate(1)
    assert view.project_state.clipart.prompts[0].prompt == "My manual prompt"
    worker.assert_not_called()


def test_revoked_automatic_right_blocks_worker(workspace):
    view, controller, gate, worker = workspace
    prepare_launch(controller)
    gate.authorize_run.return_value = authorization("clipart")
    assert controller.start() is None
    worker.assert_not_called()


def test_failed_save_blocks_window_close(workspace, monkeypatch):
    view, controller, gate, worker = workspace
    event = Mock()
    with monkeypatch.context() as patch:
        patch.setattr(view, "_save_draft", lambda: False)
        view.closeEvent(event)
    event.ignore.assert_called_once()


def test_interrupted_run_reopens_without_automatic_retry(workspace):
    from v3_run_queue import RunQueueSession, RunItemStatus
    from v3_clipart_flow import build_clipart_run_request
    from v3_project_state import ProjectMode
    view, controller, gate, worker = workspace
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), ProjectMode.CLIPART)
    controller.run_queue.session = session
    controller._save_run()
    # Simulate opening the persisted snapshot after process loss.
    session.running = False
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller("auto-clipart")
    resumed.save_timer.stop()
    assert resumed.run_queue.session.items[0].status is RunItemStatus.FAILED
    assert not resumed.run_queue.session.running
    worker.assert_not_called()


@pytest.mark.parametrize("value", [None, [], {"extra": True}, {"compiled": "bad"},
    {"run": [{"status": "succeeded", "output_path": "x", "attempts": True}]},
    {"run": [{"status": "succeeded", "output_path": "x", "attempts": 1, "editor_output_path": "y"}]}])
def test_invalid_automatic_metadata_rejected(value):
    from studio_auto_clipart_state import AutoClipartStateExtension
    with pytest.raises(ValueError):
        AutoClipartStateExtension().normalize_state({"clipart": {"automatic": value}})
