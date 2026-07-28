from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from v3_processing_editor import (
    PROCESSING_RECIPES,
    ProcessingPipelineEditor,
    apply_processing_recipe,
    processing_pipeline_steps,
)
from v3_project_state import ProjectMode, ProjectState


class ProcessingEditorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_recipe_model_applies_shared_presets(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        apply_processing_recipe(state, "prepare_clipart")
        self.assertTrue(state.processing.operations.remove_background)
        self.assertTrue(state.processing.operations.upscale_before)
        self.assertTrue(state.processing.operations.trim)
        self.assertTrue(state.processing.operations.export_300_dpi)
        self.assertEqual(state.processing.recipe, "prepare_clipart")
        self.assertIn("локальное удаление фона", PROCESSING_RECIPES["prepare_clipart"].description.lower())

    def test_shared_editor_builds_order_and_visibility(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        editor = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )
        state.processing.operations.remove_background = True
        state.processing.operations.remove_background_provider = "kie"
        editor.refresh_from_state()

        self.assertIn("Удаление фона", editor.pipeline_label.text())
        self.assertFalse(editor.operation_widgets["kie_remove_bg_model"].isHidden())
        self.assertTrue(hasattr(editor, "cleanup_checkbox"))
        self.assertFalse(editor.cleanup_checkbox.isChecked())
        editor.cleanup_checkbox.setChecked(True)
        self.assertTrue(state.processing.operations.remove_exif)
        self.assertTrue(state.processing.operations.remove_embedded_c2pa)
        self.assertTrue(state.processing.operations.preserve_icc)
        self.assertTrue(state.processing.operations.preserve_dpi)

    def test_shared_steps_match_current_pipeline_contract(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.processing.operations.upscale_before = True
        state.processing.operations.remove_background = True
        state.processing.operations.trim = True
        self.assertEqual(
            processing_pipeline_steps(state.processing.operations),
            (
                "Апскейл до удаления фона",
                "Удаление фона",
                "Trim",
                "Экспорт нового PNG",
            ),
        )

    def test_pinterest_uses_persistent_shared_recipe_state(self) -> None:
        state = ProjectState(mode=ProjectMode.PINTEREST)
        editor = ProcessingPipelineEditor(
            state.pinterest,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )
        editor.operation_widgets["trim"].setChecked(True)
        editor.cleanup_checkbox.setChecked(True)
        self.assertTrue(state.pinterest.operations.trim)
        self.assertTrue(state.pinterest.operations.remove_exif)
        self.assertIn("Trim", editor.pipeline_label.text())


if __name__ == "__main__":
    unittest.main()
