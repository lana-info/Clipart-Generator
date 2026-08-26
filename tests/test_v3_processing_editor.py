from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel

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
        self.assertEqual(
            editor.operation_widgets["kie_remove_bg_model"].itemData(0),
            "recraft/remove-background",
        )
        self.assertEqual(
            editor.operation_widgets["local_rembg_profile"].itemData(0),
            "clipart",
        )
        self.assertEqual(
            editor.operation_widgets["local_rembg_model"].itemData(0),
            "birefnet-general",
        )
        self.assertEqual(
            tuple(
                editor.operation_widgets["upscale_factor"].itemData(index)
                for index in range(editor.operation_widgets["upscale_factor"].count())
            ),
            (2, 4),
        )
        self.assertFalse(editor.operation_widgets["upscale_factor"].isHidden())
        state.processing.operations.kie_upscale_model = "recraft/crisp-upscale"
        editor.refresh_from_state()
        self.assertTrue(editor.operation_widgets["upscale_factor"].isHidden())
        state.processing.operations.kie_upscale_model = "topaz/image-upscale"
        editor.refresh_from_state()
        self.assertIn(
            "МБ",
            editor.operation_widgets["local_rembg_model"].itemText(0),
        )
        profile = editor.operation_widgets["local_rembg_profile"]
        profile.setCurrentIndex(profile.findData("anime"))
        self.assertEqual(state.processing.operations.local_rembg_model, "isnet-anime")
        state.processing.operations.upscale_after = True
        state.processing.operations.upscale_after_provider = "kie"
        state.processing.operations.kie_upscale_after_model = "recraft/crisp-upscale"
        editor.refresh_from_state()
        recraft_index = editor.operation_widgets["kie_upscale_after_model"].findData(
            "recraft/crisp-upscale"
        )
        self.assertFalse(
            editor.operation_widgets["kie_upscale_after_model"].model()
            .item(recraft_index)
            .isEnabled()
        )
        self.assertTrue(hasattr(editor, "cleanup_checkbox"))
        self.assertFalse(editor.cleanup_checkbox.isChecked())
        editor.cleanup_checkbox.setChecked(True)
        self.assertTrue(state.processing.operations.remove_exif)
        self.assertTrue(state.processing.operations.remove_embedded_c2pa)
        self.assertTrue(state.processing.operations.preserve_icc)
        self.assertTrue(state.processing.operations.preserve_dpi)

        synthid = editor.operation_widgets["invisible_watermark_cleanup"]
        self.assertFalse(synthid.isEnabled())
        self.assertFalse(synthid.isChecked())
        self.assertIn("недоступно", synthid.text().lower())

        copy = " ".join(label.text() for label in editor.findChildren(QLabel))
        self.assertIn("текстовые комментарии", copy)
        self.assertIn("встроенную миниатюру", copy)
        self.assertNotIn("comments/text", copy)
        self.assertNotIn("embedded thumbnail", copy)
        self.assertNotIn("generator fields", copy)

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

    def test_operation_requirement_can_be_disabled_for_generation_modes(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        operations = state.processing.operations
        for name in (
            "visible_mark_cleanup",
            "invisible_watermark_cleanup",
            "upscale_before",
            "upscale_after",
            "remove_background",
            "unsharp",
            "edge_shrink",
            "trim",
            "export_300_dpi",
            "remove_exif",
            "remove_xmp",
            "remove_iptc",
            "remove_comments_text",
            "remove_embedded_thumbnail",
            "remove_generator_fields",
            "remove_embedded_c2pa",
        ):
            setattr(operations, name, False)

        required = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )
        optional = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Optional pipeline",
            include_cleanup=True,
            require_operation=False,
        )

        self.assertIn("processing_operation_required", required.validation_issues())
        self.assertNotIn("processing_operation_required", optional.validation_issues())


if __name__ == "__main__":
    unittest.main()
