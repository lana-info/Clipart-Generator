"""Brush size slider 1-64 px, exact diameters, soft edge, Alt+wheel and Shift line."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from background_mask import diameter_radius, paint_mask_path
from v3_transparency_preview import (
    ClipartTransparencyEditorPage,
    diameter_slider_position,
    slider_diameter,
    step_diameter,
)

app = QApplication.instance() or QApplication([])


def _dab(diameter, hardness):
    mask = Image.new("L", (200, 200), 0)
    paint_mask_path(mask, [(100, 100)], radius=diameter_radius(diameter), action="add", hardness=hardness)
    return np.array(mask)


@pytest.mark.parametrize("diameter", range(1, 65))
def test_hard_brush_paints_exactly_the_chosen_diameter(diameter):
    dab = _dab(diameter, 100)
    rows = np.nonzero((dab >= 128).any(axis=1))[0]
    cols = np.nonzero((dab >= 128).any(axis=0))[0]
    assert len(rows) == diameter and len(cols) == diameter
    # No faint marks outside the brush and a fully solid middle.
    top, left = rows[0], cols[0]
    outside = dab.copy()
    outside[top:top + diameter, left:left + diameter] = 0
    assert outside.max() == 0
    assert dab[top + diameter // 2, left + diameter // 2] == 255


def test_small_brushes_stay_hard_and_soft_core_keeps_the_size():
    for diameter in (1, 2, 3):
        assert np.array_equal(_dab(diameter, 0), _dab(diameter, 100))
    assert (_dab(2, 100) == 255).sum() == 4                # 2 px is a solid 2x2 square
    for diameter in (4, 7, 16, 64):
        soft, hard = _dab(diameter, 0), _dab(diameter, 100)
        assert not np.array_equal(soft, hard)
        assert ((hard >= 250) <= (soft >= 250)).all()       # solid core as wide as the hard brush
        feather = np.count_nonzero(soft[100] > 0) - np.count_nonzero(hard[100] > 0)
        width = min(12, max(1, int(diameter * 0.4)))
        assert 2 * width - 2 <= feather <= 2 * width + 4      # 40 % fade, at most 12 px each side


def test_slider_scale_reaches_every_size_and_gives_half_track_to_small_sizes():
    sizes = [slider_diameter(position) for position in range(0, 1001)]
    assert sizes[0] == 1 and sizes[-1] == 64 and sizes == sorted(sizes)
    assert set(sizes) == set(range(1, 65))
    assert 16 <= slider_diameter(500) <= 17
    assert all(slider_diameter(diameter_slider_position(size)) == size for size in range(1, 65))


def test_wheel_and_key_steps():
    assert step_diameter(1, -1) == 1 and step_diameter(64, 1) == 64
    assert (step_diameter(15, 1), step_diameter(16, 1), step_diameter(32, 1)) == (16, 18, 36)
    assert (step_diameter(16, -1), step_diameter(18, -1), step_diameter(36, -1)) == (15, 16, 32)


@pytest.fixture
def page(tmp_path):
    path = tmp_path / "pink_ready.png"
    Image.new("RGBA", (60, 40), (236, 150, 172, 255)).save(path)
    page = ClipartTransparencyEditorPage()
    page.resize(1120, 780)
    page.show()
    page.set_files([path])
    page._set_zoom(100)
    app.processEvents()
    yield page
    page.close()
    page.deleteLater()


def _view_point(canvas, x, y):
    return canvas.mapFromScene(canvas._item.mapToScene(QPointF(x, y)))


def _wheel(canvas, modifiers, delta=120):
    point = QPointF(canvas.viewport().rect().center())
    event = QWheelEvent(point, canvas.viewport().mapToGlobal(point), QPoint(), QPoint(0, delta),
                        Qt.MouseButton.NoButton, modifiers, Qt.ScrollPhase.NoScrollPhase, False)
    canvas.wheelEvent(event)


def test_slider_and_alt_wheel_change_the_brush(page):
    canvas = page.canvas
    assert page.brush_diameter == 16 and canvas.brush_radius == 7.5
    page.diameter_slider.setValue(diameter_slider_position(40))
    assert page.brush_diameter == 40 and canvas.brush_radius == 19.5
    assert page.diameter_value.text() == "40 px"
    zoom = canvas.transform().m11()
    _wheel(canvas, Qt.KeyboardModifier.AltModifier)
    assert page.brush_diameter == 44 and page.diameter_value.text() == "44 px"
    assert page.diameter_slider.value() == diameter_slider_position(44)
    assert canvas._size_flash == "Alt + колесо: 44 px"
    _wheel(canvas, Qt.KeyboardModifier.AltModifier, delta=-240)
    assert page.brush_diameter == 36
    assert canvas.transform().m11() == zoom                 # Alt+wheel does not zoom
    QTest.keyClick(canvas, Qt.Key.Key_Minus)
    assert page.brush_diameter == 32


def test_shift_click_draws_a_straight_line_in_one_undo_step(page):
    canvas = page.canvas
    page._set_diameter(4)
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     _view_point(canvas, 10, 20))
    after_click = np.array(page.document.mask)
    assert after_click[20, 10] == 0 and after_click[20, 30] == 255
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     _view_point(canvas, 50, 20))
    line = np.array(page.document.mask)
    assert (line[20, 10:51] == 0).all()                      # the whole segment is erased
    assert (line[10] == 255).all() and (line[30] == 255).all()   # and nothing far from it
    page.undo()
    assert np.array_equal(np.array(page.document.mask), after_click)


def test_shift_click_without_previous_point_is_a_plain_click(page):
    canvas = page.canvas
    page._set_diameter(4)
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     _view_point(canvas, 30, 20))
    mask = np.array(page.document.mask)
    assert mask[20, 30] == 0 and mask[20, 10] == 255 and mask[20, 50] == 255
