import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from PIL import Image, ImageDraw

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox
from PyQt6.QtCore import QObject, Qt, pyqtSignal

from license_client import LicenseAuthorization, ModuleEntitlement
from v3_clipart_flow import ClipartTransparencyEditorPage, build_clipart_run_request
from v3_mode_selection import V3ApplicationView
from v3_project_state import StepId
from v3_run_queue import RunItemStatus, RunQueueSession


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


def test_auto_worker_enables_sharp_cutout_fallback_without_changing_request(workspace, monkeypatch):
    _, controller, _, _ = workspace
    prepare_launch(controller)
    request = build_clipart_run_request(controller.shell.state)
    assert "auto_clipart_sharp_fallback" not in request.settings
    launched = []
    monkeypatch.setattr(type(controller.shell), "image_run_launch",
                        lambda _self, value: launched.append(value))
    controller.create_worker_for_request(request)
    assert launched[0].settings["auto_clipart_sharp_fallback"] is True
    assert "auto_clipart_sharp_fallback" not in request.settings


def test_transparency_editor_has_native_maximize_and_keeps_tools(workspace, monkeypatch):
    _, controller, _, _ = workspace
    prepare_launch(controller)
    request = build_clipart_run_request(controller.shell.state)
    session = RunQueueSession(request, controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    output = session.output_dir / "example_ready.png"
    Image.new("RGBA", (32, 32), (120, 80, 40, 255)).save(output)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(output)
    session.running = False
    controller.run_queue.session = session
    observed = {}

    def inspect_dialog(dialog):
        observed["maximize_button"] = bool(dialog.windowFlags() & Qt.WindowType.WindowMaximizeButtonHint)
        observed["minimize_button"] = bool(dialog.windowFlags() & Qt.WindowType.WindowMinimizeButtonHint)
        dialog.show()
        dialog.showMaximized()
        editor = dialog.findChild(ClipartTransparencyEditorPage)
        observed["maximized"] = dialog.isMaximized()
        observed["tools_visible"] = editor.right_panel.isVisible()
        dialog.showNormal()
        observed["restored"] = not dialog.isMaximized()
        return 0

    monkeypatch.setattr(QDialog, "exec", inspect_dialog)
    controller._open_transparency_editor(0)
    assert observed == {
        "maximize_button": True,
        "minimize_button": True,
        "maximized": True,
        "tools_visible": True,
        "restored": True,
    }


def test_export_step_embeds_editable_sets_and_persists_new_set(workspace, monkeypatch):
    _, controller, _, _ = workspace
    prepare_launch(controller)
    request = build_clipart_run_request(controller.shell.state)
    session = RunQueueSession(request, controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    output = session.output_dir / 'example_ready.png'
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
    image.save(output)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(output)
    session.running = False
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._refresh_export()
    panel = controller.export_panel
    assert panel is not None and panel.embedded and not panel.isWindow()
    assert panel.summary_sets_value.text() == '1'
    panel._show_create_page()
    panel.new_set_name.setText('Персонажи')
    panel._create_set()
    assert panel.summary_sets_value.text() == '2'
    assert len(controller.shell.state.data.export_membership[str(output)]['memberships']) == 2
    controller._refresh_export()
    assert controller.export_panel is panel
    monkeypatch.setattr(QMessageBox, 'question',
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    for set_id, _title in list(panel._set_catalog()):
        panel._delete_set(set_id)
    controller._refresh_export()
    assert controller.export_panel is panel
    assert panel.summary_sets_value.text() == '0'
    assert controller.shell.state.data.export_membership[str(output)]['memberships'] == []
    panel._show_create_page()
    panel.new_set_name.setText('Заново собранный набор')
    panel._create_set()
    assert panel.summary_sets_value.text() == '1'


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


def test_launch_quote_updates_for_model_without_references(workspace, monkeypatch):
    from v3_clipart_flow import estimate_clipart_cost

    view, controller, _, worker = workspace
    prepare_launch(controller)
    assert controller.launch_page.count() == 2
    controller.generation_page.refresh_from_state()
    assert not controller.generation_page.model_combo.isHidden()
    assert controller.generation_page.reference_controls_container.isHidden()
    models = controller.generation_page.model_combo
    models.setCurrentIndex(models.findData('gpt-image-2'))
    gpt_cost = estimate_clipart_cost(controller.shell.state)
    models.setCurrentIndex(models.findData('nano-banana-2'))
    banana_cost = estimate_clipart_cost(controller.shell.state)
    assert banana_cost.generation_usd != gpt_cost.generation_usd
    quote = []
    def decline(*args):
        quote.append(args[2])
        return QMessageBox.StandardButton.No
    monkeypatch.setattr(QMessageBox, 'question', decline)
    controller.navigate(1)
    assert view.project_state.current_step is StepId.REVIEW_RUN
    assert len(quote) == 1
    assert 'nano-banana-2' in quote[0]
    assert banana_cost.summary in quote[0]
    worker.assert_not_called()


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


def test_text_model_and_reference_consent_in_automatic_flow(workspace, tmp_path):
    _view, controller, _gate, _worker = workspace
    panel = controller.brief.planning
    panel.model.setCurrentIndex(panel.model.findData('openai/gpt-6-sol'))
    recipe, _ = controller.brief.snapshot()
    assert recipe.assistant == {'provider': 'openrouter', 'model': 'openai/gpt-6-sol'}
    path = tmp_path / 'reference.png'
    Image.new('RGB', (12, 12), 'red').save(path)
    controller.brief.reference_editor.references = [dict(path=str(path), roles=['technique'], notes='', enabled=True)]
    assert panel.reference_images() == ()
    panel.send_references.setChecked(True)
    assert panel.reference_images() == (str(path),)
    controller.brief.reference_editor.references[0]['enabled'] = False
    assert panel.reference_images() == ()
    panel.clear_reference_images()
    assert not panel.send_references.isChecked()


def test_automatic_prompt_review_hides_but_preserves_background_block(workspace):
    from chroma_key import chroma_key_prompt_block
    from v3_project_state import PromptEntry
    from v3_prompt_editor_ui import PromptReferenceEditorDialog
    view, controller, _gate, _worker = workspace
    suffix = '\n' + chroma_key_prompt_block('blue') + '\nReference image 1: use only for character.'
    view.project_state.clipart.prompts = [PromptEntry('Акварельный мишка' + suffix, chroma_key_color='blue')]
    controller.prompt_page.refresh_from_state()
    assert controller.prompt_page.table.item(0, 0).text() == 'Акварельный мишка'
    controller.prompt_page.table.item(0, 0).setText('Акварельный заяц')
    entry = view.project_state.clipart.prompts[0]
    assert entry.prompt == 'Акварельный заяц' + suffix
    editor = PromptReferenceEditorDialog(entry)
    assert editor._prompt_edit.toPlainText() == 'Акварельный заяц'
    assert editor.prompt_entry().prompt == entry.prompt
    assert editor.prompt_entry().prompt.count('Isolated on a completely flat') == 1
    assert editor.prompt_entry().chroma_key_color == 'blue'
    editor.close()


def test_incomplete_output_reopens_as_failed_and_stays_editable(workspace, tmp_path):
    from PIL import Image
    from v3_run_queue import RunQueueSession, RunItemStatus, transparency_candidate_paths
    from v3_clipart_flow import build_clipart_run_request
    from v3_project_state import ProjectMode
    view, controller, gate, worker = workspace
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), ProjectMode.CLIPART)
    output = session.output_dir / 'unfinished_ready.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (20, 20), 'white').save(output)
    session.handle_item_progress(dict(item_index=1, total_items=1,
        stage='background_removal', status='stage_skipped'))
    session.handle_item_progress(dict(item_index=1, total_items=1,
        stage='export', status='succeeded', output_path=str(output)))
    session.handle_finished()
    controller.run_queue.session = session
    controller._save_run()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    restored = resumed.run_queue.session
    assert restored.items[0].status is RunItemStatus.FAILED
    assert 'не готов к экспорту' in restored.items[0].short_message
    assert resumed.run_queue.page._export_paths() == []
    assert output.resolve() in transparency_candidate_paths(restored)
    worker.assert_not_called()


def test_zip_export_blocks_close_and_project_switch_until_finished(workspace, monkeypatch, tmp_path):
    from threading import Event
    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtWidgets import QFileDialog
    from studio_set_export_ui import SetExportDialog
    view, controller, _, _ = workspace
    started, release = Event(), Event()
    def delayed_export(*args, **kwargs):
        started.set()
        release.wait(5)
        return []
    monkeypatch.setattr('studio_set_export_ui.export_clipart_sets', delayed_export)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    png = tmp_path / 'ready.png'
    image = Image.new('RGBA', (64, 64))
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 60, 30, 255))
    image.save(png)
    panel = SetExportDialog([png], controller.export_page, embedded=True)
    controller.export_page.layout().addWidget(panel)
    controller.export_panel = panel
    busy = []
    panel.busy_changed.connect(lambda: busy.append(controller.is_busy()))
    panel._export()
    worker = panel.worker
    try:
        assert started.wait(2)
        assert controller.is_busy()
        event = QCloseEvent()
        view.closeEvent(event)
        assert not event.isAccepted()
        shell = view.shell
        view._handle_mode_selected('processing')
        assert view.shell is shell
        assert controller.export_panel is panel
        assert not worker.cancelled.is_set()
    finally:
        release.set()
        worker.wait(3000)
        QApplication.processEvents()
    assert panel.worker is None
    assert not controller.is_busy()
    assert busy == [True, False]


def test_saved_recovery_preserves_upscale_completion_and_uses_no_prompt(workspace, tmp_path):
    from pathlib import Path
    view, controller, _, worker = workspace
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    output = session.output_dir / 'upscaled_ready.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (64, 64), 'white').save(output)
    item = session.items[0]
    item.status = RunItemStatus.FAILED
    item.output_path = str(output)
    item.stage_statuses = {'upscale_after': 'complete', 'alpha_validation': 'failed'}
    session.handle_finished()
    controller.run_queue.session = session
    controller._save_run()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    restored = resumed.run_queue.session
    retry = restored.preview_retry()
    assert retry.mode == 'mode2_process'
    assert retry.selected_files == [str(output.resolve())]
    assert retry.generated_prompts == []
    assert retry.settings['upscale_after'] is False
    assert restored.items[0].stage_statuses['alpha_validation'] == 'failed'
    worker.assert_not_called()


def test_failed_generated_source_remains_local_after_reopening(workspace):
    view, controller, _, worker = workspace
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    raw = session.transient_dir / 'original.png'
    raw.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (64, 64), 'white').save(raw)
    item = session.items[0]
    item.status = RunItemStatus.FAILED
    item.source_path = str(raw)
    item.stage_statuses = {'background_removal': 'failed'}
    session.handle_finished()
    controller.run_queue.session = session
    controller._save_run()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    restored = resumed.run_queue.session
    assert restored.items[0].source_path == str(raw)
    retry = restored.preview_retry()
    assert retry.mode == 'mode2_process'
    assert retry.selected_files == [str(raw.resolve())]
    assert not retry.generated_prompts
    worker.assert_not_called()
