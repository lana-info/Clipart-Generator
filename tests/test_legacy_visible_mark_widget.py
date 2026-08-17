import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class VisibleMarkWidgetContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_widget_contract_and_initial_state(self):
        from legacy_visible_mark_widget import VisibleMarkSettingsWidget

        widget = VisibleMarkSettingsWidget("gemini_auto")
        widget.show()
        self.addCleanup(widget.close)
        self.assertEqual(widget.objectName(), "visibleMarkSettingsWidget")
        self.assertEqual(widget.mode_combo.objectName(), "visibleMarkModeCombo")
        self.assertEqual(widget.confirmation_label.objectName(), "visibleMarkConfirmationLabel")
        self.assertEqual(widget.mode_combo.itemData(0), "gemini_auto")
        self.assertEqual(widget.mode_combo.itemData(1), "confirmed_area")
        self.assertFalse(widget.confirmation_label.isVisible())
        widget.set_enabled_state(False)
        self.assertFalse(widget.mode_combo.isEnabled())
        widget.set_enabled_state(True)
        widget.mode_combo.setCurrentIndex(1)
        self.assertTrue(widget.confirmation_label.isVisible())


if __name__ == "__main__":
    unittest.main()
