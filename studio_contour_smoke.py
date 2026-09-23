"""Offline native/packaged check of Bezier editing and saved transparency."""
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PIL import Image
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog

from studio_contour_editor import ContourEditorDialog


def check_contour_editing(evidence_dir=None):
    with TemporaryDirectory(prefix='vibix-curve-smoke-') as temporary:
        root = Path(temporary)
        source, output = root / 'original.png', root / 'curved.png'
        rgba = np.zeros((80, 100, 4), dtype=np.uint8)
        rgba[..., :3] = (31, 99, 180)
        rgba[16:65, 20:76, 3] = 255
        rgba[33:43, 39:51, 3] = 0
        Image.fromarray(rgba).save(source)
        original = source.read_bytes()
        dialog = ContourEditorDialog(source)
        try:
            dialog.show()
            app = QApplication.instance()
            app.processEvents()
            canvas = dialog.canvas
            canvas.auto_contour()
            app.processEvents()
            before = canvas.alpha.copy()
            point = canvas._to_screen(canvas.nodes[0].point)
            target = QPointF(point.x() + 18, point.y() + 14).toPoint()
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, point.toPoint())
            QTest.mouseMove(canvas, target)
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, target)
            app.processEvents()
            edited = canvas.alpha.copy()
            if np.array_equal(before, edited) or edited[38, 45] != 0:
                return False
            QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
            if not np.array_equal(canvas.alpha, before):
                return False
            QTest.keyClick(canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
            if not np.array_equal(canvas.alpha, edited):
                return False
            original_picker = QFileDialog.getSaveFileName
            try:
                QFileDialog.getSaveFileName = staticmethod(lambda *args: (str(output), 'PNG'))
                dialog.save_button.click()
            finally:
                QFileDialog.getSaveFileName = original_picker
            with Image.open(output) as saved:
                result = np.asarray(saved.convert('RGBA'))
            valid = (np.array_equal(result[..., 3], edited)
                     and np.array_equal(result[..., :3], rgba[..., :3])
                     and source.read_bytes() == original)
            if evidence_dir and valid:
                evidence = Path(evidence_dir)
                evidence.mkdir(parents=True, exist_ok=True)
                Image.fromarray(result).save(evidence / 'contour-edited-alpha.png')
                dialog.grab().save(str(evidence / 'contour-editor.png'))
            return valid
        finally:
            dialog.close()
