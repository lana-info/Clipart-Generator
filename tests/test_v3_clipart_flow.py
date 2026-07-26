import ast
import csv
import os
import tempfile
import unittest
from dataclasses import fields as dataclass_fields
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QCheckBox
from PIL import Image

import v3_clipart_flow
from v3_clipart_flow import (
    MAX_CLIPART_REQUESTS,
    ClipartFlowError,
    ClipartProcessingPage,
    ClipartProjectPage,
    ClipartPromptInputPage,
    ClipartPromptReviewPage,
    ClipartReviewRunPage,
    build_clipart_run_request,
    clipart_pipeline_steps,
    estimate_clipart_cost,
    install_clipart_flow,
    missing_runtime_requirements,
    parse_prompt_csv,
)
from v3_mode_selection import V3ApplicationView
from v3_project_state import (
    MAX_PROMPT_ENTRIES,
    ImageOperationData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
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
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
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


class V3ClipartFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_state(self, work_dir):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.common.project_name = "Ocean pack"
        state.common.work_dir = str(work_dir)
        reference_path = Path(work_dir) / "reference.png"
        Image.new("RGBA", (2, 2), (255, 255, 255, 255)).save(reference_path)
        state.clipart.prompts = [
            PromptEntry("Baby whale"),
            PromptEntry("Baby turtle", [str(reference_path)]),
        ]
        state.clipart.generation.variants = 2
        return state

    def test_application_view_installs_all_six_clipart_pages(self):
        factory = WorkerFactory()
        view = V3ApplicationView(
            runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
            worker_factory=factory,
        )
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()

        controller = view.shell.clipart_flow_controller
        self.assertEqual(set(controller.pages), set(view.shell.state.route))
        self.assertIsInstance(controller.pages[StepId.PROJECT], ClipartProjectPage)
        self.assertIsInstance(
            controller.pages[StepId.PROMPTS],
            ClipartPromptInputPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPT_REVIEW],
            ClipartPromptReviewPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROCESSING_OPTIONS],
            ClipartProcessingPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.REVIEW_RUN],
            ClipartReviewRunPage,
        )

    def test_project_and_prompt_data_survive_forward_and_back_navigation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-flow-") as temp:
            state = ProjectState(mode=ProjectMode.CLIPART)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )
            project_page = controller.pages[StepId.PROJECT]
            project_page.project_name_edit.setText("Forest pack")
            project_page.work_dir_edit.setText(temp)
            self.assertEqual(shell.go_next(), StepId.PROMPTS)

            prompt_page = controller.pages[StepId.PROMPTS]
            prompt_page.source_combo.setCurrentIndex(1)
            prompt_page.paste_edit.setPlainText("Fox\nBear")
            prompt_page.paste_button.click()
            self.assertEqual(shell.go_next(), StepId.PROMPT_REVIEW)

            review_page = controller.pages[StepId.PROMPT_REVIEW]
            review_page.table.item(0, 0).setText("Red fox")
            review_page.table.item(0, 1).setText("D:/fox.png")
            self.assertEqual(shell.go_back(), StepId.PROMPTS)
            self.assertEqual(shell.go_back(), StepId.PROJECT)

            self.assertEqual(state.common.project_name, "Forest pack")
            self.assertEqual(state.common.work_dir, temp)
            self.assertEqual(
                [entry.prompt for entry in state.clipart.prompts],
                ["Red fox", "Bear"],
            )
            self.assertEqual(
                state.clipart.prompts[0].references,
                ["D:/fox.png"],
            )

    def test_generator_page_creates_editable_prompt_entries(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPTS]
        page.theme_edit.setText("Woodland babies")
        page.subjects_edit.setPlainText("Fox\nBear")
        page.count_spin.setValue(3)

        self.assertEqual(state.clipart.prompt_generator.theme, "Woodland babies")
        self.assertEqual(state.clipart.prompt_generator.subjects, ["Fox", "Bear"])
        restored = ProjectState.from_dict(state.to_dict())
        self.assertEqual(restored.clipart.prompt_generator.count, 3)

        page.generate_button.click()
        self.assertEqual(len(state.clipart.prompts), 3)
        self.assertTrue(all(isinstance(item, PromptEntry) for item in state.clipart.prompts))
        state.clipart.prompts[0].prompt = "Manual edit"
        self.assertEqual(state.clipart.prompts[0].prompt, "Manual edit")

    def test_csv_import_preserves_quoted_text_and_bounded_references(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-csv-") as temp:
            path = Path(temp) / "prompts.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Prompt", "References"])
                writer.writerow(["Whale, watercolor", "one.png | two.png"])

            entries = parse_prompt_csv(path)

        self.assertEqual(entries[0].prompt, "Whale, watercolor")
        self.assertEqual(entries[0].references, ["one.png", "two.png"])

    def test_invalid_folder_and_malformed_csv_fail_closed(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROJECT]
        page.work_dir_edit.setText("Z:/definitely/missing/clipart-folder")

        self.assertEqual(shell.go_next(), StepId.PROJECT)
        self.assertIn("недоступна", shell.validation_label.text())

        with tempfile.TemporaryDirectory(prefix="clipart-v3-bad-csv-") as temp:
            path = Path(temp) / "broken.csv"
            path.write_text('Prompt\n"' + ("x" * 200_000), encoding="utf-8")
            with self.assertRaises(ClipartFlowError):
                parse_prompt_csv(path)
    def test_paste_add_and_duplicate_enforce_prompt_entry_limit(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        input_page = controller.pages[StepId.PROMPTS]
        input_page.paste_edit.setPlainText(
            "\n".join(f"Prompt {index}" for index in range(MAX_PROMPT_ENTRIES + 1))
        )
        input_page.paste_button.click()
        self.assertEqual(state.clipart.prompts, [])
        self.assertIn("Максимум", input_page.card.status_label.text())

        state.clipart.prompts = [PromptEntry("First")]
        review_page = controller.pages[StepId.PROMPT_REVIEW]
        review_page.refresh_from_state()
        review_page.table.setCurrentCell(0, 0)
        state.clipart.prompts = [PromptEntry(f"Prompt {index}") for index in range(MAX_PROMPT_ENTRIES)]
        review_page._add()
        review_page._duplicate()
        self.assertEqual(len(state.clipart.prompts), MAX_PROMPT_ENTRIES)
        self.assertIn("Максимум", review_page.card.status_label.text())
    def test_processing_page_exposes_every_supported_operation_setting(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROCESSING_OPTIONS]
        field_names = {definition.name for definition in dataclass_fields(ImageOperationData)}

        self.assertEqual(
            set(page.operation_widgets)
            | {"visible_mark_cleanup_mode", "upscale_factor"},
            field_names,
        )
        self.assertIsInstance(
            page.operation_widgets["remove_background"],
            QCheckBox,
        )
        page.operation_widgets["trim"].setChecked(True)
        self.assertTrue(state.clipart.operations.trim)
        self.assertIn("Trim", page.pipeline_label.text())

    def test_pipeline_summary_matches_real_worker_order(self):
        operations = ImageOperationData(
            visible_mark_cleanup=True,
            upscale_before=True,
            unsharp=True,
            remove_background=True,
            upscale_after=True,
            edge_shrink=True,
            trim=True,
            remove_xmp=True,
            export_300_dpi=True,
        )

        self.assertEqual(
            clipart_pipeline_steps(operations),
            (
                "Генерация изображения",
                "Удаление видимой метки",
                "Апскейл до удаления фона",
                "Unsharp Mask",
                "Удаление фона",
                "Апскейл после удаления фона",
                "Очистка края alpha",
                "Trim",
                "Очистка данных файла",
                "Экспорт 300 DPI",
                "Экспорт PNG",
            ),
        )

    def test_cost_and_worker_request_include_variants_references_and_operations(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-run-") as temp:
            state = self.make_state(temp)
            state.runtime.timeout = 42
            request = build_clipart_run_request(
                state,
                {"kie_api_key": "test-key", "timeout": 999999},
            )
            estimate = estimate_clipart_cost(state)

        self.assertEqual(request.mode, "mode_both")
        self.assertEqual(len(request.generated_prompts), 4)
        self.assertEqual(request.generated_prompts[2]["references"], [str(Path(temp) / "reference.png")])
        self.assertEqual(request.settings["text_generation_model"], state.clipart.generation.model)
        self.assertEqual(request.settings["remove_bg"], True)
        self.assertEqual(request.settings["timeout"], 42)
        self.assertEqual(estimate.request_count, 12)
        self.assertEqual(estimate.estimated_usd, Decimal("0.900"))
        self.assertTrue(estimate.complete)

    def test_request_is_accepted_by_real_worker_constructor(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="clipart-v3-real-worker-") as temp:
            state = self.make_state(temp)
            state.runtime.timeout = 42
            state.clipart.operations.remove_xmp = True
            request = build_clipart_run_request(
                state,
                {"kie_api_key": "test-key", "timeout": 999999},
            )
            worker = WorkerThread(**request.worker_kwargs())

        self.assertEqual(worker.mode, "mode_both")
        self.assertEqual(len(worker.generated_prompts), 4)
        self.assertEqual(worker.text_generation_model, state.clipart.generation.model)
        self.assertTrue(worker.remove_bg)
        self.assertTrue(worker.metadata_cleanup_options.remove_xmp)
        self.assertEqual(worker.timeout, 42)
        self.assertNotIn("test-key", repr(request))
    def test_wizard_run_uses_injected_legacy_worker_without_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-launch-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=factory,
            )
            started = []
            controller.started.connect(started.append)

            shell.go_next()

        self.assertEqual(len(factory.workers), 1)
        self.assertTrue(factory.workers[0].started)
        self.assertEqual(factory.workers[0].kwargs["mode"], "mode_both")
        self.assertEqual(len(started), 1)

    def test_missing_key_and_excessive_request_count_fail_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-guard-") as temp:
            state = self.make_state(temp)
            request = build_clipart_run_request(state, {})
            self.assertEqual(missing_runtime_requirements(request), ("KIE API Key",))

            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {},
                worker_factory=WorkerFactory(),
            )
            self.assertIn("KIE API Key", controller.review_page.requirements_label.text())

            state.clipart.prompts = [
                PromptEntry(f"Prompt {index}")
                for index in range((MAX_CLIPART_REQUESTS // 100) + 1)
            ]
            state.clipart.generation.variants = 100
            with self.assertRaisesRegex(ClipartFlowError, "Максимум"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_runtime_settings_are_allowlisted_and_project_bounds_win(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-runtime-") as temp:
            state = self.make_state(temp)
            state.runtime.timeout = 600
            state.runtime.retries = 10
            request = build_clipart_run_request(
                state,
                {
                    "kie_api_key": "secret-key",
                    "timeout": 10**30,
                    "retries": 10**30,
                    "unexpected": "ignored",
                },
            )

        self.assertEqual(request.settings["timeout"], 600)
        self.assertEqual(request.settings["retries"], 10)
        self.assertNotIn("unexpected", request.settings)
        self.assertNotIn("secret-key", repr(request))

    def test_unknown_processing_model_fails_and_never_shows_partial_price(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-model-") as temp:
            state = self.make_state(temp)
            state.clipart.operations.kie_upscale_model = "unknown/upscale"
            estimate = estimate_clipart_cost(state)

            self.assertFalse(estimate.complete)
            self.assertNotIn("$", estimate.summary)
            with self.assertRaisesRegex(ClipartFlowError, "не поддерживается"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_missing_local_reference_is_reported_before_run(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-reference-") as temp:
            state = self.make_state(temp)
            Path(state.clipart.prompts[1].references[0]).unlink()
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
            )

            status = controller.review_page.requirements_label.text()
            self.assertIn("reference.png", status)
            self.assertIn("не найден", status)

    def test_processing_page_hides_irrelevant_provider_parameters(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROCESSING_OPTIONS]
        widgets = page.operation_widgets

        self.assertTrue(widgets["local_ben2_alpha_threshold"].isHidden())
        widgets["remove_background_provider"].setCurrentIndex(
            widgets["remove_background_provider"].findData("local_ben2")
        )
        self.assertFalse(widgets["local_ben2_alpha_threshold"].isHidden())
        self.assertTrue(widgets["kie_remove_bg_model"].isHidden())
        widgets["unsharp"].setChecked(True)
        self.assertFalse(widgets["unsharp_amount"].isHidden())
        widgets["remove_background"].setChecked(False)
        self.assertTrue(widgets["remove_background_provider"].isHidden())

    def test_local_upscale_is_blocked_before_paid_generation_when_tool_is_missing(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-local-tool-") as temp:
            state = self.make_state(temp)
            state.clipart.operations.upscale_before_provider = "local_realesrgan"
            request = build_clipart_run_request(state, {"kie_api_key": "test-key"})

        missing = missing_runtime_requirements(request)
        self.assertTrue(any("Real-ESRGAN" in item for item in missing))

    def test_reference_preflight_rejects_malformed_url_and_non_image_file(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-ref-guard-") as temp:
            state = self.make_state(temp)
            state.clipart.prompts[1].references = ["https://"]
            with self.assertRaisesRegex(ClipartFlowError, "HTTPS"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

            text_path = Path(temp) / "not-image.txt"
            text_path.write_text("not an image", encoding="utf-8")
            state.clipart.prompts[1].references = [str(text_path)]
            with self.assertRaisesRegex(ClipartFlowError, "изображением"):
                build_clipart_run_request(state, {"kie_api_key": "test-key"})

    def test_worker_factory_and_signal_errors_redact_runtime_secrets(self):
        secret = "TEST-SECRET-KEY"
        with tempfile.TemporaryDirectory(prefix="clipart-v3-redact-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)

            def failing_factory(**_):
                raise ValueError(f"provider rejected {secret}")

            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": secret},
                worker_factory=failing_factory,
            )
            controller.start()
            self.assertNotIn(secret, controller.review_page.run_status_label.text())

            controller._runtime_settings = {"kie_api_key": secret}
            errors = []
            controller.error.connect(errors.append)
            controller._error(f"worker failed bearer abc and {secret}")
            self.assertNotIn(secret, errors[-1])
            self.assertNotIn("bearer abc", errors[-1].lower())

    def test_csv_and_table_reject_oversized_input_without_truncation(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-limits-") as temp:
            csv_path = Path(temp) / "too-many.csv"
            with csv_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Prompt"])
                for index in range(MAX_PROMPT_ENTRIES + 1):
                    writer.writerow([f"Prompt {index}"])
            with self.assertRaisesRegex(ClipartFlowError, "Максимум"):
                parse_prompt_csv(csv_path)

        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.prompts = [PromptEntry("Original")]
        shell = AppShell(state)
        controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPT_REVIEW]
        page.table.item(0, 0).setText("x" * (20_000 + 1))
        self.assertEqual(state.clipart.prompts[0].prompt, "Original")
        self.assertEqual(page.table.item(0, 0).text(), "Original")
        self.assertIn("длину", page.card.status_label.text())

    def test_cost_distinguishes_images_from_paid_provider_calls(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-cost-count-") as temp:
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.common.work_dir = temp
            state.clipart.prompts = [PromptEntry("One image")]
            estimate = estimate_clipart_cost(state)
            review = ClipartReviewRunPage(state)

        self.assertEqual(estimate.request_count, 3)
        self.assertIn("3 запросов", estimate.summary)
        self.assertIn("изображений 1", review.summary_label.text())

    def test_offscreen_layout_keeps_navigation_visible_at_minimum_size(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-ui-") as temp:
            state = self.make_state(temp)
            shell = AppShell(state)
            controller = install_clipart_flow(shell, worker_factory=WorkerFactory())
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

    def test_module_does_not_duplicate_worker_or_network_transport(self):
        source = Path(v3_clipart_flow.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        class_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)
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
