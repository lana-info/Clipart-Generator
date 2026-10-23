"""Accepted manual RGB retouch: actual Qt selection, preview and storage lifecycle."""
from concurrent.futures import Future
from threading import Event
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from v3_transparency_preview import ClipartTransparencyEditorPage, MaskEditDocument


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    rgba = np.zeros((96, 128, 4), dtype=np.uint8)
    rgba[12:84, 24:104] = (180, 140, 80, 255)
    rgba[16:80, 24:27, :3] = (95, 130, 105)
    rgba[16:80, 23] = (95, 130, 105, 100)
    a, b = tmp_path / 'a.png', tmp_path / 'b.png'
    Image.fromarray(rgba).save(a, dpi=(300, 300))
    Image.new('RGBA', (128, 96), (130, 80, 50, 255)).save(b)
    widget = ClipartTransparencyEditorPage()
    widget.resize(1120, 780)
    widget.set_files([a, b], save_dir=tmp_path / 'copies')
    widget.show()
    app.processEvents()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def wait_result(page):
    for _ in range(200):
        QApplication.processEvents()
        if page._colour_job is None:
            return
        QTest.qWait(5)
    pytest.fail('Local colour job did not finish')


def select(page, bounds=(20, 16, 32, 80)):
    page.colour_edge_button.click()
    assert page._colour_active
    page.canvas.colour_selection_bounds = bounds
    page._start_colour_region(bounds)
    wait_result(page)
    assert page._colour_preview is not None
    return page._colour_preview[3]


def test_real_mouse_rectangle_and_preview_preserve_alpha_source_and_dirty(page):
    doc = page.document
    original = doc.corrected_image().tobytes()
    source = page.current_path.read_bytes()
    page.colour_edge_button.click()
    canvas = page.canvas
    start = canvas.mapFromScene(QPointF(20, 16))
    end = canvas.mapFromScene(QPointF(32, 80))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    wait_result(page)
    assert page._colour_preview is not None
    bounds = canvas.colour_selection_bounds
    assert all(abs(a - b) <= 1 for a, b in zip(bounds, (20, 16, 32, 80)))
    assert doc.corrected_image().tobytes() == original and not doc.is_dirty and not doc.can_undo
    after = canvas._item.pixmap().toImage()
    page.edge_before_button.click()
    before = canvas._item.pixmap().toImage()
    assert before != after
    page.edge_after_button.click()
    assert canvas._item.pixmap().toImage() == after
    page.cancel_edge_button.click()
    assert canvas._item.pixmap().toImage() == before
    assert doc.corrected_image().tobytes() == original and page.current_path.read_bytes() == source


def test_apply_from_before_one_undo_redo_save_copy_dpi_and_outside_exact(page):
    doc = page.document
    before = np.array(doc.corrected_image())
    source = page.current_path.read_bytes()
    proposal = select(page)
    page.edge_before_button.click()
    page.apply_edge_button.click()
    after = np.array(doc.corrected_image())
    assert len(doc._undo) == 1 and doc.is_dirty
    assert np.array_equal(after[..., 3], before[..., 3])
    assert np.any(after[..., :3] != before[..., :3])
    changed = np.any(after[..., :3] != before[..., :3], axis=2)
    assert not changed[:16].any() and not changed[80:].any()
    assert not changed[:, :20].any() and not changed[:, 32:].any()
    assert doc.image.crop(proposal.bounds).convert('RGB').tobytes() == proposal.image_patch.tobytes()
    page.undo()
    assert doc.corrected_image().tobytes() == before.tobytes() and not doc.is_dirty
    page.redo()
    assert doc.corrected_image().tobytes() == after.tobytes()
    output, mask = page.save_current()
    assert output != page.current_path and page.current_path.read_bytes() == source
    assert not doc.is_dirty and not page._draft_rgb
    with Image.open(output) as saved:
        assert saved.convert('RGBA').tobytes() == after.tobytes()
        assert abs(saved.info['dpi'][0] - 300) < .01
    with Image.open(mask) as saved:
        assert saved.tobytes() == before[..., 3].tobytes()
    page.undo()
    assert doc.is_dirty
    page.redo()
    assert not doc.is_dirty


@pytest.mark.parametrize('brush_center', [(60, 40), (24, 40)])
def test_applied_rgb_and_mask_survive_a_b_a_and_set_files_without_saved_baseline_promotion(page, brush_center):
    doc = page.document
    original = doc.corrected_image().tobytes()
    select(page)
    page.apply_edge_button.click()
    doc.begin_stroke()
    doc.extend_stroke([brush_center], radius=3, hardness=100, action='remove')
    doc.end_stroke()
    edited = doc.corrected_image().tobytes()
    page.file_list.setCurrentRow(1)
    assert page._paths[0] in page._draft_rgb
    page.file_list.setCurrentRow(0)
    assert page.document.corrected_image().tobytes() == edited and page.document.is_dirty
    assert not page.document.can_undo  # Existing cross-file history policy.
    page.set_files(page._paths, save_dir=page._save_dir)
    assert page.document.corrected_image().tobytes() == edited and page.document.is_dirty
    page.reset()
    assert page.document.corrected_image().tobytes() == original
    page.undo()
    assert page.document.corrected_image().tobytes() == edited


def test_save_copy_reopen_and_new_draft_uses_original_file_list_key(page):
    select(page)
    page.apply_edge_button.click()
    output, _ = page.save_current()
    saved = page.document.corrected_image().tobytes()
    page.file_list.setCurrentRow(1)
    page.file_list.setCurrentRow(0)
    assert page.document.corrected_image().tobytes() == saved and not page.document.is_dirty
    bounds = (25, 20, 27, 24)
    page.document.apply_rgb_proposal(Image.new('RGB', (2, 4), (170, 100, 60)), bounds)
    edited = page.document.corrected_image().tobytes()
    original_path = page.current_path
    page.file_list.setCurrentRow(1)
    assert original_path in page._draft_rgb and output not in page._draft_rgb
    page.file_list.setCurrentRow(0)
    assert page.document.corrected_image().tobytes() == edited and page.document.is_dirty


@pytest.mark.parametrize('method', ['cancel', 'escape', 'undo', 'switch', 'reload', 'hide', 'back', 'close'])
def test_leaving_preview_discards_only_unaccepted_rgb(page, method):
    doc = page.document
    initial = doc.corrected_image().tobytes()
    select(page)
    if method == 'cancel':
        page.cancel_edge_button.click()
    elif method == 'escape':
        QTest.keyClick(page.canvas, Qt.Key.Key_Escape)
    elif method == 'switch':
        page.file_list.setCurrentRow(1)
    elif method == 'reload':
        page.set_files(page._paths)
    elif method == 'back':
        page._back_clicked()
    else:
        getattr(page, method)()
    assert not page._colour_active and page._colour_preview is None
    assert doc.corrected_image().tobytes() == initial and not doc.is_dirty and not doc.can_undo


def test_blocks_edits_and_save_but_keeps_background_zoom_and_space_pan(page):
    doc = page.document
    before = doc.corrected_image().tobytes()
    select(page)
    for button in (page.save_button, page.reset_button, page.undo_button, page.redo_button,
                   page.sharpen_edge_button, *page.tool_buttons.values()):
        assert not button.isEnabled()
    assert page.brush_controls.isHidden() and page.pen_controls.isHidden()
    QTest.keyClick(page.canvas, Qt.Key.Key_Delete)
    QTest.keyClick(page.canvas, Qt.Key.Key_Return)
    QTest.keyClick(page.canvas, Qt.Key.Key_P)
    page.canvas.auto_contour()
    page.redo()
    page.reset()
    with pytest.raises(ValueError, match='предпросмотр'):
        page.save_current()
    zoom = page.canvas.transform().m11()
    QTest.keyClick(page.canvas, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
    assert page.canvas.transform().m11() > zoom
    page._set_background('Белый')
    page._set_background('Чёрный')
    assert doc.corrected_image().tobytes() == before and not page.canvas.contour_busy


def test_empty_noop_and_oversized_selection_never_create_history(page):
    page.file_list.setCurrentRow(1)
    page.colour_edge_button.click()
    page._start_colour_region((20, 16, 32, 80))
    wait_result(page)
    assert page._colour_active and page._colour_preview is None
    assert page.canvas.colour_selection_enabled and not page.apply_edge_button.isEnabled()
    assert not page.document.can_undo and not page.document.is_dirty
    page.cancel_edge_button.click()
    # Refuse before copying a full image or scheduling a worker.
    page._document = MaskEditDocument(Image.new('RGBA', (1100, 1100), (10, 20, 30, 255)))
    page.canvas.set_document(page._document)
    page.start_colour_correction()
    with patch.object(page.document.image, 'crop', side_effect=AssertionError('oversize read')):
        page._start_colour_region((0, 0, 1100, 1100))
    assert page._colour_job is None and page.canvas.colour_selection_enabled
    page.cancel_edge_preview()
    page.set_files([])
    assert not page.colour_edge_button.isEnabled()


def test_failed_save_retains_applied_rgb_and_draft_after_switch(page):
    select(page)
    page.apply_edge_button.click()
    edited = page.document.corrected_image().tobytes()
    source = page.current_path.read_bytes()
    with patch.object(MaskEditDocument, '_replace_pair', side_effect=OSError('disk full')):
        with pytest.raises(OSError, match='disk full'):
            page.save_current()
    assert page.document.is_dirty and page.current_path.read_bytes() == source
    page.file_list.setCurrentRow(1)
    page.file_list.setCurrentRow(0)
    assert page.document.corrected_image().tobytes() == edited and page.document.is_dirty


@pytest.mark.parametrize('stale_at', ['completion', 'apply'])
def test_stale_alpha_or_rgb_proposal_rejected(page, stale_at):
    doc = page.document
    initial = doc.corrected_image().tobytes()
    if stale_at == 'apply':
        select(page)
        doc.mask_revision += 1
        page.apply_edge_button.click()
    else:
        page.start_colour_correction()
        future = Future()
        with patch('v3_transparency_preview._CONTOUR_EXECUTOR.submit', return_value=future):
            page._start_colour_region((20, 16, 32, 80))
        doc.rgb_revision += 1
        future.set_result(None)
        page._poll_colour()
    assert not page._colour_active and not doc.can_undo and doc.corrected_image().tobytes() == initial


def test_cancel_inflight_job_then_switch_does_not_touch_new_document(page):
    page.start_colour_correction()
    future = Future()
    future.set_running_or_notify_cancel()
    with patch('v3_transparency_preview._CONTOUR_EXECUTOR.submit', return_value=future):
        page._start_colour_region((20, 16, 32, 80))
    cancel = page._colour_job['cancel']
    old = page.document
    page.file_list.setCurrentRow(1)
    assert cancel.is_set() and page._colour_job is None
    future.set_result(None)
    page._poll_colour()
    assert not page.document.is_dirty and not old.is_dirty and not page._colour_active


def test_back_discard_clears_applied_rgb_drafts_and_current_image(page):
    select(page)
    page.apply_edge_button.click()
    page.file_list.setCurrentRow(1)
    assert page._has_unsaved_changes() and page._draft_rgb
    with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Discard):
        page._back_clicked()
    assert page._document is None and not page._draft_rgb and not page._draft_masks


def test_region_worker_matches_direct_full_image_proposal(page):
    from edge_colour_correction import propose_edge_colour
    from v3_transparency_preview import _edge_colour_region
    image, mask = page.document.image, page.document.mask
    bounds = (20, 16, 32, 80)
    direct = propose_edge_colour(image, Image.new('L', (12, 64), 255), bounds, alpha_mask=mask)
    context = (0, 0, 54, 96)
    local = _edge_colour_region(image.crop(context), mask.crop(context), bounds, (0, 0), Event())
    assert local.bounds == direct.bounds and local.image_patch.tobytes() == direct.image_patch.tobytes()


def test_focus_loss_stops_rectangle_drag_and_hover_cannot_move_it(page):
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QFocusEvent
    page.start_colour_correction()
    canvas = page.canvas
    start = canvas.mapFromScene(QPointF(20, 16))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    assert canvas._colour_drag_start is not None
    canvas.focusOutEvent(QFocusEvent(QEvent.Type.FocusOut))
    assert canvas._colour_drag_start is None
    before = canvas.colour_selection_bounds
    QTest.mouseMove(canvas.viewport(), canvas.mapFromScene(QPointF(40, 70)))
    assert canvas.colour_selection_bounds == before
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)


def test_canvas_document_reload_cancels_page_selection_and_unblocks_save(page):
    page.start_colour_correction()
    page.canvas.set_document(page.document)
    assert not page._colour_active and not page.canvas.edge_preview_active
    assert page._colour_preview is None
    page.save_current()


def test_worker_failure_returns_to_selection_without_unhandled_qt_slot(page):
    page.start_colour_correction()
    future = Future()
    with patch('v3_transparency_preview._CONTOUR_EXECUTOR.submit', return_value=future):
        page._start_colour_region((20, 16, 32, 80))
    future.set_exception(RuntimeError('unexpected worker failure'))
    page._poll_colour()
    assert page._colour_active and page._colour_job is None
    assert page.canvas.colour_selection_enabled and not page.apply_edge_button.isEnabled()
    assert not page.document.is_dirty and not page.document.can_undo
    assert 'Не удалось' in page.colour_note.text()


def test_reverse_drag_at_zoom_clips_to_image_without_painting(page):
    canvas = page.canvas
    page._set_zoom(150)
    page.start_colour_correction()
    initial = page.document.corrected_image().tobytes()
    start = canvas.mapFromScene(QPointF(31, 79))
    end = canvas.mapFromScene(QPointF(-5, 16))
    QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(canvas.viewport(), end)
    QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
    wait_result(page)
    assert canvas.colour_selection_bounds[0] == 0
    assert all(abs(a - b) <= 1 for a, b in zip(canvas.colour_selection_bounds, (0, 16, 31, 79)))
    assert page._colour_preview is not None
    assert page.document.corrected_image().tobytes() == initial


def test_checked_colour_action_can_cancel_selection_as_in_approved_mockup(page):
    page.colour_edge_button.click()
    assert page.colour_edge_button.isEnabled() and page.colour_edge_button.isChecked()
    page.colour_edge_button.click()
    assert not page._colour_active and not page.colour_edge_button.isChecked()
    assert not page.document.is_dirty


def test_worker_nonzero_origin_uses_current_alpha_and_matches_full_image(page):
    from edge_colour_correction import propose_edge_colour
    from v3_transparency_preview import _edge_colour_region
    image = page.document.image
    mask = page.document.mask.copy()
    mask.paste(0, (24, 66, 27, 69))
    bounds, context = (24, 60, 32, 80), (2, 38, 54, 96)
    direct = propose_edge_colour(image, Image.new('L', (8, 20), 255), bounds, alpha_mask=mask)
    local = _edge_colour_region(image.crop(context), mask.crop(context), (22, 22, 30, 42), (2, 38), Event())
    assert direct is not None and local is not None
    assert local.bounds == direct.bounds and local.image_patch.tobytes() == direct.image_patch.tobytes()
    original = image.crop((24, 66, 27, 69)).convert('RGB').tobytes()
    preview = image.convert('RGB')
    preview.paste(local.image_patch, local.bounds)
    assert preview.crop((24, 66, 27, 69)).tobytes() == original


def test_reset_budget_refusal_explains_reason_and_keeps_pixels_history_and_dirty(page):
    select(page)
    page.apply_edge_button.click()
    doc = page.document
    before = (doc.corrected_image().tobytes(), doc.history_bytes, doc.can_undo, doc.can_redo, doc.is_dirty)
    doc.HISTORY_MEMORY_LIMIT = 8
    assert page.reset_button.isEnabled()
    page.reset_button.click()
    assert 'Не хватает памяти истории' in page.contour_status.text()
    assert page.contour_status.isVisible()
    assert (doc.corrected_image().tobytes(), doc.history_bytes, doc.can_undo, doc.can_redo, doc.is_dirty) == before


def test_cancelled_old_nonempty_result_cannot_replace_new_job(page):
    from edge_colour_correction import propose_edge_colour
    doc = page.document
    proposal = propose_edge_colour(doc.image, Image.new('L', (12, 64), 255), (20, 16, 32, 80), alpha_mask=doc.mask)
    assert proposal is not None
    old, new = Future(), Future()
    old.set_running_or_notify_cancel()
    page.start_colour_correction()
    with patch('v3_transparency_preview._CONTOUR_EXECUTOR.submit', return_value=old):
        page._start_colour_region((20, 16, 32, 80))
    page.cancel_edge_preview()
    page.start_colour_correction()
    with patch('v3_transparency_preview._CONTOUR_EXECUTOR.submit', return_value=new):
        page._start_colour_region((22, 18, 34, 76))
    old.set_result(proposal)
    page._poll_colour()
    assert page._colour_job['future'] is new and page._colour_preview is None
    assert page.canvas.colour_preview_patch is None and not doc.is_dirty and not doc.can_undo
    new.set_result(None)
    page._poll_colour()
    assert page._colour_preview is None and page.canvas.colour_selection_enabled
