from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from v3_lazy_loading import InitializationProgressOverlay, InitializationStage
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode, StepId


class V3LazyLoadingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        self.app.processEvents()

    def test_first_selection_installs_only_the_selected_mode(self) -> None:
        view = V3ApplicationView()

        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

        self.assertTrue(hasattr(view.shell, "clipart_flow_controller"))
        self.assertFalse(hasattr(view.shell, "pinterest_flow_controller"))
        self.assertFalse(hasattr(view.shell, "processing_flow_controller"))
        view.close()
        view.deleteLater()

    def test_pages_materialize_on_first_visit_and_are_cached(self) -> None:
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        controller = view.shell.clipart_flow_controller

        self.assertEqual(
            controller.pages.materialized_steps - {StepId.RESULTS},
            {StepId.PROJECT},
        )
        project_page = controller.pages[StepId.PROJECT]

        view.shell.go_next()

        self.assertIn(StepId.PROMPTS, controller.pages.materialized_steps)
        self.assertNotIn(StepId.GENERATION, controller.pages.materialized_steps)
        view.shell.go_back()
        self.assertIs(controller.pages[StepId.PROJECT], project_page)
        view.close()
        view.deleteLater()

    def test_first_mode_switch_installs_target_once_and_reuses_it(self) -> None:
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        clipart_controller = view.shell.clipart_flow_controller

        view.show_mode_switcher()
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        pinterest_controller = view.shell.pinterest_flow_controller

        view.show_mode_switcher()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

        self.assertIs(view.shell.clipart_flow_controller, clipart_controller)
        self.assertIs(view.shell.pinterest_flow_controller, pinterest_controller)
        view.close()
        view.deleteLater()

    def test_initialization_progress_uses_real_completed_stage_percentages(self) -> None:
        overlay = InitializationProgressOverlay()
        self.assertEqual(overlay.focusPolicy(), Qt.FocusPolicy.NoFocus)
        self.assertTrue(
            overlay.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        )
        observed = []
        for stage in (
            InitializationStage("Начинаем", 0, 2),
            InitializationStage("Страница готова", 1, 2),
            InitializationStage("Режим готов", 2, 2),
        ):
            overlay.update_stage(stage)
            observed.append(overlay.value())

        self.assertEqual(observed, [0, 50, 100])
        self.assertEqual(overlay.labelText(), "Режим готов")
        overlay.close()
        overlay.deleteLater()


if __name__ == "__main__":
    unittest.main()
