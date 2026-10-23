"""Pen contour editing: Ctrl+click adds/deletes points, a selected group moves and deletes together
(owner-approved mockup docs/ui/3.2/transparency-edge-tools/07-pen-point-edit-mockup/)."""
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from v3_transparency_preview import ClipartTransparencyEditorPage

CTRL = Qt.KeyboardModifier.ControlModifier
SQUARE = [(30, 30), (100, 30), (100, 100), (30, 100)]


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    source = tmp_path / 'output' / 'plain.png'
    source.parent.mkdir()
    Image.new('RGBA', (130, 130), (200, 120, 90, 255)).save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120, 780)
    result.set_files([source])
    result.show()
    app.processEvents()
    result._set_zoom(200)
    result._set_tool('pen')
    canvas = result.canvas
    for point in SQUARE + [SQUARE[0]]:
        click(canvas, point)
        QTest.qWait(1)
    assert len(canvas.contour.paths) == 1 and len(canvas.contour.paths[0].nodes) == 4
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


def view(canvas, point):
    return canvas.mapFromScene(canvas._item.mapToScene(QPointF(*point)))


def click(canvas, point, button=Qt.MouseButton.LeftButton, modifiers=Qt.KeyboardModifier.NoModifier):
    QTest.mouseClick(canvas.viewport(), button, modifiers, view(canvas, point))


def points(canvas):
    return [node.point for node in canvas.contour.paths[0].nodes]


def test_ctrl_left_click_on_line_adds_corner_point_without_changing_shape(page):
    canvas = page.canvas
    click(canvas, (65, 30), modifiers=CTRL)
    nodes = canvas.contour.paths[0].nodes
    assert len(nodes) == 5
    added = nodes[1]
    assert added.kind == 'corner'
    assert abs(added.point[0] - 65) < 2 and abs(added.point[1] - 30) < 1e-6
    page.undo()
    assert points(canvas) == SQUARE


def test_ctrl_right_click_on_line_adds_smooth_point(page):
    canvas = page.canvas
    click(canvas, (100, 65), Qt.MouseButton.RightButton, CTRL)
    nodes = canvas.contour.paths[0].nodes
    assert len(nodes) == 5 and nodes[2].kind == 'smooth'


def test_ctrl_click_on_point_deletes_it_but_keeps_three(page):
    canvas = page.canvas
    click(canvas, SQUARE[1], modifiers=CTRL)
    assert points(canvas) == [SQUARE[0], SQUARE[2], SQUARE[3]]
    click(canvas, SQUARE[2], modifiers=CTRL)
    assert len(points(canvas)) == 3          # a contour never drops below three points


def test_ctrl_hover_shows_add_or_remove_hint(page):
    canvas = page.canvas
    canvas._update_point_hover(view(canvas, (65, 30)), CTRL)
    assert canvas._point_hover[0] == 'add'
    assert page.local_selection_label.text() == 'Ctrl+щелчок по линии — добавить точку'
    canvas._update_point_hover(view(canvas, SQUARE[1]), CTRL)
    assert canvas._point_hover == ('remove', SQUARE[1])
    assert page.local_selection_label.text() == 'Ctrl+щелчок по точке — удалить'
    assert canvas.cursor().shape() == Qt.CursorShape.BitmapCursor
    canvas._update_point_hover(view(canvas, SQUARE[1]), Qt.KeyboardModifier.NoModifier)
    assert canvas._point_hover is None
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor


def test_dragging_one_selected_point_moves_the_whole_group(page):
    canvas = page.canvas
    canvas.contour.select([(0, 1), (0, 2)])
    viewport = canvas.viewport()
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, view(canvas, SQUARE[1]))
    QTest.mouseMove(viewport, view(canvas, (110, 30)))
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, view(canvas, (110, 30)))
    moved = points(canvas)
    assert moved[0] == SQUARE[0] and moved[3] == SQUARE[3]
    assert abs(moved[1][0] - 110) < 1 and abs(moved[2][0] - 110) < 1
    assert moved[1][1] == 30 and moved[2][1] == 100
    assert canvas.contour.selection == {(0, 1), (0, 2)}
    page.undo()
    assert points(canvas) == SQUARE       # the whole drag is one undo step


def test_arrows_move_and_delete_removes_the_selected_group(page):
    canvas = page.canvas
    canvas.setFocus()
    canvas.contour.select([(0, 1), (0, 2)])
    QTest.keyClick(canvas, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert points(canvas)[1] == (90, 30) and points(canvas)[2] == (90, 100)
    canvas.contour.select([(0, 0), (0, 1)])
    page._refresh_local_buttons()
    assert page.local_selection_label.text().startswith('Выделено точек: 2 · Delete — удалить · Esc — снять')
    canvas.contour.select([(0, 1)])
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert len(points(canvas)) == 3
    canvas.contour.select([(0, 0), (0, 1)])
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert len(points(canvas)) == 3          # deleting two of three would break the contour: refused
