"""Мультивыделение на 30+ картинках: пересборка сетки не теряет группу, текущую и прокрутку.

Приёмка владельца («выделение группы CTRL/SHIFT», 2026-10-31) была проверена на трёх картинках.
В реальном наборе их 30–60: сетка прокручивается, группа разорвана, часть строк пропадает при фильтре
«Нужно посмотреть». Здесь тот же сценарий на 36 картинках (урок T-QUAL-5: пересборка списка).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtWidgets import QApplication

from studio_alpha_qc import AlphaQcReport
from studio_set_export_ui import SetExportDialog

COUNT = 36
GROUP = [2, 5, 17, 29, 30, 31, 32, 33, 34, 35]  # разорванная группа, хвост которой ниже первого экрана


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def dialog(app, tmp_path):
    paths = []
    for number in range(COUNT):
        path = tmp_path / f"g_{number + 1:02d}_ready.png"
        Image.new("RGBA", (24, 24), (120, 160, 200, 255)).save(path)
        paths.append(path)
    # каждая третья картинка требует просмотра, остальные «Готово»
    reports = [AlphaQcReport(str(path.resolve()), "review" if number % 3 == 0 else "ok", (), width=8, height=8)
               for number, path in enumerate(paths)]
    widget = SetExportDialog(paths, quality_reports=reports)
    widget.resize(900, 500)
    widget.show()
    widget._show_quality_review()
    widget.enable_marks({str(path.resolve()): "ok" for path in paths})
    app.processEvents()
    widget.test_paths = paths
    yield widget
    widget.reject()
    app.processEvents()


def _select(dialog, rows):
    grid = dialog.quality_list
    grid.setCurrentRow(rows[0], QItemSelectionModel.SelectionFlag.ClearAndSelect)
    for row in rows[1:]:
        grid.item(row).setSelected(True)


def _selected_rows(dialog):
    return sorted(dialog.quality_list.row(item) for item in dialog.quality_list.selectedItems())


def test_grid_really_scrolls_with_this_many_pictures(dialog):
    """Страховка сценария: если сетка вдруг помещается на экране, тесты ниже ничего не доказывают."""
    assert dialog.quality_list.verticalScrollBar().maximum() > 0


def test_torn_group_and_scroll_survive_rebuild(dialog, app):
    _select(dialog, GROUP)
    grid = dialog.quality_list
    grid.scrollToBottom()
    app.processEvents()
    scroll = grid.verticalScrollBar().value()
    assert scroll > 0
    dialog._refresh_quality_page()
    app.processEvents()
    assert _selected_rows(dialog) == GROUP
    assert grid.currentRow() == GROUP[0]
    assert grid.verticalScrollBar().value() == scroll


def test_group_mark_reaches_every_selected_picture_after_rebuild(dialog):
    _select(dialog, GROUP)
    dialog._refresh_quality_page()
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    dialog.quality_mark_buttons["bad_generation"].click()
    expected = [str(dialog.test_paths[row].resolve()) for row in GROUP]
    assert [path for path, _mark in emitted] == expected
    assert {mark for _path, mark in emitted} == {"bad_generation"}
    assert _selected_rows(dialog) == GROUP  # метка пересобирает сетку, группа остаётся


def test_problem_filter_keeps_only_surviving_group_members_and_the_current_place(dialog):
    _select(dialog, GROUP)
    dialog._set_quality_filter(True)
    grid = dialog.quality_list
    problems = [number for number in range(COUNT) if number % 3 == 0]
    assert grid.count() == len(problems)
    survivors = {problems.index(row) for row in GROUP if row in problems}
    kept = set(_selected_rows(dialog))
    assert survivors <= kept, (survivors, kept)
    # лишнее — только текущая строка «осталась на месте», выбранные ранее «Готово» не воскресают
    assert kept - survivors <= {min(GROUP[0], grid.count() - 1)}, (survivors, kept)
    assert 0 <= grid.currentRow() < grid.count()


def test_select_all_never_takes_pending_check_squares(dialog):
    """CTRL+A при идущей проверке: квадрат «проверяется…» не выделяется и в действия не попадает."""
    dialog._qc_pending = True
    dialog.quality_reports.pop(str(dialog.test_paths[10].resolve()))
    dialog._refresh_quality_page()
    assert not dialog.quality_list.item(10).data(Qt.ItemDataRole.UserRole), "row 10 must be a pending square"
    dialog.quality_list.selectAll()
    keys = dialog._selected_quality_keys()
    assert len(keys) == COUNT - 1 and all(keys)
    assert str(dialog.test_paths[10].resolve()) not in keys
