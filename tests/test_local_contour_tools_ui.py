"""Real Qt local selection, non-destructive drafts and alpha-only commits."""
from concurrent.futures import CancelledError
from dataclasses import replace
from math import cos, sin, pi
from threading import Event
import time
from unittest.mock import patch

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QComboBox

from studio_contour import BezierNode, BezierPath, rasterize_path
from studio_contour_local import smooth_selected, simplify_selected
from v3_transparency_preview import ClipartTransparencyEditorPage, _calculate_contour


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def noisy_path():
    points = [(20,30),(28,30.8),(36,29.2),(44,30.8),(52,29.2),(60,30.8),(68,30),(68,90),(20,90)]
    return BezierPath(tuple(BezierNode(p) for p in points), 255, (130,130))


@pytest.fixture
def page(app, tmp_path):
    path = noisy_path()
    alpha = rasterize_path(path, (0,0,130,130))
    y, x = np.indices(alpha.shape)
    rgba = np.dstack((x.astype('uint8'), y.astype('uint8'), np.full_like(alpha, 135), alpha))
    source = tmp_path / 'output' / 'leaf.png'
    source.parent.mkdir()
    Image.fromarray(rgba).save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120,780)
    result.set_files([source])
    result.show()
    app.processEvents()
    result._set_tool('pen')
    result.canvas.contour.paths = [path]
    result.canvas.contour.original = [path]
    result._refresh_history_buttons()
    yield result
    result.canvas.cancel_contour()
    wait(result.canvas)
    result.close()
    result.deleteLater()
    app.processEvents()


def wait(canvas):
    deadline = time.monotonic() + 15
    while canvas.contour_busy and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not canvas.contour_busy


def select(page, pairs=None):
    page.canvas.contour.select(pairs if pairs is not None else [(0,i) for i in range(7)])
    page._refresh_history_buttons()


def lasso(canvas, points, modifiers=Qt.KeyboardModifier.NoModifier):
    viewport = canvas.viewport()
    mapped = [canvas.mapFromScene(QPointF(*p)) for p in points]
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, modifiers, mapped[0])
    for point in mapped[1:-1]:
        QTest.mouseMove(viewport, point, 2)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, modifiers, mapped[-1])


def test_freehand_lasso_shift_individual_additive_zoom_and_replace(page):
    canvas = page.canvas
    page._set_zoom(150)
    page.lasso_button.click()
    lasso(canvas, [(16,25),(35,24),(39,34),(18,36),(16,25)])
    assert canvas.contour.selection == {(0,0),(0,1),(0,2)}
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     canvas.mapFromScene(QPointF(68,90)))
    assert canvas.contour.selection == {(0,0),(0,1),(0,2),(0,7)}
    lasso(canvas, [(49,24),(73,25),(72,37),(49,35),(49,24)], Qt.KeyboardModifier.ShiftModifier)
    assert canvas.contour.selection == {(0,0),(0,1),(0,2),(0,4),(0,5),(0,6),(0,7)}
    lasso(canvas, [(39,25),(48,25),(48,36),(39,36),(39,25)])
    assert canvas.contour.selection == {(0,3)}
    assert canvas.contour.selected == (0,3)
    assert '1' in page.local_selection_label.text()


def test_vector_simplification_limits_cached_availability_and_new_edge_controls(page):
    assert not page.simplify_button.isEnabled()
    assert page.smooth_edge_button.isEnabled()
    assert not hasattr(page, 'smooth_button')
    assert page.local_selection_label.text() == 'Точки не выделены'
    assert page.edge_scope_label.text() == 'Весь край'
    assert not page.pen_controls.findChildren(QComboBox)
    select(page)
    assert page.edge_scope_label.text() == 'Выделенный участок'
    assert page.simplify_button.isEnabled()
    with patch('v3_transparency_preview.simplify_selected', wraps=simplify_selected) as simplify:
        with patch('v3_transparency_preview.smooth_selected', wraps=smooth_selected) as smooth:
            for _ in range(6):
                page._refresh_history_buttons()
                page.canvas.viewport().repaint()
            assert simplify.call_count == smooth.call_count == 0
    # Retain vector smoothing coverage independently of removed lower UI action.
    for _ in range(100):
        if not page.canvas.contour.local_steps()[1].changed:
            break
        page.canvas.local_operation('smooth')
        wait(page.canvas)
    assert not page.canvas.contour.local_steps()[1].changed
    assert page.simplify_button.isEnabled()
    for _ in range(100):
        if not page.simplify_button.isEnabled():
            break
        page.simplify_button.click()
        wait(page.canvas)
    assert not page.simplify_button.isEnabled()
    assert 'Достигнут предел' in page.local_selection_label.text()
    page.undo()
    wait(page.canvas)
    assert page.simplify_button.isEnabled()
    select(page, [(0,0)])
    assert not page.simplify_button.isEnabled()
    page.canvas.contour.paths = [noisy_path()]
    select(page)
    assert page.canvas.contour.local_steps()[1].changed
    QTest.keyClick(page.canvas, Qt.Key.Key_Right)
    wait(page.canvas)
    expected = smooth_selected(tuple(page.canvas.contour.paths), page.canvas.contour.selection)
    assert page.canvas.contour.local_steps()[1] == expected


def test_preview_before_cancel_history_apply_undo_save_rgb(page):
    canvas, document = page.canvas, page.document
    initial = document.mask.tobytes()
    rgb = document.image.convert('RGB').tobytes()
    select(page)
    before = tuple(canvas.contour.paths)
    page.simplify_button.click()
    wait(canvas)
    after = tuple(canvas.contour.paths)
    assert after != before
    assert document.mask.tobytes() == initial
    assert not document.can_undo
    assert canvas._preview_alpha is not None
    page.before_button.click()
    assert not canvas.contour.preview_after
    assert tuple(canvas.contour.paths) == after
    with pytest.raises(ValueError):
        page.save_current()
    page.cancel_local_button.click()
    assert tuple(canvas.contour.paths) == before
    assert document.mask.tobytes() == initial
    page.undo()
    wait(canvas)
    assert canvas.contour.local_active
    assert tuple(canvas.contour.paths) == after
    # Apply must commit After even when the owner is currently viewing Before.
    page.before_button.click()
    page.apply_contour_button.click()
    output, mask = page.save_current()  # Waits for an already requested Apply.
    assert not canvas.contour.local_active
    assert document.can_undo
    applied = document.mask.tobytes()
    assert applied != initial
    assert len(document._undo) == 1
    with Image.open(output) as saved, Image.open(mask) as alpha:
        assert saved.convert('RGB').tobytes() == rgb
        assert saved.getchannel('A').tobytes() == alpha.tobytes() == applied
    page.undo()
    assert document.mask.tobytes() == initial
    page.redo()
    assert document.mask.tobytes() == applied


def test_local_cancel_keeps_prior_manual_draft_and_manual_action_is_explicit(page):
    canvas, document = page.canvas, page.document
    document.mask.putpixel((100,100),55)
    original = document.mask.tobytes()
    canvas.contour.selected = (0,7)
    QTest.keyClick(canvas, Qt.Key.Key_Right)
    prior_draft = tuple(canvas.contour.paths)
    select(page)
    page.simplify_button.click()
    wait(canvas)
    page.cancel_local_button.click()
    assert tuple(canvas.contour.paths) == prior_draft
    assert canvas.contour.dirty
    canvas.contour.manual = True
    select(page)
    page.canvas.local_operation('smooth')
    wait(canvas)
    assert canvas.contour.local_active
    assert not canvas.contour_busy
    assert canvas._preview_alpha is None
    assert document.mask.tobytes() == original
    assert page.keep_contour_button.isVisible()
    assert page.apply_contour_button.text() == 'Удалить внутри'
    page.keep_contour_button.click()
    wait(canvas)
    assert document.can_undo
    assert document.mask.getpixel((100,100)) == 0


def test_late_preview_cancel_file_switch_and_selection_reindex(page, tmp_path):
    canvas = page.canvas
    select(page)
    original = tuple(canvas.contour.paths)
    real = _calculate_contour
    started, release = Event(), Event()
    def delayed(*args):
        started.set()
        release.wait(5)
        return real(*args)
    with patch('v3_transparency_preview._calculate_contour', side_effect=delayed):
        page.simplify_button.click()
        deadline = time.monotonic() + 5
        while not started.is_set() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert started.is_set()
        assert not page.smooth_edge_button.isEnabled()
        assert not page.file_list.isEnabled()
        page.cancel_job_button.click()
        release.set()
        wait(canvas)
        page.cancel_local_button.click()
    assert tuple(canvas.contour.paths) == original
    assert canvas._preview_alpha is None
    select(page, [(0,2),(0,5)])
    canvas.contour._selected = (0,2)
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert canvas.contour.selection == {(0,4)}
    page.undo()
    assert canvas.contour.selection == {(0,2),(0,5)}
    second = tmp_path / 'second.png'
    Image.new('RGBA',(130,130),(2,4,8,255)).save(second)
    page.set_files([page.current_path, second], selected_index=1)
    assert canvas.contour.selection == set()
    page.file_list.setCurrentRow(0)
    assert canvas.contour.selection == {(0,2),(0,5)}
    canvas.contour.selection.add((500,900))
    page._refresh_history_buttons()
    assert (500,900) not in canvas.contour.selection


def test_controls_reachable_pen_1120_by_780_and_brush_layout_restored(page):
    # The file list must not collapse when the contour controls are shown.
    for index in range(20):
        page.file_list.addItem(f'image-{index:02d}.png')
    heights = []
    for tool in ('brush', 'pen', 'brush', 'pen'):
        QTest.mouseClick(page.tool_buttons[tool], Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        heights.append(page.files_frame.height())
        assert page.file_list.viewport().height() >= 5 * page.file_list.sizeHintForRow(0)
        assert page.files_frame.maximumHeight() == 16777215
    assert max(heights) - min(heights) <= 2
    for button in (page.simplify_button, page.smooth_edge_button, page.save_button, page.back_button):
        page.tools_scroll.ensureWidgetVisible(button)
        QApplication.processEvents()
        rectangle = button.mapTo(page.tools_scroll.viewport(), button.rect().topLeft())
        assert 0 <= rectangle.y() < page.tools_scroll.viewport().height()
    page._set_tool('brush')
    QApplication.processEvents()
    assert page.files_frame.maximumHeight() == 16777215
    assert not page.local_contour_controls.isVisible()
    assert page.brush_controls.isVisible()


@pytest.mark.parametrize('kind', ['local-preview','local-apply'])
def test_disconnected_runs_protect_raw_alpha_other_paths_and_hole(kind):
    p = BezierPath(tuple(BezierNode(q) for q in [(20,40),(30,40.8),(40,39.2),(50,40.8),(60,40),
                     (110,40),(120,40.8),(130,39.2),(140,40.8),(150,40),(150,110),(20,110)]),255,(180,180))
    hole = BezierPath(tuple(BezierNode(q) for q in [(73,60),(90,60),(90,80),(73,80)]),0,(180,180))
    other = BezierPath(tuple(BezierNode(q) for q in [(28,31),(31,31),(31,34),(28,34)]),255,(180,180))
    alpha = rasterize_path(p,(0,0,180,180))
    alpha[rasterize_path(hole,(0,0,180,180)) > 0] = 0
    alpha[rasterize_path(other,(0,0,180,180)) > 0] = 177
    alpha[36:40,70:100] = 81  # Unrepresented fur along an untouched edge.
    paths = (p,hole,other)
    result = smooth_selected(paths, {(0,i) for i in list(range(5))+list(range(5,10))})
    assert result.changed
    edited, _ = _calculate_contour(kind, alpha, paths, result.paths, Event())
    assert np.array_equal(edited[:,70:100], alpha[:,70:100])
    assert np.array_equal(edited[31:35,28:32], alpha[31:35,28:32])
    assert np.array_equal(edited[60:81,73:91], alpha[60:81,73:91])


def test_c_shaped_changed_run_bbox_does_not_touch_unselected_inner_raw_edge():
    angles = np.linspace(-.8*pi,.8*pi,81)
    outer = [(150+(100+(.6 if i%2 else -.6))*cos(a),150+(100+(.6 if i%2 else -.6))*sin(a)) for i,a in enumerate(angles)]
    inner = [(150+50*cos(a),150+50*sin(a)) for a in reversed(angles)]
    p = BezierPath(tuple(BezierNode(q) for q in outer+inner),255,(310,310))
    alpha = rasterize_path(p,(0,0,310,310))
    alpha[146:155,198:204] = 81
    result = smooth_selected((p,), {(0,i) for i in range(len(outer))})
    assert result.changed
    edited, _ = _calculate_contour('local-apply',alpha,(p,),result.paths,Event())
    assert np.array_equal(edited[130:170,185:220],alpha[130:170,185:220])
    assert np.any(edited != alpha)


def test_nearby_path_support_overlap_composes_changes_independent_of_path_order():
    def make(points):
        return BezierPath(tuple(BezierNode(p) for p in points),255,(100,100))
    a = make([(10,10),(60,10),(60,40),(50,40),(45,40.7),(40,40),(10,40)])
    b = make([(40,43),(45,43.7),(50,43),(60,43),(60,70),(40,70)])
    alpha = np.maximum(rasterize_path(a,(0,0,100,100)),rasterize_path(b,(0,0,100,100)))
    selection = {(0,3),(0,4),(0,5),(1,0),(1,1),(1,2)}
    changed = simplify_selected((a,b), selection)
    assert changed.paths[0] != a and changed.paths[1] != b
    only_a, _ = _calculate_contour('local-apply',alpha,(a,b),(changed.paths[0],b),Event())
    only_b, _ = _calculate_contour('local-apply',alpha,(a,b),(a,changed.paths[1]),Event())
    both, _ = _calculate_contour('local-apply',alpha,(a,b),changed.paths,Event())
    reverse, _ = _calculate_contour('local-apply',alpha,(b,a),tuple(reversed(changed.paths)),Event())
    assert np.any(only_a != alpha) and np.any(only_b != alpha)
    assert np.array_equal(both,reverse)
    assert np.array_equal(both[only_a != alpha],only_a[only_a != alpha])
    assert np.array_equal(both[only_b != alpha],only_b[only_b != alpha])


def test_brush_during_local_draft_refreshes_after_without_losing_stroke_or_history(page):
    canvas, document = page.canvas, page.document
    select(page)
    page.simplify_button.click()
    wait(canvas)
    page._set_tool('brush')
    page._set_diameter(6)
    page.hardness_slider.setValue(100)
    QTest.mouseClick(canvas.viewport(),Qt.MouseButton.LeftButton,
                     pos=canvas.mapFromScene(QPointF(40,60)))
    wait(canvas)
    assert document.mask.getpixel((40,60)) == 0
    fresh_mask = np.asarray(document.mask).copy()
    expected, _ = _calculate_contour('local-preview',fresh_mask,tuple(canvas.contour.original),tuple(canvas.contour.paths),Event())
    assert np.array_equal(canvas._preview_alpha,expected)
    page.before_button.click()
    page.after_button.click()
    assert canvas._item.pixmap().toImage().pixelColor(40,60).alpha() == 0
    page.undo()
    wait(canvas)
    assert document.mask.getpixel((40,60)) == 255
    assert canvas._preview_alpha[60,40] == 255
    page.redo()
    wait(canvas)
    assert document.mask.getpixel((40,60)) == 0
    assert canvas._preview_alpha[60,40] == 0
    page.apply_contour_button.click()
    wait(canvas)
    assert document.mask.getpixel((40,60)) == 0
    assert np.array_equal(np.asarray(document.mask),expected)
    page.undo()
    assert np.array_equal(np.asarray(document.mask),fresh_mask)


@pytest.mark.parametrize('operation',['simplify','smooth'])
def test_selected_hole_expansion_preview_and_apply_match_changed_hole_alpha(page,operation):
    def make(points,fill):
        return BezierPath(tuple(BezierNode(p) for p in points),fill,(130,130))
    outer = make([(5,5),(95,5),(95,95),(5,95)],255)
    hole = make([(40,43),(45,43.7),(50,43),(60,43),(60,70),(40,70)],0)
    initial = rasterize_path(outer,(0,0,130,130))
    old_hole = rasterize_path(hole,(0,0,130,130))
    initial[old_hole > 0] = 0
    page.document.mask = Image.fromarray(initial)
    page.document.mask_revision += 1
    page.canvas.contour.paths = [outer,hole]
    page.canvas.contour.original = [outer,hole]
    page.canvas.refresh_image()
    select(page,{(1,0),(1,1),(1,2)})
    button = page.simplify_button if operation == 'simplify' else None
    for _ in range(3 if operation == 'smooth' else 1):
        if button is not None:
            assert button.isEnabled()
            button.click()
        else:
            assert page.canvas.contour.local_steps()[1].changed
            page.canvas.local_operation('smooth')
        wait(page.canvas)
    changed_hole = rasterize_path(page.canvas.contour.paths[1],(0,0,130,130))
    expected = initial.copy()
    expected[(old_hole>0) & (changed_hole==0)] = 255
    expected[(old_hole==0) & (changed_hole>0)] = 0
    assert np.any(expected != initial)
    assert np.array_equal(page.canvas._preview_alpha,expected)
    assert np.array_equal(np.asarray(page.document.mask),initial)
    page.apply_contour_button.click()
    wait(page.canvas)
    assert np.array_equal(np.asarray(page.document.mask),expected)
    page.undo()
    assert np.array_equal(np.asarray(page.document.mask),initial)


def test_file_switch_discards_late_preview_publication_and_restores_draft(page,tmp_path):
    canvas = page.canvas
    source = page.current_path
    second = tmp_path / 'opaque.png'
    Image.new('RGBA',(130,130),(3,6,9,255)).save(second)
    select(page)
    real = _calculate_contour
    started, release = Event(), Event()
    def delayed(*args):
        started.set()
        release.wait(5)
        return real(*args)
    with patch('v3_transparency_preview._calculate_contour',side_effect=delayed):
        page.simplify_button.click()
        deadline = time.monotonic() + 5
        while not started.is_set() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert started.is_set()
        draft = tuple(canvas.contour.paths)
        page.set_files([source,second],selected_index=1)
        release.set()
        wait(canvas)
    assert page.current_path == second
    assert np.all(np.asarray(page.document.mask) == 255)
    assert canvas._preview_alpha is None
    assert canvas.contour.selection == set()
    page.file_list.setCurrentRow(0)
    wait(canvas)
    assert tuple(canvas.contour.paths) == draft
    assert canvas.contour.local_active
    assert canvas._preview_alpha is not None


def test_preview_worker_rejects_changed_mask_revision(page):
    canvas = page.canvas
    select(page)
    real = _calculate_contour
    started, release = Event(), Event()
    def delayed(*args):
        started.set()
        release.wait(5)
        return real(*args)
    with patch('v3_transparency_preview._calculate_contour',side_effect=delayed):
        page.simplify_button.click()
        deadline = time.monotonic() + 5
        while not started.is_set() and time.monotonic() < deadline:
            QTest.qWait(10)
        assert started.is_set()
        page.document.mask.putpixel((40,60),0)
        page.document.mask_revision += 1
        release.set()
        wait(canvas)
    assert canvas._preview_alpha is None
    assert page.document.mask.getpixel((40,60)) == 0
    assert not page.document.can_undo
