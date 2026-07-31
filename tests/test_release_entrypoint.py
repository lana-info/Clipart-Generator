import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from main import create_v3_application_window
from v3_components import ModeCard
from v3_mode_selection import MODE_CARD_SPECS, V3ApplicationView


class ReleaseEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_production_entrypoint_is_v3(self):
        window = create_v3_application_window()
        self.assertIsInstance(window, V3ApplicationView)
        self.assertEqual(window.windowTitle(), "Clipart Generator 3.0")
        cards = list(window.mode_selection.mode_cards.values())
        self.assertEqual(set(window.mode_selection.mode_cards), set(MODE_CARD_SPECS))
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(isinstance(card, ModeCard) for card in cards))
        self.assertTrue(all(card.accessibleName() for card in cards))
        window.close()


if __name__ == "__main__":
    unittest.main()
