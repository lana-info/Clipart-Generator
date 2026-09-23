"""Real canvas interactions: no modal, shared alpha, keyboard and persisted output."""
import tempfile
import unittest
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from PyQt6.QtCore import Qt, QPointF, QEvent
from PyQt6.QtGui import QFocusEvent, QKeyEvent, QMouseEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from v3_transparency_preview import ClipartTransparencyEditorPage


class ContourIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'output' / 'cup.png'
        self.source.parent.mkdir()
        image = Image.new('RGBA', (128,128), (30,60,90,0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((15,15,110,110), fill=(30,60,90,255))
        draw.ellipse((45,45,65,65), fill=(30,60,90,0))
        image.save(self.source)
        self.page = ClipartTransparencyEditorPage()
        self.page.resize(1120,780)
        self.page.set_files([self.source])
        self.page.show()
        self.app.processEvents()
        self.addCleanup(self.page.close)
        self.addCleanup(self.page.deleteLater)
        self.canvas = self.page.canvas

    def wait_contour(self):
        deadline = time.monotonic() + 10
        while self.canvas.contour_busy and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertFalse(self.canvas.contour_busy, "Background contour timed out")

    def pen(self):
        self.page.tool_buttons['pen'].click()
        self.page.contour_button.click()
        self.wait_contour()
        self.assertIsNone(QApplication.activeModalWidget())
        self.assertTrue(self.canvas.contour.paths)

    def select_node(self):
        pi = next(i for i,p in enumerate(self.canvas.contour.paths) if p.fill_value == 255)
        node = self.canvas.contour.paths[pi].nodes[0]
        point = self.canvas.mapFromScene(QPointF(*node.point))
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(self.canvas.contour.selected, (pi,0))
        return pi, node

    def test_switch_preserves_canvas_zoom_draft_and_keyboard_diameters(self):
        document = self.page.document
        self.page._set_zoom(200)
        self.pen()
        self.select_node()
        QTest.keyClick(self.canvas, Qt.Key.Key_Right)
        draft = list(self.canvas.contour.paths)
        self.page.tool_buttons['brush'].click()
        self.assertIs(self.page.document, document)
        self.assertEqual(self.canvas.zoom_percent, 200)
        for expected in (32,64,64):
            QTest.keyClick(self.canvas, Qt.Key.Key_Equal)
            self.assertEqual(self.canvas.brush_radius*2, expected)
        for expected in (32,16,10,6,2,2):
            QTest.keyClick(self.canvas, Qt.Key.Key_Minus)
            self.assertEqual(self.canvas.brush_radius*2, expected)
        QTest.keyClick(self.canvas, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.canvas.zoom_percent, 250)
        self.assertEqual(self.canvas.brush_radius*2, 2)
        QTest.keyClick(self.canvas, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.canvas.zoom_percent, 200)
        QApplication.sendEvent(self.canvas, QKeyEvent(QEvent.Type.KeyPress, 0, Qt.KeyboardModifier.NoModifier, 'з'))
        self.assertEqual(self.canvas.tool, 'pen')
        self.assertEqual(self.canvas.contour.paths, draft)

    def test_nodes_toggle_insert_delete_nudge_and_pending_undo(self):
        self.pen()
        pi, node = self.select_node()
        position = self.canvas.mapFromScene(QPointF(*node.point))
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, position)
        self.assertEqual(self.canvas.contour.paths[pi].nodes[0].kind, 'smooth')
        QTest.keyClick(self.canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.canvas.contour.paths[pi].nodes[0].point[0], node.point[0]+10)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.canvas.contour.paths[pi].nodes[0].point, node.point)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.canvas.contour.paths[pi].nodes[0].point[0], node.point[0]+10)
        count = len(self.canvas.contour.paths[pi].nodes)
        QTest.keyClick(self.canvas, Qt.Key.Key_Delete)
        self.assertEqual(len(self.canvas.contour.paths[pi].nodes), count-1)
        path = self.canvas.contour.paths[pi]
        a,b = path.nodes[2], path.nodes[3]
        mid = (np.array(a.point)+3*np.array(a.out_handle or a.point)+3*np.array(b.in_handle or b.point)+np.array(b.point))/8
        QTest.mouseDClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=self.canvas.mapFromScene(QPointF(*mid)))
        self.assertEqual(len(self.canvas.contour.paths[pi].nodes), count)

    def test_apply_shared_history_save_rgb_hole_and_brush_alt(self):
        original = self.source.read_bytes()
        self.pen()
        self.select_node()
        initial = self.page.document.mask.tobytes()
        QTest.keyClick(self.canvas, Qt.Key.Key_Down, Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(self.page.document.mask.tobytes(), initial)
        QTest.keyClick(self.canvas, Qt.Key.Key_Return)
        self.wait_contour()
        applied = self.page.document.mask.tobytes()
        self.assertNotEqual(applied, initial)
        self.assertEqual(self.page.document.mask.getpixel((55,55)), 0)
        self.page.tool_buttons['brush'].click()
        self.page._set_diameter(6)
        position = self.canvas.mapFromScene(QPointF(85,65))
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        brushed = self.page.document.mask.tobytes()
        self.assertNotEqual(brushed, applied)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.page.document.mask.tobytes(), applied)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.page.document.mask.tobytes(), initial)
        self.page.redo(); self.page.redo()
        self.assertEqual(self.page.document.mask.tobytes(), brushed)
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, position)
        self.assertGreater(self.page.document.mask.getpixel((85,65)), Image.frombytes('L',(128,128),brushed).getpixel((85,65)))
        self.assertEqual(self.canvas.brush_action, 'remove')
        self.assertEqual(self.source.read_bytes(), original)
        output, mask = self.page.save_current()
        with Image.open(output) as saved, Image.open(mask) as alpha:
            self.assertEqual(saved.getchannel('A').tobytes(), alpha.tobytes())
            self.assertEqual(saved.convert('RGB').tobytes(), self.page.document.image.convert('RGB').tobytes())

    def test_pending_contour_survives_file_switch_and_saved_implicitly(self):
        self.pen(); self.select_node()
        QTest.keyClick(self.canvas, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
        paths = list(self.canvas.contour.paths)
        second = self.source.with_name('second.png')
        Image.open(self.source).save(second)
        self.page.set_files([self.source, second], selected_index=1)
        self.page.file_list.setCurrentRow(0)
        self.assertEqual(self.canvas.contour.paths, paths)
        self.assertTrue(self.canvas.contour.dirty)
        self.page._save_clicked()
        self.wait_contour()
        self.assertFalse(self.canvas.contour.dirty)

    def test_empty_and_opaque_are_safe_without_modal(self):
        self.page.set_files([])
        self.assertFalse(self.page.contour_button.isEnabled())
        self.assertFalse(self.page.tool_buttons['pen'].isEnabled())
        Image.new('RGBA',(24,24),(1,2,3,255)).save(self.source)
        self.page.set_files([self.source])
        self.page._set_tool('pen'); self.page.contour_button.click()
        self.wait_contour()
        self.assertFalse(self.canvas.contour.paths)
        self.assertIn('прозрачным', self.page.contour_status.text())
        self.assertIsNone(QApplication.activeModalWidget())

    def test_drag_handle_rebase_brush_and_export_current_output(self):
        from zipfile import ZipFile
        from studio_set_export import export_clipart_sets
        self.pen()
        pi, node = self.select_node()
        point = self.canvas.mapFromScene(QPointF(*node.point))
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.AltModifier, point)
        node = self.canvas.contour.paths[pi].nodes[0]
        handle = self.canvas.mapFromScene(QPointF(*node.out_handle))
        target = self.canvas.mapFromScene(QPointF(node.out_handle[0]+5, node.out_handle[1]+4))
        QTest.mousePress(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=handle)
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(target), QPointF(target), Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(self.canvas.viewport(), move)
        QTest.mouseRelease(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=target)
        self.assertNotEqual(self.canvas.contour.paths[pi].nodes[0].out_handle, node.out_handle)
        self.page.tool_buttons['brush'].click()
        self.page._set_diameter(6)
        spot = self.canvas.mapFromScene(QPointF(85,65))
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=spot)
        alpha = self.page.document.mask.getpixel((85,65))
        self.page._save_clicked()
        self.wait_contour()
        self.assertEqual(self.page.document.mask.getpixel((85,65)), alpha)
        archives = export_clipart_sets([{'title':'Cup', 'images':[self.page.current_path]}], Path(self.tmp.name))
        with ZipFile(archives[0]) as archive:
            png = next(name for name in archive.namelist() if name.endswith('.png'))
            self.assertEqual(archive.read(png), self.source.read_bytes())

    def test_focus_loss_finishes_stroke_and_releases_pan(self):
        position = self.canvas.mapFromScene(QPointF(85,65))
        QTest.mousePress(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=position)
        self.assertTrue(self.canvas._painting)
        QApplication.sendEvent(self.canvas, QFocusEvent(QEvent.Type.FocusOut))
        self.assertFalse(self.canvas._painting)
        self.assertTrue(self.page.document.can_undo)
        self.canvas.set_space_pan_active(True)
        QApplication.sendEvent(self.canvas, QFocusEvent(QEvent.Type.FocusOut))
        self.assertFalse(self.canvas._space_pressed)
        self.assertFalse(self.canvas._panning)
