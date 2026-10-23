"""Edge buttons in the window: lasso area scope, one undo step per press, reachable controls (PRD item 4)."""
import time

import numpy as np
from PIL import Image
import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_edge_operations import area_scope, edge_proposal


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    from v3_transparency_preview import ClipartTransparencyEditorPage
    y, x = np.mgrid[:130, :130]
    # A square with a 6 px soft edge on every side.
    inside = np.minimum.reduce([x - 25, 105 - x, y - 25, 105 - y]).astype(np.float64)
    alpha = np.rint(np.clip(inside / 6 + 0.5, 0, 1) * 255).astype(np.uint8)
    rgba = np.dstack((np.full_like(alpha, 200), np.full_like(alpha, 120), np.full_like(alpha, 90), alpha))
    source = tmp_path / 'output' / 'square.png'
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


def wait(canvas):
    deadline = time.monotonic() + 15
    while canvas.contour_busy and time.monotonic() < deadline:
        QTest.qWait(10)
    assert not canvas.contour_busy


def press(page, operation):
    button = page.edge_buttons[operation]
    page.tools_scroll.ensureWidgetVisible(button)
    QApplication.processEvents()
    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    wait(page.canvas)


def lasso(canvas, points):
    viewport = canvas.viewport()
    mapped = [canvas.mapFromScene(canvas._item.mapToScene(QPointF(*p))) for p in points]
    QTest.mousePress(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mapped[0])
    for point in mapped[1:-1]:
        QTest.mouseMove(viewport, point, 2)
    QTest.mouseRelease(viewport, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mapped[-1])


LEFT_SIDE = [(10, 40), (45, 40), (45, 90), (10, 90), (10, 40)]


@pytest.mark.parametrize('operation', ['harder', 'softer', 'shrink', 'grow'])
def test_buttons_work_inside_the_lasso_area_only_and_undo_one_step(page, operation):
    canvas, doc = page.canvas, page.document
    page._set_tool('lasso')
    lasso(canvas, LEFT_SIDE)
    assert page.edge_scope_label.text() == 'Область лассо'
    area = canvas.lasso_area_key()
    before = np.array(doc.mask)
    press(page, operation)
    after = np.array(doc.mask)
    expected = np.asarray(edge_proposal(Image.fromarray(before), operation, area=area))
    np.testing.assert_array_equal(after, expected)
    scope = np.asarray(area_scope(doc.mask.size, area)) > 0
    np.testing.assert_array_equal(after[~scope], before[~scope])
    assert not np.array_equal(after[scope], before[scope])
    assert len(doc._undo) == 1
    QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    np.testing.assert_array_equal(np.array(doc.mask), before)
    QTest.keyClick(canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
    np.testing.assert_array_equal(np.array(doc.mask), after)


def test_without_area_the_whole_image_changes_and_repeats_continue(page):
    doc = page.document
    assert page.edge_scope_label.text() == 'Всё изображение'
    start = np.array(doc.mask)
    press(page, 'shrink')
    press(page, 'shrink')
    assert len(doc._undo) == 2
    covered = lambda a: (a.astype(np.float64) / 255).sum()
    assert covered(np.array(doc.mask)) < covered(start) - 4 * 76   # two pixels off each of four ~78 px sides
    page.undo()
    page.undo()
    np.testing.assert_array_equal(np.array(doc.mask), start)


def test_harder_stops_at_its_limit_and_the_button_reports_it(page):
    for _ in range(4):
        if page.edge_buttons['harder'].isEnabled():
            press(page, 'harder')
    press(page, 'harder')
    assert not page.edge_buttons['harder'].isEnabled()
    assert page.edge_buttons['softer'].isEnabled()
    row = np.array(page.document.mask)[65]
    assert np.count_nonzero((row > 0) & (row < 255)) >= 2


@pytest.mark.parametrize('tool', ['brush', 'pen', 'lasso'])
def test_edge_block_reachable_at_1120_by_780(page, app, tool):
    page._set_tool(tool)
    app.processEvents()
    for button in page.edge_buttons.values():
        page.tools_scroll.ensureWidgetVisible(button)
        app.processEvents()
        top = button.mapTo(page.tools_scroll.viewport(), button.rect().topLeft()).y()
        assert 0 <= top < page.tools_scroll.viewport().height()
