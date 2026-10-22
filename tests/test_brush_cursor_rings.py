"""Brush cursor of two rings: visible on any background, sized to the real brush (PRD item 2)."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtWidgets import QApplication

from background_mask import diameter_radius, paint_mask_path
from v3_transparency_preview import ClipartTransparencyEditorPage

app = QApplication.instance() or QApplication([])


@pytest.fixture
def page(tmp_path):
    source = tmp_path / "output" / "plain.png"
    source.parent.mkdir()
    Image.new("RGBA", (200, 200), (0, 0, 0, 0)).save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120, 780)
    result.set_files([source])
    result.show()
    app.processEvents()
    result._set_zoom(100)
    yield result
    result.close()
    result.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("diameter", [1, 2, 16, 40, 64])
def test_solid_rings_match_the_real_diameter_dark_under_light(page, diameter):
    page._set_diameter(diameter)
    rings = page.canvas.brush_rings()
    dark, light = rings[0], rings[1]
    assert dark[0] == light[0] == diameter / 2
    assert dark[1].lightness() < 30 and light[1].lightness() > 240
    assert dark[2] > light[2], "the dark ring must show around the light one"
    assert len(rings) == 2, "a hard brush has no soft-edge ring"


def test_soft_ring_marks_where_the_real_soft_edge_ends(page):
    page._set_diameter(40)
    page._hardness_changed(0)
    rings = page.canvas.brush_rings()
    assert len(rings) == 4
    assert all(style == Qt.PenStyle.DotLine for *_, style in rings[2:])
    outer = rings[2][0]
    mask = Image.new("L", (200, 200), 0)
    paint_mask_path(mask, [(100, 100)], radius=diameter_radius(40), action="add", hardness=0)
    xs = np.nonzero(np.array(mask)[100])[0]
    painted_radius = (xs.max() - xs.min() + 1) / 2
    assert abs(outer - painted_radius) <= 1.5


def test_small_soft_brush_stays_hard_and_has_no_soft_ring(page):
    page._set_diameter(3)
    page._hardness_changed(0)
    assert len(page.canvas.brush_rings()) == 2


@pytest.mark.parametrize("background", ["Белый", "Чёрный", "Шахматный"])
def test_ring_is_visible_on_every_background(page, background):
    page.background_buttons[background].click()
    page._set_diameter(40)
    canvas = page.canvas
    centre = canvas._item.mapToScene(QPointF(100, 100))
    canvas._brush_scene_point = centre
    canvas.viewport().repaint()
    app.processEvents()
    image = canvas.viewport().grab().toImage()
    point = canvas.mapFromScene(centre)
    ratio = image.devicePixelRatio()
    row = [image.pixelColor(int((point.x() + dx) * ratio), int(point.y() * ratio)).lightness()
           for dx in range(14, 27)]
    background_level = row[0]                       # inside the ring, plain background
    assert max(abs(v - background_level) for v in row) >= 100, row
    assert max(row) - min(row) >= 100, row
