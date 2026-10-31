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
from PyQt6.QtWidgets import QApplication

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
