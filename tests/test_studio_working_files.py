import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from main import WorkerThread
from studio_set_export_ui import ExportWorker, SetExportDialog
from studio_working_files import cleanup_working_files, digest, link_edited_output


@pytest.fixture
def owned(tmp_path):
    app = QApplication.instance() or QApplication([])
    output = tmp_path / 'output'
    output.mkdir()
    worker = WorkerThread('mode_both', str(tmp_path), {
        'workspace_root': str(tmp_path), 'output_dir': str(output),
        'trim_enabled': False, 'export_300_dpi': False,
    })
    raw = Path(worker._create_run_raw_dir())
    finals = []
    for idx in (1, 2):
        source = raw / f'gen_{idx:03d}_{worker.run_stamp}.png'
        processed = raw / f'gen_chroma_key_nobg_{idx:03d}_{worker.run_stamp}.png'
        Image.new('RGBA', (32, 32), (100, 80, idx, 255)).save(source)
        Image.new('RGBA', (32, 32), (100, 80, idx, 128)).save(processed)
        final = output / f'final-{idx}.png'
        worker._save_final_output(str(processed), str(source), str(final), str(raw), idx, 'gen')
        finals.append(final)
    # A failed item has intermediates but no successfully published final.
    Image.new('RGBA', (32, 32), 'red').save(raw / f'gen_003_{worker.run_stamp}.png')
    worker._persist_rough_outputs(str(raw))
    receipt = next((tmp_path / 'rough').glob('.cleanup-*.json'))
    records = json.loads(receipt.read_text())
    yield tmp_path, finals, records
    app.processEvents()


@pytest.mark.parametrize('intermediates,originals,count', [
    (False, False, 0), (True, False, 1), (False, True, 1), (True, True, 2),
])
def test_independent_options_only_delete_exported_image(owned, intermediates, originals, count):
    root, finals, records = owned
    worker = ExportWorker([{'title': 'Set', 'images': [finals[0]]}], root,
                          workspace=root, delete_intermediates=intermediates,
                          delete_originals=originals)
    worker.run()
    assert not worker.error
    assert len(worker.paths) == 1
    assert len(list((root / 'rough').glob('*.png'))) == 5 - count
    assert all(path.exists() for path in finals)
    for record in records:
        selected = record['outputs'][0]['path'] == str(finals[0])
        for file in record['files']:
            delete = selected and (originals if file['category'] == 'generated' else intermediates)
            assert (root / 'rough' / file['name']).exists() is not delete
    assert (root / 'rough' / 'rough_03_generated.png').exists()


def test_cancel_and_export_error_never_clean(owned):
    root, finals, _ = owned
    before = {path: path.read_bytes() for path in (root / 'rough').glob('*.png')}
    for cancel in (True, False):
        worker = ExportWorker([{'title': 'Set', 'images': [finals[0] if cancel else root / 'missing.png']}],
                              root, workspace=root, delete_intermediates=True, delete_originals=True)
        if cancel:
            worker.cancelled.set()
        worker.run()
        assert worker.error and not worker.paths
        assert before == {path: path.read_bytes() for path in before}


def test_invalid_archive_never_cleans(owned):
    root, finals, _ = owned
    worker = ExportWorker([{'title': 'Set', 'images': [finals[0]]}], root,
                          workspace=root, delete_intermediates=True, delete_originals=True)
    with patch('studio_set_export.ZipFile.testzip', return_value='broken.png'):
        worker.run()
    assert worker.error and not worker.paths
    assert len(list((root / 'rough').glob('*.png'))) == 5
    assert not list(root.glob('clipart-sets-*'))


def test_modified_untracked_symlink_and_other_run_files_are_preserved(owned):
    root, finals, records = owned
    first = next(r for r in records if r['outputs'][0]['path'] == str(finals[0]))
    modified = root / 'rough' / first['files'][0]['name']
    modified.write_bytes(b'user edit')
    linked = root / 'rough' / first['files'][1]['name']
    linked.unlink()
    linked.symlink_to(finals[0])
    old = root / 'rough' / 'rough_99_generated.png'
    old.write_bytes(b'old untracked file')
    assert cleanup_working_files(root, {str(finals[0]): digest(finals[0])},
                                 intermediates=True, originals=True) == (0, 2)
    assert modified.read_bytes() == b'user edit'
    assert linked.is_symlink() and old.exists() and finals[0].exists()


def test_changed_final_requires_explicit_edit_lineage(owned):
    root, finals, _ = owned
    Image.new('RGBA', (32, 32), 'blue').save(finals[0])
    exported = {str(finals[0]): digest(finals[0])}
    assert cleanup_working_files(root, exported, originals=True) == (0, 0)
    link_edited_output(root, [str(finals[0])], finals[0])
    assert cleanup_working_files(root, exported, originals=True) == (1, 0)


def test_receipt_cannot_delete_outside_rough_or_through_symlink(owned):
    root, finals, _ = owned
    receipt = next((root / 'rough').glob('.cleanup-*.json'))
    records = json.loads(receipt.read_text())
    records[0]['files'] = [{'name': '../output/final-1.png',
                            'category': 'generated', 'sha256': digest(finals[0])}]
    records[1]['files'] = []
    receipt.write_text(json.dumps(records))
    exported = {str(path): digest(path) for path in finals}
    assert cleanup_working_files(root, exported, originals=True) == (0, 1)
    assert all(path.exists() for path in finals)
    receipt.unlink()
    external = root / 'external.json'
    external.write_text(json.dumps(records))
    receipt.symlink_to(external)
    assert cleanup_working_files(root, exported, originals=True) == (0, 0)


def test_cleanup_failure_does_not_disguise_successful_export(owned):
    root, finals, _ = owned
    worker = ExportWorker([{'title': 'Set', 'images': [finals[0]]}], root,
                          workspace=root, delete_originals=True)
    with patch('studio_working_files.cleanup_working_files', side_effect=OSError('disk')):
        worker.run()
    assert worker.paths and not worker.error
    assert 'очистку' in worker.cleanup_message


def test_edited_copy_can_clean_its_original_working_files(owned):
    root, finals, _ = owned
    edited = root / 'edited.png'
    Image.new('RGBA', (32, 32), 'blue').save(edited)
    link_edited_output(root, [str(finals[0])], edited)
    assert cleanup_working_files(root, {str(edited): digest(edited)},
                                 intermediates=True, originals=True) == (2, 0)
    assert edited.exists() and finals[0].exists()


def test_adopted_final_inside_rough_is_never_deleted(owned):
    root, finals, records = owned
    record = next(r for r in records if r['outputs'][0]['path'] == str(finals[0]))
    adopted = root / 'rough' / record['files'][0]['name']
    link_edited_output(root, [str(finals[0])], adopted)
    link_edited_output(root, [str(adopted)], finals[0])
    deleted, skipped = cleanup_working_files(root, {str(finals[0]): digest(finals[0])},
                                             intermediates=True, originals=True)
    assert (deleted, skipped) == (1, 1)
    assert adopted.exists()


def test_options_are_unchecked_and_reset_after_export(owned, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    root, finals, _ = owned
    dialog = SetExportDialog(finals, workspace=root)
    assert not dialog.delete_intermediates.isChecked()
    assert not dialog.delete_originals.isChecked()
    dialog.delete_originals.setChecked(True)
    monkeypatch.setattr(QFileDialog, 'getExistingDirectory', lambda *args: str(root))
    monkeypatch.setattr(ExportWorker, 'start', lambda self: None)
    dialog._export()
    assert not dialog.delete_originals.isEnabled()
    assert dialog.worker.delete_originals and not dialog.worker.delete_intermediates
    dialog.worker.run()
    dialog._finished()
    assert not dialog.delete_originals.isChecked()
    assert dialog.delete_originals.isEnabled()
    assert 'удалено: 2' in dialog.status.text()
    dialog.close()
