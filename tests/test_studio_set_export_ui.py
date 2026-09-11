from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile
import json

import pytest
from PIL import Image
from PyQt6.QtCore import QEventLoop, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QFileDialog

from studio_set_export import export_clipart_sets, ExportCancelled
from studio_set_export_ui import SetExportDialog
from v3_project_state import ProjectState, ProjectMode, save_project_draft, load_project_draft
from v3_run_queue import RunResultsPage, RunItem, RunItemStatus


@pytest.fixture
def images(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = []
    for n in range(3):
        path = tmp_path / f'item-{n}.png'
        Image.new('RGBA', (32, 32), (60, 80, 90, 128)).save(path)
        paths.append(path)
    yield paths
    app.processEvents()


def test_membership_and_review_invalidation(images):
    dialog = SetExportDialog(images)
    dialog.table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)
    dialog.table.item(1, 1).setText('Второй набор')
    assert [len(group['images']) for group in dialog.groups()] == [1, 1]
    dialog.reviewed.setChecked(True)
    dialog.table.item(1, 1).setText('Изменённый набор')
    assert not dialog.reviewed.isChecked()
    dialog.table.item(1, 1).setText('')
    with pytest.raises(ValueError):
        dialog.groups()
    dialog.reject()


def test_review_required_before_folder_selection(images, monkeypatch):
    dialog = SetExportDialog(images)
    calls = []
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: calls.append(args))
    dialog._export()
    assert not calls
    assert dialog.worker is None
    dialog.reject()


def test_real_background_export_two_archives(images, tmp_path, monkeypatch):
    dialog = SetExportDialog(images)
    dialog.table.item(2, 1).setText('Второй набор')
    dialog.reviewed.setChecked(True)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(tmp_path))
    dialog._export()
    worker = dialog.worker
    loop = QEventLoop()
    worker.finished.connect(loop.quit)
    QTimer.singleShot(5000, loop.quit)
    loop.exec()
    assert dialog.worker is None
    assert len(dialog.exported) == 2
    counts = []
    for archive in dialog.exported:
        with ZipFile(archive) as z:
            counts.append(json.loads(z.read('manifest.json'))['count'])
            assert z.read('overview.pdf').startswith(b'%PDF')
    assert counts == [2, 1]
    assert dialog.export_button.isEnabled()
    dialog.reject()


def test_cancel_before_publish_removes_staging(images, tmp_path):
    before = set(tmp_path.iterdir())
    calls = []
    def cancelled():
        calls.append(1)
        return len(calls) >= 4
    with pytest.raises(ExportCancelled):
        export_clipart_sets([dict(title='Test', images=images)], tmp_path, cancelled=cancelled)
    assert set(tmp_path.iterdir()) == before


def test_results_only_export_current_successes(images, tmp_path):
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.session = SimpleNamespace(running=False, output_dir=tmp_path, items=[
        RunItem(1, 'success', status=RunItemStatus.SUCCEEDED, output_path=str(images[0])),
        RunItem(2, 'failed', status=RunItemStatus.FAILED, output_path=str(images[1])),
        RunItem(3, 'duplicate', status=RunItemStatus.SUCCEEDED, output_path=str(images[0])),
    ])
    assert page._export_paths() == [images[0]]
    # Unrecorded PNGs in the directory never become set members automatically.
    page.session.running = True
    assert page._export_paths() == []
    page.close()


def test_export_hidden_outside_clipart(images):
    page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING))
    assert page.export_sets_button.isHidden()
    page.close()


def test_membership_save_reopen_and_preserve_other_runs(images, tmp_path):
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.export_membership = {'/older/result.png': {'title': 'Старый набор', 'included': True}}
    page = RunResultsPage(state)
    dialog = SetExportDialog(images, membership=state.clipart.export_membership)
    dialog.membership_saved.connect(page._save_export_membership)
    changed = []
    page.membership_changed.connect(lambda: changed.append(True))
    dialog.table.item(1, 1).setText('Набор два')
    dialog.table.item(2, 0).setCheckState(Qt.CheckState.Unchecked)
    dialog._save_membership()
    assert changed == [True]
    assert '/older/result.png' in state.clipart.export_membership
    path = tmp_path / 'project.json'
    save_project_draft(state, path)
    restored = load_project_draft(path)
    reopened = SetExportDialog(images, membership=restored.clipart.export_membership)
    assert reopened.table.item(1, 1).text() == 'Набор два'
    assert reopened.table.item(2, 0).checkState() == Qt.CheckState.Unchecked
    assert not reopened.reviewed.isChecked()
    for widget in (dialog, reopened, page):
        widget.close()


def test_invalid_membership_cannot_overwrite_draft(images, tmp_path):
    state = ProjectState()
    path = tmp_path / 'project.json'
    save_project_draft(state, path)
    before = path.read_bytes()
    state.clipart.export_membership = {'image.png': {'title': 'test', 'included': 'yes'}}
    with pytest.raises(ValueError):
        save_project_draft(state, path)
    assert path.read_bytes() == before


def test_many_memberships_edit_save_reopen_preserves_other_links(images, tmp_path):
    from studio_export_membership import validate_export_membership
    key = str(images[0])
    membership = validate_export_membership({key: {'title': 'Mini', 'included': True},
        '/older/missing.png': {'title': 'Old', 'included': False}})
    for title in ('Standard', 'Maxi', 'Bundle'):
        membership[key]['memberships'].extend(validate_export_membership(
            {key: {'title': title, 'included': True}})[key]['memberships'])
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.export_membership = membership
    page = RunResultsPage(state)
    dialog = SetExportDialog([images[0]], membership=membership)
    dialog.membership_saved.connect(page._save_export_membership)
    assert dialog.table.rowCount() == 4
    assert len(dialog.groups()) == 4
    dialog.reviewed.setChecked(True)
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Unchecked)
    assert not dialog.reviewed.isChecked()
    dialog._save_membership()
    path = tmp_path / 'many.json'
    save_project_draft(state, path)
    restored = load_project_draft(path)
    reopened = SetExportDialog([images[0]], membership=restored.clipart.export_membership)
    assert [link['included'] for link in restored.clipart.export_membership[key]['memberships']] == [True, False, True, True]
    assert restored.clipart.export_membership['/older/missing.png'] == membership['/older/missing.png']
    assert [group['title'] for group in reopened.groups()] == ['Mini', 'Maxi', 'Bundle']
    assert not reopened.reviewed.isChecked()
    # The source assignment and all non-edited IDs remain unchanged.
    assert state.clipart.export_membership[key]['asset_id'] == membership[key]['asset_id']
    assert [link['set_id'] for link in state.clipart.export_membership[key]['memberships']] == [
        link['set_id'] for link in membership[key]['memberships']]
    for widget in (dialog, reopened, page):
        widget.close()
