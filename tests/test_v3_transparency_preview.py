import unittest

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


if __name__ == "__main__":
    unittest.main()
