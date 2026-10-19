"""Real canvas interactions: no modal, shared alpha, keyboard and persisted output."""
import tempfile
from io import BytesIO
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

    def test_one_pixel_real_click_at_different_zooms_undo_redo_and_saved_rgb(self):
        original = self.source.read_bytes()
        for zoom in (50, 100, 300):
            for action, initial, target in (("remove", 255, 0), ("add", 0, 255)):
                with self.subTest(zoom=zoom, action=action):
                    self.page.document.mask = Image.new("L", (128, 128), initial)
                    self.canvas.refresh_image()
                    self.page._set_zoom(zoom)
                    self.page._set_action(action)
                    QTest.mouseClick(self.page.diameter_buttons[1], Qt.MouseButton.LeftButton)
                    self.app.processEvents()
                    pos = self.canvas.mapFromScene(QPointF(35.5, 35.5))
                    point = self.canvas._image_point(pos)
                    self.assertIsNotNone(point)
                    before = np.array(self.page.document.mask)
                    QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=pos)
                    after = np.array(self.page.document.mask)
                    self.assertEqual(np.count_nonzero(before != after), 1)
                    self.assertEqual(after[point[1], point[0]], target)
                    self.page.undo()
                    np.testing.assert_array_equal(np.array(self.page.document.mask), before)
                    self.page.redo()
                    np.testing.assert_array_equal(np.array(self.page.document.mask), after)
        self.assertEqual(self.source.read_bytes(), original)
        output, _ = self.page.save_current()
        with Image.open(output) as saved, Image.open(BytesIO(original)) as source:
            np.testing.assert_array_equal(np.array(saved)[..., :3], np.array(source)[..., :3])
            np.testing.assert_array_equal(np.array(saved)[..., 3], after)

    def test_three_pixel_brush_preserves_three_pixel_footprint(self):
        self.page.document.mask = Image.new("L", (128, 128), 255)
        self.canvas.refresh_image()
        self.page._set_zoom(300)
        QTest.mouseClick(self.page.brush_style_buttons[100], Qt.MouseButton.LeftButton)
        self.assertEqual(self.canvas.brush_hardness, 100)
        QTest.mouseClick(self.page.diameter_buttons[3], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        pos = self.canvas.mapFromScene(QPointF(35.5, 35.5))
        point = self.canvas._image_point(pos)
        QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        ys, xs = np.where(np.array(self.page.document.mask) != 255)
        self.assertEqual((xs.min(), ys.min(), xs.max(), ys.max()),
                         (point[0]-1, point[1]-1, point[0]+1, point[1]+1))

    def test_drag_stroke_is_smoothed_and_reaches_last_pointer_position(self):
        self.page.document.mask = Image.new("L", (128, 128), 255)
        self.canvas.refresh_image()
        self.page._set_zoom(300)
        self.page.brush_action_buttons["remove"].click() if hasattr(self.page, "brush_action_buttons") else None
        QTest.mouseClick(self.page.brush_style_buttons[100], Qt.MouseButton.LeftButton)
        QTest.mouseClick(self.page.diameter_buttons[3], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        start = self.canvas.mapFromScene(QPointF(30.5, 30.5))
        end = self.canvas.mapFromScene(QPointF(60.5, 40.5))
        QTest.mousePress(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=start)
        for step in range(1, 9):
            pos = self.canvas.mapFromScene(QPointF(30.5 + 30 * step / 8, 30.5 + 10 * step / 8))
            QTest.mouseMove(self.canvas.viewport(), pos)
            self.app.processEvents()
        QTest.mouseRelease(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=end)
        changed = np.array(self.page.document.mask) != 255
        ys, xs = np.where(changed)
        self.assertTrue(changed.any())
        last = self.canvas._image_point(end)
        self.assertLessEqual(abs(int(xs.max()) - (last[0] + 1)), 2)
        self.assertLessEqual(abs(int(ys.max()) - (last[1] + 1)), 2)

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
        for expected in (32,16,6,3,1,1):
            QTest.keyClick(self.canvas, Qt.Key.Key_Minus)
            self.assertTrue(self.page.diameter_buttons[expected].isChecked())
            self.assertEqual(self.canvas.brush_radius, expected // 2)
        QTest.keyClick(self.canvas, Qt.Key.Key_Equal, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.canvas.zoom_percent, 250)
        self.assertEqual(self.canvas.brush_radius, 0)
        self.assertTrue(self.page.diameter_buttons[1].isChecked())
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

    def manual_rectangle(self):
        self.page.tool_buttons['pen'].click()
        for point in ((75,50), (98,50), (98,80)):
            QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                             pos=self.canvas.mapFromScene(QPointF(*point)))
        QTest.mouseDClick(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                         pos=self.canvas.mapFromScene(QPointF(75,80)))
        self.assertFalse(self.canvas.contour.points)
        self.assertEqual(len(self.canvas.contour.paths[0].nodes), 4)

    def test_manual_double_click_remove_and_mask_undo_redo(self):
        before = np.array(self.page.document.mask)
        source_bytes = self.source.read_bytes()
        self.manual_rectangle()
        np.testing.assert_array_equal(np.array(self.page.document.mask), before)
        self.assertEqual(self.page.apply_contour_button.text(), 'Удалить внутри')
        self.page.apply_contour_button.click()
        self.wait_contour()
        after = np.array(self.page.document.mask)
        self.assertEqual(after[65,85], 0)
        self.assertEqual(after[80,35], before[80,35])
        self.assertEqual(set(np.unique(after)), {0,255})
        self.assertEqual(self.source.read_bytes(), source_bytes)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        np.testing.assert_array_equal(np.array(self.page.document.mask), before)
        QTest.keyClick(self.canvas, Qt.Key.Key_Y, Qt.KeyboardModifier.ControlModifier)
        np.testing.assert_array_equal(np.array(self.page.document.mask), after)

    def test_manual_keep_preserves_inside_and_existing_transparency(self):
        before = np.array(self.page.document.mask)
        self.manual_rectangle()
        self.page.keep_contour_button.click()
        self.wait_contour()
        after = np.array(self.page.document.mask)
        self.assertEqual(after[65,85], before[65,85])
        self.assertEqual(after[80,35], 0)
        self.assertFalse(np.any(after > before))

    def test_manual_point_history_close_history_and_zoom_shortcuts(self):
        self.page.tool_buttons['pen'].click()
        for point in ((75,50), (98,50), (98,80)):
            QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                             pos=self.canvas.mapFromScene(QPointF(*point)))
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.canvas.contour.points), 2)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)
        self.assertEqual(len(self.canvas.contour.points), 3)
        point = self.canvas.mapFromScene(QPointF(98,80))
        QTest.mouseDClick(self.canvas.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertEqual(len(self.canvas.contour.paths[0].nodes), 3)
        QTest.keyClick(self.canvas, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.canvas.contour.points), 3)
        scale = self.canvas.transform().m11()
        QTest.keyClick(self.canvas, Qt.Key.Key_Plus, Qt.KeyboardModifier.ControlModifier)
        self.assertGreater(self.canvas.transform().m11(), scale)
        larger = self.canvas.transform().m11()
        QTest.keyClick(self.page, Qt.Key.Key_Minus, Qt.KeyboardModifier.ControlModifier)
        self.assertLess(self.canvas.transform().m11(), larger)

    def test_manual_save_does_not_choose_destructive_action(self):
        self.manual_rectangle()
        before = np.array(self.page.document.mask)
        self.page._save_clicked()
        self.assertFalse(self.canvas.contour_busy)
        np.testing.assert_array_equal(np.array(self.page.document.mask), before)
        self.assertIn('Сначала выберите', self.page.contour_status.text())
        QTest.keyClick(self.canvas, Qt.Key.Key_Escape)
        self.assertFalse(self.canvas.contour.dirty)
        self.page.undo()
        self.assertTrue(self.canvas.contour.dirty)

    def test_manual_contour_starts_on_opaque_image_and_rejects_open_apply(self):
        image = Image.new('RGBA', (128,128), (30,60,90,255))
        image.save(self.source)
        self.page.set_files([self.source])
        self.page.tool_buttons['pen'].click()
        for point in ((10,10), (90,10)):
            QTest.mouseClick(self.canvas.viewport(), Qt.MouseButton.LeftButton,
                             pos=self.canvas.mapFromScene(QPointF(*point)))
        self.canvas.apply_contour()
        self.assertFalse(self.canvas.contour_busy)
        self.assertEqual(self.page.document.mask.getextrema(), (255,255))
        QTest.keyClick(self.canvas, Qt.Key.Key_Backspace)
        self.assertEqual(len(self.canvas.contour.points), 1)
