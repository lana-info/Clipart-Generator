"""Pen manual outline: left click places a corner point, right click a smooth curve point (owner request)."""
import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_contour import rasterize_path
from v3_transparency_preview import ClipartTransparencyEditorPage


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
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


SQUARE = [(30, 30), (100, 30), (100, 100), (30, 100)]


def click(canvas, point, button=Qt.MouseButton.LeftButton):
    QTest.mouseClick(canvas.viewport(), button, Qt.KeyboardModifier.NoModifier,
                     canvas.mapFromScene(canvas._item.mapToScene(QPointF(*point))))


def outline(page, button):
    canvas = page.canvas
    for point in SQUARE:
        click(canvas, point, button)
        QTest.qWait(1)                 # keep clicks apart, they are not double clicks
    click(canvas, SQUARE[0])           # back on the first point closes the outline
    assert not canvas.contour.points and len(canvas.contour.paths) == 1
    return canvas.contour.paths[0]


def test_left_clicks_make_corner_points(page):
    path = outline(page, Qt.MouseButton.LeftButton)
    assert [node.kind for node in path.nodes] == ['corner'] * 4
    assert [node.point for node in path.nodes] == SQUARE


def test_right_clicks_make_smooth_points_with_handles_along_the_neighbours(page):
    path = outline(page, Qt.MouseButton.RightButton)
    assert [node.kind for node in path.nodes] == ['smooth'] * 4
    first = path.nodes[0]
    # Handles lie on the line from the previous to the next point: (30,100) -> (100,30).
    assert first.in_handle is not None and first.out_handle is not None
    direction = np.subtract(SQUARE[1], SQUARE[3])
    for handle in (first.in_handle, first.out_handle):
        offset = np.subtract(handle, first.point)
        assert abs(offset[0] * direction[1] - offset[1] * direction[0]) < 1e-6
    # A curve through the four corners bulges out between them, like a circle through the points.
    corner = rasterize_path(outline_corner(), (0, 0, 130, 130))
    curved = rasterize_path(path, (0, 0, 130, 130))
    circle = np.pi * (np.hypot(35, 35)) ** 2
    assert (corner > 0).sum() < (curved > 0).sum() < circle


def outline_corner():
    from studio_contour import BezierNode, BezierPath
    return BezierPath(tuple(BezierNode(p) for p in SQUARE), 0, (130, 130))


def test_mixed_points_keep_their_kind(page):
    canvas = page.canvas
    for point, button in zip(SQUARE, (Qt.MouseButton.LeftButton, Qt.MouseButton.RightButton) * 2):
        click(canvas, point, button)
        QTest.qWait(1)
    assert canvas.contour.smooth_points == {1, 3}
    nodes = canvas.contour.manual_nodes(closed=False)
    assert [n.kind for n in nodes] == ['corner', 'smooth', 'corner', 'corner'], 'the open end stays a corner'
    click(canvas, SQUARE[0])
    assert [n.kind for n in canvas.contour.paths[0].nodes] == ['corner', 'smooth', 'corner', 'smooth']


def test_undo_delete_and_escape_forget_the_curve_flag(page):
    canvas = page.canvas
    click(canvas, SQUARE[0])
    click(canvas, SQUARE[1], Qt.MouseButton.RightButton)
    assert canvas.contour.smooth_points == {1}
    page.undo()
    assert canvas.contour.points == [SQUARE[0]] and canvas.contour.smooth_points == frozenset()
    page.redo()
    assert canvas.contour.smooth_points == {1}
    QTest.keyClick(canvas, Qt.Key.Key_Delete)
    assert canvas.contour.points == [SQUARE[0]] and canvas.contour.smooth_points == frozenset()
    click(canvas, SQUARE[1], Qt.MouseButton.RightButton)
    QTest.keyClick(canvas, Qt.Key.Key_Escape)
    assert canvas.contour.points == [] and canvas.contour.smooth_points == frozenset()


def test_quick_second_right_click_is_another_curve_point(page):
    canvas = page.canvas
    click(canvas, SQUARE[0])
    view = lambda p: canvas.mapFromScene(canvas._item.mapToScene(QPointF(*p)))
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, view(SQUARE[1]))
    QTest.mouseDClick(canvas.viewport(), Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier, view(SQUARE[2]))
    assert canvas.contour.points[-1] == SQUARE[2]
    assert {1, len(canvas.contour.points) - 1} <= canvas.contour.smooth_points


def test_right_click_does_nothing_once_a_contour_exists(page):
    outline(page, Qt.MouseButton.LeftButton)
    canvas = page.canvas
    before = list(canvas.contour.paths)
    click(canvas, (60, 60), Qt.MouseButton.RightButton)
    assert canvas.contour.paths == before and not canvas.contour.points
