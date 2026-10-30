import os
from dataclasses import replace
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from PIL import Image, ImageDraw

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QFileDialog
from PyQt6.QtCore import QObject, Qt, pyqtSignal, QEventLoop, QTimer
from PyQt6 import sip

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



def wait_png_check(panel, timeout=20):
    """The export panel checks PNGs one by one in the background; export opens when it ends."""
    import time
    deadline = time.monotonic() + timeout
    while panel._qc_pending and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    assert not panel._qc_pending
    QApplication.processEvents()


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
    # A test may leave saving broken; closing then asks, and nobody answers offscreen.
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    if not sip.isdeleted(controller.save_timer):
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


def test_automatic_clipart_deliverable_settings_and_title(workspace):
    _view, controller, _gate, _worker = workspace
    # Old draft flags must not disable the automatic deliverable requirements.
    operations = controller.shell.state.data.operations
    operations.trim = False
    operations.trim_mode = "white"
    operations.export_300_dpi = False
    prepare_launch(controller)
    request = build_clipart_run_request(controller.shell.state)
    assert request.settings["trim_enabled"] is True
    assert request.settings["trim_mode"] == "alpha"
    assert request.settings["trim_padding_percent"] == 1
    assert request.settings["export_300_dpi"] is True
    assert _view.shell.mode_label.text() == "Автоматический клипарт"


def test_old_automatic_run_restores_delivery_flags(workspace):
    _view, controller, _gate, _worker = workspace
    prepare_launch(controller)
    controller.run_queue.session = RunQueueSession(
        build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    controller._save_run()
    operations = controller.shell.state.data.operations
    operations.trim = False
    operations.trim_mode = "white"
    operations.export_300_dpi = False
    controller._restore_run()
    settings = controller.run_queue.session.request.settings
    assert settings["trim_enabled"] is True
    assert settings["trim_mode"] == "alpha"
    assert settings["trim_padding_percent"] == 1
    assert settings["export_300_dpi"] is True


def test_restored_run_and_its_regeneration_keep_chroma_cutout_and_upscale(workspace):
    _view, controller, _gate, _worker = workspace
    prepare_launch(controller)
    controller.run_queue.session = RunQueueSession(
        build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    controller._save_run()
    operations = controller.shell.state.data.operations
    operations.remove_background = False
    operations.remove_background_provider = "kie"
    operations.upscale_after = False
    controller._restore_run()
    session = controller.run_queue.session
    settings = session.request.settings  # a regeneration copies these settings
    assert settings["remove_bg"] is True
    assert settings["remove_bg_provider"] == "local_chroma_key"
    assert settings["upscale_after"] is True


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


def test_reducing_existing_plan_uses_one_slot_and_restores_unused_ideas(workspace):
    view, controller, _, worker = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    original = controller.brief.object_editor.value()
    assert len(original) == 20
    for _ in range(5):
        controller.navigate(-1)
    controller.brief.total.setValue(1)
    prepare_launch(controller)
    assert len(controller.shell.state.data.prompts) == 1
    assert len(controller.brief.object_editor.items) == 1
    assert controller.shell.state.data.recipe['total'] == 1
    assert len(build_clipart_run_request(controller.shell.state).generated_prompts) == 1
    from studio_clipart_planner import planning_request
    recipe, palette = controller.brief._planning_snapshot()
    assert len(planning_request(recipe, palette)['targets']) == 1
    worker.assert_not_called()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    for _ in range(5):
        resumed.navigate(-1)
    resumed.brief.total.setValue(20)
    prepare_launch(resumed)
    assert [dict(item, pinned=item.get('pinned', False)) for item in resumed.brief.object_editor.value()] == [dict(item, pinned=item.get('pinned', False)) for item in original]
    assert len(resumed.shell.state.data.prompts) == 20
    worker.assert_not_called()


def test_edited_prompt_mark_survives_reopening_the_project(workspace):
    view, controller, _, _ = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    output = session.output_dir / 'single_ready.png'
    Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(output)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(output)
    session.items[0].prompt_edited = True
    # What «Изменить промпт» does: the text changes in the project's prompt record and in the run payload.
    controller.shell.state.data.prompts[0].prompt += ' Corrected by the owner.'
    session.items[0].payload['prompt'] = controller.shell.state.data.prompts[0].prompt
    for item in session.items[1:]:
        item.status = RunItemStatus.CANCELLED
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    assert resumed.run_queue.session.items[0].prompt_edited is True
    assert resumed.review.edited_paths() == {str(output.resolve())}


def test_cancelled_slots_do_not_block_ready_export_after_reopen(workspace, monkeypatch, tmp_path):
    view, controller, _, worker = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    output = session.output_dir / 'single_ready.png'
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
    image.save(output)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(output)
    # The owner pressed «Ок»: only confirmed pictures join export sets (SET-0, 2026-10-28).
    session.items[0].review_mark, session.items[0].review_checked = 'ok', True
    for item in session.items[1:]:
        item.status = RunItemStatus.CANCELLED
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    assert all(item.status is RunItemStatus.CANCELLED for item in resumed.run_queue.session.items[1:])
    resumed._refresh_export()
    wait_png_check(resumed.export_panel)
    assert resumed.export_panel.review_issues == []
    assert resumed.export_panel.export_button.isEnabled()
    assert resumed.export_panel.groups()[0]['images'] == [output.resolve()]
    export_folder = tmp_path / 'archives'
    export_folder.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(export_folder))
    resumed._select_step(StepId.TRANSPARENCY)
    view.shell.next_button.click()
    export_worker = resumed.export_panel.worker
    assert export_worker is not None
    loop = QEventLoop()
    export_worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert resumed.export_panel.worker is None
    assert resumed.export_panel.exported
    from zipfile import ZipFile
    for archive in resumed.export_panel.exported:
        with ZipFile(archive) as stream:
            assert stream.testzip() is None
            png_names = [name for name in stream.namelist() if name.endswith('.png')]
            assert len(png_names) == 1
            assert stream.read(png_names[0]) == output.read_bytes()
    worker.assert_not_called()


def test_active_run_cannot_be_replanned_until_cancelled_and_history_is_kept(workspace, monkeypatch):
    view, controller, _, factory = workspace
    fake_worker = FixtureWorker()
    factory.return_value = fake_worker
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    controller.upscale_provider.setCurrentIndex(controller.upscale_provider.findData('kie'))
    view.shell.go_next()
    session = controller.run_queue.session
    assert session.running and len(session.items) == 20
    controller.navigate(-1)
    assert controller.shell.state.current_step is StepId.RESULTS
    assert controller.run_queue.session is session
    assert fake_worker.running
    session.items[0].source_path = str(session.output_dir / 'kept_raw.png')
    session.items[0].paid_completed_stages = ('upscale_before',)
    controller.run_queue.stop_now()
    assert not fake_worker.running and not session.running
    assert all(item.status is RunItemStatus.CANCELLED for item in session.items)
    controller.navigate(-1)
    assert controller.run_queue.session is session
    assert len(controller.shell.state.data.automatic['run']) == 20
    for _ in range(5):
        controller.navigate(-1)
    controller.brief.total.setValue(1)
    prepare_launch(controller)
    assert controller.run_queue.session is None
    assert len(controller.shell.state.data.prompts) == 1
    archived = controller.shell.state.data.automatic['previous_runs'][-1]
    assert len(archived['prompts']) == 20 and len(archived['run']) == 20
    assert all(row['status'] == 'cancelled' for row in archived['run'])
    assert archived['run'][0]['source_path'] == session.items[0].source_path
    assert archived['run'][0]['paid_completed_stages'] == ['upscale_before']
    factory.assert_called_once()
    view.shell.go_next()
    assert factory.call_count == 2
    assert len(controller.run_queue.session.items) == 1
    controller.run_queue.stop_now()


def test_real_failed_requested_output_remains_an_export_issue(workspace):
    _, controller, _, factory = workspace
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.items[0].status = RunItemStatus.FAILED
    session.items[0].attempts = 1
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    assert controller.run_queue.page._bundle_export_issues() == [{
        'kind': 'missing', 'object_id': session.items[0].payload['object_id'], 'count': 0, 'paths': [],
    }]
    factory.assert_not_called()


def test_manual_object_edits_survive_reduced_plan_and_do_not_collide_with_unused_ideas(workspace):
    _, controller, _, factory = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    for _ in range(5):
        controller.navigate(-1)
    controller.brief.total.setValue(1)
    prepare_launch(controller)
    editor = controller.brief.object_editor
    editor.add()
    editor.fields['name'].setText('Manual flower')
    controller.flush()
    assert controller.brief.recipe.total == 2
    assert controller.brief.total.value() == 2
    assert controller.brief.sum_label.text() == 'Всего изображений: 2'
    assert len(editor.items) == 2
    combined = editor.items + controller.shell.state.data.automatic['inactive_objects']
    assert len({item['id'] for item in combined}) == len(combined)
    assert len({item['ordinal'] for item in combined}) == len(combined)
    from studio_auto_clipart_state import AutoClipartStateExtension
    AutoClipartStateExtension().normalize_state({'clipart': controller.shell.state.data.to_dict()})
    factory.assert_not_called()


@pytest.mark.parametrize('case', ['not_list', 'duplicate_id', 'duplicate_ordinal', 'too_many'])
def test_inactive_idea_schema_rejects_invalid_combined_records(case):
    from studio_auto_clipart_state import AutoClipartStateExtension
    from studio_clipart_objects import new_object
    active = new_object('hero', 1)
    inactive = [new_object('decor', 2)]
    if case == 'not_list':
        inactive = None
    elif case == 'duplicate_id':
        inactive[0]['id'] = active['id']
    elif case == 'duplicate_ordinal':
        inactive[0]['ordinal'] = 1
    else:
        inactive = [new_object('decor', index) for index in range(2, 1002)]
    with pytest.raises(ValueError):
        AutoClipartStateExtension().normalize_state({'clipart': {
            'recipe': {'objects': [active]}, 'automatic': {'inactive_objects': inactive},
        }})


@pytest.mark.parametrize('entry', [{}, {'prompts': [], 'run': []},
    {'prompts': [{'prompt': 'x', 'result_kind': 'clipart', 'object_id': 'a'}], 'run': []},
    {'prompts': [{'prompt': 'x'}], 'run': [{'status': 'failed', 'output_path': '', 'attempts': 1}]}])
def test_previous_run_schema_rejects_invalid_history(entry):
    from studio_auto_clipart_state import AutoClipartStateExtension
    with pytest.raises(ValueError):
        AutoClipartStateExtension().normalize_state({'clipart': {'automatic': {'previous_runs': [entry]}}})


@pytest.mark.parametrize('change', ['none', 'manual_keep_hero', 'prompt', 'settings', 'missing_png', 'legacy_settings'])
def test_replan_reuses_ready_output_only_with_confirmed_unchanged_provenance(workspace, monkeypatch, tmp_path, change):
    view, controller, _, factory = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    output = session.output_dir / 'retained_ready.png'
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
    image.save(output)
    # The approved balanced recipe for one image retains the first decor idea.
    role = 'hero' if change == 'manual_keep_hero' else 'decor'
    retained_id = next(item['id'] for item in controller.brief.object_editor.items if item['role'] == role)
    ready_item = next(item for item in session.items if item.payload['object_id'] == retained_id)
    for item in session.items:
        item.status = RunItemStatus.FAILED
    ready_item.status = RunItemStatus.SUCCEEDED
    ready_item.output_path = str(output)
    ready_item.paid_completed_stages = ('upscale_after',)
    # The owner pressed «Ок» on the retained picture before the replan (SET-0, 2026-10-28).
    ready_item.review_mark, ready_item.review_checked = 'ok', True
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    if change == 'legacy_settings':
        controller.shell.state.data.automatic.pop('run_settings_fingerprint')
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    for _ in range(5):
        resumed.navigate(-1)
    if change != 'manual_keep_hero':
        resumed.brief.total.setValue(1)
    if change == 'settings':
        resumed.shell.state.data.operations.unsharp = not resumed.shell.state.data.operations.unsharp
    if change == 'missing_png':
        output.unlink()
    for _ in range(4):
        resumed.navigate(1)
    if change == 'manual_keep_hero':
        editor = resumed.brief.object_editor
        while len(editor.items) > 1:
            editor.list.setCurrentRow(len(editor.items) - 1)
            editor.remove()
        assert editor.items[0]['id'] == retained_id
    if change == 'prompt':
        resumed.brief.object_editor.items[0]['name'] = 'Different asset'
        resumed.brief.object_editor.refresh()
    view.shell.next_button.click()
    archive = resumed.shell.state.data.automatic['previous_runs'][-1]
    assert len(archive['run']) == 20
    assert archive['run'][ready_item.index - 1]['paid_completed_stages'] == ['upscale_after']
    if change not in {'none', 'manual_keep_hero'}:
        assert resumed.run_queue.session is None
        factory.assert_not_called()
        return
    retained = resumed.run_queue.session
    assert retained is not None and len(retained.items) == 1 and not retained.running
    assert resumed.brief.sum_label.text() == 'Всего изображений: 1'
    assert resumed.shell.state.current_step is StepId.RESULTS
    assert retained.items[0].status is RunItemStatus.SUCCEEDED
    assert retained.items[0].output_path == str(output)
    assert retained.items[0].paid_completed_stages == ('upscale_after',)
    resumed._refresh_export()
    wait_png_check(resumed.export_panel)
    assert resumed.export_panel.review_issues == []
    assert resumed.export_panel.export_button.isEnabled()
    resumed.flush()
    assert view.continue_saved_project(view._active_project_id)
    reopened = view.shell.workflow_controller('auto-clipart')
    reopened.save_timer.stop()
    assert reopened.shell.state.current_step is StepId.RESULTS
    view.shell.next_button.click()
    assert reopened.shell.state.current_step is StepId.TRANSPARENCY
    wait_png_check(reopened.export_panel)
    export_folder = tmp_path / 'replanned-archives'
    export_folder.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(export_folder))
    view.shell.next_button.click()
    worker = reopened.export_panel.worker
    assert worker is not None
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    from zipfile import ZipFile
    assert reopened.export_panel.exported
    for archive_path in reopened.export_panel.exported:
        with ZipFile(archive_path) as stream:
            assert stream.testzip() is None
            names = [name for name in stream.namelist() if name.endswith('.png')]
            assert len(names) == 1 and stream.read(names[0]) == output.read_bytes()
    factory.assert_not_called()


@pytest.mark.parametrize('missing_paid_output', [False, True])
def test_mixed_reused_results_retry_only_failed_and_preserve_missing_paid_provenance(workspace, monkeypatch, missing_paid_output):
    view, controller, _, factory = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    controller.upscale_provider.setCurrentIndex(controller.upscale_provider.findData('kie'))
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    ids = {role: next(item['id'] for item in controller.brief.object_editor.items if item['role'] == role)
           for role in ('hero', 'decor')}
    ready = next(item for item in session.items if item.payload['object_id'] == ids['hero'])
    failed = next(item for item in session.items if item.payload['object_id'] == ids['decor'])
    for item in session.items:
        item.status = RunItemStatus.FAILED
    ready.output_path = str(session.output_dir / 'kept_ready.png')
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
    image.save(ready.output_path)
    ready.status = RunItemStatus.SUCCEEDED
    # The owner pressed «Ок» on the kept picture before the replan (SET-0, 2026-10-28).
    ready.review_mark, ready.review_checked = 'ok', True
    if missing_paid_output:
        failed.status = RunItemStatus.SUCCEEDED
        failed.output_path = str(session.output_dir / 'deleted_paid_ready.png')
        failed.source_path = str(session.output_dir / 'preserved_raw.png')
        image.save(failed.source_path)
        failed.attempts = 4
        failed.paid_completed_stages = ('upscale_after',)
        failed.stage_statuses = {'generation': 'complete', 'upscale_after': 'complete'}
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    for _ in range(5):
        controller.navigate(-1)
    controller.brief.total.setValue(2)
    for _ in range(4):
        controller.navigate(1)
    view.shell.next_button.click()
    mixed = controller.run_queue.session
    assert controller.shell.state.current_step is StepId.RESULTS
    assert len(mixed.items) == 2
    kept = next(item for item in mixed.items if item.payload['object_id'] == ids['hero'])
    problem = next(item for item in mixed.items if item.payload['object_id'] == ids['decor'])
    assert kept.status is RunItemStatus.SUCCEEDED and problem.status is RunItemStatus.FAILED
    assert controller.run_queue.page.retry_button.isEnabled()
    assert len(controller.run_queue.page._bundle_export_issues()) == 1
    factory.assert_not_called()
    if missing_paid_output:
        assert problem.output_path == failed.output_path and problem.source_path == failed.source_path
        assert problem.attempts == 4 and problem.paid_completed_stages == ('upscale_after',)
        assert problem.stage_statuses == failed.stage_statuses
        assert problem.short_message == 'Сохранённый PNG недоступен. Проверьте файл результата.'
        assert Path(problem.source_path).is_file()
        assert mixed.preview_retry() is None
        controller.run_queue.page.retry_button.click()
        factory.assert_not_called()
    else:
        preview = mixed.preview_retry()
        assert len(preview.generated_prompts) == 1
        assert preview.generated_prompts[0]['object_id'] == ids['decor']
        factory.return_value = FixtureWorker()
        controller.run_queue.page.retry_button.click()
        factory.assert_called_once()
        assert len(factory.call_args.kwargs['generated_prompts']) == 1
        assert kept.status is RunItemStatus.SUCCEEDED
        controller.run_queue.stop_now()


def test_increased_reused_plan_resumes_only_19_unsubmitted_items_with_explicit_click(workspace, monkeypatch):
    view, controller, _, factory = workspace
    prepare_launch(controller)
    controller.upscale_provider.setCurrentIndex(controller.upscale_provider.findData('kie'))
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    output = session.output_dir / 'previous_ready.png'
    image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
    image.save(output)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(output)
    retained_id = session.items[0].payload['object_id']
    # The owner pressed «Ок» on the retained picture (SET-0, 2026-10-28).
    session.items[0].review_mark, session.items[0].review_checked = 'ok', True
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    for _ in range(5):
        controller.navigate(-1)
    controller.brief.total.setValue(20)
    for _ in range(4):
        controller.navigate(1)
    for item in controller.brief.object_editor.items:
        item['name'] = 'Winter flower'
    controller.brief.object_editor.refresh()
    confirmations = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: confirmations.append(args[2]) or QMessageBox.StandardButton.Yes)
    view.shell.next_button.click()
    resumed = controller.run_queue.session
    assert controller.shell.state.current_step is StepId.RESULTS
    assert len(resumed.items) == 20 and len(resumed.failed_indices) == 0
    assert len([item for item in resumed.items if item.status is RunItemStatus.CANCELLED and item.attempts == 0]) == 19
    factory.assert_not_called()
    assert controller.run_queue.page.retry_button.isEnabled()
    assert controller.run_queue.page.retry_button.text() == 'Доделать оставшиеся (19)'
    preview = resumed.preview_retry()
    assert len(preview.generated_prompts) == 19
    assert retained_id not in {item['object_id'] for item in preview.generated_prompts}
    factory.return_value = FixtureWorker()
    controller.run_queue.page.retry_button.click()
    assert len(confirmations) == 2
    factory.assert_called_once()
    assert len(factory.call_args.kwargs['generated_prompts']) == 19
    retained = next(item for item in resumed.items if item.payload['object_id'] == retained_id)
    assert retained.status is RunItemStatus.SUCCEEDED and retained.output_path == str(output)
    controller.run_queue.stop_now()


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


def test_png_check_keeps_its_page_and_selected_picture_when_a_file_changes(workspace):
    import time
    _, controller, _, _ = workspace
    prepare_launch(controller)
    request = build_clipart_run_request(controller.shell.state)
    session = RunQueueSession(request, controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    while len(session.items) < 2:
        session.items.append(replace(session.items[0], index=len(session.items) + 1))
    for index in range(2):
        output = session.output_dir / f'example_{index}_ready.png'
        Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(output)
        session.items[index].status = RunItemStatus.SUCCEEDED
        session.items[index].output_path = str(output)
        outputs.append(output)
    session.running = False
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)

    def wait_checked():
        deadline = time.monotonic() + 10
        while controller.export_panel._qc_pending and time.monotonic() < deadline:
            QApplication.processEvents()
            time.sleep(0.01)
        QApplication.processEvents()

    controller._refresh_export()
    wait_checked()
    controller.export_panel._show_quality_review()
    controller.export_panel.quality_list.setCurrentRow(1)
    selected = controller.export_panel._current_quality_key()
    assert selected == str(outputs[1].resolve())
    old_panel = controller.export_panel
    Image.new('RGBA', (64, 64), (10, 20, 30, 255)).save(outputs[0])  # another picture was redone
    controller._refresh_export()
    assert controller.export_panel is not old_panel  # the panel is rebuilt for the new file
    wait_checked()
    panel = controller.export_panel
    assert panel.stack.currentWidget() is panel.quality_page
    assert panel._current_quality_key() == selected


def test_regenerated_picture_stays_in_the_png_check_list(workspace):
    """AC-R1 (owner 2026-10-28): after «Перегенерировать» the picture appears among the PNG previews
    again. The regenerated picture loses its «Ок» mark, so the check list must not be built from the
    confirmed set members alone — sets stay confirmed-only, the review shows every ready picture."""
    _, controller, _, _ = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for index in range(3):
        path = session.output_dir / f'flower_{index + 1:02d}_ready.png'
        Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(path)
        session.items[index].status = RunItemStatus.SUCCEEDED
        session.items[index].output_path = str(path)
        session.items[index].review_mark, session.items[index].review_checked = 'ok', True
        outputs.append(path)
    session.running = False
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._refresh_export()
    wait_png_check(controller.export_panel)
    panel = controller.export_panel
    panel._show_quality_review()
    keys = [panel.quality_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(panel.quality_list.count())]
    assert sorted(key for key in keys if key) == sorted(str(path.resolve()) for path in outputs)
    # The regeneration keeps the old picture as a version and clears its marks (see studio_clipart_versions).
    session.items[0].review_mark, session.items[0].review_checked = 'ok', False
    Image.new('RGBA', (64, 64), (10, 20, 30, 255)).save(outputs[0])
    controller._refresh_export()
    wait_png_check(controller.export_panel)
    panel = controller.export_panel
    panel._show_quality_review()
    listed = [panel.quality_list.item(row).data(Qt.ItemDataRole.UserRole)
              for row in range(panel.quality_list.count())]
    assert str(outputs[0].resolve()) in [key for key in listed if key]
    assert panel.quality_list.count() == 3
    # The unconfirmed picture is not a set member yet.
    assert outputs[0].resolve() not in [Path(path) for path in panel.paths]
    # While a redo runs the check page keeps the other ready pictures on screen instead of emptying.
    session.running = True
    session.items[0].status = RunItemStatus.PENDING
    session.items[0].output_path = ''
    controller._refresh_export()
    assert len(controller.export_panel.review_paths) == 2
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(outputs[0])
    session.running = False


def test_gallery_badges_every_mark_note_and_survives_a_reopen(workspace):
    """Owner 2026-10-29: the PNG gallery badges every state (принято / брак генерации / брак
    вырезания), a corrected prompt and a note; the badges come from the session, so they survive
    leaving the page, reopening the project and switching projects."""
    from studio_clipart_versions import keep_version
    _, controller, _, _ = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for index in range(3):
        path = session.output_dir / f'flower_{index + 1:02d}_ready.png'
        Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(path)
        session.items[index].status = RunItemStatus.SUCCEEDED
        session.items[index].output_path = str(path)
        paths.append(path)
    session.items[0].review_mark, session.items[0].review_checked = 'ok', False   # «Не проверено»
    session.items[1].review_mark, session.items[1].review_checked = 'bad_cutout', True
    session.items[2].review_mark, session.items[2].review_checked = 'bad_generation', True
    session.items[2].review_note = 'переснять фон'
    session.items[2].prompt_edited = True
    session.running = False
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._refresh_export()
    wait_png_check(controller.export_panel)
    panel = controller.export_panel
    panel._show_quality_review()
    assert panel._marks[str(paths[1].resolve())] == 'bad_cutout'
    assert panel._marks[str(paths[2].resolve())] == 'bad_generation'
    assert panel._notes[str(paths[2].resolve())] == 'переснять фон'
    assert str(paths[2].resolve()) in panel._edited
    # The badges are drawn: a marked picture's thumbnail differs from a plain one.
    marked = panel._quality_icon(str(paths[1].resolve()), None, True, True).pixmap(120, 120).toImage()
    plain = panel._quality_icon(str(paths[0].resolve()), None, True, True).pixmap(120, 120).toImage()
    assert marked != plain
    # The state is explained on hover.
    tooltips = {panel.quality_list.item(row).data(Qt.ItemDataRole.UserRole):
                panel.quality_list.item(row).toolTip() for row in range(panel.quality_list.count())}
    assert 'Брак вырезания' in tooltips[str(paths[1].resolve())]
    assert 'промпт исправлен' in tooltips[str(paths[2].resolve())]
    assert 'заметка: переснять фон' in tooltips[str(paths[2].resolve())]
    # A fresh page over the same session (leaving the step, reopening the project) shows the same badges.
    reopened = controller.review.notes_by_path()
    assert reopened[str(paths[2].resolve())] == 'переснять фон'
    assert controller.review.marks_by_path()[str(paths[1].resolve())] == 'bad_cutout'
    assert str(paths[2].resolve()) in controller.review.edited_paths()
    # A regeneration moves the mark and the note into the saved version and clears them (owner 2026-10-29);
    # «промпт исправлен» stays because the prompt really was corrected.
    assert keep_version(session.items[2], session.output_dir, prompt='зимний цветок')
    assert session.items[2].review_mark == 'ok' and session.items[2].review_checked is False
    assert session.items[2].review_note == '' and session.items[2].prompt_edited is True
    assert session.items[2].versions and session.items[2].versions[-1]['note'] == 'переснять фон'
    # Removing a note takes its badge away with it.
    session.items[2].review_note = 'временная'
    assert str(paths[2].resolve()) in controller.review.notes_by_path()
    session.items[2].review_note = ''
    assert str(paths[2].resolve()) not in controller.review.notes_by_path()


def test_second_redo_asked_while_one_runs_waits_in_a_queue_and_starts_after(workspace, monkeypatch):
    _, controller, _, _ = workspace
    prepare_launch(controller)
    request = build_clipart_run_request(controller.shell.state)
    session = RunQueueSession(request, controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    first, second = session.output_dir / 'a_ready.png', session.output_dir / 'b_ready.png'
    controller.run_queue.session = session
    started = []
    monkeypatch.setattr(controller.review, 'regenerate_path', lambda path: started.append(('regenerate', path)) or object())
    monkeypatch.setattr(controller.review, 'cutout_path', lambda path: started.append(('cutout', path)) or object())
    notes = []
    monkeypatch.setattr(QMessageBox, 'information', lambda *args, **kwargs: notes.append(args[2]))
    session.running = True
    controller._regenerate_from_png_check(str(second))
    controller._cutout_from_png_check(str(first))
    controller._cutout_from_png_check(str(first))  # asking twice does not queue it twice
    assert started == [] and len(controller._redo_queue) == 2
    # Owner 2026-10-29: the second ask for the same picture is refused with a note, not queued again.
    assert notes == ["Эта картинка уже переделывается. Дождитесь окончания — второй раз запускать не нужно."]
    session.running = False
    controller._start_queued_redo()
    assert started == [('regenerate', str(second))]  # one at a time, in the order asked
    assert controller._redo_queue == [('cutout', str(first))]
    controller._redo_queue.clear()  # no stray timer may start it in a later test


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
    # The owner pressed «Ок»: only confirmed pictures join export sets (SET-0, 2026-10-28).
    session.items[0].review_mark, session.items[0].review_checked = 'ok', True
    session.running = False
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._refresh_export()
    panel = controller.export_panel
    assert panel is not None and panel.embedded and not panel.isWindow()
    assert panel.table.columnCount() == 2
    panel._show_create_page()
    panel.new_set_name.setText('Персонажи')
    panel._create_set()
    assert panel.table.columnCount() == 3
    assert len(controller.shell.state.data.export_membership[str(output)]['memberships']) == 2
    controller._refresh_export()
    assert controller.export_panel is panel
    monkeypatch.setattr(QMessageBox, 'question',
                        lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    for set_id, _title in list(panel._set_catalog()):
        panel._delete_set(set_id)
    controller._refresh_export()
    assert controller.export_panel is panel
    assert panel.table.columnCount() == 1
    assert controller.shell.state.data.export_membership[str(output)]['memberships'] == []
    panel._show_create_page()
    panel.new_set_name.setText('Заново собранный набор')
    panel._create_set()
    assert panel.table.columnCount() == 2


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
    assert f'ориентировочно ${banana_cost.estimated_usd:.3f}' in quote[0]
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
    # The owner pressed «Ок»: only confirmed pictures join export sets (SET-0, 2026-10-28).
    session.items[0].review_mark, session.items[0].review_checked = "ok", True
    controller.navigate(1)
    assert view.project_state.current_step is StepId.TRANSPARENCY
    wait_png_check(controller.export_panel)
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
        ask = Mock(return_value=QMessageBox.StandardButton.No)  # the user declines to close
        patch.setattr(QMessageBox, "question", ask)
        view.closeEvent(event)
    ask.assert_called_once()
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


def test_run_history_is_trimmed_so_the_project_stays_savable(workspace, monkeypatch):
    import json
    import studio_auto_clipart_flow
    monkeypatch.setattr(studio_auto_clipart_flow, 'PREVIOUS_RUNS_MAX_BYTES', 20000)
    PREVIOUS_RUNS_MAX_BYTES = 20000
    _view, controller, _gate, _worker = workspace
    prepare_launch(controller)
    data = controller.shell.state.data
    controller.run_queue.session = RunQueueSession(
        build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    for index in range(40):
        for item in controller.run_queue.session.items:
            item.payload['prompt'] = f'prompt {index} ' + 'x' * 40000
        data.automatic['run'] = [
            {'status': 'failed', 'output_path': '', 'attempts': index}
            for _ in controller.run_queue.session.items]
        controller._archive_run()
    history = data.automatic['previous_runs']
    assert 1 <= len(history) < 40
    assert len(json.dumps(history, ensure_ascii=False).encode()) <= PREVIOUS_RUNS_MAX_BYTES * 1.1
    assert history[-1]['run'][0]['attempts'] == 39


def test_failing_save_does_not_trap_the_close_button(workspace, monkeypatch):
    from PyQt6.QtGui import QCloseEvent
    view, controller, _, _ = workspace
    monkeypatch.setattr(view, "_save_before_leaving", lambda: False)
    answers = [QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes]
    monkeypatch.setattr(QMessageBox, "question",
                        lambda *a: answers.pop(0) if answers else QMessageBox.StandardButton.Yes)
    refused = QCloseEvent()
    view.closeEvent(refused)
    assert not refused.isAccepted()
    # The second answer lets the close proceed instead of silently refusing it.
    assert view._confirm_close_without_saving() is True
    assert not answers


def test_save_failure_journal_keeps_error_chain(workspace):
    view, controller, _, _ = workspace
    events = []
    prepare_launch(controller)

    def broken(*args, **kwargs):
        raise ValueError("Неверная история запусков набора")

    # A scoped patch: the fixture teardown closes the window and must save normally.
    with pytest.MonkeyPatch.context() as local:
        local.setattr(view, "_diagnostic_event", lambda event, summary, **kw: events.append((event, kw)))
        local.setattr(view._project_documents, "save", broken)
        local.setattr(view._project_documents, "create", broken)
        assert view._save_draft() is False
    saved = [kw for name, kw in events if name == "save_failed"][0]["details"]
    assert saved["error_code"] == "ValueError"
    assert saved["error_message"] == "Неверная история запусков набора"


def test_saved_recovery_preserves_upscale_completion_and_uses_no_prompt(workspace, tmp_path):
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
    assert restored.items[0].paid_completed_stages == ('upscale_after',)
    worker.assert_not_called()


def test_failed_generated_source_remains_local_after_reopening(workspace, monkeypatch):
    view, controller, _, worker = workspace
    prepare_launch(controller)
    from main import WorkerThread
    controller.shell.state.data.operations.upscale_after = False
    request = build_clipart_run_request(controller.shell.state)
    request.settings['kie_api_key'] = 'fixture-only'
    session = RunQueueSession(request, controller.shell.state.mode)
    actual = WorkerThread(**request.worker_kwargs())
    monkeypatch.setattr(actual, '_kie_generate_image', lambda *args: 'https://fixture.invalid/raw.png')
    monkeypatch.setattr(actual, '_download_file', lambda url, path: Image.new('RGB', (64, 64), 'blue').save(path))
    def fail_processing(*args, **kwargs):
        raise RuntimeError('Local processing failure after generation')
    monkeypatch.setattr(actual, '_run_processing_pipeline', fail_processing)
    actual.item_progress.connect(session.handle_item_progress, Qt.ConnectionType.DirectConnection)
    actual.diagnostic.connect(session.handle_diagnostic, Qt.ConnectionType.DirectConnection)
    actual.completed.connect(lambda message: session.handle_finished(), Qt.ConnectionType.DirectConnection)
    actual.error.connect(session.handle_fatal_error, Qt.ConnectionType.DirectConnection)
    actual.run()
    item = session.items[0]
    assert item.status is RunItemStatus.FAILED
    raw = Path(item.source_path)
    assert raw.is_file()
    controller.run_queue.session = session
    controller._save_run()
    controller.save_timer.stop()
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    restored = resumed.run_queue.session
    assert restored.items[0].source_path == str(raw)
    assert raw.is_file()
    retry = restored.preview_retry()
    assert retry.mode == 'mode2_process'
    assert retry.selected_files == [str(raw.resolve())]
    assert not retry.generated_prompts
    worker.assert_not_called()




import hashlib
import json


def test_launch_confirmation_discloses_expired_results_in_one_dialog(
    app, workspace, monkeypatch,
):
    """The single launch dialog already names payable re-generation.

    The rendered screenshot doubles as owner-facing UI evidence for 3.2.30;
    answering No after the capture keeps the run unstarted."""
    from PyQt6.QtWidgets import QMessageBox
    from fal_provider import FalTaskJournal
    from gpt25_provider import generation_payload
    from v3_clipart_flow import build_clipart_run_request

    evidence = Path(__file__).resolve().parents[1].parent / "artifacts" / "studio-3.2.30-stable-20261019"
    evidence.mkdir(parents=True, exist_ok=True)
    view, controller, _gate, _worker = workspace
    prepare_launch(controller)
    generation_page = controller.generation_page
    option_index = generation_page.model_combo.findData("piapi/gpt-image-2.5-flare")
    assert option_index >= 0, generation_page.model_combo.itemText(0)
    generation_page.model_combo.setCurrentIndex(option_index)
    app.processEvents()
    prepared = build_clipart_run_request(controller.shell.state)
    assert "one continuous closed silhouette" in prepared.generated_prompts[0]["prompt"]
    model = prepared.settings["text_generation_model"]
    assert model == "piapi/gpt-image-2.5-flare"
    entry = prepared.generated_prompts[0]
    payload = generation_payload(
        model, entry["prompt"],
        prepared.settings.get("text_generation_ratio", "1:1"),
        prepared.settings.get("text_generation_resolution", "1K"),
    )
    fingerprint = hashlib.sha256(json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    journal = Path(prepared.work_dir) / ".vibix_piapi_tasks.json"
    FalTaskJournal(journal).upsert(
        "old", "generation", model, "expired", input_fingerprint=fingerprint,
    )

    captured = {}

    def record_question(_parent, title, text, *args, **kwargs):
        captured["title"], captured["text"] = title, text
        box = QMessageBox(_parent)
        box.setWindowTitle(title)
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(text)
        box.show()
        app.processEvents()
        box.grab().save(str(evidence / "ui-single-launch-confirmation.png"))
        box.close()
        box.deleteLater()
        return QMessageBox.StandardButton.No

    monkeypatch.setattr(QMessageBox, "question", record_question)
    controller.navigate(1)
    app.processEvents()

    assert captured["title"] == "Подтвердить запуск"
    assert "заранее неизвестна" in captured["text"]
    assert "генерация 1" in captured["text"]
    assert "прежние результаты для 1 объекта (PiAPI) больше недоступны" in captured["text"]
    # Owner 2026-10-29: the long «платно/тариф» warning is gone from the confirmation.
    assert "платную генерацию по текущему тарифу" not in captured["text"]
    assert controller.shell.state.current_step is StepId.REVIEW_RUN


def test_refused_launch_after_confirmation_is_reported_visibly(app, workspace, monkeypatch):
    """A start refused after "Yes" must not look like nothing happened."""
    from PyQt6.QtWidgets import QMessageBox

    view, controller, _gate, _worker = workspace
    prepare_launch(controller)
    warnings = []
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, title, text, *a, **k: warnings.append((title, text)))

    def refuse():
        controller.error.emit("Причина отказа")
        return None

    monkeypatch.setattr(controller, "start", refuse)
    controller.navigate(1)

    assert warnings == [("Запуск не выполнен", "Причина отказа")]
    assert controller._start_errors is None


def test_launch_confirmation_is_short_structured_and_readable():
    from types import SimpleNamespace
    from studio_auto_clipart_flow import launch_confirmation_html

    cost = SimpleNamespace(request_count=2, generation_request_count=1, processing_request_count=1,
                           complete=False, incomplete_providers=("fal", "piapi"), estimated_usd=0)
    text = launch_confirmation_html(
        object_count=1, models=["piapi/gpt-image-2.5"], cost=cost,
        references=["C:/refs/24_gosling_reading_in_garden.png"], reference_model="piapi/gpt-image-2.5")
    lines = text.split("<br>")
    assert lines[0] == "<b>Создать изображения: 1 объект?</b>"
    assert "<b>Модель:</b> piapi/gpt-image-2.5" in lines
    assert "<b>Запросов:</b> 2 (генерация 1, обработка 1)" in lines
    assert any(line.startswith("<b>Цена:</b> заранее неизвестна") for line in lines)
    assert "<b>Референсы (1):</b> получит модель piapi/gpt-image-2.5" in lines
    assert "• 24_gosling_reading_in_garden.png" in lines
    assert max(len(line) for line in lines) < 90        # no wall of text

    known = SimpleNamespace(request_count=3, generation_request_count=3, processing_request_count=0,
                            complete=True, incomplete_providers=(), estimated_usd=0.5)
    assert "<b>Цена:</b> ориентировочно $0.500" in launch_confirmation_html(
        object_count=5, models=["a", "b"], cost=known).split("<br>")
    assert "Создать изображения: 5 объектов?" in launch_confirmation_html(object_count=5, models=["a"], cost=known)
    assert "Создать изображения: 22 объекта?" in launch_confirmation_html(object_count=22, models=["a"], cost=known)
    assert "<b>Модели:</b> a, b" in launch_confirmation_html(object_count=2, models=["a", "b"], cost=known)


def test_ready_files_in_the_result_folder_can_be_reconnected_without_generation(workspace, monkeypatch):
    """Owner 2026-10-25: a new run was started and stopped, the old results vanished from the project, but the
    PNG files were still in the result folder."""
    view, controller, _, worker = workspace
    controller.brief.total.setValue(6)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    for number in (1, 2, 4):
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
        image.save(session.output_dir / f'flower_{number:02d}_ready.png')
    for item in session.items:
        item.status = RunItemStatus.CANCELLED
        item.short_message = 'Не выполнялся после остановки.'
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()
    controller._refresh_more_menu()
    assert controller.more_recover_action.isVisible()
    assert controller.more_recover_action.text() == 'Вернуть готовые файлы (3)'
    assert controller._recoverable_outputs().keys() == {0, 1, 3}
    asked = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: asked.append(args[2]) or QMessageBox.StandardButton.Yes)
    controller.recover_results()
    assert 'найдено готовых PNG: 3' in asked[0] and 'платных запросов нет' in asked[0]
    done = [item for item in session.items if item.status is RunItemStatus.SUCCEEDED]
    assert [Path(item.output_path).name for item in done] == [
        'flower_01_ready.png', 'flower_02_ready.png', 'flower_04_ready.png']
    assert all(not item.review_checked for item in done)  # still «Не проверено»
    # Reconnected pictures are results, not set members, until the owner confirms «Ок» (SET-0, 2026-10-28).
    assert controller.run_queue.page._export_paths() == []
    for item in done:
        item.review_mark, item.review_checked = 'ok', True
    assert len(controller.run_queue.page._export_paths()) == 3
    assert controller._recoverable_outputs() == {}
    controller.recover_results()  # nothing left: no second question
    assert len(asked) == 1
    worker.assert_not_called()


def test_results_png_check_button_opens_png_check_before_export(workspace):
    view, controller, _, _ = workspace
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    path = session.output_dir / 'duck_birthday_01.png'
    image = Image.new('RGBA', (96, 96), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((12, 12, 83, 83), fill=(240, 200, 140, 255))
    image.save(path)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(path)
    # The owner pressed «Ок»: only confirmed pictures reach the PNG check (SET-0, 2026-10-28).
    session.items[0].review_mark, session.items[0].review_checked = 'ok', True
    for item in session.items[1:]:
        item.status = RunItemStatus.FAILED
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._select_step(StepId.RESULTS)
    button = controller.run_queue.page.check_transparency_button
    assert button.text() == "Проверка PNG"
    controller._open_png_check()
    assert view.project_state.current_step is StepId.TRANSPARENCY
    panel = controller.export_panel
    wait_png_check(panel)
    assert panel.stack.currentWidget() is panel.quality_page
    assert panel.quality_list.count() == 1


def test_reopened_project_journals_refused_regeneration_and_keeps_pictures(workspace, monkeypatch):
    """Owner 2026-10-27 (UP-14): after reopening a project «Пересоздать помеченные» failed every
    picture with the generic stub, and the diagnostics had no run events at all."""
    import studio_image_run_services
    view, controller, _gate, factory = workspace
    controller.brief.total.setValue(2)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(session.items):
        output = session.output_dir / f'picture{index}_ready.png'
        Image.new('RGBA', (64, 64), (200, 0, 0, 255)).save(output)
        item.status, item.output_path, item.attempts = RunItemStatus.SUCCEEDED, str(output), 1
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()
    journal = Mock()
    view._diagnostic_journal = journal
    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    restored = resumed.run_queue.session
    before = [item.output_path for item in restored.items]
    for item in restored.items:
        item.review_mark = 'bad_generation'
    monkeypatch.setattr(studio_image_run_services, 'missing_runtime_requirements',
                        lambda _request: ('KIE API Key',))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    resumed.review.recreate_marked()
    factory.assert_not_called()
    events = {call.args[0]: call.kwargs for call in journal.record.call_args_list}
    assert 'regenerate_blocked' in events
    assert events['regenerate_blocked']['details']['reason'] == 'worker_start_failed'
    assert 'KIE API Key' in events['regenerate_blocked']['details']['error_message']
    # A refused launch changes nothing: the pictures stay current, marked and not versioned.
    assert [item.status for item in restored.items] == [RunItemStatus.SUCCEEDED] * 2
    assert [item.output_path for item in restored.items] == before
    assert all(item.review_mark == 'bad_generation' and not item.versions for item in restored.items)
    assert not restored.running
    assert 'KIE API Key' in resumed.run_queue.page.summary_label.text()


def _ready_run(controller, count, confirmed=()):
    """A finished run whose first ``count`` pictures are on disk; the listed indexes carry «Ок»."""
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    for index, item in enumerate(session.items[:count]):
        output = session.output_dir / f'ready_{index}.png'
        image = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 80, 40, 255))
        image.save(output)
        item.status = RunItemStatus.SUCCEEDED
        item.output_path = str(output)
    for index in confirmed:
        session.items[index].review_mark, session.items[index].review_checked = 'ok', True
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()
    return session


def test_export_step_shows_ready_pictures_that_are_not_confirmed_yet(workspace):
    """Владелец 2026-10-30: «Готовых PNG пока нет» при готовых картинках — неправда, и счётчик «Не помечено «Ок»» молчал.

    Before: the counters were computed over confirmed set members only, so a finished run with nothing
    confirmed yet showed «0 изображений · 0 наборов», the «no ready PNG» hint and no reminder at all.
    """
    view, controller, _, worker = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    _ready_run(controller, 3, confirmed=())

    controller._refresh_export()
    wait_png_check(controller.export_panel)
    panel = controller.export_panel
    assert len(panel.review_paths) == 3 and not panel.paths  # nothing confirmed: sets stay empty by the owner's rule
    assert panel.summary_counts.text() == 'Готово картинок: 3 · в наборах: 0 · наборов: 0'
    assert not panel.empty_hint.isHidden()
    assert panel.empty_hint.text() == 'В наборы попадут только картинки, подтверждённые «Ок».'
    assert not panel.quality_panel.isHidden()
    assert panel.quality_summary_label.text() == 'Не помечено «Ок»: 3'
    assert not panel.export_button.isEnabled()  # nothing to export until «Ок» is placed


def test_replan_reuses_a_ready_picture_that_is_not_marked_ok_yet(workspace, monkeypatch):
    """Владелец 2026-10-30: готовая картинка без «Ок» не выбрасывается и не просит второй оплаты.

    Before: reuse looked at confirmed set members, so an unconfirmed ready picture was dropped — the app
    walked to the launch step and offered a new paid run for a file already on disk.
    """
    view, controller, _, factory = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    # the hero survives the reduction below, so it is the picture the replan has to keep
    ready_id = next(item['id'] for item in controller.brief.object_editor.items if item['role'] == 'hero')
    ready_item = next(item for item in session.items if item.payload['object_id'] == ready_id)
    output = session.output_dir / 'retained_ready.png'
    Image.new('RGBA', (64, 64), (0, 0, 0, 0)).save(output)
    for item in session.items:
        item.status = RunItemStatus.FAILED
    ready_item.status = RunItemStatus.SUCCEEDED
    ready_item.output_path = str(output)
    # the owner has not looked at it yet: no «Ок»
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()

    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    for _ in range(5):
        resumed.navigate(-1)
    editor = resumed.brief.object_editor
    while len(editor.items) > 1:
        editor.list.setCurrentRow(len(editor.items) - 1)
        editor.remove()
    assert editor.items[0]['id'] == ready_id
    for _ in range(4):
        resumed.navigate(1)
    view.shell.next_button.click()

    retained = resumed.run_queue.session
    assert retained is not None, 'приложение ушло на шаг запуска вместо переиспользования готовой картинки'
    assert retained.items[0].status is RunItemStatus.SUCCEEDED
    assert retained.items[0].output_path == str(output)
    assert resumed.shell.state.current_step is StepId.RESULTS
    factory.assert_not_called()


def test_replan_keeps_unconfirmed_pictures_beside_confirmed_ones(workspace, monkeypatch):
    """Смешанный случай: подтверждённая и неподтверждённая готовые картинки остаются целыми, без ложного провала."""
    view, controller, _, factory = workspace
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    keep_ids = [item['id'] for item in controller.brief.object_editor.items[:2]]
    kept = [item for item in session.items if item.payload['object_id'] in keep_ids]
    assert len(kept) == 2
    outputs = {}
    for item in session.items:
        item.status = RunItemStatus.FAILED
    for position, item in enumerate(kept):
        output = session.output_dir / f'kept_{position}.png'
        Image.new('RGBA', (64, 64), (0, 0, 0, 0)).save(output)
        item.status = RunItemStatus.SUCCEEDED
        item.output_path = str(output)
        outputs[item.payload['object_id']] = str(output)
    # the owner confirmed only the first picture before the replan
    kept[0].review_mark, kept[0].review_checked = 'ok', True
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()

    assert view.continue_saved_project(view._active_project_id)
    resumed = view.shell.workflow_controller('auto-clipart')
    resumed.save_timer.stop()
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
    for _ in range(5):
        resumed.navigate(-1)
    editor = resumed.brief.object_editor
    while len(editor.items) > 2:
        editor.list.setCurrentRow(len(editor.items) - 1)
        editor.remove()
    for _ in range(4):
        resumed.navigate(1)
    view.shell.next_button.click()

    retained = resumed.run_queue.session
    assert retained is not None and len(retained.items) == 2
    by_object = {item.payload['object_id']: item for item in retained.items}
    for object_id, path in outputs.items():
        item = by_object[object_id]
        assert item.status is RunItemStatus.SUCCEEDED, 'готовая картинка объявлена провалом'
        assert item.output_path == path
        assert 'недоступен' not in (item.short_message or '')
    assert by_object[kept[0].payload['object_id']].review_checked
    assert not by_object[kept[1].payload['object_id']].review_checked  # «Ок» was never placed; the mark travels as it was
    factory.assert_not_called()


def test_a_done_picture_whose_file_vanished_can_be_brought_back(workspace, monkeypatch):
    """Владелец 2026-10-30: файл картинки пропал — её нет ни в сетке, ни в «Вернуть готовые файлы».

    A recorded path is not a picture: the recovery used to treat «succeeded with a path» as done, so a
    file removed or moved away left the position unreachable from both screens.
    """
    view, controller, _, worker = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    gone = session.output_dir / 'flower_01_ready.png'   # the recorded picture, already removed from disk
    kept = session.output_dir / 'flower_02_ready_2.png'  # another ready picture of that position on disk
    for path, position in ((kept, 1),):
        Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(path)
    for index, item in enumerate(session.items):
        item.status = RunItemStatus.CANCELLED
    session.items[1].status = RunItemStatus.SUCCEEDED
    session.items[1].output_path = str(gone)            # the file is not there any more
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()

    controller._refresh_more_menu()
    assert controller.more_recover_action.isEnabled()
    assert controller.more_recover_action.text() == 'Вернуть готовые файлы (1)'
    assert controller._recoverable_outputs().keys() == {1}
    asked = []
    monkeypatch.setattr(QMessageBox, 'question', lambda *args, **kwargs: asked.append(args[2]) or QMessageBox.StandardButton.Yes)
    controller.recover_results()
    assert session.items[1].output_path == str(kept.resolve())
    assert session.items[1].status is RunItemStatus.SUCCEEDED
    assert not session.items[1].review_checked  # back as «Не проверено»


def test_the_recovery_menu_item_shows_only_when_there_is_something_to_return(workspace, monkeypatch):
    """Владелец 2026-10-30: «пункт виден всегда, как будто файлы есть», а когда файлы есть — «он не возвращает».

    Пункт «Ещё» → «Вернуть готовые файлы» выводится только при кандидатах; кандидаты пересчитываются при
    каждом открытии меню. Раньше файл, положенный в папку результата уже после обновления экрана, оставлял
    пункт за устаревшим «Подключать нечего»: клик по выключенному пункту не вызывал подключение вовсе.
    """
    view, controller, _, worker = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    session = _ready_run(controller, 3, confirmed=(0, 1, 2))
    controller._refresh_more_menu()
    assert not controller.more_recover_action.isVisible()       # вернуть нечего — пункта в меню нет

    # Владелец кладёт готовый PNG в папку результата при открытом приложении; экран не обновлялся.
    orphan = session.output_dir / 'flower_03_ready_2.png'
    Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(orphan)
    controller.more_button.menu().aboutToShow.emit()            # открытие «Ещё» пересчитывает кандидатов
    assert controller.more_recover_action.isVisible()
    assert controller.more_recover_action.isEnabled()           # клик больше не падает в устаревший запрет
    assert controller.more_recover_action.text() == 'Вернуть готовые файлы (1)'
    asked = []
    monkeypatch.setattr(QMessageBox, 'question',
                        lambda *args, **kwargs: asked.append(args[2]) or QMessageBox.StandardButton.Yes)
    controller.recover_results()
    assert 'найдено готовых PNG: 1' in asked[0]
    assert Path(session.items[2].output_path) == orphan.resolve()
    assert not session.items[2].review_checked                  # подключено как «Не проверено», а не «Ок»
    controller._refresh_more_menu()
    assert not controller.more_recover_action.isVisible()       # подключили — снова нечего возвращать


def test_a_position_already_showing_its_file_does_not_block_other_positions(workspace):
    """Нечего вернуть для позиции, которая уже показывает именно этот файл, — но не для остальных."""
    view, controller, _, worker = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    own = session.output_dir / 'flower_01_ready.png'
    orphan = session.output_dir / 'flower_02_ready.png'
    for path in (own, orphan):
        Image.new('RGBA', (64, 64), (120, 80, 40, 255)).save(path)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(own)                     # позиция 0 показывает ровно этот файл
    session.items[1].status = RunItemStatus.CANCELLED
    session.items[2].status = RunItemStatus.CANCELLED
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    controller.save_timer.stop()
    controller._refresh_more_menu()
    assert controller._recoverable_outputs().keys() == {1}      # позиция 0 не блокирует позицию 1
    assert controller.more_recover_action.isVisible()


def test_a_picture_marked_as_a_defect_leaves_the_sets_at_once(workspace):
    """Владелец 2026-10-30: на странице наборов видны картинки, помеченные браком.

    A confirmed «Ок» picture that is then marked as a defect stops being a set member (SET-0). The
    sets table used to keep its row until the owner left the step and came back.
    """
    view, controller, _, worker = workspace
    controller.brief.total.setValue(3)
    prepare_launch(controller)
    session = _ready_run(controller, 3, confirmed=(0, 1, 2))
    controller._refresh_export()
    wait_png_check(controller.export_panel)
    panel = controller.export_panel
    assert len(panel.paths) == 3

    defect = str(Path(session.items[1].output_path).resolve())
    controller.review.mark_output(defect, "bad_generation")
    controller.save_timer.stop()
    import time
    deadline = time.monotonic() + 5
    while defect in [str(path) for path in panel.paths] and time.monotonic() < deadline:
        QApplication.processEvents()
        time.sleep(0.01)
    panel = controller.export_panel or panel

    assert defect not in [str(path) for path in panel.paths], "картинка с браком осталась в наборах"
    assert len(panel.paths) == 2
    # В проверке PNG она остаётся — там владелец её и видит (правило 2026-10-28).
    assert defect in [str(path) for path in panel.review_paths]
