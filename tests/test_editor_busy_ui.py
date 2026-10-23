"""Real Qt shared edge/contour jobs: busy lifecycle, cancellation and publication guards."""
from dataclasses import replace
from threading import Event, get_ident
import time
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from studio_contour import BezierNode, BezierPath
from studio_edge_operations import edge_proposal, selection_scope
from v3_transparency_preview import ClipartTransparencyEditorPage, MaskEditDocument


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    alpha = np.full((80, 80), 160, dtype=np.uint8)
    alpha[:10] = 0
    source = tmp_path / 'edge.png'
    image = Image.new('RGBA', (80, 80), (17, 31, 93, 255))
    image.putalpha(Image.fromarray(alpha))
    image.save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120, 780)
    result.set_files([source])
    result.show()
    QTest.qWait(10)
    path = BezierPath(tuple(BezierNode(p) for p in ((10,10),(40,10),(70,10),(70,70),(10,70))),255,(80,80))
    result.canvas.contour.paths = result.canvas.contour.original = [path]
    result._refresh_history_buttons()
    yield result
    result.canvas.cancel_contour()
    wait(result.canvas)
    result.close()
    result.deleteLater()
    app.processEvents()


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert predicate()


def wait(canvas):
    until(lambda: not canvas.contour_busy, 15)


def delayed_job():
    started, release = Event(), Event()
    def calculate(mask, operation, **kwargs):
        started.set()
        assert release.wait(5)
        # Deliberately ignore cancellation in worker: publisher must reject it.
        return mask.point(tuple(min(255, value + 1) for value in range(256)))
    return started, release, calculate


@pytest.mark.parametrize('operation', ['harder', 'smooth', 'shrink'])
def test_busy_paints_before_copy_worker_ignores_repeat_and_explicit_cancel(page, operation):
    canvas, doc = page.canvas, page.document
    before = doc.mask.tobytes()
    started, release, calculate = delayed_job()
    copies, main_thread = [], get_ident()
    real_copy = Image.Image.copy
    def copied(mask):
        if mask is doc.mask:
            copies.append(get_ident())
        return real_copy(mask)
    with patch('v3_transparency_preview.edge_proposal', side_effect=calculate):
        with patch.object(Image.Image, 'copy', copied):
            page._edge_operation(operation)
            assert canvas.contour_busy and canvas._contour_job['future'] is None
            assert page.busy_bar.isVisible() and page.busy_progress.minimum() == page.busy_progress.maximum() == 0
            assert not copies
            until(started.is_set)
            assert copies and all(thread != main_thread for thread in copies)
            assert not page.file_list.isEnabled() and not page.save_button.isEnabled()
            assert not page.undo_button.isEnabled() and not page.reset_button.isEnabled()
            assert not page.back_button.isEnabled()
            assert all(not b.isEnabled() for b in page.tool_buttons.values())
            assert all(b.isEnabled() for b in page.zoom_buttons.values())
            canvas.auto_contour()
            canvas.apply_contour()
            page._edge_operation(operation)
            assert not canvas._contour_job['cancelled'].is_set()
            page._set_zoom(150)
            assert canvas.zoom_percent == 150
            page.cancel_job_button.click()
            assert canvas._contour_job['cancelled'].is_set()
            assert page.busy_bar.isVisible()
            release.set()
            wait(canvas)
    assert not page.busy_bar.isVisible()
    assert doc.mask.tobytes() == before and not doc.can_undo
    assert 'отменён' in page.contour_status.text()


@pytest.mark.parametrize('mutation', ['revision', 'selection', 'paths', 'document', 'escape', 'area'])
def test_stale_or_cancelled_edge_result_never_publishes(page, mutation):
    canvas, doc = page.canvas, page.document
    before = doc.mask.tobytes()
    started, release, calculate = delayed_job()
    with patch('v3_transparency_preview.edge_proposal', side_effect=calculate):
        page._edge_operation('harder')
        until(started.is_set)
        if mutation == 'revision':
            doc.mask_revision += 1
        elif mutation == 'selection':
            canvas.contour.select({(0, 0)})
        elif mutation == 'paths':
            path = canvas.contour.paths[0]
            canvas.contour.paths[0] = replace(path, nodes=(replace(path.nodes[0], point=(11,10)), *path.nodes[1:]))
        elif mutation == 'document':
            canvas.set_document(MaskEditDocument(Image.new('RGBA',(80,80),(2,3,4,255))))
        elif mutation == 'area':
            canvas.lasso_area = [[(0, 0), (20, 0), (20, 20)]]
        else:
            QTest.keyClick(canvas, Qt.Key.Key_Escape)
        release.set()
        wait(canvas)
    assert doc.mask.tobytes() == before and not doc.can_undo
    assert not page.busy_bar.isVisible()


@pytest.mark.parametrize('operation', ['harder', 'smooth', 'shrink'])
def test_same_actual_selection_scope_preserved_for_repeated_alpha_steps(page, operation):
    canvas, doc = page.canvas, page.document
    canvas.contour.select({(0,0),(0,1)})
    paths, selection = tuple(canvas.contour.paths), frozenset(canvas.contour.selection)
    page._refresh_history_buttons()
    assert page.edge_scope_label.text() == 'Выделенный участок'
    before = np.array(doc.mask)
    expected = edge_proposal(doc.mask, operation, paths=paths, selection=selection)
    page._edge_operation(operation)
    wait(canvas)
    np.testing.assert_array_equal(np.array(doc.mask),np.array(expected))
    scope = np.asarray(selection_scope(doc.mask.size, paths, selection)) > 0
    np.testing.assert_array_equal(np.array(doc.mask)[~scope], before[~scope])
    assert tuple(canvas.contour.paths) == paths
    assert frozenset(canvas.contour.selection) == selection
    assert not canvas.contour.dirty
    history = len(doc._undo)
    if history:
        page.undo()
        assert frozenset(canvas.contour.selection) == selection
        assert page.edge_scope_label.text() == 'Выделенный участок'
        page.redo()
        assert frozenset(canvas.contour.selection) == selection
        np.testing.assert_array_equal(np.array(doc.mask),np.array(expected))
    page._edge_operation(operation)
    wait(canvas)
    assert tuple(canvas.contour.paths) == paths and frozenset(canvas.contour.selection) == selection
    assert len(doc._undo) in (history, history + 1)
    canvas.contour.select(set())
    page._refresh_history_buttons()
    assert page.edge_scope_label.text() == 'Всё изображение'


def test_noop_cache_uses_revision_and_selection_without_calculation_on_refresh(page):
    canvas, doc = page.canvas, page.document
    with patch('v3_transparency_preview.edge_proposal', side_effect=lambda mask,*a,**kw: mask) as calculate:
        page.smooth_edge()
        wait(canvas)
        assert not page.smooth_edge_button.isEnabled() and not doc.can_undo
        for _ in range(3):
            page._refresh_history_buttons()
        assert calculate.call_count == 1
        canvas.contour.select({(0,0),(0,1)})
        page._refresh_history_buttons()
        assert page.smooth_edge_button.isEnabled()
        page.smooth_edge()
        wait(canvas)
        assert not page.smooth_edge_button.isEnabled()
        doc.mask_revision += 1
        page._refresh_history_buttons()
        assert page.smooth_edge_button.isEnabled()


def test_worker_error_and_memory_error_leave_history_mask_and_rgb_unchanged(page):
    doc = page.document
    before = (doc.mask.tobytes(), doc.mask_revision, list(doc._undo), list(doc._redo), doc.image.tobytes())
    with patch('v3_transparency_preview.edge_proposal', side_effect=MemoryError('worker')):
        page.smooth_edge()
        wait(page.canvas)
    assert not page.busy_bar.isVisible() and page.save_button.isEnabled()
    assert 'worker' in page.contour_status.text()
    real_crop = Image.Image.crop
    def allocation_error(image, box=None):
        if image is doc.mask:
            raise MemoryError('history')
        return real_crop(image, box)
    with patch.object(Image.Image, 'crop', allocation_error):
        page._edge_operation('harder')
        wait(page.canvas)
    assert before == (doc.mask.tobytes(), doc.mask_revision, doc._undo, doc._redo, doc.image.tobytes())
    assert 'history' in page.contour_status.text()
    assert not page.busy_bar.isVisible() and page.save_button.isEnabled()


def test_short_tooltips_icons_and_busy_row_belongs_to_canvas_only(page):
    assert not hasattr(page, 'smooth_button')
    for widget in page.findChildren(QWidget):
        assert len(widget.toolTip().split()) <= 2, widget.toolTip()
    for button in (page.add_button, page.remove_button, page.new_contour_button, page.contour_button, page.lasso_button):
        assert not button.icon().isNull() and button.accessibleName()
    assert [b.text() for b in page.edge_buttons.values()] == ['Жёстче', 'Мягче', 'Сгладить', 'Сузить', 'Расширить']
    assert all(b.accessibleName() for b in page.edge_buttons.values())
    assert not hasattr(page, 'sharpen_edge_button')
    assert page.save_button.text() == 'Сохранить PNG'
    assert page.brush_diameter == 16 and page.diameter_value.text() == '16 px'
    assert page.canvas.brush_radius == 7.5
    assert page.busy_bar.parent() is page.canvas.parent()
    layout = page.busy_bar.parent().layout()
    assert layout.getItemPosition(layout.indexOf(page.busy_bar))[:2] == (1,0)


def test_noop_cache_releases_replaced_document(page):
    previous = page.document
    with patch('v3_transparency_preview.edge_proposal', side_effect=lambda mask,*a,**kw: mask):
        page.smooth_edge()
        wait(page.canvas)
    assert page.canvas.edge_noops
    page.canvas.set_document(MaskEditDocument(Image.new('RGBA',(80,80),(2,3,4,255))))
    page._refresh_history_buttons()
    assert not page.canvas.edge_noops
    assert all(key[0] is not previous for key in page.canvas.edge_noops)


def test_vector_transform_busy_precedes_calculation_and_cancel_prevents_draft(page):
    canvas = page.canvas
    canvas.contour.select({(0,0),(0,1),(0,2)})
    before = canvas.contour.snapshot()
    started, release = Event(), Event()
    def transform(paths, selection):
        started.set()
        assert release.wait(5)
        from studio_contour_local import simplify_selected
        return simplify_selected(paths, selection)
    with patch('v3_transparency_preview.simplify_selected', side_effect=transform):
        canvas.local_operation('simplify')
        assert canvas.contour_busy and page.busy_bar.isVisible()
        assert not started.is_set()
        until(started.is_set)
        page.cancel_job_button.click()
        release.set()
        wait(canvas)
    assert canvas.contour.snapshot() == before
    assert not canvas.contour.local_active


def test_invalid_selected_scope_rejects_without_global_fallback(page):
    doc = page.document
    initial = doc.mask.tobytes()
    page.canvas.contour.selection = {(99,99)}
    page._edge_operation('harder')
    wait(page.canvas)
    assert doc.mask.tobytes() == initial and not doc.can_undo
    assert page.contour_status.text()
