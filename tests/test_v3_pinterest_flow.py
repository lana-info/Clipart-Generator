import ast
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

import v3_pinterest_flow
from v3_mode_selection import V3ApplicationView
from v3_pinterest_flow import (
    PinterestFormatModelPage,
    PinterestPromptInputPage,
    PinterestReviewRunPage,
    build_pinterest_run_request,
    estimate_pinterest_cost,
    install_pinterest_flow,
)
from v3_clipart_flow import ClipartPromptReviewPage
from v3_project_state import (
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
    migrate_v2_config,
)
from v3_wizard import AppShell


class FakeWorker(QObject):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def isRunning(self):
        return self.started


class WorkerFactory:
    def __init__(self):
        self.workers = []

    def __call__(self, **kwargs):
        worker = FakeWorker(**kwargs)
        self.workers.append(worker)
        return worker


class V3PinterestFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_state(self, work_dir):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.common.project_name = "Summer pins"
        state.common.work_dir = str(work_dir)
        state.pinterest.prompts = [
            PromptEntry("Summer garden inspiration"),
            PromptEntry("Coastal living room ideas"),
        ]
        state.pinterest.generation.variants = 2
        return state

    def test_application_view_installs_exact_b1_to_b6_route(self):
        view = V3ApplicationView(
            runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
            worker_factory=WorkerFactory(),
        )
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        self.app.processEvents()

        controller = view.shell.pinterest_flow_controller
        self.assertEqual(set(controller.pages), set(view.shell.state.route))
        self.assertEqual(
            tuple(controller.pages),
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PROMPT_REVIEW,
                StepId.PIN_FORMAT_MODEL,
                StepId.PROCESSING_OPTIONS,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )
        self.assertIsInstance(
            controller.pages[StepId.PROCESSING_OPTIONS],
            v3_pinterest_flow.PinterestProcessingPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPTS],
            PinterestPromptInputPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPT_REVIEW],
            ClipartPromptReviewPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PIN_FORMAT_MODEL],
            PinterestFormatModelPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.REVIEW_RUN],
            PinterestReviewRunPage,
        )

    def test_generator_uses_pinterest_defaults_and_creates_editable_series(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPTS]

        self.assertIn("vertical", page.composition_edit.text().lower())
        self.assertIn("safe zones", page.composition_edit.text().lower())
        page.generator_section.set_expanded(True)
        page.theme_edit.setText("Small balcony ideas")
        page.subjects_edit.setPlainText("Herb garden\nReading corner")
        page.count_spin.setValue(3)
        page.preview_button.click()
        page.replace_variants_button.click()

        self.assertEqual(len(state.pinterest.prompts), 3)
        self.assertTrue(
            all("vertical" in entry.prompt.lower() for entry in state.pinterest.prompts)
        )
        state.pinterest.prompts[0].prompt = "Manual Pinterest edit"
        self.assertEqual(
            state.pinterest.prompts[0].prompt,
            "Manual Pinterest edit",
        )

    def test_reference_models_expand_and_report_incompatibility(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-ref-") as temp:
            image_path = Path(temp) / "reference.png"
            Image.new("RGB", (4, 6), "white").save(image_path)
            state = self.make_state(temp)
            state.pinterest.prompts[0].references = [str(image_path)]
            shell = AppShell(state)
            controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
            page = controller.pages[StepId.PIN_FORMAT_MODEL]
            page.refresh_from_state()

            self.assertFalse(page.reference_advanced.isHidden())
            self.assertTrue(page.reference_advanced.is_expanded)

            current_model = str(page.model_combo.currentData())
            with patch.dict(
                v3_pinterest_flow._PINTEREST_REFERENCE_MODEL_BY_TEXT,
                {current_model: "missing-reference-model"},
                clear=False,
            ):
                page._enforce_single_format()

            self.assertIn("Нет парной reference-модели", page.reference_status_label.text())
            self.assertIn("incompatible_reference_model", page.validation_issues())

    def test_vertical_ratio_is_default_and_supported_ratio_can_change(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        self.assertEqual(state.pinterest.generation.ratio, "9:16")
        self.assertEqual(state.pinterest.generation.reference_ratio, "9:16")
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PIN_FORMAT_MODEL]

        self.assertEqual(page.ratio_combo.currentText(), "9:16")
        self.assertIn("9:16", page.ratio_preview.accessibleName())
        alternatives = [
            page.ratio_combo.itemText(index)
            for index in range(page.ratio_combo.count())
            if page.ratio_combo.itemText(index) != "9:16"
        ]
        self.assertTrue(alternatives)
        page.ratio_combo.setCurrentText(alternatives[0])
        self.assertEqual(
            state.pinterest.generation.ratio,
            alternatives[0],
        )
        self.assertIn(alternatives[0], page.ratio_preview.accessibleName())

    def test_changed_format_is_shared_by_text_and_reference_prompts(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-format-") as temp:
            image_path = Path(temp) / "reference.png"
            Image.new("RGB", (4, 6), "white").save(image_path)
            state = self.make_state(temp)
            state.pinterest.prompts[1].references = [str(image_path)]
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )
            page = controller.pages[StepId.PIN_FORMAT_MODEL]
            page.ratio_combo.setCurrentText("16:9")
            page.resolution_combo.setCurrentText("2K")
            request = build_pinterest_run_request(
                state,
                {"kie_api_key": "test-key"},
            )
            controller.pages[StepId.REVIEW_RUN].refresh_from_state()

        self.assertEqual(state.pinterest.generation.ratio, "16:9")
        self.assertEqual(state.pinterest.generation.reference_ratio, "16:9")
        self.assertEqual(state.pinterest.generation.resolution, "2K")
        self.assertEqual(state.pinterest.generation.reference_resolution, "2K")
        self.assertEqual(request.settings["text_generation_ratio"], "16:9")
        self.assertEqual(request.settings["reference_generation_ratio"], "16:9")
        self.assertEqual(request.settings["text_generation_resolution"], "2K")
        self.assertEqual(request.settings["reference_generation_resolution"], "2K")
        self.assertIn(
            "16:9",
            controller.pages[StepId.REVIEW_RUN].summary_label.text(),
        )

    def test_v2_migration_uses_independent_supported_pinterest_defaults(self):
        state = migrate_v2_config(
            {
                "text_generation_model": "gpt-image/1.5-text-to-image",
                "text_generation_ratio": "1:1",
                "reference_generation_model": "gpt-image/1.5-image-to-image",
            }
        )
        state.switch_mode(ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PIN_FORMAT_MODEL]

        self.assertEqual(state.pinterest.generation.model, "gpt-image-2")
        self.assertEqual(state.pinterest.generation.reference_model, "gpt-image-2")
        self.assertEqual(state.pinterest.generation.ratio, "9:16")
        self.assertEqual(state.pinterest.generation.reference_ratio, "9:16")
        self.assertEqual(page.ratio_combo.currentText(), "9:16")

    def test_each_text_model_uses_its_deterministic_reference_pair(self):
        expected_pairs = {
            "flux-2/flex-text-to-image": "flux-2/flex-image-to-image",
            "flux-2/pro-text-to-image": "flux-2/pro-image-to-image",
            "gpt-image/1.5-text-to-image": "gpt-image/1.5-image-to-image",
            "gpt-image-2": "gpt-image-2",
            "nano-banana-2": "nano-banana-2",
            "nano-banana-pro": "nano-banana-pro",
            "qwen-image-2": "qwen-image-2",
        }
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-model-pairs-") as temp:
            state = self.make_state(temp)
            reference_path = Path(temp) / "reference.png"
            Image.new("RGB", (4, 6), "white").save(reference_path)
            state.pinterest.prompts[1].references = [str(reference_path)]
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )
            page = controller.pages[StepId.PIN_FORMAT_MODEL]
            self.assertFalse(page.reference_advanced.isHidden())

            for index in range(page.model_combo.count()):
                page.model_combo.setCurrentIndex(index)
                text_model = str(page.model_combo.currentData())
                request = build_pinterest_run_request(
                    state,
                    {"kie_api_key": "test-key"},
                )
                review = controller.pages[StepId.REVIEW_RUN]
                review.refresh_from_state()
                self.assertEqual(
                    state.pinterest.generation.reference_model,
                    expected_pairs[text_model],
                )
                self.assertEqual(
                    request.settings["reference_generation_model"],
                    expected_pairs[text_model],
                )
                self.assertIn(text_model, review.summary_label.text())
                self.assertIn(
                    expected_pairs[text_model],
                    review.summary_label.text(),
                )

    def test_request_uses_existing_generation_without_processing(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="pinterest-v3-request-") as temp:
            state = self.make_state(temp)
            request = build_pinterest_run_request(
                state,
                {"kie_api_key": "test-key"},
            )
            estimate = estimate_pinterest_cost(state)
            worker = WorkerThread(**request.worker_kwargs())

        self.assertEqual(request.mode, "mode1_generate_only")
        self.assertEqual(len(request.generated_prompts), 4)
        self.assertFalse(request.settings["upscale"])
        self.assertFalse(request.settings["remove_bg"])
        self.assertFalse(request.settings["unsharp_enabled"])
        self.assertEqual(worker.mode, "mode1_generate_only")
        self.assertEqual(len(worker.generated_prompts), 4)
        self.assertEqual(estimate.request_count, 4)
        self.assertEqual(estimate.estimated_usd, Decimal("0.120"))

    def test_reference_prompt_remains_vertical_and_is_preflighted(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-reference-") as temp:
            image_path = Path(temp) / "reference.png"
            Image.new("RGB", (4, 6), "white").save(image_path)
            state = self.make_state(temp)
            state.pinterest.prompts[1].references = [str(image_path)]
            request = build_pinterest_run_request(
                state,
                {"kie_api_key": "test-key"},
            )

        self.assertEqual(
            request.settings["reference_generation_ratio"],
            "9:16",
        )
        self.assertEqual(
            request.generated_prompts[2]["references"],
            [str(image_path)],
        )

    def test_navigation_preserves_project_prompts_and_format(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-nav-") as temp:
            state = ProjectState(mode=ProjectMode.PINTEREST)
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )
            project = controller.pages[StepId.PROJECT]
            project.work_dir_edit.setText(temp)
            self.assertEqual(shell.go_next(), StepId.PROMPTS)
            prompts = controller.pages[StepId.PROMPTS]
            prompts.paste_edit.setPlainText("Kitchen idea\nGarden idea")
            prompts.paste_button.click()
            self.assertEqual(shell.go_next(), StepId.PROMPT_REVIEW)
            self.assertEqual(shell.go_next(), StepId.PIN_FORMAT_MODEL)
            format_page = controller.pages[StepId.PIN_FORMAT_MODEL]
            format_page.variants_spin.setValue(3)
            selected_ratio = format_page.ratio_combo.currentText()
            self.assertEqual(shell.go_back(), StepId.PROMPT_REVIEW)
            self.assertEqual(shell.go_back(), StepId.PROMPTS)

        self.assertEqual(state.common.project_name, "")
        self.assertEqual(
            [entry.prompt for entry in state.pinterest.prompts],
            ["Kitchen idea", "Garden idea"],
        )
        self.assertEqual(state.pinterest.generation.variants, 3)
        self.assertEqual(state.pinterest.generation.ratio, selected_ratio)

    def test_review_is_generation_only_and_run_requires_explicit_action(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-run-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=factory,
                authorization_provider=lambda: None,
            )

            self.assertEqual(factory.workers, [])
            self.assertIn(
                "Пакетный экспорт PNG",
                controller.review_page.pipeline_label.text(),
            )
            self.assertNotIn("Редактора текста", controller.review_page.warning_label.text())
            shell.go_next()

        self.assertEqual(len(factory.workers), 1)
        self.assertTrue(factory.workers[0].started)
        self.assertEqual(
            factory.workers[0].kwargs["mode"],
            "mode1_generate_only",
        )

    def test_missing_key_and_invalid_reference_block_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-guard-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {},
                worker_factory=factory,
            )
            self.assertIn(
                "KIE API Key",
                controller.review_page.requirements_label.text(),
            )
            shell.go_next()
            self.assertEqual(factory.workers, [])

            state.pinterest.prompts[0].references = ["https://"]
            controller._refresh_preflight()
            self.assertIn(
                "HTTPS",
                controller.review_page.requirements_label.text(),
            )

    def test_offscreen_route_keeps_navigation_visible_at_minimum_size(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-ui-") as temp:
            state = self.make_state(temp)
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                worker_factory=WorkerFactory(),
            )
            shell.resize(980, 700)
            shell.show()
            self.app.processEvents()

            self.assertTrue(shell.next_button.isVisible())
            self.assertTrue(shell.back_button.isVisible())
            for step, page in controller.pages.items():
                state.set_step(step)
                page.refresh_from_state()
                shell.refresh()
                self.app.processEvents()
                self.assertTrue(page.isVisible())
                self.assertTrue(page.accessibleName())
            shell.close()

    def test_module_has_no_worker_or_network_implementation(self):
        source = Path(v3_pinterest_flow.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
        }
        imported_roots = {
            alias.name.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        self.assertNotIn("WorkerThread", class_names)
        self.assertTrue(
            imported_roots.isdisjoint(
                {"requests", "urllib", "httpx", "aiohttp", "socket"}
            )
        )


if __name__ == "__main__":
    unittest.main()
