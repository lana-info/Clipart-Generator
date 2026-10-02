"""Deliberate edge contrast with a non-destructive Qt preview and exact RGB."""
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_contour import BezierNode, BezierPath
from v3_transparency_preview import ClipartTransparencyEditorPage, MaskEditDocument


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    y, x = np.indices((40, 64))
    alpha = np.tile(np.array([0, 16, 64, 96, 127, 128, 160, 191, 224, 255], dtype='uint8'), (40, 7))[:, :64]
    rgba = np.dstack((x.astype('uint8'), y.astype('uint8'), np.full_like(alpha, 139), alpha))
    path = tmp_path / 'sample.png'
    Image.fromarray(rgba).save(path)
    widget = ClipartTransparencyEditorPage()
    widget.resize(1120, 780)
    widget.set_files([path], save_dir=tmp_path / 'edited')
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def test_preview_compare_cancel_preserves_mask_rgb_history_and_source(page):
    document = page.document
    mask, rgb = document.mask.tobytes(), document.image.convert('RGB').tobytes()
    source = page.current_path.read_bytes()
    page.sharpen_edge_button.click()
    assert page.canvas.edge_preview_active
    assert page.edge_comparison.isVisible()
    assert page.canvas.edge_preview_mask.tobytes() != mask
    assert document.mask.tobytes() == mask and not document.is_dirty
    assert not document.can_undo and not document.can_redo
    after = page.canvas._item.pixmap().toImage()
    page.edge_before_button.click()
    before = page.canvas._item.pixmap().toImage()
    assert after != before
    assert page.canvas.edge_preview_mask is None and page.canvas.edge_preview_active
    page.edge_after_button.click()
    assert page.canvas._item.pixmap().toImage() == after
    assert document.image.convert('RGB').tobytes() == rgb
    with pytest.raises(ValueError, match='предпросмотр'):
        page.save_current()
    page.cancel_edge_button.click()
    assert document.mask.tobytes() == mask and not document.can_undo
    assert not page.canvas.edge_preview_active and not page.edge_comparison.isVisible()
    assert page.canvas._item.pixmap().toImage() == before
    assert page.current_path.read_bytes() == source


def test_apply_while_viewing_before_commits_after_one_undo_copy_save_and_reset(page):
    doc = page.document
    old = doc.mask.tobytes()
    original = page.current_path.read_bytes()
    rgb = doc.image.convert('RGB').tobytes()
    page.sharpen_edge_button.click()
    proposal = page.canvas.edge_preview_mask.tobytes()
    page.edge_before_button.click()
    page.apply_edge_button.click()
    assert doc.mask.tobytes() == proposal
    assert len(doc._undo) == 1 and doc.is_dirty
    page.undo()
    assert doc.mask.tobytes() == old
    page.redo()
    assert doc.mask.tobytes() == proposal
    output, mask = page.save_current()
    assert output != page.current_path and page.current_path.read_bytes() == original
    with Image.open(output) as saved:
        assert saved.convert('RGB').tobytes() == rgb
        assert saved.getchannel('A').tobytes() == proposal
    with Image.open(mask) as saved:
        assert saved.tobytes() == proposal
    page.reset()
    assert doc.mask.tobytes() == old
    assert doc.image.convert('RGB').tobytes() == rgb


def test_preview_blocks_canvas_edits_contour_jobs_save_reset_and_redo_but_allows_zoom(page):
    doc = page.document
    old = doc.mask.tobytes()
    page.sharpen_edge_button.click()
    for button in (page.save_button, page.reset_button, page.undo_button, page.redo_button, *page.tool_buttons.values()):
        assert not button.isEnabled()
    QTest.mouseClick(page.canvas.viewport(), Qt.MouseButton.LeftButton,
                    pos=page.canvas.mapFromScene(QPointF(32, 20)))
    QTest.keyClick(page.canvas, Qt.Key.Key_Delete)
    QTest.keyClick(page.canvas, Qt.Key.Key_Return)
    QTest.keyClick(page.canvas, Qt.Key.Key_P)
    page.canvas.auto_contour()
    page.redo()
    page.reset()
    page._save_clicked()
    assert doc.mask.tobytes() == old and not doc.can_undo
    assert not page.canvas.contour_busy and page._edge_preview is not None
    zoom = page.canvas.transform().m11()
    QTest.keyClick(page.canvas, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    assert page.canvas.transform().m11() > zoom
    QTest.keyClick(page.canvas, Qt.Key.Key_Escape)
    assert page._edge_preview is None and doc.mask.tobytes() == old


@pytest.mark.parametrize('method', ['undo', 'hide', 'switch', 'reload', 'back'])
def test_leaving_or_undo_discards_only_preview(page, method, tmp_path):
    old_doc = page.document
    old = old_doc.mask.tobytes()
    page.sharpen_edge_button.click()
    if method == 'switch':
        second = tmp_path / 'second.png'
        Image.new('RGBA', (10, 10), (10, 20, 30, 255)).save(second)
        page._paths.append(second)
        page.file_list.addItem(second.name)
        page.file_list.setCurrentRow(1)
    elif method == 'reload':
        page.set_files([page.current_path])
    elif method == 'back':
        page._back_clicked()
    else:
        getattr(page, method)()
    assert old_doc.mask.tobytes() == old and not old_doc.can_undo
    assert page._edge_preview is None and not page.canvas.edge_preview_active


def test_stale_proposal_is_not_committed(page):
    doc = page.document
    page.sharpen_edge_button.click()
    doc.begin_stroke()
    doc.extend_stroke(((30, 20),), radius=2, action='remove', hardness=100)
    doc.end_stroke()
    current = doc.mask.tobytes()
    count = len(doc._undo)
    page.apply_edge_button.click()
    assert page._edge_preview is None
    assert doc.mask.tobytes() == current and len(doc._undo) == count


def test_limit_empty_and_pending_geometry_disable_the_action(page):
    page.document.mask = Image.new('L', page.document.mask.size, 255)
    page._refresh_history_buttons()
    assert not page.sharpen_edge_button.isEnabled()
    # Reaching a fixed point also stops repeated steps without accumulating history.
    page.document.mask = Image.new('L', page.document.mask.size, 128)
    page._refresh_history_buttons()
    assert not page.sharpen_edge_button.isEnabled()
    page.preview_sharper_edge()
    assert page._edge_preview is None and not page.document.can_undo
    page.document.mask.putpixel((3, 3), 96)
    page.document.mask_revision += 1
    path = BezierPath(tuple(BezierNode(p) for p in [(10,10),(25,10),(25,25),(10,25)]),255,(64,40))
    page.canvas.contour.paths = [path]
    page.canvas.contour.original = []
    page._refresh_history_buttons()
    assert not page.sharpen_edge_button.isEnabled()
    page.preview_sharper_edge()
    assert page._edge_preview is None
    page.set_files([])
    assert not page.sharpen_edge_button.isEnabled()


def test_apply_budget_failure_keeps_mask_history_and_cancels_preview(page):
    old = page.document.mask.tobytes()
    page.sharpen_edge_button.click()
    with patch.object(MaskEditDocument, 'HISTORY_MEMORY_LIMIT', 8):
        page.apply_edge_button.click()
    assert page._edge_preview is None
    assert page.document.mask.tobytes() == old and not page.document.can_undo
    assert 'Маска не изменена' in page.contour_status.text()


def test_repeat_after_apply_is_a_separate_step_and_after_undo_reenables(page):
    old = page.document.mask.tobytes()
    page.sharpen_edge_button.click()
    page.apply_edge_button.click()
    once = page.document.mask.tobytes()
    page.sharpen_edge_button.click()
    assert page.document.mask.tobytes() == once
    page.apply_edge_button.click()
    twice = page.document.mask.tobytes()
    assert twice != once and len(page.document._undo) == 2
    page.undo()
    assert page.document.mask.tobytes() == once
    page.undo()
    assert page.document.mask.tobytes() == old and page.sharpen_edge_button.isEnabled()


def test_cancel_preserves_prior_edits_and_redo_history(page):
    doc = page.document
    initial = doc.mask.tobytes()
    doc.begin_stroke()
    doc.extend_stroke(((30, 20),), radius=2, action='remove', hardness=100)
    doc.end_stroke()
    edited = doc.mask.tobytes()
    page._refresh_history_buttons()
    page.sharpen_edge_button.click()
    page.cancel_edge_button.click()
    assert doc.mask.tobytes() == edited and len(doc._undo) == 1
    page.undo()
    assert doc.mask.tobytes() == initial and doc.can_redo
    page.sharpen_edge_button.click()
    page.cancel_edge_button.click()
    assert doc.can_redo
    page.redo()
    assert doc.mask.tobytes() == edited


def test_proposal_history_trim_retains_new_step_and_rejection_preserves_existing_history():
    doc = MaskEditDocument(Image.new('RGBA', (4, 4), (10, 20, 30, 160)))
    doc.HISTORY_MEMORY_LIMIT = 64
    for alpha in (120, 100, 90):
        doc.apply_mask_proposal(Image.new('L', (4, 4), alpha))
    assert doc.history_bytes <= doc.HISTORY_MEMORY_LIMIT
    doc.undo()
    assert doc.mask.getpixel((0, 0)) == 100 and doc.can_redo
    before = (doc.mask.tobytes(), doc.mask_revision, list(doc._undo), list(doc._redo))
    doc.HISTORY_MEMORY_LIMIT = 30
    with pytest.raises(ValueError, match='Маска не изменена'):
        doc.apply_mask_proposal(Image.new('L', (4, 4), 80))
    assert before == (doc.mask.tobytes(), doc.mask_revision, doc._undo, doc._redo)
