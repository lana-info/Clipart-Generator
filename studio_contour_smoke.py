"""Offline native/packaged check of the shared transparency canvas."""
from pathlib import Path
import time
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from v3_transparency_preview import ClipartTransparencyEditorPage


def _wait_for_contour(canvas):
    deadline = time.monotonic() + 30
    while canvas.contour_busy and time.monotonic() < deadline:
        QTest.qWait(10)
    if canvas.contour_busy:
        raise TimeoutError("Contour worker timed out")


def _check_shared_edge_actions(page, source, evidence_dir):
    """Exercise the shipped edge helper, busy indication, history and PNG save."""
    y, x = np.indices((80, 100))
    alpha = (np.hypot(x-49.3, y-39.8) <= 26.6).astype(np.uint8)*255
    rgba = np.zeros((80, 100, 4), dtype=np.uint8)
    rgba[..., :3] = (31, 99, 180)
    rgba[..., 3] = alpha
    Image.fromarray(rgba).save(source)
    original = source.read_bytes()
    page.set_files([source])
    page.tool_buttons['brush'].click()
    if page.diameter_value.text() != f"{page.brush_diameter} px":
        return False
    page.smooth_edge_button.click()
    if not page.canvas.contour_busy or not page.busy_bar.isVisible():
        return False
    _wait_for_contour(page.canvas)
    smoothed = np.array(page.document.mask)
    if (np.array_equal(smoothed, alpha)
            or not np.array_equal(smoothed >= 128, alpha >= 128)
            or source.read_bytes() != original):
        return False
    page.undo_button.click()
    if not np.array_equal(np.array(page.document.mask), alpha):
        return False
    page.redo_button.click()
    if not np.array_equal(np.array(page.document.mask), smoothed):
        return False
    if evidence_dir:
        page.tools_scroll.ensureWidgetVisible(page.smooth_edge_button)
        QApplication.instance().processEvents()
        page.grab().save(str(Path(evidence_dir) / 'edge-editor.png'))
    page.sharpen_edge_button.click()
    _wait_for_contour(page.canvas)
    if not np.array_equal(np.array(page.document.mask), alpha):
        return False
    page.undo_button.click()
    output, mask = page.save_current()
    with Image.open(output) as saved, Image.open(mask) as saved_mask:
        result = np.array(saved.convert('RGBA'))
        return (np.array_equal(result[..., :3], rgba[..., :3])
                and np.array_equal(result[..., 3], smoothed)
                and np.array_equal(np.array(saved_mask), smoothed)
                and not page.busy_bar.isVisible())


def check_contour_editing(evidence_dir=None):
    with TemporaryDirectory(prefix="vibix-curve-smoke-") as temporary:
        source = Path(temporary) / "output" / "original.png"
        source.parent.mkdir()
        rgba = np.zeros((80, 100, 4), dtype=np.uint8)
        rgba[..., :3] = (31, 99, 180)
        rgba[16:65, 20:76, 3] = 255
        rgba[33:43, 39:51, 3] = 0
        Image.fromarray(rgba).save(source)
        original = source.read_bytes()
        page = ClipartTransparencyEditorPage()
        try:
            page.resize(1120, 780)
            page.set_files([source])
            page.show()
            app = QApplication.instance()
            app.processEvents()
            canvas = page.canvas
            page.tool_buttons["pen"].click()
            page.contour_button.click()
            _wait_for_contour(canvas)
            pi = next(i for i, path in enumerate(canvas.contour.paths) if path.fill_value == 255)
            point = canvas.mapFromScene(QPointF(*canvas.contour.paths[pi].nodes[0].point))
            QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, point)
            QTest.keyClick(canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
            QTest.keyClick(canvas, Qt.Key.Key_Return)
            _wait_for_contour(canvas)
            edited = np.array(page.document.mask)
            if np.array_equal(rgba[..., 3], edited) or edited[38, 45] != 0:
                return False
            QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            if not np.array_equal(np.array(page.document.mask), rgba[..., 3]):
                return False
            QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            if not np.array_equal(np.array(page.document.mask), edited):
                return False
            page.tool_buttons["brush"].click()
            QTest.keyClick(canvas, Qt.Key.Key_Minus)
            if (canvas.brush_radius != 7 or page.diameter_value.text() != "15 px"
                    or source.read_bytes() != original):
                return False
            output, mask = page.save_current()
            with Image.open(output) as saved, Image.open(mask) as saved_mask:
                result = np.array(saved.convert("RGBA"))
                valid = (np.array_equal(result[..., 3], edited)
                         and np.array_equal(np.array(saved_mask), edited)
                         and np.array_equal(result[..., :3], rgba[..., :3]))
            if evidence_dir and valid:
                evidence = Path(evidence_dir)
                evidence.mkdir(parents=True, exist_ok=True)
                Image.fromarray(result).save(evidence / "contour-edited-alpha.png")
                page.tool_buttons["pen"].click()
                page.contour_button.click()
                _wait_for_contour(canvas)
                app.processEvents()
                page.grab().save(str(evidence / "contour-editor.png"))
            return valid and _check_shared_edge_actions(page, source.with_name('edge.png'), evidence_dir)
        finally:
            page.close()
            page.deleteLater()
