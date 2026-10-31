"""Столбцы наборов: значки действий и подсветка выбранного столбца (жалоба владельца 2026-10-31).

Владелец не видел ✓ ✎ ⇅ в шапке и не видел, какой столбец выбран. Причина первая: `QHeaderView.paintSection`
оставляет у painter пустую область отсечения, всё нарисованное после `super()` пропадало. Причина вторая:
столбец по размеру заголовка не резервировал места под значки, на узких столбцах значки лежали поверх
названия или вылезали за границу секции. Тесты смотрят на реальные пиксели шапки, а не на вызовы.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QApplication

from studio_set_export_ui import SetExportDialog
from studio_export_membership import validate_export_membership
from v3_components import build_v3_stylesheet

TITLES = ['А', 'Мини', 'Стандартный набор']


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _membership(images, titles):
    """The first picture sits in every set, the others in the last one (same shape as the export screen)."""
    key = str(images[0].resolve())
    value = validate_export_membership({key: {'title': titles[0], 'included': True}})
    for title in titles[1:]:
        value[key]['memberships'].extend(validate_export_membership(
            {key: {'title': title, 'included': True}})[key]['memberships'])
    for image in images[1:]:
        value.update(validate_export_membership({str(image.resolve()): {'title': titles[-1], 'included': True}}))
    return value


@pytest.fixture
def dialog(app, tmp_path):
    images = []
    for number in range(3):
        path = tmp_path / f'item-{number}.png'
        Image.new('RGBA', (32, 32), (60, 80, 90, 255)).save(path)
        images.append(path)
    widget = SetExportDialog(images, membership=_membership(images, TITLES))
    widget.setStyleSheet(build_v3_stylesheet())  # the stylesheet of the real application
    widget.resize(1120, 700)
    widget._show_manual_editor()
    widget.show()
    app.processEvents()
    yield widget
    widget.reject()
    app.processEvents()


def _header_image(dialog):
    header = dialog.table.horizontalHeader()
    return header, header.viewport().grab().toImage()


def _ink(image, rect, background):
    """Pixels of `rect` that clearly differ from the section background (a drawn glyph)."""
    count = 0
    for x in range(max(rect.left(), 0), min(rect.right() + 1, image.width())):
        for y in range(max(rect.top(), 0), min(rect.bottom() + 1, image.height())):
            pixel = image.pixelColor(x, y)
            if (abs(pixel.red() - background.red()) + abs(pixel.green() - background.green())
                    + abs(pixel.blue() - background.blue())) > 90:
                count += 1
    return count


def _tinted(dialog, row, column):
    return dialog.table.item(row, column).background().style() != Qt.BrushStyle.NoBrush


def _set_columns(dialog):
    return range(1, dialog.table.columnCount())


def test_every_action_glyph_is_painted_inside_its_own_column(dialog):
    header, image = _header_image(dialog)
    for column in _set_columns(dialog):
        left = header.sectionViewportPosition(column)
        right = left + header.sectionSize(column)
        background = image.pixelColor(left + 3, header.height() - 4)
        for glyph in header._glyph_rects(column):
            assert glyph.left() > left and glyph.right() < right, (column, glyph, left, right)
            assert _ink(image, glyph, background) > 12, (column, glyph)


def test_glyphs_never_cover_the_column_title(dialog):
    header = dialog.table.horizontalHeader()
    metrics = QFontMetrics(header.font())
    for column, title in enumerate(TITLES, 1):
        marks, _pencil, sort = header._glyph_rects(column)
        title_room = marks.left() - header.sectionViewportPosition(column)
        assert title_room >= metrics.horizontalAdvance(title), (title, title_room)
        assert sort.right() < header.sectionViewportPosition(column) + header.sectionSize(column)


def test_chosen_column_is_tinted_in_header_and_body(dialog):
    header = dialog.table.horizontalHeader()
    other, chosen = 1, 2
    dialog._choose_set_column(chosen)
    QApplication.processEvents()
    image = header.viewport().grab().toImage()
    probe_y = header.height() - 4

    def background(column):
        return image.pixelColor(header.sectionViewportPosition(column) + 3, probe_y)

    assert background(chosen) != background(other)
    assert _tinted(dialog, 0, chosen) and not _tinted(dialog, 0, other)


def test_chosen_column_highlight_survives_table_rebuild_and_follows_the_choice(dialog):
    dialog._choose_set_column(2)
    dialog._rebuild_manual_table()
    assert _tinted(dialog, 1, 2) and not _tinted(dialog, 1, 1)
    dialog._choose_set_column(1)
    assert _tinted(dialog, 1, 1) and not _tinted(dialog, 1, 2)


def test_nothing_is_tinted_while_no_column_is_chosen(dialog):
    dialog._editing_set_id = None
    dialog._rebuild_manual_table()
    for column in _set_columns(dialog):
        assert not _tinted(dialog, 0, column)
