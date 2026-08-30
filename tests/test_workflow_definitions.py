import unittest

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from v3_project_state import ProjectMode, StepId
from workflow_definitions import (
    WorkflowDefinition,
    WorkflowPageSpec,
    WorkflowStepSpec,
    workflow_for_mode,
)
from v3_processing_editor import ProcessingPipelineEditor
from v3_wizard import AppShell


class WorkflowDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_clipart_and_pinterest_have_different_processing_surfaces(self):
        clipart = workflow_for_mode(ProjectMode.CLIPART)
        pinterest = workflow_for_mode(ProjectMode.PINTEREST)

        self.assertIn("remove_background", clipart.processing_operations)
        self.assertIn("trim", clipart.processing_operations)
        self.assertNotIn("remove_background", pinterest.processing_operations)
        self.assertNotIn("trim", pinterest.processing_operations)
        self.assertEqual(clipart.prompt_builder_id, "clipart_structured")
        self.assertEqual(pinterest.prompt_builder_id, "pinterest_structured")
        self.assertTrue(clipart.supports_provider_control("generation_model"))
        self.assertTrue(clipart.supports_export("png"))
        self.assertEqual(pinterest.validation_id, "pinterest_default")

    def test_workflow_pages_preserve_order_and_allow_custom_builder(self):
        definition = WorkflowDefinition(
            workflow_id="trendwatcher",
            mode=ProjectMode.CLIPART,
            prompt_builder_id="trendwatcher_prompt_builder",
            pages=(
                WorkflowPageSpec(StepId.PROJECT, "shared.project"),
                WorkflowPageSpec(StepId.PROMPTS, "trendwatcher.prompt_builder"),
                WorkflowPageSpec(StepId.RESULTS, "shared.results"),
            ),
        )

        self.assertEqual(
            definition.page_steps,
            (StepId.PROJECT, StepId.PROMPTS, StepId.RESULTS),
        )
        self.assertEqual(
            definition.page_for_step(StepId.PROMPTS).component_id,
            "trendwatcher.prompt_builder",
        )

    def test_external_steps_require_confirmation_and_have_artifact_contract(self):
        step = WorkflowStepSpec(
            step_id="upload_google_drive",
            kind="external_delivery",
            input_artifacts=("png",),
            output_artifacts=("drive_file",),
            external_side_effect=True,
            requires_confirmation=True,
        )
        self.assertTrue(step.external_side_effect)
        self.assertTrue(step.requires_confirmation)
        self.assertEqual(step.input_artifacts, ("png",))

        with self.assertRaises(ValueError):
            WorkflowStepSpec(
                step_id="unsafe_upload",
                kind="external_delivery",
                input_artifacts=("png",),
                output_artifacts=("remote_file",),
                external_side_effect=True,
            )

    def test_hidden_operations_are_not_allowed_by_definition(self):
        pinterest = workflow_for_mode(ProjectMode.PINTEREST)
        self.assertFalse(pinterest.allows_processing_operation("trim"))
        self.assertFalse(pinterest.allows_processing_operation("remove_background"))
        self.assertFalse(pinterest.allows_processing_operation("upscale_before"))

    def test_clipart_and_processing_allow_300_dpi_export(self):
        for mode in (ProjectMode.CLIPART, ProjectMode.PROCESSING):
            with self.subTest(mode=mode.value):
                workflow = workflow_for_mode(mode)
                self.assertTrue(
                    workflow.allows_processing_operation("export_300_dpi")
                )

                owner = type("Owner", (), {})()
                owner.operations = __import__("v3_project_state").ImageOperationData(
                    export_300_dpi=True
                )
                editor = ProcessingPipelineEditor(
                    owner,
                    lambda: None,
                    title="Processing",
                    description="Test",
                    include_cleanup=True,
                    allowed_operations=workflow.processing_operations,
                )
                editor.show()
                self.app.processEvents()

                self.assertTrue(editor.operation_widgets["export_300_dpi"].isVisible())
                self.assertTrue(owner.operations.export_300_dpi)
                editor.close()

    def test_pinterest_declares_prompt_only_generation_pages_and_operations(self):
        """Pinterest accepts prompts/CSV and shares generation, not processing."""
        pinterest = workflow_for_mode(ProjectMode.PINTEREST)

        self.assertEqual(
            pinterest.page_steps,
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PROMPT_REVIEW,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )
        self.assertEqual(
            tuple(page.component_id for page in pinterest.pages),
            (
                "pinterest.project",
                "pinterest.prompt_input",
                "pinterest.prompt_review",
                "pinterest.generation",
                "pinterest.review_run",
                "shared.results",
            ),
        )
        self.assertEqual(pinterest.processing_operations, ())
        self.assertFalse(pinterest.supports_provider_control("processing_providers"))
        self.assertTrue(pinterest.supports_provider_control("reference_model"))

    def test_processing_editor_hides_operations_not_in_workflow_profile(self):
        pinterest = workflow_for_mode(ProjectMode.PINTEREST)
        owner = type("Owner", (), {})()
        owner.operations = __import__("v3_project_state").ImageOperationData()
        editor = ProcessingPipelineEditor(
            owner,
            lambda: None,
            title="Processing",
            description="Test",
            include_cleanup=True,
            allowed_operations=pinterest.processing_operations,
        )
        editor.show()
        self.app.processEvents()

        self.assertFalse(editor.operation_widgets["upscale_before"].isVisible())
        self.assertFalse(editor.operation_widgets["remove_background"].isVisible())
        self.assertFalse(editor.operation_widgets["trim"].isVisible())
        self.assertFalse(editor.cleanup_checkbox.isVisible())
        editor.close()

    def test_component_id_is_checked_when_registering_workflow_page(self):
        definition = workflow_for_mode(ProjectMode.CLIPART)
        self.assertEqual(
            definition.page_for_step(StepId.PROMPTS).component_id,
            "shared.prompts",
        )

    def test_custom_definition_controls_navigation_route(self):
        custom = WorkflowDefinition(
            workflow_id="short_clipart",
            mode=ProjectMode.CLIPART,
            prompt_builder_id="custom_prompt_builder",
            pages=(
                WorkflowPageSpec(StepId.PROJECT, "shared.project"),
                WorkflowPageSpec(StepId.RESULTS, "shared.results"),
            ),
        )
        state = __import__("v3_project_state").ProjectState(mode=ProjectMode.CLIPART)
        state.common.work_dir = "."
        shell = AppShell(state, workflow_definitions={ProjectMode.CLIPART: custom})

        self.assertEqual(shell.state.route, (StepId.PROJECT, StepId.RESULTS))
        self.assertEqual(shell.go_next(), StepId.RESULTS)
        shell.close()


if __name__ == "__main__":
    unittest.main()
