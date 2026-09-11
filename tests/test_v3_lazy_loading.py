from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel

from v3_lazy_loading import (
    InitializationProgressOverlay,
    InitializationStage,
    LazyPageRegistry,
)
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode, StepId
from v3_wizard import AppShell


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

        # Navigation requires a writable folder; do not depend on the machine's
        # saved/default Pictures path when testing lazy page materialization.
        work_dir = tempfile.TemporaryDirectory(prefix="vibix-lazy-pages-")
        self.addCleanup(work_dir.cleanup)
        project_page.work_dir_edit.setText(work_dir.name)

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

    def test_slow_factory_sees_visible_progress_without_processing_input(self) -> None:
        view = V3ApplicationView()
        shell = AppShell()
        view.shell = shell
        shell.initialization_stage.connect(view._show_initialization_stage)
        target = StepId.PROMPTS
        observed = []

        shell.set_step_factory(
            ProjectMode.CLIPART,
            target,
            lambda: (
                observed.append(bool(view._initialization_overlay.isVisible())),
                QLabel("Готово"),
            )[1],
        )

        shell.ensure_step_page(ProjectMode.CLIPART, target)

        self.assertEqual(observed, [True])
        shell.close()
        shell.deleteLater()
        view.close()
        view.deleteLater()

    def test_failed_factory_is_retained_and_can_be_retried(self) -> None:
        shell = AppShell()
        target = StepId.PROMPTS
        calls = []

        def factory():
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                raise RuntimeError("private detail")
            return QLabel("Готово")

        shell.set_step_factory(ProjectMode.CLIPART, target, factory)
        placeholder = shell.ensure_step_page(ProjectMode.CLIPART, target)

        self.assertEqual(calls, [1])
        self.assertFalse(shell.retry_page_button.isHidden())
        self.assertNotIn("private detail", shell.validation_label.text())

        recovered = shell.ensure_step_page(ProjectMode.CLIPART, target)

        self.assertEqual(calls, [1, 2])
        self.assertIsNot(recovered, placeholder)
        self.assertFalse(shell.retry_page_button.isVisible())
        shell.close()
        shell.deleteLater()

    def test_registry_returns_placeholder_then_recovers_after_factory_failure(
        self,
    ) -> None:
        shell = AppShell()
        registry = LazyPageRegistry(shell, ProjectMode.CLIPART)
        calls = []

        def factory():
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                raise RuntimeError("private detail")
            return QLabel("Готово")

        registry.register(StepId.PROMPTS, factory)

        placeholder = registry[StepId.PROMPTS]
        recovered = registry[StepId.PROMPTS]

        self.assertEqual(calls, [1, 2])
        self.assertIsNot(recovered, placeholder)
        self.assertEqual(recovered.text(), "Готово")
        shell.close()
        shell.deleteLater()

    def test_processing_page_does_not_probe_synthid_hardware(self) -> None:
        with patch("ai_watermark_backend.gpu_backend_available") as probe:
            view = V3ApplicationView()
            view.mode_selection.mode_cards[
                ProjectMode.PROCESSING
            ].start_button.click()
            view.shell.processing_flow_controller.pages[StepId.PIPELINE]

        probe.assert_not_called()
        view.close()
        view.deleteLater()


if __name__ == "__main__":
    unittest.main()
