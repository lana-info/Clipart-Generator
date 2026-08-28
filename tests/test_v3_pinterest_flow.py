import ast
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QAbstractButton, QLabel

import v3_pinterest_flow
from v3_mode_selection import V3ApplicationView
from v3_pinterest_flow import (
    PinVariant,
    PinterestCopySuggestionService,
    PinterestFormatModelPage,
    PinterestPinPreviewPage,
    PinterestProductInputPage,
    PinterestPromptInputPage,
    PinterestReviewRunPage,
    build_pinterest_pin_series,
    build_pinterest_run_request,
    estimate_pinterest_cost,
    install_pinterest_flow,
)
from pinterest_pin_composer import ProductLayer, assert_product_pixels_preserved
from v3_clipart_flow import ClipartPromptReviewPage
from v3_project_state import (
    PinterestPinData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
    migrate_v2_config,
)
from v3_wizard import AppShell
from v3_run_queue import RunQueueSession


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

    @staticmethod
    def protected_product() -> ProductLayer:
        rgba = Image.new("RGBA", (24, 32), (23, 67, 121, 0))
        for x in range(5, 19):
            for y in range(4, 29):
                rgba.putpixel((x, y), (23, 67, 121, 255))
        return ProductLayer(
            "product.png",
            rgba=rgba,
            alpha_mask=rgba.getchannel("A"),
        )

    def test_pin_series_has_six_stable_slots_and_protects_product_pixels(self):
        """Removing a template/scene or bypassing protected composition must fail."""
        draft = PinterestPinData(
            product_paths=["product.png"],
            pin_title="Summer tote",
            pin_subtitle="For weekends",
            pin_cta="See details",
            style="clean editorial",
            background_description="sunlit market table",
        )
        calls: list[tuple[str, int]] = []

        def fake_background(prompt: str, slot_index: int) -> Image.Image:
            calls.append((prompt, slot_index))
            return Image.new("RGBA", (1000, 1500), (241, 228, 210, 255))

        variants = build_pinterest_pin_series(
            draft,
            product=self.protected_product(),
            generate_background=fake_background,
        )

        self.assertEqual(
            [variant.variant_id for variant in variants],
            [
                "template-01", "template-02", "template-03",
                "ai-scene-01", "ai-scene-02", "ai-scene-03",
            ],
        )
        self.assertEqual(
            [variant.variant_kind for variant in variants],
            ["template", "template", "template", "ai_scene", "ai_scene", "ai_scene"],
        )
        self.assertEqual([index for _, index in calls], [1, 2, 3])
        self.assertTrue(all(variant.status == "success" for variant in variants))
        self.assertTrue(all(not variant.retryable for variant in variants))
        self.assertTrue(all(variant.image is not None for variant in variants))
        for variant in variants:
            self.assertEqual(variant.source_product_path, "product.png")
            self.assertTrue(variant.product_layer_digest)
            self.assertNotIn("product.png", variant.scene_prompt)
            assert_product_pixels_preserved(
                self.protected_product().rgba,
                variant.image,
                product_box=variant.product_box,
            )

    def test_pin_series_keeps_templates_and_retryable_failed_scene_slots_offline(self):
        """Replacing a failed scene with a missing slot or raw provider error must fail."""
        draft = PinterestPinData(
            product_paths=["product.png"],
            background_description="secret api_key=not-for-metadata",
        )
        calls = 0

        def fake_background(_: str, __: int) -> Image.Image:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("provider failure api_key=not-for-metadata")
            return Image.new("RGBA", (1000, 1500), "white")

        variants = build_pinterest_pin_series(
            draft,
            product=self.protected_product(),
            generate_background=fake_background,
        )

        self.assertEqual(len(variants), 6)
        self.assertTrue(all(item.status == "success" for item in variants[:3]))
        failed = variants[4]
        self.assertEqual(failed.variant_id, "ai-scene-02")
        self.assertEqual(failed.status, "failed")
        self.assertTrue(failed.retryable)
        self.assertIsNone(failed.image)
        self.assertEqual(failed.error_code, "background_generation_failed")
        self.assertNotIn("not-for-metadata", failed.error_message)
        self.assertNotIn("not-for-metadata", failed.scene_prompt)
        self.assertEqual(variants[5].status, "success")

    def test_pin_series_stops_admitting_scene_backgrounds_after_cancellation(self):
        """Ignoring cancellation would continue provider work after the first scene."""
        calls: list[int] = []

        def fake_background(_: str, slot_index: int) -> Image.Image:
            calls.append(slot_index)
            return Image.new("RGBA", (1000, 1500), "white")

        variants = build_pinterest_pin_series(
            PinterestPinData(product_paths=["product.png"]),
            product=self.protected_product(),
            generate_background=fake_background,
            cancelled=lambda: len(calls) >= 1,
        )

        self.assertEqual(calls, [1])
        self.assertTrue(all(item.status == "success" for item in variants[:4]))
        self.assertTrue(all(item.status == "failed" for item in variants[4:]))
        self.assertTrue(all(item.retryable for item in variants[4:]))

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
            PinterestProductInputPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPT_REVIEW],
            ClipartPromptReviewPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PIN_FORMAT_MODEL],
            PinterestFormatModelPage,
        )

    def test_product_input_binds_selected_photo_copy_scene_and_output_folder(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-product-input-") as temp:
            first_product = Path(temp) / "first.png"
            second_product = Path(temp) / "second.png"
            Image.new("RGBA", (8, 10), "white").save(first_product)
            Image.new("RGBA", (8, 10), "black").save(second_product)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            shell = AppShell(state)
            controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
            page = controller.pages[StepId.PROMPTS]

            page.set_product_paths((str(first_product), str(second_product)))
            page.selected_product_combo.setCurrentIndex(1)
            page.title_edit.setText("Summer tote")
            page.subtitle_edit.setText("For weekend markets")
            page.cta_edit.setText("See details")
            page.style_edit.setText("Clean editorial")
            page.scene_edit.setText("Sunlit market table")
            page.output_dir_edit.setText(temp)

            self.assertEqual(state.pinterest.pin.product_paths, [str(first_product), str(second_product)])
            self.assertEqual(state.pinterest.pin.selected_product_index, 1)
            self.assertEqual(state.pinterest.pin.pin_title, "Summer tote")
            self.assertEqual(state.pinterest.pin.pin_subtitle, "For weekend markets")
            self.assertEqual(state.pinterest.pin.pin_cta, "See details")
            self.assertEqual(state.pinterest.pin.style, "Clean editorial")
            self.assertEqual(state.pinterest.pin.background_description, "Sunlit market table")
            self.assertEqual(state.output_dir_for_mode(ProjectMode.PINTEREST), temp)

    def test_copy_suggestions_preserve_only_user_provided_facts(self):
        suggestions = PinterestCopySuggestionService().suggest(
            {"title": "Linen apron", "subtitle": "Adjustable fit", "cta": "Shop now"},
            locale="en",
        )

        self.assertEqual(suggestions.title, "Linen apron")
        self.assertEqual(suggestions.subtitle, "Adjustable fit")
        self.assertEqual(suggestions.cta, "Shop now")
        localized_page = PinterestProductInputPage(
            v3_pinterest_flow._pinterest_project_adapter(
                ProjectState(mode=ProjectMode.PINTEREST)
            ),
            lambda: None,
            locale="en-US",
        )
        self.assertEqual(localized_page.card.title_label.text(), "Product and pin copy")

    def test_install_propagates_locale_to_real_pinterest_pages(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(
            shell,
            worker_factory=WorkerFactory(),
            locale="en-US",
        )

        self.assertEqual(
            controller.pages[StepId.PROMPTS].card.title_label.text(),
            "Product and pin copy",
        )
        self.assertEqual(
            controller.pages[StepId.RESULTS].card.title_label.text(),
            "Pinterest pin preview",
        )
        self.assertEqual(
            controller.pages[StepId.PIN_FORMAT_MODEL].card.title_label.text(),
            "Format and model",
        )
        self.assertEqual(
            controller.pages[StepId.PROCESSING_OPTIONS].accessibleName(),
            "Image processing",
        )
        self.assertEqual(
            controller.pages[StepId.REVIEW_RUN].card.description_label.text(),
            "Review the image package and cost before explicitly starting it.",
        )

    def test_legacy_cleanup_draft_does_not_reach_pinterest_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-diagnostics-") as temp:
            state = self.make_state(temp)
            payload = state.to_dict()
            payload["pinterest"]["operations"].update(
                {"remove_background": True, "remove_exif": True, "trim": True}
            )
            restored = ProjectState.from_dict(payload)
            journal = Mock()
            request = build_pinterest_run_request(
                restored,
                {"kie_api_key": "test-key"},
            )

            RunQueueSession(
                request,
                ProjectMode.PINTEREST,
                diagnostic_journal=journal,
            )

            details = journal.record.call_args.kwargs["details"]
            self.assertNotIn("background_removal", details["enabled_stages"])
            self.assertNotIn("metadata_cleanup", details["enabled_stages"])
            self.assertNotIn("trim", details["enabled_stages"])

    def test_preview_has_six_selected_product_slots_and_local_acceptance_apis(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-preview-") as temp:
            first_product = Path(temp) / "first.png"
            second_product = Path(temp) / "second.png"
            Image.new("RGBA", (8, 10), "white").save(first_product)
            Image.new("RGBA", (8, 10), "black").save(second_product)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.pinterest.pin.product_paths = [str(first_product), str(second_product)]
            state.pinterest.pin.selected_product_index = 1
            state.pinterest.results = [
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="template-01",
                    variant_kind="template",
                    source_product_path=str(second_product),
                    output_path=str(Path(temp) / "accepted.png"),
                    accepted=True,
                    status="success",
                    product_layer_digest="protected-digest",
                )
            ]
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(shell, worker_factory=factory)
            page = controller.pages[StepId.RESULTS]

            self.assertEqual(len(page.variant_cards), 6)
            self.assertEqual(
                [result.source_product_path for result in state.pinterest.results],
                [str(second_product)] * 6,
            )
            self.assertEqual(page.export_accepted(), (str(Path(temp) / "accepted.png"),))

            page.set_variant_accepted("ai-scene-01", True)
            page.regenerate_variant("ai-scene-01")

            retried = next(
                result for result in state.pinterest.results if result.variant_id == "ai-scene-01"
            )
            self.assertFalse(retried.accepted)
            self.assertEqual(retried.status, "pending")
            self.assertTrue(retried.retryable)
            self.assertEqual(factory.workers, [])

    def test_regeneration_clears_stale_export_and_fidelity_metadata(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.results = [
            v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                output_path="old-result.png",
                accepted=True,
                status="success",
                product_layer_digest="protected-digest",
                export_status="exported",
            )
        ]
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())

        controller.pages[StepId.RESULTS].regenerate_variant("template-01")

        result = state.pinterest.results[0]
        self.assertEqual(result.status, "pending")
        self.assertEqual(result.output_path, "")
        self.assertEqual(result.product_layer_digest, "")
        self.assertEqual(result.export_status, "not_exported")

    def test_worker_completion_populates_preview_slots_from_existing_queue(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-completion-") as temp:
            output_dir = Path(temp) / "output"
            output_dir.mkdir()
            state = self.make_state(temp)
            state.pinterest.prompts = [PromptEntry(f"Pin {index}") for index in range(1, 7)]
            state.pinterest.generation.variants = 1
            state.set_output_dir_for_mode(str(output_dir), ProjectMode.PINTEREST)
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=factory,
                authorization_provider=lambda: None,
            )

            shell.go_next()
            worker = factory.workers[0]
            for index in range(1, 7):
                result_path = output_dir / f"pin-{index}.png"
                Image.new("RGB", (4, 6), "white").save(result_path)
                worker.progress.emit(f"[{index}/6] Генерация")
                worker.progress.emit(f"Итог сохранён: {result_path}")
            worker.started = False
            worker.finished.emit("Готово (6/6)")
            self.app.processEvents()

            self.assertEqual(
                [result.status for result in state.pinterest.results],
                ["success"] * 6,
            )
            self.assertEqual(
                [Path(result.output_path).name for result in state.pinterest.results],
                [f"pin-{index}.png" for index in range(1, 7)],
            )
            card = controller.pages[StepId.RESULTS].variant_cards["template-01"]
            self.assertIn("template-01", card.accessibleName())
            self.assertTrue(
                any(
                    label.pixmap() is not None and not label.pixmap().isNull()
                    for label in card.findChildren(QLabel)
                )
            )

    def test_worker_error_marks_all_preview_slots_failed(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-worker-error-") as temp:
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

            shell.go_next()
            factory.workers[0].error.emit("provider failed")
            self.app.processEvents()

            self.assertEqual(
                [result.status for result in state.pinterest.results],
                ["failed"] * 6,
            )

    def test_preview_rebinds_existing_slots_to_the_selected_product(self):
        """A source switch must not turn the fixed six-slot series into two products."""
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.pin.product_paths = ["first.png", "selected.png"]
        state.pinterest.pin.selected_product_index = 1
        state.pinterest.results = [
            v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                variant_kind="template",
                source_product_path="first.png",
            )
        ]
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())

        controller.pages[StepId.RESULTS]

        self.assertEqual(
            [result.source_product_path for result in state.pinterest.results],
            ["selected.png"] * 6,
        )

    def test_text_only_edits_keep_existing_product_fidelity_evidence(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.results = [
            v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                source_product_path="product.png",
                output_path="result.png",
                accepted=True,
                status="success",
                product_layer_digest="protected-digest",
            )
        ]
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPTS]

        page.title_edit.setText("Text-only revision")

        result = state.pinterest.results[0]
        self.assertEqual(result.output_path, "result.png")
        self.assertEqual(result.product_layer_digest, "protected-digest")

    def test_preview_warns_when_successful_result_has_no_protected_layer_evidence(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.results = [
            v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                source_product_path="product.png",
                output_path="result.png",
                status="success",
            )
        ]
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.RESULTS]

        warning_copy = " ".join(
            label.text() for label in page.findChildren(QLabel)
        )
        self.assertIn("точность товара", warning_copy.casefold())

    def test_pinterest_pages_omit_clipart_transparency_and_background_cleanup_controls(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        pages = (
            controller.pages[StepId.PROMPTS],
            controller.pages[StepId.PROCESSING_OPTIONS],
            controller.pages[StepId.RESULTS],
        )
        state.set_step(StepId.PROCESSING_OPTIONS)
        shell.refresh()
        shell.show()
        self.app.processEvents()

        visible_copy = " ".join(
            widget.text()
            for page in pages
            for widget in (*page.findChildren(QLabel), *page.findChildren(QAbstractButton))
            if widget.isVisible()
        ).casefold()
        shell.close()
        self.assertNotIn("прозрач", visible_copy)
        self.assertNotIn("удалить фон", visible_copy)
        self.assertNotIn("очистить служебные", visible_copy)

    def test_process_more_starts_clean_pinterest_workflow_at_first_step(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.prompts = [PromptEntry("old pin prompt")]
        state.set_step(StepId.RESULTS)
        shell = AppShell(state)
        controller = install_pinterest_flow(shell)

        controller.run_queue.process_more()
        self.app.processEvents()

        self.assertEqual(state.current_step, StepId.PROJECT)
        self.assertEqual(state.pinterest.prompts, [])
        self.assertIs(shell.current_page, controller.pages[StepId.PROJECT])
        self.assertIsInstance(
            controller.pages[StepId.REVIEW_RUN],
            PinterestReviewRunPage,
        )

    def test_prompt_review_deletes_selected_pinterest_prompt(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.prompts = [
            PromptEntry("First pin"),
            PromptEntry("Second pin"),
        ]
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROMPT_REVIEW]
        page.table.selectRow(0)

        page.delete_button.click()

        self.assertEqual(
            [entry.prompt for entry in state.pinterest.prompts],
            ["Second pin"],
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

    def test_pinterest_processing_can_be_skipped(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.operations.upscale_before = False
        adapter = v3_pinterest_flow._pinterest_project_adapter(state)
        page = v3_pinterest_flow.PinterestProcessingPage(adapter, lambda: None)

        self.assertNotIn("processing_operation_required", page.validation_issues())

    def test_pinterest_processing_edits_persist_allowed_operations_and_provider(self):
        """Dropping the adapter assignment must leave the persisted fields unchanged."""
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(shell, worker_factory=WorkerFactory())
        page = controller.pages[StepId.PROCESSING_OPTIONS]

        page.operation_widgets["upscale_before"].setChecked(True)
        provider = page.operation_widgets["upscale_before_provider"]
        provider.setCurrentIndex(provider.findData("local_realesrgan"))
        page.operation_widgets["local_realesrgan_scale"].setCurrentIndex(
            page.operation_widgets["local_realesrgan_scale"].findData(2)
        )
        page.operation_widgets["unsharp"].setChecked(True)

        persisted = ProjectState.from_dict(state.to_dict()).pinterest.operations
        self.assertTrue(persisted.upscale_before)
        self.assertEqual(persisted.upscale_before_provider, "local_realesrgan")
        self.assertEqual(persisted.local_realesrgan_scale, 2)
        self.assertTrue(persisted.unsharp)

    def test_successful_new_run_clears_stale_result_acceptance_and_metadata(self):
        """Starting another run must not retain acceptance or evidence from an old file."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-new-run-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            state.pinterest.results = [
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="template-01",
                    source_product_path="product.png",
                    output_path="old-result.png",
                    accepted=True,
                    status="success",
                    product_layer_digest="old-protected-digest",
                    export_status="exported",
                )
            ]
            shell = AppShell(state)
            controller = install_pinterest_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
                worker_factory=WorkerFactory(),
                authorization_provider=lambda: None,
            )

            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)
            controller.start()

            result = next(
                item
                for item in state.pinterest.results
                if item.variant_id == "template-01"
            )
            self.assertEqual(result.status, "pending")
            self.assertFalse(result.accepted)
            self.assertEqual(result.product_layer_digest, "")
            self.assertEqual(result.export_status, "not_exported")

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
            state.pinterest.prompts = [
                PromptEntry("Kitchen idea"),
                PromptEntry("Garden idea"),
            ]
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
            prompts.title_edit.setText("Kitchen collection")
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
            review_copy = " ".join(
                label.text()
                for label in controller.review_page.findChildren(QLabel)
            )
            self.assertNotIn("API-ключи не сохраняются", review_copy)
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
