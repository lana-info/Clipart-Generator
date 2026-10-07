"""Immediate alpha contrast: independent undo steps, unchanged RGB and explicit save."""
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton

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


def click(page, button):
    page.tools_scroll.ensureWidgetVisible(button)
    QApplication.processEvents()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    QApplication.processEvents()


def test_single_click_commits_exact_alpha_without_extra_confirmation(page):
    doc = page.document
    before = np.array(doc.mask)
    rgb = doc.image.convert('RGB').tobytes()
    original = page.current_path.read_bytes()
    view = page.canvas._item.pixmap().toImage()
    click(page, page.sharpen_edge_button)
    expected = {0:0, 16:0, 64:0, 96:64, 127:126, 128:128,
                160:192, 191:254, 224:255, 255:255}
    np.testing.assert_array_equal(np.array(doc.mask), np.vectorize(expected.__getitem__)(before))
    assert doc.is_dirty and len(doc._undo) == 1 and not doc.can_redo
    assert page.canvas._item.pixmap().toImage() != view
    assert doc.image.convert('RGB').tobytes() == rgb
    assert page.current_path.read_bytes() == original
    assert not hasattr(page, 'edge_comparison')
    assert not {'До', 'После', 'Применить'} & {b.text() for b in page.findChildren(QPushButton) if b.isVisible()}
    assert page.save_button.isEnabled() and page.undo_button.isEnabled()
    assert all(button.isEnabled() for button in page.tool_buttons.values())


def test_repeat_clicks_each_undo_redo_and_explicit_save_reset(page):
    doc = page.document
    old = doc.mask.tobytes()
    original = page.current_path.read_bytes()
    rgb = doc.image.convert('RGB').tobytes()
    click(page, page.sharpen_edge_button)
    once = doc.mask.tobytes()
    click(page, page.sharpen_edge_button)
    twice = doc.mask.tobytes()
    assert old != once != twice and len(doc._undo) == 2
    click(page, page.undo_button)
    assert doc.mask.tobytes() == once
    click(page, page.undo_button)
    assert doc.mask.tobytes() == old and not doc.is_dirty
    click(page, page.redo_button)
    assert doc.mask.tobytes() == once
    click(page, page.redo_button)
    assert doc.mask.tobytes() == twice
    output, mask = page.save_current()
    assert output != page.current_path and page.current_path.read_bytes() == original
    with Image.open(output) as saved:
        assert saved.convert('RGB').tobytes() == rgb
        assert saved.getchannel('A').tobytes() == twice
    with Image.open(mask) as saved:
        assert saved.tobytes() == twice
    page.reset()
    assert doc.mask.tobytes() == old


def test_terminal_mask_disables_button_and_undo_reenables_without_empty_history(page):
    doc = page.document
    start = np.array(doc.mask)
    steps = 0
    while page.sharpen_edge_button.isEnabled():
        assert steps < 10
        before = doc.mask.tobytes()
        click(page, page.sharpen_edge_button)
        assert doc.mask.tobytes() != before
        steps += 1
    expected = np.where(start < 128, 0, np.where(start > 128, 255, 128))
    np.testing.assert_array_equal(np.array(doc.mask), expected)
    assert len(doc._undo) == steps
    page.sharpen_edge()
    assert len(doc._undo) == steps
    click(page, page.undo_button)
    assert page.sharpen_edge_button.isEnabled()
    click(page, page.redo_button)
    assert not page.sharpen_edge_button.isEnabled()


@pytest.mark.parametrize('terminal', [0, 128, 255])
def test_unchangeable_and_empty_masks_do_not_add_history(page, terminal):
    page.document.mask = Image.new('L', page.document.mask.size, terminal)
    page._refresh_history_buttons()
    assert not page.sharpen_edge_button.isEnabled()
    page.sharpen_edge()
    assert not page.document.can_undo
    page.set_files([])
    page.sharpen_edge()
    assert not page.sharpen_edge_button.isEnabled()


def test_budget_failure_preserves_mask_revision_and_both_history_stacks(page):
    doc = page.document
    click(page, page.sharpen_edge_button)
    page.undo()
    before = (doc.mask.tobytes(), doc.mask_revision, list(doc._undo), list(doc._redo))
    with patch.object(MaskEditDocument, 'HISTORY_MEMORY_LIMIT', 8):
        click(page, page.sharpen_edge_button)
    assert before == (doc.mask.tobytes(), doc.mask_revision, doc._undo, doc._redo)
    assert 'Маска не изменена' in page.contour_status.text()


def test_brush_and_sharpen_steps_keep_their_own_order_and_new_branch_clears_redo(page):
    doc = page.document
    initial = doc.mask.tobytes()
    doc.begin_stroke()
    doc.extend_stroke(((30,20),), radius=2, action='remove', hardness=100)
    doc.end_stroke()
    brushed = doc.mask.tobytes()
    page._refresh_history_buttons()
    click(page, page.sharpen_edge_button)
    sharpened = doc.mask.tobytes()
    page.undo()
    assert doc.mask.tobytes() == brushed
    page.undo()
    assert doc.mask.tobytes() == initial
    page.redo()
    assert doc.mask.tobytes() == brushed
    click(page, page.sharpen_edge_button)
    assert doc.mask.tobytes() == sharpened and not doc.can_redo
    # A fresh brush stroke after sharpening remains a separate undo step.
    doc.begin_stroke()
    doc.extend_stroke(((40,25),), radius=0, action='add', hardness=100)
    doc.end_stroke()
    page.undo()
    assert doc.mask.tobytes() == sharpened


@pytest.mark.parametrize('method', ['hide', 'switch', 'reload'])
def test_leaving_preserves_committed_step_as_draft_without_writing_source(page, method, tmp_path):
    source = page.current_path
    original = source.read_bytes()
    doc = page.document
    click(page, page.sharpen_edge_button)
    changed = doc.mask.tobytes()
    if method == 'hide':
        page.hide()
        page.show()
    elif method == 'reload':
        page.set_files([source], save_dir=tmp_path/'edited')
    else:
        second = tmp_path/'second.png'
        Image.new('RGBA',(10,10),(10,20,30,255)).save(second)
        page._paths.append(second)
        page.file_list.addItem(second.name)
        page.file_list.setCurrentRow(1)
        assert page.document.mask.getextrema() == (255,255)
        page.file_list.setCurrentRow(0)
    assert page.document.mask.tobytes() == changed and page.document.is_dirty
    if method == 'hide':
        assert page.document is doc and page.document.can_undo
    else:
        # Existing per-file policy restores the draft mask, not raster undo stacks.
        assert not page.document.can_undo
    assert source.read_bytes() == original


def test_back_requires_explicit_discard_of_immediate_changes(page):
    doc = page.document
    click(page, page.sharpen_edge_button)
    changed = doc.mask.tobytes()
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Cancel) as warning:
        page._back_clicked()
        warning.assert_called_once()
    assert page.document.mask.tobytes() == changed
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
        page._back_clicked()
    assert page._document is None and not page._draft_masks


@pytest.mark.parametrize('guard', ['points', 'dirty', 'painting', 'busy'])
def test_incomplete_or_active_edits_block_sharpening(page, guard):
    old = page.document.mask.tobytes()
    if guard == 'points':
        page.canvas.contour.add_point((10,10))
    elif guard == 'dirty':
        path = BezierPath(tuple(BezierNode(p) for p in [(10,10),(25,10),(25,25),(10,25)]),255,(64,40))
        page.canvas.contour.paths = [path]
        page.canvas.contour.original = []
    elif guard == 'painting':
        page.canvas._painting = True
    else:
        page.canvas._contour_job = {'kind':'extract'}
    try:
        page._refresh_history_buttons()
        if guard != 'painting':
            assert not page.sharpen_edge_button.isEnabled()
        page.sharpen_edge()
        assert page.document.mask.tobytes() == old and not page.document.can_undo
    finally:
        page.canvas._painting = False
        page.canvas._contour_job = None


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
