"""Field and mode contracts through real Qt widgets, using only the local host."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, QPoint, QTimer
from PyQt6.QtWidgets import QLineEdit, QApplication, QComboBox, QDialog, QLabel, QPushButton

from prompt_composer.catalog import catalogue
from prompt_composer.ui import FIELDS, PromptComposerPage
from studio_prompt_composer_host import PromptComposerHost


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def composer(tmp_path, app):
    host = PromptComposerHost(tmp_path / "library", settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    page.resize(1100, 850)
    page.show()
    app.processEvents()
    yield page
    page.hide()
    host.close()
    page.deleteLater()
    app.processEvents()


def test_catalogue_choices_have_translations_and_stable_unique_ids():
    options = catalogue()["options"]
    for key in ("location", "surface", "aspect", "duration", "action"):
        assert len(options[key]) >= 2
        assert len({o["id"] for o in options[key]}) == len(options[key])
        assert all(o["ru"].strip() and o["en"].strip() for o in options[key])
    assert len(options["action"]) >= 18
    for option in options["action"]:
        assert not any(word in option["ru"].lower() for word in ("чашк", "кот", "рука", "флакон", "ткань", "лепесток", "кисть", "ложка"))
    assert FIELDS["aspect"] == "Формат кадра"


def test_initial_mode_controls_centered_without_repeated_heading(composer, app):
    page = composer
    for mode in ("image", "reels"):
        page._set_mode(mode)
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        image = page.findChild(QPushButton, "mode_image")
        reels = page.findChild(QPushButton, "mode_reels")
        assert page.findChild(QLabel, "selectedModeHeading") is None
        assert image.width() == reels.width() == 190
        assert image.isChecked() == (mode == "image")
        assert reels.isChecked() == (mode == "reels")
        center = (image.mapTo(page, QPoint()).x() + reels.mapTo(page, QPoint()).x() + reels.width()) / 2
        assert abs(center - page.width() / 2) <= 2
        assert "QPushButton:checked { background:#20ae9e" in image.styleSheet()
        active = image if mode == "image" else reels
        active.click()
        assert active.isChecked()
    page.findChild(QPushButton, "mode_image").click()
    assert page.draft["mode"] == "image"


@pytest.mark.parametrize("mode", ["image", "reels"])
def test_mode_chosen_at_start_controls_scene_fields_without_duplicate_switches(composer, app, mode):
    composer._set_mode(mode)
    for step in (1, 2, 3):
        composer.goto_step(step)
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        assert composer.findChild(QPushButton, "mode_image") is None
        assert composer.findChild(QPushButton, "mode_reels") is None
        assert composer.findChild(QLabel, "selectedModeHeading") is None
    expected = {"action", "camera", "duration", "aspect", "exclusions"} if mode == "reels" else {"shot", "angle", "aspect", "exclusions"}
    actual = {c.objectName().removeprefix("field_") for c in composer.findChildren(QComboBox) if c.objectName().startswith("field_")}
    assert actual == expected
    assert composer.draft["mode"] == mode


@pytest.mark.parametrize("step", [1, 2, 3])
def test_forms_no_repeated_summary_or_cancel(composer, app, step):
    composer.goto_step(step)
    app.processEvents()
    cancel = composer.findChild(QPushButton, "cancelAiButton")
    assert cancel is None or not cancel.isVisible()
    labels = [label.text() for label in composer.findChildren(QLabel)]
    assert "Ваша сцена" not in labels
    assert not any("Здесь создаётся только текст" in text for text in labels)
    if step == 2:
        button = composer.findChild(QPushButton, "randomizeButton")
        location = composer.findChild(QComboBox, "field_location")
        assert button.width() == 320 and button.height() >= 40
        assert button.geometry().bottom() < location.geometry().top()
        assert "background:#20ae9e" in button.styleSheet()


@pytest.mark.parametrize("mode,scene_keys", [("image", ("shot", "angle", "aspect")), ("reels", ("action", "camera", "duration", "aspect"))])
def test_randomize_only_visible_mode_fields_uses_choice_and_preserves_locks(composer, mode, scene_keys):
    page = composer
    page._set_mode(mode)
    options = page._catalog["options"]
    page.draft["fields"].update({key: {lang: choices[0][lang] for lang in ("ru", "en")} for key, choices in options.items()})
    page.draft["fields"]["exclusions"] = {"ru": "без текста", "en": "no text"}
    page.draft["locks"] = ["lighting", "aspect"]
    page.draft["selection_seed"] = 37
    before = deepcopy(page.draft)
    expected = set(("location", "surface", "style", "lighting", "time") + scene_keys) - {"lighting", "aspect"}
    with patch("prompt_composer.ui.random.choice", side_effect=lambda choices: choices[-1]) as choose:
        page.randomize_unlocked()
    changed = {key for key, pair in page.draft["fields"].items() if pair != before["fields"].get(key)}
    assert changed == expected
    assert choose.call_count == len(expected)
    for key in expected:
        assert page.draft["fields"][key] != before["fields"][key]
    assert page.draft["locks"] == before["locks"]
    assert page.draft["mode"] == mode
    assert page.draft["selection_seed"] == 0


def test_randomize_manual_guard_can_decline_without_changes(composer):
    composer.draft["manual_ru"] = "ручной промпт"
    before = deepcopy(composer.draft)
    with patch.object(composer, "_guard_manual_rebuild", return_value=False), patch("prompt_composer.ui.random.choice") as choose:
        composer.randomize_unlocked()
    assert composer.draft == before
    choose.assert_not_called()


def test_empty_placeholder_and_single_custom_value_survive_render(composer, app):
    page = composer
    page.goto_step(2)
    combo = page.findChild(QComboBox, "field_location")
    assert combo.currentIndex() == -1 and combo.currentText() == ""
    assert combo.lineEdit().placeholderText() == "Выберите или введите своё…"
    combo.setCurrentIndex(1)
    assert page.draft["fields"]["location"] == {k: combo.currentData()[k] for k in ("ru", "en")}
    def fill_dialog():
        dialog = app.activeModalWidget()
        assert isinstance(dialog, QDialog)
        dialog.findChild(QLineEdit, "customFieldText").setText("свой двор")
        dialog.accept()
    QTimer.singleShot(0, fill_dialog)
    page.findChild(QPushButton, "custom_location").click()
    combo = page.findChild(QComboBox, "field_location")
    assert combo.currentText() == "свой двор"
    assert page.draft["fields"]["location"] == {"ru": "свой двор", "en": ""}
    combo.lineEdit().setText("новое место")
    combo.lineEdit().editingFinished.emit()
    assert page.draft["fields"]["location"] == {"ru": "новое место", "en": ""}


def test_cancel_initial_mode_change_restores_checked_button(composer,app):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox
    page = composer
    page.draft['manual_en'] = 'My literal manual prompt'
    before = deepcopy(page.draft)
    def reject_guard():
        dialog = app.activeModalWidget()
        assert isinstance(dialog,QMessageBox)
        dialog.reject()
    QTimer.singleShot(0,reject_guard)
    QTest.mouseClick(page.findChild(QPushButton,'mode_reels'),Qt.MouseButton.LeftButton)
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert page.draft == before
    assert page.findChild(QPushButton,'mode_image').isChecked()
    assert not page.findChild(QPushButton,'mode_reels').isChecked()
    assert page.findChild(QLabel,'selectedModeHeading') is None
