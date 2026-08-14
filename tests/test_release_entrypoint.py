import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from main import create_v3_application_window
from v3_components import ModeCard
from v3_mode_selection import MODE_CARD_SPECS, V3ApplicationView
from v3_project_state import ProjectMode


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
        window.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()
        gate = window._license_gate
        self.assertIsNotNone(gate)
        controllers = (
            window.shell.clipart_flow_controller,
            window.shell.pinterest_flow_controller,
            window.shell.processing_flow_controller,
        )
        self.assertTrue(
            all(
                getattr(controller.authorization_provider, "__self__", None) is gate
                for controller in controllers
            )
        )
        window.close()


if __name__ == "__main__":
    unittest.main()
