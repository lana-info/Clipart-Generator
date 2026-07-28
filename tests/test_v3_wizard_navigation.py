import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel

from v3_project_state import (
    ClipartModeData,
    CommonProjectData,
    GenerationData,
    PinterestModeData,
    ProcessingModeData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
)
from v3_wizard import AppShell, STEP_TITLES


def complete_state(mode: ProjectMode) -> ProjectState:
    return ProjectState(
        mode=mode,
        common=CommonProjectData(work_dir="D:/work"),
        clipart=ClipartModeData(
            prompts=[PromptEntry("blue whale")],
            generation=GenerationData(
                model="gpt-image-2",
                ratio="1:1",
                resolution="2K",
            ),
        ),
        pinterest=PinterestModeData(
            prompts=[PromptEntry("vertical summer pin")],
            generation=GenerationData(
                model="nano-banana-2",
                ratio="9:16",
                resolution="2K",
            ),
        ),
        processing=ProcessingModeData(
            selected_files=["D:/input.png"],
        ),
    )


class V3WizardNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_all_three_routes_move_forward_and_back_through_project_state(self):
        for mode in ProjectMode:
            with self.subTest(mode=mode):
                state = complete_state(mode)
                shell = AppShell(state)
                visited = [state.current_step]

                while state.current_step is not StepId.REVIEW_RUN:
                    visited.append(shell.go_next())

                self.assertEqual(tuple(visited), state.route[: len(visited)])
                if mode is ProjectMode.PROCESSING:
                    emitted = []
                    shell.run_requested.connect(emitted.append)
                    shell.go_next()
                    self.assertEqual(emitted, [ProjectMode.PROCESSING.value])
                    self.assertEqual(shell.show_results(), StepId.RESULTS)

                while state.current_step is not state.route[0]:
                    shell.go_back()
                self.assertEqual(state.current_step, state.route[0])
                shell.close()
                shell.deleteLater()

    def test_invalid_step_blocks_only_forward_navigation(self):
        state = complete_state(ProjectMode.CLIPART)
        shell = AppShell(state)
        self.assertEqual(shell.go_next(), StepId.PROMPTS)

        state.clipart.prompts.clear()
        failures = []
        shell.validation_failed.connect(
            lambda step, issues: failures.append((step, issues))
        )
        self.assertEqual(shell.go_next(), StepId.PROMPTS)
        self.assertEqual(
            failures,
            [(StepId.PROMPTS.value, ("prompts_required",))],
        )
        self.assertFalse(shell.validation_label.isHidden())
        self.assertTrue(shell.step_labels[1].text().startswith("✕"))

        self.assertEqual(shell.go_back(), StepId.PROJECT)
        self.assertTrue(shell.validation_label.isHidden())
        shell.close()
        shell.deleteLater()

    def test_navigation_state_survives_shell_recreation(self):
        state = complete_state(ProjectMode.PINTEREST)
        first_shell = AppShell(state)
        first_shell.go_next()
        first_shell.go_next()
        self.assertEqual(state.current_step, StepId.PROMPT_REVIEW)
        first_shell.close()
        first_shell.deleteLater()

        restored_shell = AppShell(state)
        self.assertEqual(restored_shell.state.current_step, StepId.PROMPT_REVIEW)
        self.assertIn(
            STEP_TITLES[StepId.PROMPT_REVIEW],
            restored_shell.step_labels[2].text(),
        )
        self.assertIs(restored_shell.page_stack.currentWidget(), restored_shell.current_page)
        restored_shell.close()
        restored_shell.deleteLater()

    def test_stepper_uses_text_statuses_not_color_alone(self):
        shell = AppShell(complete_state(ProjectMode.CLIPART))
        self.assertTrue(shell.step_labels[0].text().startswith("●"))
        self.assertIn("Текущий", shell.step_labels[0].accessibleName())
        self.assertTrue(shell.step_labels[1].text().startswith("○"))

        shell.go_next()
        self.assertTrue(shell.step_labels[0].text().startswith("✓"))
        self.assertIn("Пройден", shell.step_labels[0].accessibleName())
        self.assertTrue(shell.step_labels[1].text().startswith("●"))
        shell.close()
        shell.deleteLater()

    def test_mode_switch_applies_immediately_and_preserves_data(self):
        state = complete_state(ProjectMode.CLIPART)
        shell = AppShell(state)
        shell.mark_dirty()

        self.assertTrue(shell.request_mode_switch(ProjectMode.PINTEREST))
        self.assertEqual(state.mode, ProjectMode.PINTEREST)
        self.assertEqual(state.clipart.prompts[0].prompt, "blue whale")
        self.assertTrue(shell.is_dirty)
        self.assertTrue(shell.mode_switch_banner.isHidden())
        shell.close()
        shell.deleteLater()

    def test_review_run_emits_without_connecting_pipeline(self):
        for mode in (ProjectMode.CLIPART, ProjectMode.PINTEREST):
            with self.subTest(mode=mode):
                state = complete_state(mode)
                shell = AppShell(state)
                while state.current_step is not StepId.REVIEW_RUN:
                    shell.go_next()
                requests = []
                shell.run_requested.connect(requests.append)

                self.assertEqual(shell.next_button.text(), "Запустить")
                self.assertEqual(shell.go_next(), StepId.REVIEW_RUN)
                self.assertEqual(requests, [mode.value])
                self.assertEqual(state.current_step, StepId.REVIEW_RUN)
                shell.close()
                shell.deleteLater()

    def test_custom_page_registration_is_mode_and_step_specific(self):
        shell = AppShell(complete_state(ProjectMode.CLIPART))
        original = shell.current_page
        original_count = shell.page_stack.count()
        shell.set_step_page(ProjectMode.CLIPART, StepId.PROJECT, original)
        self.assertEqual(shell.page_stack.count(), original_count)

        replacement = QLabel("Настройки проекта")
        shell.set_step_page(ProjectMode.CLIPART, StepId.PROJECT, replacement)
        self.assertIs(shell.current_page, replacement)
        self.assertIs(shell.page_stack.currentWidget(), replacement)

        with self.assertRaises(ValueError):
            shell.set_step_page(
                ProjectMode.CLIPART,
                StepId.FILES,
                QLabel("Неверный шаг"),
            )
        with self.assertRaises(ValueError):
            shell.set_step_page(
                ProjectMode.CLIPART,
                StepId.PROMPTS,
                replacement,
            )
        self.assertEqual(shell.page_stack.count(), original_count)
        shell.close()
        shell.deleteLater()

    def test_results_require_a_successful_run_request(self):
        state = complete_state(ProjectMode.PROCESSING)
        state.set_step(StepId.REVIEW_RUN)
        shell = AppShell(state)

        with self.assertRaises(RuntimeError):
            shell.show_results()
        self.assertEqual(state.current_step, StepId.REVIEW_RUN)

        requests = []
        shell.run_requested.connect(requests.append)
        shell.go_next()
        self.assertEqual(requests, [ProjectMode.PROCESSING.value])
        self.assertEqual(shell.show_results(), StepId.RESULTS)

        shell.close()
        shell.deleteLater()

    def test_offscreen_shell_smoke_at_980_by_700(self):
        shell = AppShell(complete_state(ProjectMode.PROCESSING))
        shell.resize(980, 700)
        shell.show()
        self.app.processEvents()

        self.assertEqual((shell.width(), shell.height()), (980, 700))
        self.assertTrue(shell.isVisible())
        self.assertGreater(shell.page_stack.width(), 0)
        self.assertLessEqual(
            shell.sidebar.geometry().right(),
            shell.contentsRect().right(),
        )
        self.assertLessEqual(
            shell.footer.geometry().bottom(),
            shell.contentsRect().bottom(),
        )
        self.assertIs(shell.page_stack.currentWidget(), shell.current_page)
        self.assertTrue(shell.styleSheet())
        self.assertLess(shell.back_button.width(), 200)
        self.assertLess(shell.next_button.width(), 200)

        shell.mark_dirty()
        self.assertTrue(shell.request_mode_switch(ProjectMode.CLIPART))
        self.app.processEvents()
        self.assertTrue(shell.mode_switch_banner.isHidden())
        self.assertLessEqual(
            shell.mode_switch_banner.geometry().bottom(),
            shell.contentsRect().bottom(),
        )
        self.assertLessEqual(
            shell.footer.geometry().bottom(),
            shell.contentsRect().bottom(),
        )

        shell.close()
        shell.deleteLater()


    def test_keyboard_focus_reaches_primary_navigation(self):
        shell = AppShell(complete_state(ProjectMode.CLIPART))
        shell.show()
        self.app.processEvents()

        shell.change_mode_button.setFocus()
        self.app.processEvents()
        self.assertTrue(shell.change_mode_button.hasFocus())

        QTest.keyClick(shell, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), shell.next_button)

        shell.close()
        shell.deleteLater()
if __name__ == "__main__":
    unittest.main()
