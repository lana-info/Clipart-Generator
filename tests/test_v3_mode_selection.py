import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_first_screen_shows_license_and_api_controls_before_mode_selection(self):
        screen = ModeSelectionScreen()
        license_requests = []
        api_requests = []
        screen.license_requested.connect(lambda: license_requests.append(True))
        screen.api_settings_requested.connect(lambda: api_requests.append(True))

        screen.set_license_status(
            "Лицензия активна",
            "Проверено онлайн: 15.08.2026 10:30",
        )
        screen.license_button.click()
        screen.api_settings_button.click()

        self.assertFalse(screen.account_card.isHidden())
        self.assertEqual(screen.license_status_label.text(), "Лицензия активна")
        self.assertEqual(
            screen.license_verification_label.text(),
            "Проверено онлайн: 15.08.2026 10:30",
        )
        self.assertEqual(screen.license_button.text(), "Сменить лицензию")
        self.assertEqual(screen.api_settings_button.text(), "Настройки API")
        self.assertEqual(license_requests, [True])
        self.assertEqual(api_requests, [True])
        screen.close()
        screen.deleteLater()

    def test_new_project_defaults_to_pictures_instead_of_process_directory(self):
        with tempfile.TemporaryDirectory(prefix="clipart-default-folder-") as temp:
            default_folder = Path(temp) / "Pictures" / "Clipart Generator"
            draft_path = Path(temp) / "app-data" / "project_state.json"
            with patch(
                "v3_mode_selection.default_work_directory",
                return_value=default_folder,
            ):
                view = V3ApplicationView(draft_path=draft_path)
                view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

            self.assertEqual(view.project_state.common.work_dir, str(default_folder))
            self.assertTrue(default_folder.is_dir())
            self.assertNotEqual(view.project_state.common.work_dir, os.getcwd())
            view.close()
            view.deleteLater()

    def test_last_selected_work_and_output_folders_are_reused(self):
        with tempfile.TemporaryDirectory(prefix="clipart-last-folder-") as temp:
            root = Path(temp)
            default_folder = root / "Pictures" / "Clipart Generator"
            selected_work = root / "selected-work"
            selected_output = root / "selected-output"
            selected_work.mkdir()
            selected_output.mkdir()
            draft_path = root / "app-data" / "project_state.json"

            with patch(
                "v3_mode_selection.default_work_directory",
                return_value=default_folder,
            ):
                clipart = V3ApplicationView(draft_path=draft_path)
                clipart.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
                clipart.shell.current_page.work_dir_edit.setText(str(selected_work))
                self.app.processEvents()
                clipart.close()
                clipart.deleteLater()

                processing = V3ApplicationView(draft_path=draft_path)
                processing.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
                processing.shell.current_page.output_selector.edit.setText(
                    str(selected_output)
                )
                self.app.processEvents()
                processing.close()
                processing.deleteLater()

                intervening_clipart = V3ApplicationView(draft_path=draft_path)
                intervening_clipart.mode_selection.mode_cards[
                    ProjectMode.CLIPART
                ].start_button.click()
                intervening_clipart.close()
                intervening_clipart.deleteLater()

                restored = V3ApplicationView(draft_path=draft_path)
                restored.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()

            self.assertEqual(restored.project_state.common.work_dir, str(selected_work))
            self.assertEqual(
                restored.project_state.output_dir_for_mode(ProjectMode.PROCESSING),
                str(selected_output),
            )
            restored.close()
            restored.deleteLater()

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
        recent.set_step(StepId.PROMPTS)
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
        self.assertEqual(state.current_step, StepId.PROMPTS)
        self.assertEqual(
            state.pinterest.prompts[0].prompt,
            "vertical beach pin",
        )
        self.assertEqual(continued, [ProjectMode.PINTEREST.value])
        view.close()
        view.deleteLater()

    def test_recent_project_draft_is_restored_from_disk(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-draft-") as temp:
            draft_path = Path(temp) / "project_state.json"
            view = V3ApplicationView(draft_path=draft_path)
            view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
            state = view.project_state
            state.common.work_dir = temp
            state.clipart.prompts.append(PromptEntry("restored clipart prompt"))
            state.pinterest.prompts.append(PromptEntry("restored pinterest prompt"))
            view.shell.mark_dirty()
            view.close()
            view.deleteLater()

            restored = V3ApplicationView(draft_path=draft_path)
            self.assertFalse(restored.mode_selection.recent_project_card.isHidden())
            self.assertTrue(
                restored.mode_selection.continue_button.accessibleDescription()
            )
            restored.mode_selection.continue_button.click()
            restored_state = restored.project_state
            self.assertEqual(
                restored_state.clipart.prompts[0].prompt,
                "restored clipart prompt",
            )
            self.assertEqual(
                restored_state.pinterest.prompts[0].prompt,
                "restored pinterest prompt",
            )
            restored.close()
            restored.deleteLater()

    def test_continue_is_unavailable_without_a_recent_project(self):
        view = V3ApplicationView()
        self.assertTrue(view.mode_selection.recent_project_card.isHidden())
        self.assertFalse(view.continue_last_project())
        self.assertIsNone(view.project_state)
        view.close()
        view.deleteLater()

    def test_mode_switcher_reuses_project_and_switches_immediately(self):
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

        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        self.assertIs(view.stack.currentWidget(), view.shell)
        self.assertEqual(state.mode, ProjectMode.PINTEREST)
        self.assertEqual(
            state.clipart.prompts[0].prompt,
            "kept clipart prompt",
        )
        self.assertTrue(view.shell.mode_switch_banner.isHidden())
        view.close()
        view.deleteLater()

    def test_done_returns_to_mode_selection_without_reusing_completed_shell(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        completed_shell = view.shell
        completed_shell.state.set_step(StepId.RESULTS)
        completed_shell.refresh()

        completed_shell.next_button.click()
        self.app.processEvents()

        self.assertIs(view.stack.currentWidget(), view.mode_selection)
        self.assertIs(view.shell, completed_shell)
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        self.assertIsNot(view.shell, completed_shell)
        self.assertEqual(view.shell.state.processing.selected_files, [])
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
