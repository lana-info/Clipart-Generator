"""Lasso cursor reset on tool change and Esc order (ERRORS.md #transparency-lasso-cursor-20261022)."""
from dataclasses import replace

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_contour import BezierNode, BezierPath, rasterize_path
from v3_transparency_preview import ClipartTransparencyEditorPage


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    points = [(20, 30), (44, 30), (68, 30), (68, 90), (20, 90)]
    path = BezierPath(tuple(BezierNode(p) for p in points), 255, (130, 130))
    alpha = rasterize_path(path, (0, 0, 130, 130))
    rgba = np.dstack((np.full_like(alpha, 90), np.full_like(alpha, 120), np.full_like(alpha, 135), alpha))
    source = tmp_path / 'output' / 'leaf.png'
    source.parent.mkdir()
    Image.fromarray(rgba).save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120, 780)
    result.set_files([source])
    result.show()
    app.processEvents()
    result._set_tool('pen')
    result.canvas.contour.paths = [path]
    result.canvas.contour.original = [path]
    result._refresh_history_buttons()
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


def lasso(canvas, points):
    viewport = canvas.viewport()
    mapped = [canvas.mapFromScene(QPointF(*p)) for p in points]
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mapped[0])
    for point in mapped[1:-1]:
        QTest.mouseMove(viewport, point, 2)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mapped[-1])


def select_top(page):
    page._set_zoom(150)
    page.lasso_button.click()
    lasso(page.canvas, [(14, 24), (74, 24), (74, 36), (14, 36), (14, 24)])
    assert page.canvas.contour.selection == {(0, 0), (0, 1), (0, 2)}


def test_pen_lasso_brush_leaves_only_the_brush_ring(page):
    canvas = page.canvas
    select_top(page)
    assert canvas.cursor().shape() == Qt.CursorShape.CrossCursor
    page._set_tool('brush')
    assert not page.lasso_button.isChecked()
    assert not canvas.lasso_enabled
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor
    # Space-pan must also return to the tool cursor, not to a stale lasso cross.
    canvas.set_space_pan_active(True)
    canvas.set_space_pan_active(False)
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor
    page._set_tool('pen')
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor
    page.lasso_button.click()
    canvas.set_space_pan_active(True)
    canvas.set_space_pan_active(False)
    assert canvas.cursor().shape() == Qt.CursorShape.CrossCursor


def test_esc_drops_selection_before_leaving_focus_mode(page):
    canvas = page.canvas
    select_top(page)
    page.toggle_focus_mode()
    assert 'Esc' in page.local_selection_label.text()
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.contour.selection == set()
    assert canvas._lasso_outline == []
    assert page._focus_mode, 'first Esc must only drop the selection'
    assert page.local_selection_label.text() == 'Точки не выделены'
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert not page._focus_mode


def test_esc_with_selection_keeps_contour_edits(page):
    canvas = page.canvas
    select_top(page)
    path = canvas.contour.paths[0]
    moved = replace(path, nodes=(BezierNode((22, 32)),) + path.nodes[1:])
    canvas.contour.paths = [moved]
    assert canvas.contour.dirty
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.contour.selection == set()
    assert canvas.contour.paths == [moved], 'Esc with a selection must not reset the contour'
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.contour.paths == [path]
