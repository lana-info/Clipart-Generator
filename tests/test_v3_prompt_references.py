import os
import tempfile
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PIL import Image

from v3_clipart_flow import PromptReferenceEditorDialog, PromptWorkspacePage
from v3_project_state import (
    ProjectMode,
    ProjectState,
    PromptEntry,
    load_project_draft,
    save_project_draft,
)


class V3PromptReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def _make_image(self, directory: str, name: str) -> str:
        path = Path(directory) / name
        Image.new("RGB", (8, 8), "white").save(path)
        return str(path)

    def test_editor_allows_adding_and_removing_local_files(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-refs-") as temp:
            image_one = self._make_image(temp, "one.png")
            image_two = self._make_image(temp, "two.png")
            missing = str(Path(temp) / "missing.png")
            dialog = PromptReferenceEditorDialog(
                PromptEntry("Prompt", [missing, image_one])
            )

            self.assertIn("нет файла", dialog._references.item(0).text())
            dialog.add_references([image_two, image_one])
            dialog._references.setCurrentRow(0)
            dialog._remove_selected()

            self.assertEqual(dialog.references(), [image_one, image_two])
            self.assertEqual(dialog.prompt_entry().references, [image_one, image_two])

            dialog.close()
            dialog.deleteLater()

    def test_bulk_add_replace_and_clear_references(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-refs-bulk-") as temp:
            image_one = self._make_image(temp, "one.png")
            image_two = self._make_image(temp, "two.png")
            image_three = self._make_image(temp, "three.png")
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.clipart.prompts = [
                PromptEntry("First"),
                PromptEntry("Second"),
                PromptEntry("Third"),
            ]
            workspace = PromptWorkspacePage(state, lambda: None)
            review = workspace.review_section

            review._pick_reference_scope = lambda: "all"  # type: ignore[assignment]
            review._choose_reference_files = lambda: [image_one, image_two]  # type: ignore[assignment]
            review._add_references()
            self.assertEqual(
                [entry.references for entry in state.clipart.prompts],
                [[image_one, image_two]] * 3,
            )

            review.table.selectRow(0)
            review._pick_reference_scope = lambda: "selected"  # type: ignore[assignment]
            review._choose_reference_files = lambda: [image_three]  # type: ignore[assignment]
            review._replace_references()
            self.assertEqual(state.clipart.prompts[0].references, [image_three])
            self.assertEqual(state.clipart.prompts[1].references, [image_one, image_two])

            review._delete_all_references()
            self.assertEqual([entry.references for entry in state.clipart.prompts], [[], [], []])

            workspace.close()
            workspace.deleteLater()

    def test_selected_scope_does_not_fall_back_to_current_row(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-refs-selected-") as temp:
            image_one = self._make_image(temp, "one.png")
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.clipart.prompts = [
                PromptEntry("First"),
                PromptEntry("Second"),
            ]
            workspace = PromptWorkspacePage(state, lambda: None)
            review = workspace.review_section

            review.table.setCurrentCell(0, 0)
            review.table.clearSelection()
            review._pick_reference_scope = lambda: "selected"  # type: ignore[assignment]
            review._choose_reference_files = lambda: [image_one]  # type: ignore[assignment]

            review._add_references()

            self.assertEqual([entry.references for entry in state.clipart.prompts], [[], []])

            workspace.close()
            workspace.deleteLater()

    def test_cleared_references_persist_through_project_draft(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-refs-draft-") as temp:
            draft_path = Path(temp) / "project_state.json"
            image_path = self._make_image(temp, "reference.png")
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.common.work_dir = temp
            state.clipart.prompts = [PromptEntry("One", [image_path])]

            save_project_draft(state, draft_path)
            restored = load_project_draft(draft_path)
            self.assertEqual(restored.clipart.prompts[0].references, [image_path])

            restored.clipart.prompts[0].references = []
            save_project_draft(restored, draft_path)
            cleared = load_project_draft(draft_path)
            self.assertEqual(cleared.clipart.prompts[0].references, [])


if __name__ == "__main__":
    unittest.main()
