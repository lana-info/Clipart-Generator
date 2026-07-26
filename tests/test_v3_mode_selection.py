import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from v3_mode_selection import (
    MODE_CARD_SPECS,
    ModeSelectionScreen,
    SelectionIntent,
    V3ApplicationView,
)
from v3_project_state import (
    CommonProjectData,
    PinterestModeData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
    route_for_mode,
)


class V3ModeSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_each_mode_card_starts_a_fresh_project_on_the_correct_route(self):
        for mode in ProjectMode:
            with self.subTest(mode=mode):
                view = V3ApplicationView()
                started = []
                view.new_project_started.connect(started.append)

                view.mode_selection.mode_cards[mode].start_button.click()
                state = view.project_state

                self.assertIsNotNone(state)
                self.assertEqual(state.mode, mode)
                self.assertEqual(state.route, route_for_mode(mode))
                self.assertEqual(state.current_step, route_for_mode(mode)[0])
                self.assertEqual(started, [mode.value])
                self.assertIs(view.stack.currentWidget(), view.shell)
                view.close()
                view.deleteLater()

    def test_pinterest_card_promises_only_images_from_prompts(self):
        screen = ModeSelectionScreen()
        spec = MODE_CARD_SPECS[ProjectMode.PINTEREST]
        card = screen.mode_cards[ProjectMode.PINTEREST]
        promise = f"{spec.description} {spec.result}".lower()

        self.assertIn("только", promise)
        self.assertIn("изображения", promise)
        self.assertIn("по промптам", promise)
        self.assertIn("без публикации", promise)
        self.assertIn("без публикации", card.accessibleDescription().lower())
        self.assertNotIn("публикуем", promise)
        screen.close()
        screen.deleteLater()

    def test_new_projects_do_not_inherit_another_modes_values(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        clipart_state = view.project_state
        clipart_state.clipart.prompts.append(PromptEntry("private clipart prompt"))

        view.show_new_project()
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        pinterest_state = view.project_state
        self.assertIsNot(pinterest_state, clipart_state)
        self.assertEqual(pinterest_state.clipart.prompts, [])
        self.assertEqual(pinterest_state.pinterest.prompts, [])
        self.assertEqual(pinterest_state.processing.selected_files, [])
        pinterest_state.pinterest.prompts.append(PromptEntry("vertical pin"))

        view.show_new_project()
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        processing_state = view.project_state
        self.assertIsNot(processing_state, pinterest_state)
        self.assertEqual(processing_state.clipart.prompts, [])
        self.assertEqual(processing_state.pinterest.prompts, [])
        self.assertEqual(processing_state.processing.selected_files, [])
        view.close()
        view.deleteLater()

    def test_last_project_is_snapshotted_and_can_be_continued(self):
        recent = ProjectState(
            mode=ProjectMode.PINTEREST,
            common=CommonProjectData(project_name="Summer Pins"),
            pinterest=PinterestModeData(
                prompts=[PromptEntry("vertical beach pin")],
            ),
        )
        recent.set_step(StepId.PROMPT_REVIEW)
        view = V3ApplicationView(recent)
        continued = []
        view.project_continued.connect(continued.append)

        self.assertFalse(view.mode_selection.recent_project_card.isHidden())
        self.assertIn(
            "Summer Pins",
            view.mode_selection.continue_button.accessibleDescription(),
        )

        recent.pinterest.prompts[0].prompt = "mutated outside"
        view.mode_selection.continue_button.click()
        state = view.project_state
        self.assertEqual(state.mode, ProjectMode.PINTEREST)
        self.assertEqual(state.current_step, StepId.PROMPT_REVIEW)
        self.assertEqual(
            state.pinterest.prompts[0].prompt,
            "vertical beach pin",
        )
        self.assertEqual(continued, [ProjectMode.PINTEREST.value])
        view.close()
        view.deleteLater()

    def test_continue_is_unavailable_without_a_recent_project(self):
        view = V3ApplicationView()
        self.assertTrue(view.mode_selection.recent_project_card.isHidden())
        self.assertFalse(view.continue_last_project())
        self.assertIsNone(view.project_state)
        view.close()
        view.deleteLater()

    def test_mode_switcher_reuses_project_and_shows_unsaved_confirmation(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        state = view.project_state
        state.clipart.prompts.append(PromptEntry("kept clipart prompt"))
        view.shell.mark_dirty()

        view.shell.change_mode_button.click()
        self.assertEqual(view.selection_intent, SelectionIntent.SWITCH_MODE)
        self.assertIs(view.stack.currentWidget(), view.mode_selection)
        self.assertTrue(view.mode_selection.recent_project_card.isHidden())
        self.assertFalse(view.mode_selection.cancel_button.isHidden())

        view.mode_selection.cancel_button.click()
        self.assertIs(view.stack.currentWidget(), view.shell)
        self.assertEqual(state.mode, ProjectMode.CLIPART)

        view.shell.change_mode_button.click()
        self.assertIs(view.stack.currentWidget(), view.mode_selection)

        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        self.assertIs(view.stack.currentWidget(), view.shell)
        self.assertEqual(state.mode, ProjectMode.CLIPART)
        self.assertFalse(view.shell.mode_switch_banner.isHidden())

        view.shell.continue_mode_button.click()
        self.assertEqual(state.mode, ProjectMode.PINTEREST)
        self.assertEqual(
            state.clipart.prompts[0].prompt,
            "kept clipart prompt",
        )
        view.close()
        view.deleteLater()

    def test_offscreen_selection_layout_and_keyboard_flow_at_980_by_700(self):
        screen = ModeSelectionScreen()
        screen.resize(980, 700)
        screen.show()
        self.app.processEvents()

        cards = list(screen.mode_cards.values())
        self.assertEqual((screen.width(), screen.height()), (980, 700))
        self.assertTrue(screen.isVisible())
        self.assertLessEqual(
            screen.cards_container.geometry().right(),
            screen.contentsRect().right(),
        )
        for card in cards:
            self.assertGreater(card.width(), 0)
            self.assertLessEqual(
                card.geometry().bottom(),
                screen.cards_container.contentsRect().bottom(),
            )
        widths = [card.width() for card in cards]
        self.assertLessEqual(max(widths) - min(widths), 1)

        cards[0].start_button.setFocus()
        self.app.processEvents()
        self.assertTrue(cards[0].start_button.hasFocus())
        QTest.keyClick(screen, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), cards[1].start_button)

        screen.close()
        screen.deleteLater()


if __name__ == "__main__":
    unittest.main()
