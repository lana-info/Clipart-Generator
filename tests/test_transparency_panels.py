"""Transparency window panels «Файлы» / «Инструменты» and zoom on the picture
(approved mockups docs/ui/3.2/photoshop-panels/, 2026-10-23)."""
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication, QLabel

from v3_transparency_preview import ClipartTransparencyEditorPage


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path, monkeypatch):
    monkeypatch.setattr(ClipartTransparencyEditorPage, "PANEL_SETTINGS", ("Vibix-test", f"panels-{os.getpid()}"))
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()
    source = tmp_path / "a.png"
    Image.new("RGBA", (64, 64), (200, 120, 90, 255)).save(source)
    result = ClipartTransparencyEditorPage()
    result.resize(1120, 780)
    result.set_files([source])
    result.show()
    app.processEvents()
    yield result
    result.close()
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()


def test_panels_menu_hides_and_resets(page, app):
    files, tools = page.panel_docks["files"], page.panel_docks["tools"]
    assert files.widget() is page.files_frame and tools.widget() is page.tools_scroll
    names = [action.text() for action in page.panels_button.menu().actions() if action.text()]
    assert names == ["Файлы", "Инструменты", "Размеры", "Превью", "Сбросить расположение"]
    assert not files.isVisible() and tools.isVisible()  # the file list is out of the way until asked for
    files.show()
    page.panel_host.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tools)
    page.reset_panels()
    app.processEvents()
    assert not files.isVisible() and tools.isVisible()
    assert page.panel_host.dockWidgetArea(tools) == Qt.DockWidgetArea.RightDockWidgetArea


def test_review_window_keeps_the_file_panel_it_works_through(page, app):
    page.insert_file_filter(QLabel("filter"))
    page.reset_panels()
    app.processEvents()
    assert page.panel_docks["files"].isVisible()


def test_files_are_stepped_by_keys_and_there_is_no_counter_or_arrows(app, tmp_path, monkeypatch):
    monkeypatch.setattr(ClipartTransparencyEditorPage, "PANEL_SETTINGS", ("Vibix-test", f"nav-{os.getpid()}"))
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()
    files = []
    for name in ("a", "b", "c"):
        path = tmp_path / f"{name}.png"
        Image.new("RGBA", (64, 64), (200, 120, 90, 255)).save(path)
        files.append(path)
    window = ClipartTransparencyEditorPage()
    window.resize(1120, 780)
    window.set_files(files)
    window.show()
    app.processEvents()
    # owner 2026-10-27: no «N из M» counter and no ‹ › arrows; PageUp/PageDown and the thumbnails move along the files
    assert not window.file_counter_label.isVisible() and not window.prev_file_button.isVisible()
    assert not window.next_file_button.isVisible()
    window._step_file(1)
    assert window.file_list.currentRow() == 1
    window._step_file(-1)
    window._step_file(-1)
    assert window.file_list.currentRow() == 2  # wraps around
    window.close()
    single = ClipartTransparencyEditorPage()
    single.set_files(files[:1])
    single.show()
    app.processEvents()
    assert not single.prev_file_button.isVisible() and not single.file_counter_label.isVisible()
    single.close()
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()


def test_layout_is_remembered_for_the_next_window(page, app, tmp_path):
    page.panel_docks["files"].hide()
    page.hide()
    second = ClipartTransparencyEditorPage()
    second.set_files([tmp_path / "a.png"])
    second.show()
    app.processEvents()
    assert not second.panel_docks["files"].isVisible() and second.panel_docks["tools"].isVisible()
    second.close()


def test_focus_mode_hides_panels_and_brings_back_only_the_shown_ones(page, app):
    page.panel_docks["files"].hide()
    page.toggle_focus_mode()
    app.processEvents()
    assert not page.panel_docks["tools"].isVisible() and not page.panels_button.isVisible()
    page.toggle_focus_mode()
    app.processEvents()
    assert page.panel_docks["tools"].isVisible() and not page.panel_docks["files"].isVisible()


def test_zoom_bar_is_the_size_panel(page, app):
    assert page.size_frame.isAncestorOf(page.zoom_bar) and page.panel_docks["size"].widget() is page.size_frame
    assert not any(button.isVisible() for button in page.zoom_buttons.values())
    page.zoom_buttons[150].click()
    assert page.zoom_menu_button.text() == "150 % ▾"
    menu_texts = [action.text() for action in page.zoom_menu_button.menu().actions()]
    assert menu_texts == ["По размеру", "50 %", "100 %", "150 %", "200 %", "300 %"]
    page.zoom_menu_button.menu().actions()[0].trigger()
    app.processEvents()
    assert page.zoom_buttons["fit"].isChecked() and page.zoom_menu_button.text().endswith(" % ▾")


def test_thumbnail_strip_is_its_own_panel_independent_of_the_files_panel(app, tmp_path, monkeypatch):
    monkeypatch.setattr(ClipartTransparencyEditorPage, "PANEL_SETTINGS", ("Vibix-test", f"strip-{os.getpid()}"))
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()
    files = []
    for name in ("a", "b", "c"):
        path = tmp_path / f"{name}.png"
        Image.new("RGBA", (64, 64), (200, 120, 90, 255)).save(path)
        files.append(path)
    window = ClipartTransparencyEditorPage()
    window.resize(1120, 780)
    window.set_files(files)
    window.show()
    app.processEvents()
    assert window.file_strip.isVisible() and window.file_strip.count() == 3
    assert not window.file_strip.item(0).icon().isNull()
    window.file_strip.setCurrentRow(2)  # a click on the third thumbnail
    assert window.file_list.currentRow() == 2
    window._step_file(1)
    assert window.file_strip.currentRow() == 0
    window.panel_docks["files"].show()
    app.processEvents()
    assert window.file_strip.isVisible()  # the preview panel does not depend on the file panel
    window.panel_docks["preview"].hide()
    app.processEvents()
    assert not window.file_strip.isVisible() and window.panel_docks["files"].isVisible()
    window.close()
    QSettings(*ClipartTransparencyEditorPage.PANEL_SETTINGS).clear()
