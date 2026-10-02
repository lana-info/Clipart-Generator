"""Approved export table through the real saved-project and ZIP routes."""
from zipfile import ZipFile

from PIL import Image, ImageDraw
from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QFileDialog

from tests.test_auto_clipart_workflow import app, workspace, prepare_launch
from v3_clipart_flow import build_clipart_run_request
from v3_project_state import StepId
from v3_run_queue import RunItemStatus, RunQueueSession


def _legacy_partial(controller):
    controller.brief.total.setValue(20)
    prepare_launch(controller)
    session = RunQueueSession(build_clipart_run_request(controller.shell.state), controller.shell.state.mode)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    path = session.output_dir / 'duck_birthday_01.png'
    image = Image.new('RGBA', (96, 96), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((12, 12, 83, 83), fill=(240, 200, 140, 255))
    image.save(path)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(path)
    for item in session.items[1:]:
        item.status = RunItemStatus.FAILED
    session.handle_finished()
    controller.run_queue.session = session
    controller.run_queue.page.set_session(session)
    controller._save_run()
    # Old projects have no settings fingerprint. Partial delivery must still work.
    controller.shell.state.data.automatic.pop('run_settings_fingerprint')
    controller._select_step(StepId.RESULTS)
    controller.shell.go_next()
    return session, path


def test_legacy_failed_jobs_export_ready_png_without_erasing_saved_work(workspace, monkeypatch, tmp_path):
    view, controller, _, factory = workspace
    session, path = _legacy_partial(controller)
    panel = controller.export_panel
    assert panel is not None and panel.table.rowCount() == 1
    assert len(panel.review_issues) == 19
    assert not view.shell.next_button.isEnabled()
    assert not panel.export_button.isVisible()  # One export action in the footer.
    panel.table.item(0, 1).setCheckState(Qt.CheckState.Unchecked)
    panel.ready_only.setChecked(True)
    assert view.shell.next_button.isEnabled()
    before = path.read_bytes()
    selected_groups = panel.groups()
    view.shell.save_project_button.click()
    assert not view.shell.save_error_label.text()
    assert view.shell.project_save_label.text() == 'Проект сохранён'
    assert len(controller.shell.state.data.automatic['run']) == 20
    destination = tmp_path / 'zip-delivery'
    destination.mkdir()
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(destination))
    view.shell.next_button.click()
    worker = panel.worker
    assert worker is not None
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert len(panel.exported) == len(selected_groups)
    for archive in panel.exported:
        with ZipFile(archive) as stream:
            assert stream.testzip() is None
            pngs = [name for name in stream.namelist() if name.endswith('.png')]
            assert len(pngs) == 1 and stream.read(pngs[0]) == before
    assert path.read_bytes() == before
    assert sum(item.status is RunItemStatus.FAILED for item in session.items) == 19
    assert view.continue_saved_project(view._active_project_id)
    reopened = view.shell.workflow_controller('auto-clipart')
    reopened.save_timer.stop()
    assert len(reopened.run_queue.session.items) == 20
    assert sum(item.status is RunItemStatus.FAILED for item in reopened.run_queue.session.items) == 19
    assert reopened.export_panel.table.item(0, 1).checkState() == Qt.CheckState.Unchecked
    assert not reopened.export_panel.ready_only.isChecked()
    assert not view.shell.next_button.isEnabled()
    factory.assert_not_called()


def test_empty_export_can_save_and_reports_project_save_failure(workspace, monkeypatch):
    view, controller, _, factory = workspace
    controller._select_step(StepId.TRANSPARENCY)
    panel = controller.export_panel
    assert panel is not None and panel.table.rowCount() == 0
    assert panel.summary_counts.text() == '0 изображений · 0 наборов'
    assert not view.shell.next_button.isEnabled()
    assert view.shell.save_project_button.isEnabled()
    view.shell.save_project_button.click()
    assert not view.shell.save_error_label.text()
    assert view._active_project_id

    def fail_save(*_args, **_kwargs):
        raise OSError('test persistence unavailable')

    monkeypatch.setattr(view._project_documents, 'save', fail_save)
    view.shell.save_project_button.click()
    assert 'Не удалось сохранить' in view.shell.save_error_label.text()
    assert view.shell.project_save_label.text() == ''
    factory.assert_not_called()
