import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from v3_components import V3StepLabel


class V3StepLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_text_contract_keeps_marker_number_and_title(self):
        label = V3StepLabel("✓ 2. Визуальное направление")
        self.assertEqual(label.text(), "✓ 2. Визуальное направление")

    def test_long_title_wraps_and_grows_the_row(self):
        label = V3StepLabel("○ 2. Визуальное направление набора с очень длинным названием")
        short = V3StepLabel("○ 1. Идея")
        self.assertTrue(label.hasHeightForWidth())
        self.assertGreater(label.heightForWidth(200), short.heightForWidth(200))
        self.assertGreaterEqual(short.heightForWidth(200), V3StepLabel._BADGE + 2 * V3StepLabel._PAD_Y)

    def test_every_state_paints_without_error(self):
        for marker in "✓●○✕":
            label = V3StepLabel(f"{marker} 3. Референсы")
            label.resize(220, label.heightForWidth(220))
            pixmap = QPixmap(label.size())
            label.render(pixmap)
            self.assertFalse(pixmap.isNull())

    def test_text_without_marker_falls_back_to_plain_label(self):
        label = V3StepLabel("Без маркера")
        self.assertFalse(label.hasHeightForWidth())


if __name__ == "__main__":
    unittest.main()
