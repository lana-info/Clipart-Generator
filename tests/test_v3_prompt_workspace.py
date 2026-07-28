import os
import unittest


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from v3_clipart_flow import PromptWorkspacePage
from v3_project_state import ProjectMode, ProjectState, PromptEntry


class V3PromptWorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_workspace_combines_prompt_input_and_review_sections(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        workspace = PromptWorkspacePage(state, lambda: None)

        self.assertFalse(workspace.generator_section.is_expanded)
        self.assertTrue(workspace.review_section.up_button.isHidden())
        self.assertTrue(workspace.review_section.down_button.isHidden())
        self.assertTrue(hasattr(workspace, "theme_edit"))
        self.assertTrue(hasattr(workspace, "table"))

        workspace.close()
        workspace.deleteLater()

    def test_reordering_prompts_keeps_text_and_references_together(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [
            PromptEntry("First", ["one.png"]),
            PromptEntry("Second", ["two.png"]),
        ]
        workspace = PromptWorkspacePage(state, lambda: None)

        workspace.review_section.table.setCurrentCell(0, 0)
        workspace.review_section._move(1)

        self.assertEqual(
            [entry.prompt for entry in state.clipart.prompts],
            ["Second", "First"],
        )
        self.assertEqual(
            [entry.references for entry in state.clipart.prompts],
            [["two.png"], ["one.png"]],
        )

        workspace.close()
        workspace.deleteLater()


if __name__ == "__main__":
    unittest.main()
