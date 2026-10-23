"""Transparency window panels «Файлы» / «Инструменты» and zoom on the picture
(approved mockups docs/ui/3.2/photoshop-panels/, 2026-10-23)."""
import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication

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
    assert names == ["Файлы", "Инструменты", "Сбросить расположение"]
    files.hide()
    page.panel_host.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, tools)
    page.reset_panels()
    app.processEvents()
    assert files.isVisible() and tools.isVisible()
    assert page.panel_host.dockWidgetArea(tools) == Qt.DockWidgetArea.RightDockWidgetArea


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


def test_zoom_bar_on_the_picture(page, app):
    assert page.zoom_bar.parentWidget() is page.canvas.parentWidget()
    assert not any(button.isVisible() for button in page.zoom_buttons.values())
    page.zoom_buttons[150].click()
    assert page.zoom_menu_button.text() == "150 % ▾"
    menu_texts = [action.text() for action in page.zoom_menu_button.menu().actions()]
    assert menu_texts == ["По размеру", "50 %", "100 %", "150 %", "200 %", "300 %"]
    page.zoom_menu_button.menu().actions()[0].trigger()
    app.processEvents()
    assert page.zoom_buttons["fit"].isChecked() and page.zoom_menu_button.text().endswith(" % ▾")
