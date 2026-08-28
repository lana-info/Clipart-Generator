import unittest
import tempfile
from pathlib import Path

from PIL import Image
from PyQt6.QtWidgets import QApplication

from v3_transparency_preview import ClipartTransparencyPreview


class TransparencyPreviewWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_widget_exposes_approved_background_choices(self):
        widget = ClipartTransparencyPreview()

        self.assertEqual(widget.background_combo.count(), 6)
        self.assertEqual(widget.background_combo.currentText(), "Шахматный")
        self.assertTrue(widget.preview.pixmap().isNull())

    def test_widget_renders_image_and_reacts_to_background_change(self):
        widget = ClipartTransparencyPreview()
        widget.resize(420, 320)
        widget.set_image(Image.new("RGBA", (20, 20), (10, 20, 30, 128)))
        first = widget.preview.pixmap().toImage().pixel(0, 0)

        widget.background_combo.setCurrentText("Ярко-розовый")
        second = widget.preview.pixmap().toImage().pixel(0, 0)

        self.assertFalse(widget.preview.pixmap().isNull())
        self.assertNotEqual(first, second)

    def test_brush_changes_mask_and_reset_restores_source_alpha(self):
        widget = ClipartTransparencyPreview()
        widget.set_image(Image.new("RGBA", (20, 20), (10, 20, 30, 255)))
        widget.action_combo.setCurrentText("Стереть область")
        widget.radius_spin.setValue(2)

        widget.apply_stroke((10, 10))

        self.assertEqual(widget._mask.getpixel((10, 10)), 0)
        widget.reset_button.click()
        self.assertEqual(widget._mask.getpixel((10, 10)), 255)

    def test_corrected_png_keeps_rgb_and_can_save_mask_separately(self):
        widget = ClipartTransparencyPreview()
        widget.set_image(Image.new("RGBA", (4, 4), (10, 20, 30, 255)))
        widget.action_combo.setCurrentText("Стереть область")
        widget.radius_spin.setValue(1)
        widget.apply_stroke((2, 2))

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "corrected.png"
            mask = Path(directory) / "corrected-mask.png"
            widget.save_corrected_png(output)
            widget.save_mask(mask)
            with Image.open(output) as image:
                self.assertEqual(image.getpixel((0, 0)), (10, 20, 30, 255))
                self.assertEqual(image.getpixel((2, 2))[-1], 0)
            with Image.open(mask) as saved_mask:
                self.assertEqual(saved_mask.mode, "L")
                self.assertEqual(saved_mask.getpixel((2, 2)), 0)


if __name__ == "__main__":
    unittest.main()
