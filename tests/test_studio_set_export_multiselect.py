"""Мультивыделение на проверке PNG (запрос владельца 2026-10-31).

Характеристика одиночного поведения: клик по одной картинке помечает только её,
повторный клик по той же кнопке снимает пометку, исключение трогает только
текущую, а пересборка сетки (урок T-QUAL-5) сохраняет текущую картинку.
После включения ExtendedSelection те же сценарии работают как раньше, а CTRL/
SHIFT-выделение группы распространяет существующие кнопки (метки, исключение,
«Перегенерировать»/«Убрать фон») на все выделенные — новых кнопок нет.
"""
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QItemSelection, QItemSelectionModel
from PyQt6.QtWidgets import QApplication, QAbstractItemView

from studio_set_export_ui import SetExportDialog
from studio_alpha_qc import AlphaQcReport


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def png(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (24, 24), (120, 160, 200, 255)).save(path)
    return path


def quality_dialog(tmp_path, count=3):
    paths = [png(tmp_path / f"gosling_{index + 1:02d}_ready.png") for index in range(count)]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    dialog = SetExportDialog(paths, quality_reports=reports)
    dialog._show_quality_review()
    return dialog, paths


def keys(paths):
    return [str(path.resolve()) for path in paths]


def membership_for(paths, titles):
    """Every picture in one set; the same shape the export screen stores."""
    from studio_export_membership import validate_export_membership
    value = {}
    for path in paths:
        key = str(path.resolve())
        for title in titles:
            value.update(validate_export_membership({key: {"title": title, "included": True}}))
    return value


def test_click_on_one_picture_marks_only_it(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "ok" for key in keys(paths)})
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    dialog.quality_list.setCurrentRow(1)
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(str(paths[1].resolve()), "bad_generation")]
    assert dialog._marks[str(paths[1].resolve())] == "bad_generation"
    assert dialog._marks[str(paths[0].resolve())] == "ok"  # соседей клик не трогает
    assert dialog._marks[str(paths[2].resolve())] == "ok"
    dialog.reject()


def test_clicking_the_same_mark_again_unmarks_the_picture(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({str(paths[0].resolve()): "bad_generation"})
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(str(paths[0].resolve()), "unchecked")]
    assert dialog._marks[str(paths[0].resolve())] == "unchecked"
    dialog.reject()


def test_exclude_button_touches_only_the_current_picture(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.saved_membership = membership_for(paths, ["Мини"])
    dialog._show_quality_review()
    saved = []
    dialog.membership_saved.connect(saved.append)
    dialog.quality_list.setCurrentRow(0)
    dialog.quality_exclude_button.click()
    key0, key1, key2 = keys(paths)
    assert all(not link["included"] for link in saved[-1][key0]["memberships"])
    assert all(link["included"] for link in saved[-1][key1]["memberships"])
    assert all(link["included"] for link in saved[-1][key2]["memberships"])
    dialog.reject()


def test_rebuild_keeps_the_current_picture(app, tmp_path):
    """Урок T-QUAL-5: пересборка списка не должна ронять текущую картинку на первую."""
    dialog, paths = quality_dialog(tmp_path)
    dialog.quality_list.setCurrentRow(1)
    dialog._refresh_quality_page()
    assert dialog._current_quality_key() == str(paths[1].resolve())
    dialog.reject()


def select_rows(dialog, *rows):
    """Программный аналог кликов владельца: первый ряд как обычный клик, остальные как CTRL."""
    lw = dialog.quality_list
    lw.setCurrentRow(rows[0], QItemSelectionModel.SelectionFlag.ClearAndSelect)
    for row in rows[1:]:
        lw.item(row).setSelected(True)


def shift_rows(dialog, first, last):
    """Программный аналог SHIFT-кликов: группа между первой и последней картинкой."""
    lw = dialog.quality_list
    group = QItemSelection()
    group.select(lw.model().index(first, 0), lw.model().index(last, 0))
    lw.selectionModel().select(group, QItemSelectionModel.SelectionFlag.ClearAndSelect)


def test_grid_uses_extended_selection(app, tmp_path):
    """Негативный контроль: откат к SingleSelection ломает всю группу мультивыделения."""
    dialog, _ = quality_dialog(tmp_path)
    assert dialog.quality_list.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    dialog.reject()


def test_ctrl_click_group_marks_all_three(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "ok" for key in keys(paths)})
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    select_rows(dialog, 0, 1, 2)
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(key, "bad_generation") for key in keys(paths)]
    assert all(dialog._marks[key] == "bad_generation" for key in keys(paths))
    dialog.reject()


def test_shift_group_between_pictures_marks_all(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "ok" for key in keys(paths)})
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    shift_rows(dialog, 0, 2)
    assert len(dialog.quality_list.selectedItems()) == 3
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(key, "bad_generation") for key in keys(paths)]
    dialog.reject()


def test_ok_mark_applies_to_two_selected(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    marks = {key: "bad_generation" for key in keys(paths)}
    dialog.enable_marks(marks)
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    select_rows(dialog, 1, 2)
    dialog.quality_mark_buttons["ok"].click()
    assert emitted == [(str(paths[1].resolve()), "ok"), (str(paths[2].resolve()), "ok")]
    assert dialog._marks[str(paths[1].resolve())] == "ok"
    assert dialog._marks[str(paths[2].resolve())] == "ok"
    assert dialog._marks[str(paths[0].resolve())] == "bad_generation"  # невыделенная не тронута
    dialog.reject()


def test_group_mark_unmarks_when_every_selected_carries_it(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "bad_generation" for key in keys(paths)})
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    select_rows(dialog, 0, 1)
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(key, "unchecked") for key in keys(paths)[:2]]
    assert dialog._marks[str(paths[2].resolve())] == "bad_generation"  # невыделенная осталась
    dialog.reject()


def test_group_mark_skips_pictures_without_marks_and_says_so(app, tmp_path):
    """Картинки без сопоставления с позицией (нет записи пометки) пропускаются с плашкой."""
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "ok" for key in keys(paths)[:2]})  # третья — «из папки», без пометки
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    select_rows(dialog, 0, 1, 2)
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(key, "bad_generation") for key in keys(paths)[:2]]
    assert str(paths[2].resolve()) not in dialog._marks  # её пометить нельзя — нет записи
    assert not dialog.quality_drop_notice.isHidden()
    assert "Пропущено: 1" in dialog.quality_drop_notice.text()
    assert "Помечено картинок: 2" in dialog.quality_drop_notice.text()
    dialog.reject()


def test_exclude_two_selected_pictures_and_bring_them_back(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.saved_membership = membership_for(paths, ["Мини"])
    dialog._show_quality_review()
    saved = []
    dialog.membership_saved.connect(saved.append)
    select_rows(dialog, 0, 1)
    dialog.quality_exclude_button.click()
    key0, key1, key2 = keys(paths)
    assert all(not link["included"] for link in saved[-1][key0]["memberships"])
    assert all(not link["included"] for link in saved[-1][key1]["memberships"])
    assert all(link["included"] for link in saved[-1][key2]["memberships"])
    assert "Исключены из наборов: 2" in dialog.status.text()
    assert dialog.quality_drop_notice.isHidden()  # пропущенных нет — плашка не нужна
    # вся выделенная группа вне наборов → та же кнопка возвращает всех
    dialog.quality_exclude_button.click()
    assert all(link["included"] for link in saved[-1][key0]["memberships"])
    assert all(link["included"] for link in saved[-1][key1]["memberships"])
    assert "Возвращены в наборы: 2" in dialog.status.text()
    dialog.reject()


def test_exclude_skips_selected_pictures_without_sets(app, tmp_path):
    """Картинка только для проверки (ещё не «Ок», не в наборах) пропускается, остальные работают."""
    from studio_alpha_qc import AlphaQcReport
    paths = [png(tmp_path / f"gosling_{index + 1:02d}_ready.png") for index in range(3)]
    reports = [AlphaQcReport(str(path.resolve()), "ok", (), width=8, height=8) for path in paths]
    # третья картинка известна только проверке PNG: в наборах она ещё не участвует
    dialog = SetExportDialog(paths[:2], quality_reports=reports, review_paths=paths)
    dialog._show_quality_review()
    assert dialog.quality_list.count() == 3
    saved = []
    dialog.membership_saved.connect(saved.append)
    select_rows(dialog, 0, 1, 2)
    dialog.quality_exclude_button.click()
    key0, key1, key2 = keys(paths)
    assert all(not link["included"] for link in saved[-1][key0]["memberships"])
    assert all(not link["included"] for link in saved[-1][key1]["memberships"])
    assert key2 not in saved[-1]
    assert not dialog.quality_drop_notice.isHidden()
    assert "Пропущено: 1" in dialog.quality_drop_notice.text()
    dialog.reject()


def test_selection_survives_quality_page_rebuild(app, tmp_path):
    """Пересборка сетки (автопроверка, метка) не сбрасывает CTRL/SHIFT-выделение (урок T-QUAL-5)."""
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "ok" for key in keys(paths)})
    select_rows(dialog, 0, 1, 2)
    dialog._refresh_quality_page()
    selected = [dialog.quality_list.row(item) for item in dialog.quality_list.selectedItems()]
    assert selected == [0, 1, 2]
    assert dialog._current_quality_key() == str(paths[0].resolve())  # текущая на месте
    # и метки по-прежнему применяются ко всей выжившей группе
    emitted = []
    dialog.mark_requested.connect(lambda path, mark: emitted.append((path, mark)))
    dialog.quality_mark_buttons["bad_generation"].click()
    assert emitted == [(key, "bad_generation") for key in keys(paths)]
    dialog.reject()


def test_regenerate_and_cutout_emit_for_every_selected_picture(app, tmp_path):
    dialog, paths = quality_dialog(tmp_path)
    dialog.enable_marks({key: "bad_generation" for key in keys(paths)})
    regenerated, cutouts = [], []
    dialog.regenerate_requested.connect(regenerated.append)
    dialog.cutout_requested.connect(cutouts.append)
    select_rows(dialog, 1, 2)
    dialog.quality_regenerate_button.click()
    assert regenerated == [str(paths[1].resolve()), str(paths[2].resolve())]
    dialog.enable_marks({key: "bad_cutout" for key in keys(paths)})
    select_rows(dialog, 0, 2)
    dialog.quality_cutout_button.click()
    assert cutouts == [str(paths[0].resolve()), str(paths[2].resolve())]
    dialog.reject()
