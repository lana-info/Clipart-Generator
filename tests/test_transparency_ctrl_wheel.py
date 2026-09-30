import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import Image
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtWidgets import QApplication
import pytest

from v3_transparency_preview import ClipartTransparencyEditorPage


@pytest.fixture
def page(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path / 'test.png'
    Image.new('RGBA', (800, 800), (70, 90, 110, 170)).save(source)
    editor = ClipartTransparencyEditorPage()
    editor.resize(1120, 780)
    editor.set_files([source])
    editor.show()
    app.processEvents()
    yield editor, app
    editor.close()
    editor.deleteLater()
    app.processEvents()


def wheel(page, app, delta, *, ctrl=True, pixel_delta=0):
    viewport = page.canvas.viewport()
    pos = viewport.rect().center()
    event = QWheelEvent(QPointF(pos), QPointF(viewport.mapToGlobal(pos)),
        QPoint(0, pixel_delta), QPoint(0, delta), Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(viewport, event)
    app.processEvents()


@pytest.mark.parametrize('tool', ['brush', 'pen'])
def test_ctrl_wheel_zooms_both_directions_without_changing_mask(page, tool):
    editor, app = page
    editor._set_tool(tool)
    editor._set_zoom(100)
    before = editor.document.mask.tobytes()
    wheel(editor, app, 120)
    assert editor.canvas.zoom_percent == 125
    wheel(editor, app, -120)
    assert editor.canvas.zoom_percent == 100
    assert editor.zoom_buttons[100].isChecked()
    assert editor.document.mask.tobytes() == before
    assert not editor.document.can_undo


def test_plain_wheel_scrolls_without_zooming(page):
    editor, app = page
    editor._set_zoom(300)
    scrollbar = editor.canvas.verticalScrollBar()
    scrollbar.setValue(scrollbar.maximum() // 2)
    before = scrollbar.value()
    wheel(editor, app, -120, ctrl=False)
    assert scrollbar.value() > before
    assert editor.canvas.zoom_percent == 300


def test_ctrl_wheel_handles_limits_partial_detents_and_fit(page):
    editor, app = page
    editor._set_zoom(100)
    wheel(editor, app, 60)
    assert editor.canvas.zoom_percent == 100
    wheel(editor, app, 60)
    assert editor.canvas.zoom_percent == 125
    wheel(editor, app, -240)
    assert editor.canvas.zoom_percent == 80
    editor._set_zoom(1600)
    wheel(editor, app, 120)
    assert editor.canvas.zoom_percent == 1600
    editor._set_zoom(10)
    wheel(editor, app, -120)
    assert editor.canvas.zoom_percent == 10
    editor._set_zoom('fit')
    before = editor.canvas.transform().m11()
    wheel(editor, app, 120)
    assert editor.canvas.transform().m11() > before
    wheel(editor, app, 0)
    assert editor.canvas.zoom_percent is not None


def test_pixel_wheel_and_direction_change_do_not_leave_stale_steps(page):
    editor, app = page
    editor._set_zoom(100)
    wheel(editor, app, 60)
    wheel(editor, app, -120)
    assert editor.canvas.zoom_percent == 80
    wheel(editor, app, 0, pixel_delta=5)
    assert editor.canvas.zoom_percent == 100
    wheel(editor, app, 0, pixel_delta=-5)
    assert editor.canvas.zoom_percent == 80
    wheel(editor, app, 0)
    assert editor.canvas.zoom_percent == 80
