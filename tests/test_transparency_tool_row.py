"""Tool row Brush / Pen / Lasso and the lasso as a separate area tool (PRD item 3)."""
import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_contour import BezierNode, BezierPath, rasterize_path
from v3_transparency_preview import ClipartTransparencyEditorPage


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


SQUARE = BezierPath(tuple(BezierNode(p) for p in [(20, 30), (44, 30), (68, 30), (68, 90), (20, 90)]), 255, (130, 130))


@pytest.fixture
def page(app, tmp_path):
    alpha = rasterize_path(SQUARE, (0, 0, 130, 130))
    rgba = np.dstack((np.full_like(alpha, 90), np.full_like(alpha, 120), np.full_like(alpha, 135), alpha))
    source = tmp_path / 'output' / 'leaf.png'
    source.parent.mkdir()
    Image.fromarray(rgba).save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120, 780)
    result.set_files([source])
    result.show()
    app.processEvents()
    result._set_zoom(150)
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


def with_contour(page):
    page._set_tool('pen')
    page.canvas.contour.paths = [SQUARE]
    page.canvas.contour.original = [SQUARE]
    page._refresh_history_buttons()


def lasso(canvas, points, modifiers=Qt.KeyboardModifier.NoModifier):
    viewport = canvas.viewport()
    mapped = [canvas.mapFromScene(canvas._item.mapToScene(QPointF(*p))) for p in points]
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, modifiers, mapped[0])
    for point in mapped[1:-1]:
        QTest.mouseMove(viewport, point, 2)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, modifiers, mapped[-1])


TOP = [(14, 24), (74, 24), (74, 36), (14, 36), (14, 24)]
BOTTOM = [(14, 84), (74, 84), (74, 96), (14, 96), (14, 84)]


def test_three_tools_in_one_row_with_their_own_panels(page, app):
    buttons = page.tool_buttons
    assert list(buttons) == ['brush', 'pen', 'lasso']
    assert [b.text() for b in buttons.values()] == ['Кисть', 'Перо', 'Лассо']
    assert page.lasso_button is buttons['lasso']
    assert len({b.geometry().top() for b in buttons.values()}) == 1, 'one row'
    assert max(b.width() for b in buttons.values()) - min(b.width() for b in buttons.values()) <= 2
    for tool, panel in (('brush', page.brush_controls), ('pen', page.pen_controls), ('lasso', page.lasso_controls)):
        QTest.mouseClick(buttons[tool], Qt.MouseButton.LeftButton)
        app.processEvents()
        assert page.canvas.tool == tool
        assert [k for k, b in buttons.items() if b.isChecked()] == [tool]
        assert panel.isVisible()
        assert sum(p.isVisible() for p in (page.brush_controls, page.pen_controls, page.lasso_controls)) == 1
    page._set_tool('brush')
    for text, tool in (('l', 'lasso'), ('и', 'brush'), ('д', 'lasso'), ('p', 'pen')):
        QApplication.sendEvent(page.canvas, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, text))
        assert page.canvas.tool == tool, text


def test_pen_contour_block_keeps_two_even_buttons_and_no_lasso(page):
    with_contour(page)
    assert not page.pen_controls.isAncestorOf(page.lasso_button)
    assert page.new_contour_button.geometry().top() == page.contour_button.geometry().top()
    assert abs(page.new_contour_button.width() - page.contour_button.width()) <= 2


def test_lasso_draws_an_area_without_a_contour(page):
    page._set_tool('lasso')
    canvas = page.canvas
    assert canvas.cursor().shape() == Qt.CursorShape.CrossCursor
    assert page.lasso_status_label.text() == 'Область не выделена'
    assert not page.clear_lasso_button.isEnabled()
    lasso(canvas, TOP)
    assert len(canvas.lasso_area) == 1
    assert page.lasso_status_label.text() == 'Область выделена'
    lasso(canvas, BOTTOM, Qt.KeyboardModifier.ShiftModifier)
    assert len(canvas.lasso_area) == 2, 'Shift adds to the area'
    lasso(canvas, TOP)
    assert len(canvas.lasso_area) == 1, 'a new stroke replaces the area'
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     canvas.mapFromScene(canvas._item.mapToScene(QPointF(100, 110))))
    assert canvas.lasso_area == [], 'a plain click clears the area'
    lasso(canvas, TOP)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.lasso_area == []
    lasso(canvas, TOP)
    page.clear_lasso_button.click()
    assert canvas.lasso_area == []


def test_lasso_selects_area_and_contour_points_used_by_the_pen(page):
    with_contour(page)
    page._set_tool('lasso')
    canvas = page.canvas
    lasso(canvas, TOP)
    assert canvas.contour.selection == {(0, 0), (0, 1), (0, 2)}
    assert page.lasso_status_label.text() == 'Область выделена · точек контура в ней: 3'
    page._set_tool('pen')
    assert canvas.contour.selection == {(0, 0), (0, 1), (0, 2)}
    assert page.simplify_button.isEnabled()
    assert len(canvas.lasso_area) == 1, 'the area outlives the tool switch'


def test_area_stays_while_painting_and_brush_still_paints(page):
    page._set_tool('lasso')
    canvas = page.canvas
    lasso(canvas, TOP)
    page._set_tool('brush')
    before = page.document.mask.tobytes()
    point = canvas.mapFromScene(canvas._item.mapToScene(QPointF(40, 60)))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    assert page.document.mask.tobytes() != before
    assert len(canvas.lasso_area) == 1


def test_lasso_panel_reachable_at_1120_by_780(page, app):
    page._set_tool('lasso')
    app.processEvents()
    for button in (page.clear_lasso_button, page.save_button):
        page.tools_scroll.ensureWidgetVisible(button)
        app.processEvents()
        top = button.mapTo(page.tools_scroll.viewport(), button.rect().topLeft()).y()
        assert 0 <= top < page.tools_scroll.viewport().height()
