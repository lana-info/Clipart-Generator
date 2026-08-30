from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QGridLayout, QLabel

from v3_processing_editor import (
    PROCESSING_RECIPES,
    ProcessingPipelineEditor,
    apply_processing_recipe,
    processing_pipeline_steps,
)
from v3_pinterest_flow import PinterestProcessingPage, _pinterest_project_adapter
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
        self.assertNotIn("текстовые комментарии", copy)
        self.assertNotIn("встроенную миниатюру", copy)
        self.assertNotIn("Очистка следов ИИ", copy)
        self.assertEqual(
            editor.operation_widgets["visible_mark_cleanup"].text(),
            "Удалить водяной знак Gemini",
        )

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

    def test_stage_sections_follow_enabled_pipeline_order(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        operations = state.processing.operations
        operations.upscale_before = True
        operations.unsharp = True
        operations.remove_background = True
        operations.edge_shrink = True
        operations.trim = True
        editor = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )

        self.assertEqual(
            editor.visible_stage_keys(),
            ("upscale_before", "unsharp", "remove_background", "edge_shrink", "trim"),
        )
        self.assertTrue(editor.stage_sections["upscale_after"].isHidden())

    def test_stage_dividers_only_appear_between_enabled_stages(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.processing.operations.upscale_before = False
        state.processing.operations.remove_background = False
        editor = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )

        self.assertTrue(all(divider.isHidden() for divider in editor.stage_dividers.values()))
        state.processing.operations.trim = True
        editor.refresh_from_state()
        self.assertTrue(all(divider.isHidden() for divider in editor.stage_dividers.values()))

        state.processing.operations.unsharp = True
        editor.refresh_from_state()
        self.assertFalse(editor.stage_dividers["trim"].isHidden())
        self.assertNotIn("upscale_before", editor.stage_dividers)

    def test_operations_are_arranged_in_three_columns(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        editor = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )

        self.assertIsInstance(editor.operations_grid, QGridLayout)
        self.assertEqual(editor.operations_grid.columnCount(), 3)

    def test_local_chroma_key_shows_only_the_three_preset_colors(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        operations = state.processing.operations
        operations.remove_background = True
        operations.remove_background_provider = "local_chroma_key"
        editor = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )

        color = editor.operation_widgets["chroma_key_color"]
        self.assertFalse(color.isHidden())
        self.assertEqual(
            tuple(color.itemData(index) for index in range(color.count())),
            ("blue", "red", "green"),
        )
        self.assertNotIn("chroma_key_tolerance", editor.operation_widgets)
        self.assertNotIn("chroma_key_softness", editor.operation_widgets)

    def test_fal_controls_show_selected_model_and_only_its_parameters(self) -> None:
        state = ProjectState(mode=ProjectMode.PROCESSING)
        operations = state.processing.operations
        operations.upscale_before = True
        operations.upscale_before_provider = "fal"
        operations.remove_background = True
        operations.remove_background_provider = "fal"
        editor = ProcessingPipelineEditor(
            state.processing,
            lambda: None,
            title="Pipeline",
            description="Common pipeline",
            include_cleanup=True,
        )

        self.assertFalse(editor.operation_widgets["fal_upscale_model"].isHidden())
        self.assertFalse(editor.operation_widgets["fal_upscale_scale"].isHidden())

        model = editor.operation_widgets["fal_remove_bg_model"]
        model.setCurrentIndex(model.findData("fal-ai/bria/background/remove"))
        self.assertTrue(editor.operation_widgets["fal_birefnet_model"].isHidden())
        self.assertTrue(editor.operation_widgets["fal_birefnet_resolution"].isHidden())
        self.assertTrue(editor.operation_widgets["fal_rembg_crop_to_bbox"].isHidden())

        model.setCurrentIndex(model.findData("fal-ai/birefnet/v2"))
        self.assertFalse(editor.operation_widgets["fal_birefnet_model"].isHidden())
        self.assertFalse(editor.operation_widgets["fal_birefnet_resolution"].isHidden())
        self.assertFalse(editor.operation_widgets["fal_birefnet_refine_foreground"].isHidden())
        self.assertTrue(editor.operation_widgets["fal_rembg_crop_to_bbox"].isHidden())

        model.setCurrentIndex(model.findData("fal-ai/imageutils/rembg"))
        self.assertTrue(editor.operation_widgets["fal_birefnet_model"].isHidden())
        self.assertFalse(editor.operation_widgets["fal_rembg_crop_to_bbox"].isHidden())

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
