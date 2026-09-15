from studio_workflow_host import WorkflowHost
import ast
import os
import re
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QAbstractButton, QLabel

import v3_localization
import v3_pinterest_flow
from v3_mode_selection import V3ApplicationView
from v3_pinterest_flow import (
    PinVariant,
    PinterestCopySuggestionService,
    PinterestCopyLayoutPage,
    PinterestFormatModelPage,
    PinterestPinRunRequest,
    PinterestPinWorkerAdapter,
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
from v3_clipart_flow import (
    ClipartFlowError,
    ClipartGenerationPage,
    ClipartPromptReviewPage,
    ClipartReviewRunPage,
)
from v3_project_state import (
    PinterestPinData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
    migrate_v2_config,
)
from v3_wizard import AppShell
from v3_run_queue import RunItemStatus, RunQueueSession
from workflow_definitions import workflow_for_mode


class UnexpectedPinterestOrchestrator:
    def build(self, request, *, cancelled):
        del request, cancelled
        raise RuntimeError("background provider api_key=do-not-disclose")


class CancellationAwarePinterestOrchestrator:
    def __init__(self, variants=()) -> None:
        self.started = threading.Event()
        self.released = threading.Event()
        self.variants = tuple(variants)
        self.cancelled: bool | None = None
        self.thread_id: int | None = None

    def build(self, request, *, cancelled):
        del request
        self.thread_id = threading.get_ident()
        self.started.set()
        self.released.wait(timeout=5)
        self.cancelled = cancelled()
        return self.variants

    @staticmethod
    def output_path(request, variant) -> Path:
        return Path(request.settings["output_dir"]) / f"pinterest-{variant.variant_id}.png"


class StaticPinterestOrchestrator:
    def __init__(self, variants) -> None:
        self.variants = tuple(variants)

    def build(self, request, *, cancelled):
        del request, cancelled
        return self.variants


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


class PinterestPromptOnlyFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_prompt_only_pinterest_uses_core_image_gateway_not_raw_runtime_settings(self):
        source = Path(v3_pinterest_flow.__file__).read_text(encoding="utf-8")
        self.assertNotIn("self.shell.runtime_settings()", source)
        self.assertIn("self.shell.image_run_launch(", source)

    def test_application_installs_the_active_prompt_only_route(self):
        view = V3ApplicationView(
            runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
            worker_factory=WorkerFactory(),
        )
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        self.app.processEvents()

        controller = view.shell.workflow_controller("pinterest")
        self.assertEqual(
            tuple(controller.pages),
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PROMPT_REVIEW,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )

    def test_deferred_selective_regeneration_uses_real_pinterest_worker_path(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-regeneration-production-") as temp:
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp
            product_path = Path(temp) / "product.png"
            Image.new("RGBA", (8, 10), (20, 40, 60, 255)).save(product_path)
            state.pinterest.pin.product_paths = [str(product_path)]
            state.set_output_dir_for_mode(temp, ProjectMode.PINTEREST)
            shell = AppShell(state)
            controller = install_pinterest_flow(
                WorkflowHost(
                    shell,
                    "pinterest",
                    authorization_provider=lambda: None,
                    run_preparer=lambda: None,
                )
            )
            preview = PinterestPinPreviewPage(
                controller.adapter_state,
                shell.mark_dirty,
                regenerate_handler=controller.regenerate_variant,
            )
            controller.pages._factories.pop(StepId.RESULTS, None)
            controller.pages._materialized[StepId.RESULTS] = preview

            request = controller.regenerate_variant("template-01")

            self.assertIsInstance(request, PinterestPinRunRequest)
            self.assertIsInstance(controller.worker, PinterestPinWorkerAdapter)
            self.assertEqual(
                request.queue_items,
                ({"variant_id": "template-01", "variant_kind": "template"},),
            )
            self.assertTrue(controller.worker.wait(2_000))
            self.app.processEvents()

    def test_module_owned_pinterest_worker_is_blocked_when_core_save_fails(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-core-save-") as temp:
            gate = Mock()
            gate.authorize_run = Mock(return_value=None)
            view = V3ApplicationView(
                draft_path=Path(temp) / "draft.json", license_gate=gate
            )
            view._handle_mode_selected(ProjectMode.PINTEREST.value)
            controller = view.shell.workflow_controller("pinterest")
            request = PinterestPinRunRequest(
                work_dir=temp,
                product_path=str(Path(temp) / "product.png"),
                pin=PinterestPinData(product_paths=[str(Path(temp) / "product.png")]),
                settings={"output_dir": temp},
                queue_items=({"variant_id": "template-01", "variant_kind": "template"},),
            )
            with patch.object(
                view._project_store, "save", side_effect=OSError("disk")
            ), patch.object(v3_pinterest_flow, "PinterestPinWorkerAdapter") as worker_type:
                with self.assertRaises(OSError):
                    controller.create_worker_for_request(request)
                worker_type.assert_not_called()
            view.close()
            view.deleteLater()

    def test_pinterest_ready_prompt_omits_clipart_chroma_controls(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        page = PinterestPromptInputPage(state, lambda: None)

        self.assertFalse(hasattr(page, "paste_chroma_enabled"))
        self.assertTrue(hasattr(page, "add_references_button"))
        self.assertTrue(hasattr(page, "add_prompt_button"))

    def test_pinterest_reference_profile_is_a_plain_conditional_control(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.pinterest.prompts = [
            PromptEntry("Text-only pin"),
            PromptEntry("Pin with reference", ["reference.png"]),
        ]
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
        page = controller.pages[StepId.PIN_FORMAT_MODEL]

        self.assertFalse(hasattr(page, "reference_advanced"))
        self.assertFalse(page.primary_scope_label.isVisible())
        self.assertFalse(page.model_capability_label.isVisible())
        self.assertFalse(page.card.description_label.isVisible())
        self.assertFalse(page.reference_model_combo.isHidden())
        self.assertFalse(page.reference_ratio_combo.isHidden())
        self.assertFalse(page.reference_resolution_combo.isHidden())
        page.reference_model_combo.setCurrentIndex(
            page.reference_model_combo.findData("gpt-image/1.5-image-to-image")
        )
        page.reference_ratio_combo.setCurrentText("2:3")
        self.assertEqual(
            state.pinterest.generation.reference_model,
            "gpt-image/1.5-image-to-image",
        )
        self.assertEqual(state.pinterest.generation.reference_ratio, "2:3")
        self.assertFalse(page.ratio_preview.isHidden())

    def test_clipart_generation_has_the_same_ratio_preview(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        page = ClipartGenerationPage(state, lambda: None)

        self.assertEqual(page.ratio_preview_label.text(), page.ratio_combo.currentText())
        self.assertFalse(page.ratio_preview.isHidden())

    def test_qwen_text_model_offers_only_contract_supported_ratios(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        page = ClipartGenerationPage(state, lambda: None)

        page.model_combo.setCurrentIndex(page.model_combo.findData("qwen-image-2"))

        ratios = {
            page.ratio_combo.itemText(index)
            for index in range(page.ratio_combo.count())
        }
        self.assertNotIn("2:3", ratios)
        self.assertEqual(page.ratio_combo.currentText(), state.clipart.generation.ratio)


@unittest.skip(
    "Six-slot product/template Pinterest workflow is deferred; active MVP is prompt-only"
)
class V3PinterestFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def wait_for_worker(cls, worker: QThread, timeout: float = 15.0) -> bool:
        deadline = time.monotonic() + timeout
        while worker.isRunning() and time.monotonic() < deadline:
            cls.app.processEvents()
            time.sleep(0.01)
        cls.app.processEvents()
        return not worker.isRunning()

    def make_state(self, work_dir):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        state.common.project_name = "Summer pins"
        state.common.work_dir = str(work_dir)
        product_path = Path(work_dir) / "product.png"
        image = Image.new("RGBA", (8, 10), (20, 40, 60, 0))
        image.putpixel((4, 5), (20, 40, 60, 255))
        image.save(product_path)
        state.pinterest.pin.product_paths = [str(product_path)]
        state.set_output_dir_for_mode(str(work_dir), ProjectMode.PINTEREST)
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

    def test_pinterest_request_registers_its_own_six_slots_in_the_shared_queue(self):
        """Routing this request as clipart would lose the stable pin-slot contract."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-request-") as temp:
            product_path = Path(temp) / "product.png"
            Image.new("RGBA", (8, 10), (20, 40, 60, 0)).save(product_path)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp
            state.pinterest.pin.product_paths = [str(product_path)]

            request = build_pinterest_run_request(state)
            session = RunQueueSession(request, ProjectMode.PINTEREST)

            self.assertIsInstance(request, PinterestPinRunRequest)
            self.assertEqual(
                [item.payload["variant_id"] for item in session.items],
                [
                    "template-01", "template-02", "template-03",
                    "ai-scene-01", "ai-scene-02", "ai-scene-03",
                ],
            )
            self.assertEqual(
                [item.payload["variant_kind"] for item in session.items],
                ["template", "template", "template", "ai_scene", "ai_scene", "ai_scene"],
            )

    def test_pinterest_retry_request_contains_only_the_failed_ai_slot(self):
        """Treating a Pinterest retry as clipart would raise TypeError or regenerate every slot."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-retry-") as temp:
            state = self.make_state(temp)
            request = build_pinterest_run_request(state)
            session = RunQueueSession(request, ProjectMode.PINTEREST)
            session.items[4].status = RunItemStatus.FAILED
            session.running = False

            retry = session.prepare_retry()

        self.assertIsInstance(retry, PinterestPinRunRequest)
        self.assertEqual(
            retry.queue_items,
            ({"variant_id": "ai-scene-02", "variant_kind": "ai_scene"},),
        )
        self.assertEqual(session.active_order, [4])
        self.assertEqual(session.items[4].attempts, 2)

    def test_orchestrator_regenerates_only_selected_scene_with_cached_product_layer(self):
        """Reloading product pixels or recreating every slot would break selective regeneration."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-selective-regeneration-") as temp:
            state = self.make_state(temp)
            request = build_pinterest_run_request(state)
            background_calls: list[int] = []

            def fake_background(_: str, slot_index: int) -> Image.Image:
                background_calls.append(slot_index)
                return Image.new("RGBA", (1000, 1500), (slot_index, 20, 30, 255))

            request = replace(request, generate_background=fake_background)
            orchestrator = v3_pinterest_flow.PinterestPinOrchestrator()
            with patch.object(
                v3_pinterest_flow,
                "load_product_layer",
                wraps=v3_pinterest_flow.load_product_layer,
            ) as load_product:
                first_series = orchestrator.build(request)
                background_calls.clear()
                regenerated = orchestrator.build(
                    replace(
                        request,
                        queue_items=(
                            {"variant_id": "ai-scene-02", "variant_kind": "ai_scene"},
                        ),
                    )
                )

        self.assertEqual(load_product.call_count, 1)
        self.assertEqual(background_calls, [2])
        self.assertEqual([variant.variant_id for variant in regenerated], ["ai-scene-02"])
        first_scene = next(
            variant for variant in first_series if variant.variant_id == "ai-scene-02"
        )
        self.assertEqual(regenerated[0].source_product_path, first_scene.source_product_path)
        self.assertEqual(
            regenerated[0].product_layer_digest,
            first_scene.product_layer_digest,
        )

    def test_pinterest_worker_reports_unexpected_exception_and_finishes(self):
        """An uncaught orchestration error would leave the shared run queue running forever."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-worker-error-") as temp:
            request = PinterestPinRunRequest(
                work_dir=temp,
                product_path=str(Path(temp) / "product.png"),
                pin=PinterestPinData(product_paths=["product.png"]),
                settings={"output_dir": temp},
                queue_items=({"variant_id": "template-01", "variant_kind": "template"},),
            )
            worker = PinterestPinWorkerAdapter(
                request,
                orchestrator=UnexpectedPinterestOrchestrator(),
            )
            errors: list[str] = []
            completions: list[str] = []
            worker.error.connect(errors.append)
            worker.finished.connect(completions.append)

            worker.start()
            self.assertTrue(worker.wait(1_000))
            self.app.processEvents()

        self.assertEqual(errors, [v3_localization.message_for("pinterest.error.pin_prepare_failed", locale="ru")])
        self.assertEqual(completions, [v3_localization.message_for("pinterest.status.run_finished", locale="ru")])

    def test_pinterest_worker_runs_off_gui_thread_and_stop_is_observable(self):
        """Running orchestration from QTimer would block the GUI and hide cancellation."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-worker-thread-") as temp:
            request = PinterestPinRunRequest(
                work_dir=temp,
                product_path=str(Path(temp) / "product.png"),
                pin=PinterestPinData(product_paths=["product.png"]),
                settings={"output_dir": temp},
                queue_items=({"variant_id": "template-01", "variant_kind": "template"},),
            )
            orchestrator = CancellationAwarePinterestOrchestrator()
            worker = PinterestPinWorkerAdapter(request, orchestrator=orchestrator)

            self.assertIsInstance(worker, QThread)
            worker.start()
            self.assertTrue(orchestrator.started.wait(timeout=1))
            worker.stop()
            orchestrator.released.set()
            self.assertTrue(worker.wait(1_000))
            self.app.processEvents()

        self.assertNotEqual(orchestrator.thread_id, threading.get_ident())
        self.assertTrue(orchestrator.cancelled)

    def test_pinterest_worker_defers_stop_after_current_until_orchestration_returns(self):
        """Treating deferred stop as immediate would cancel the current Pinterest slot."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-deferred-stop-") as temp:
            request = PinterestPinRunRequest(
                work_dir=temp,
                product_path=str(Path(temp) / "product.png"),
                pin=PinterestPinData(product_paths=["product.png"]),
                settings={"output_dir": temp},
                queue_items=({"variant_id": "ai-scene-01", "variant_kind": "ai_scene"},),
            )
            current_variant = PinVariant(
                variant_id="ai-scene-01",
                variant_kind="ai_scene",
                image=Image.new("RGBA", (1000, 1500), "white"),
                source_product_path="product.png",
                scene_prompt="",
                status="success",
                retryable=False,
                product_layer_digest="protected-digest",
            )
            orchestrator = CancellationAwarePinterestOrchestrator((current_variant,))
            worker = PinterestPinWorkerAdapter(request, orchestrator=orchestrator)

            worker.start()
            self.assertTrue(orchestrator.started.wait(timeout=1))
            worker.request_stop_after_current()
            orchestrator.released.set()
            self.assertTrue(worker.wait(1_000))
            self.app.processEvents()

        self.assertFalse(orchestrator.cancelled)
        self.assertIn("ai-scene-01", worker.output_paths)

    def test_queue_stop_after_current_keeps_active_pinterest_variant(self):
        """Missing pre-build RUNNING makes shared deferred stop cancel the active slot."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-queue-stop-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            variants = tuple(
                PinVariant(
                    variant_id=variant_id,
                    variant_kind=variant_kind,
                    image=Image.new("RGBA", (1000, 1500), "white"),
                    source_product_path="product.png",
                    scene_prompt="",
                    status="success",
                    retryable=False,
                    product_layer_digest="protected-digest",
                )
                for variant_id, variant_kind in (
                    ("template-01", "template"),
                    ("template-02", "template"),
                    ("template-03", "template"),
                    ("ai-scene-01", "ai_scene"),
                    ("ai-scene-02", "ai_scene"),
                    ("ai-scene-03", "ai_scene"),
                )
            )
            orchestrator = CancellationAwarePinterestOrchestrator(variants)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None))
            workers: list[PinterestPinWorkerAdapter] = []

            def create_worker(request):
                worker = PinterestPinWorkerAdapter(
                    request,
                    orchestrator=orchestrator,
                )
                workers.append(worker)
                return worker

            controller.create_worker_for_request = create_worker  # type: ignore[method-assign]
            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)
            self.assertIsNotNone(controller.start())
            worker = workers[0]
            self.assertTrue(orchestrator.started.wait(timeout=1))
            deadline = time.monotonic() + 1
            while (
                controller.run_queue.session.items[0].status is not RunItemStatus.RUNNING
                and time.monotonic() < deadline
            ):
                self.app.processEvents()
                time.sleep(0.01)

            self.assertIs(
                controller.run_queue.session.items[0].status,
                RunItemStatus.RUNNING,
            )
            self.assertTrue(controller.run_queue.stop_after_current())
            orchestrator.released.set()
            self.assertTrue(self.wait_for_worker(worker))

        session = controller.run_queue.session
        self.assertIs(session.items[0].status, RunItemStatus.SUCCEEDED)
        self.assertTrue(
            all(item.status is RunItemStatus.CANCELLED for item in session.items[1:])
        )
        self.assertFalse(orchestrator.cancelled)

    def test_pinterest_retry_sync_preserves_successful_slots_outside_retry_request(self):
        """Missing retry-local variants must not overwrite prior successful Pinterest slots."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-retry-sync-") as temp:
            state = self.make_state(temp)
            state.pinterest.results = [
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id=variant_id,
                    variant_kind=variant_kind,
                    source_product_path="product.png",
                    output_path=f"old-{variant_id}.png",
                    status="failed" if variant_id == "ai-scene-02" else "success",
                    retryable=variant_id == "ai-scene-02",
                    product_layer_digest="prior-digest",
                )
                for variant_id, variant_kind in (
                    ("template-01", "template"),
                    ("template-02", "template"),
                    ("template-03", "template"),
                    ("ai-scene-01", "ai_scene"),
                    ("ai-scene-02", "ai_scene"),
                    ("ai-scene-03", "ai_scene"),
                )
            ]
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None))
            request = build_pinterest_run_request(state)
            session = RunQueueSession(request, ProjectMode.PINTEREST)
            for item in session.items:
                item.status = (
                    RunItemStatus.FAILED
                    if item.payload["variant_id"] == "ai-scene-02"
                    else RunItemStatus.SUCCEEDED
                )
            session.running = False
            retry = session.prepare_retry()
            retry_output = Path(temp) / "pinterest-ai-scene-02.png"
            Image.new("RGBA", (10, 15), "white").save(retry_output)
            retry_variant = PinVariant(
                variant_id="ai-scene-02",
                variant_kind="ai_scene",
                image=Image.new("RGBA", (1000, 1500), "white"),
                source_product_path="product.png",
                scene_prompt="",
                status="success",
                retryable=False,
                product_layer_digest="retry-digest",
            )
            worker = PinterestPinWorkerAdapter(
                retry,
                orchestrator=StaticPinterestOrchestrator((retry_variant,)),
            )
            worker.variants = (retry_variant,)
            worker.output_paths = {"ai-scene-02": str(retry_output)}
            controller.worker = worker
            controller.run_queue.session = session
            session.handle_item_progress(
                {
                    "item_index": 1,
                    "total_items": 1,
                    "stage": "export",
                    "status": "succeeded",
                    "output_path": str(retry_output),
                }
            )

            controller._sync_preview_results_from_queue()

        results = {result.variant_id: result for result in state.pinterest.results}
        self.assertTrue(all(
            results[variant_id].status == "success"
            for variant_id in (
                "template-01", "template-02", "template-03",
                "ai-scene-01", "ai-scene-02", "ai-scene-03",
            )
        ))
        self.assertEqual(results["template-01"].output_path, "old-template-01.png")
        self.assertEqual(results["ai-scene-02"].output_path, str(retry_output))
        self.assertEqual(results["ai-scene-02"].product_layer_digest, "retry-digest")

    def test_real_pinterest_start_routes_orchestrated_variants_to_all_six_slots(self):
        """Replacing the adapter with the legacy worker would omit protected pin metadata."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-orchestrator-") as temp:
            product_path = Path(temp) / "product.png"
            product = Image.new("RGBA", (24, 32), (23, 67, 121, 0))
            for x in range(5, 19):
                for y in range(4, 29):
                    product.putpixel((x, y), (23, 67, 121, 255))
            product.save(product_path)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp
            state.set_output_dir_for_mode(temp, ProjectMode.PINTEREST)
            state.pinterest.pin.product_paths = [str(product_path)]
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=Mock(side_effect=AssertionError('legacy worker must not run')), authorization_provider=lambda: None))

            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)
            request = controller.start()
            self.assertTrue(self.wait_for_worker(controller.worker))

            self.assertIsInstance(request, PinterestPinRunRequest)
            self.assertIsInstance(controller.worker, PinterestPinWorkerAdapter)
            self.assertEqual(
                [result.variant_id for result in state.pinterest.results],
                [
                    "template-01", "template-02", "template-03",
                    "ai-scene-01", "ai-scene-02", "ai-scene-03",
                ],
            )
            self.assertEqual(
                [result.status for result in state.pinterest.results],
                ["success"] * 6,
            )
            self.assertTrue(all(result.product_layer_digest for result in state.pinterest.results[:3]))
            self.assertTrue(all(Path(result.output_path).is_file() for result in state.pinterest.results[:3]))
            self.assertTrue(all(not result.retryable for result in state.pinterest.results[3:]))

    def test_application_view_installs_exact_b1_to_b6_route(self):
        view = V3ApplicationView(
            runtime_settings_provider=lambda: {"kie_api_key": "test-key"},
            worker_factory=WorkerFactory(),
        )
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        self.app.processEvents()

        controller = view.shell.workflow_controller("pinterest")
        self.assertEqual(set(controller.pages), set(view.shell.state.route))
        self.assertEqual(
            tuple(controller.pages),
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )
        self.assertIsInstance(
            controller.pages[StepId.PROMPTS],
            PinterestCopyLayoutPage,
        )
        self.assertIsInstance(
            controller.pages[StepId.PIN_FORMAT_MODEL],
            PinterestFormatModelPage,
        )

    def test_pinterest_route_has_no_clipart_review_or_processing_page(self):
        """Clipart prompt/content and cleanup pages must not leak into Pinterest."""
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))

        self.assertEqual(
            state.route,
            (
                StepId.PROJECT,
                StepId.PROMPTS,
                StepId.PIN_FORMAT_MODEL,
                StepId.REVIEW_RUN,
                StepId.RESULTS,
            ),
        )
        self.assertNotIn(StepId.PROMPT_REVIEW, controller.pages)
        self.assertNotIn(StepId.PROCESSING_OPTIONS, controller.pages)
        self.assertNotIsInstance(controller.pages[StepId.REVIEW_RUN], ClipartReviewRunPage)

    def test_missing_product_and_unsupported_folder_use_localized_registry_messages(self):
        """Hard-coded validation text leaves the English Pinterest route untranslated."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-localized-errors-") as temp:
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp

            for locale in ("ru", "en-US"):
                with self.subTest(locale=locale):
                    with self.assertRaisesRegex(
                        ClipartFlowError,
                        re.escape(v3_localization.message_for("pinterest.error.missing_product", locale=locale)),
                    ):
                        build_pinterest_run_request(state, locale=locale)

            state.pinterest.pin.product_paths = [str(Path(temp) / "product.png")]
            Image.new("RGBA", (8, 10), "white").save(state.pinterest.pin.product_paths[0])
            state.set_output_dir_for_mode(str(Path(temp) / "not-a-folder"), ProjectMode.PINTEREST)
            with patch.object(Path, "mkdir", side_effect=OSError("blocked")):
                with self.assertRaisesRegex(
                    ClipartFlowError,
                    re.escape(v3_localization.message_for("pinterest.error.output_folder", locale="en")),
                ):
                    build_pinterest_run_request(state, locale="en")

    def test_unavailable_scene_provider_uses_safe_template_fallback_and_localized_status(self):
        """An unsupported provider must never submit the product to an unsafe scene call."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-provider-fallback-") as temp:
            product_path = Path(temp) / "product.png"
            Image.new("RGBA", (8, 10), "white").save(product_path)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp
            state.pinterest.pin.product_paths = [str(product_path)]
            request = build_pinterest_run_request(
                state,
                locale="en",
                provider_capabilities={"background_generation": False, "protected_product": False},
            )

        self.assertEqual(request.scene_strategy, "safe_template")
        self.assertEqual(
            request.status_message,
            v3_localization.message_for("pinterest.status.safe_template_fallback", locale="en"),
        )

    def test_real_controller_uses_safe_template_capability_and_localized_status(self):
        """An unimplemented AI-scene provider must fall back before the worker starts."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-controller-fallback-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None), locale='en')
            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)

            request = controller.start()

            self.assertIsNotNone(request)
            assert request is not None
            self.assertEqual(request.scene_strategy, "safe_template")
            expected = v3_localization.message_for(
                "pinterest.status.safe_template_fallback", locale="en"
            )
            self.assertEqual(request.status_message, expected)
            self.assertIn(expected, controller.review_page.run_status_label.text())
            self.assertTrue(self.wait_for_worker(controller.worker))

    def test_product_and_copy_layout_pages_are_separate_ui_slices(self):
        """Combining the source product with copy fields makes the two-step route deceptive."""
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))

        product_page = controller.pages[StepId.PROJECT]
        copy_page = controller.pages[StepId.PROMPTS]

        self.assertIsInstance(product_page, PinterestProductInputPage)
        self.assertIsInstance(copy_page, PinterestCopyLayoutPage)
        self.assertIsNot(product_page, copy_page)
        self.assertFalse(hasattr(product_page, "title_edit"))
        self.assertFalse(hasattr(copy_page, "selected_product_combo"))

    def test_format_page_status_uses_english_registry_message(self):
        """Inherited generation controls must not leak Russian status into the English route."""
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()), locale='en')

        page = controller.pages[StepId.PIN_FORMAT_MODEL]

        self.assertEqual(
            page.reference_status_label.text(),
            v3_localization.message_for("pinterest.status.reference_ready", locale="en"),
        )

    def test_failed_scene_and_partial_export_use_localized_registry_messages(self):
        """Scene and export failures need actionable language in both supported locales."""
        self.assertEqual(
            v3_pinterest_flow.scene_failure_message(locale="ru"),
            v3_localization.message_for("pinterest.error.scene_failed", locale="ru"),
        )
        self.assertEqual(
            v3_pinterest_flow.scene_failure_message(locale="en"),
            v3_localization.message_for("pinterest.error.scene_failed", locale="en"),
        )
        self.assertEqual(
            v3_pinterest_flow.partial_export_message(2, locale="en"),
            v3_localization.message_for("pinterest.status.partial_export", locale="en", count=2),
        )

    def test_product_input_binds_selected_photo_copy_scene_and_output_folder(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-product-input-") as temp:
            first_product = Path(temp) / "first.png"
            second_product = Path(temp) / "second.png"
            Image.new("RGBA", (8, 10), "white").save(first_product)
            Image.new("RGBA", (8, 10), "black").save(second_product)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
            page = controller.pages[StepId.PROJECT]

            page.set_product_paths((str(first_product), str(second_product)))
            page.selected_product_combo.setCurrentIndex(1)
            copy_page = controller.pages[StepId.PROMPTS]
            copy_page.title_edit.setText("Summer tote")
            copy_page.subtitle_edit.setText("For weekend markets")
            copy_page.cta_edit.setText("See details")
            copy_page.style_edit.setText("Clean editorial")
            copy_page.scene_edit.setText("Sunlit market table")
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
        self.assertEqual(localized_page.card.title_label.text(), "Product photo")

    def test_install_propagates_locale_to_real_pinterest_pages(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()), locale='en-US')

        self.assertEqual(
            controller.pages[StepId.PROMPTS].card.title_label.text(),
            "Pin copy and layout",
        )
        self.assertEqual(
            controller.pages[StepId.RESULTS].card.title_label.text(),
            "Pinterest pin preview",
        )
        self.assertEqual(
            controller.pages[StepId.PIN_FORMAT_MODEL].card.title_label.text(),
            "Pinterest pin generation",
        )
        self.assertNotIn(StepId.PROCESSING_OPTIONS, controller.pages)
        self.assertEqual(
            controller.pages[StepId.REVIEW_RUN].card.description_label.text(),
            "Check the six slots before explicitly starting generation.",
        )

    def test_legacy_cleanup_draft_does_not_reach_pinterest_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-diagnostics-") as temp:
            state = self.make_state(temp)
            payload = state.to_dict()
            payload["pinterest"]["operations"] = {
                "remove_background": True, "remove_exif": True, "trim": True
            }
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
            accepted_source = Path(temp) / "accepted.png"
            Image.new("RGBA", (8, 10), "white").save(first_product)
            Image.new("RGBA", (8, 10), "black").save(second_product)
            Image.new("RGBA", (1000, 1500), "white").save(accepted_source)
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.pinterest.pin.product_paths = [str(first_product), str(second_product)]
            state.pinterest.pin.selected_product_index = 1
            state.set_output_dir_for_mode(temp, ProjectMode.PINTEREST)
            state.pinterest.results = [
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="template-01",
                    variant_kind="template",
                    source_product_path=str(second_product),
                    output_path=str(accepted_source),
                    accepted=True,
                    status="success",
                    product_layer_digest="protected-digest",
                )
            ]
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=factory))
            page = controller.pages[StepId.RESULTS]

            self.assertEqual(len(page.variant_cards), 6)
            self.assertEqual(
                [result.source_product_path for result in state.pinterest.results],
                [str(second_product)] * 6,
            )
            self.assertEqual(
                page.export_accepted(),
                (str(Path(temp) / "second_template_01.png"),),
            )

            page.set_variant_accepted("ai-scene-01", True)
            page.regenerate_variant("ai-scene-01")

            retried = next(
                result for result in state.pinterest.results if result.variant_id == "ai-scene-01"
            )
            self.assertTrue(retried.accepted)
            self.assertEqual(retried.status, "pending")
            self.assertFalse(retried.retryable)
            self.assertEqual(factory.workers, [])

    def test_preview_regeneration_starts_only_the_selected_slot(self):
        """Restarting the full six-slot series would replace unrelated accepted pins."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-preview-regeneration-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None))
            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)
            self.assertIsNotNone(controller.start())
            self.assertTrue(self.wait_for_worker(controller.worker))
            initial_worker = controller.worker
            initial_product_layer = initial_worker.product_layer
            self.assertIsNotNone(initial_product_layer)
            page = controller.pages[StepId.RESULTS]
            preserved = next(
                result for result in state.pinterest.results if result.variant_id == "template-02"
            )
            preserved.status = "success"
            preserved.accepted = True
            preserved.output_path = "preserved-template.png"
            preserved.product_layer_digest = "preserved-digest"

            page.regenerate_variant("template-01")

            self.assertIsInstance(controller.worker, PinterestPinWorkerAdapter)
            self.assertIsNot(controller.worker, initial_worker)
            self.assertIs(controller.worker.request.product_layer, initial_product_layer)
            self.assertEqual(
                controller.worker.request.queue_items,
                ({"variant_id": "template-01", "variant_kind": "template"},),
            )
            self.assertTrue(self.wait_for_worker(controller.worker))

        self.assertEqual(preserved.status, "success")
        self.assertTrue(preserved.accepted)
        self.assertEqual(preserved.output_path, "preserved-template.png")
        self.assertEqual(preserved.product_layer_digest, "preserved-digest")

    def test_export_accepted_writes_collision_safe_files_and_keeps_partial_successes(self):
        """Overwriting an existing pin or discarding an earlier export after one failure is unsafe."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-export-") as temp:
            root = Path(temp)
            export_folder = root / "selected export"
            product_path = root / "product image.png"
            Image.new("RGBA", (8, 10), (20, 40, 60, 0)).save(product_path)
            jpg_source = root / "template.jpg"
            png_source = root / "scene.png"
            Image.new("RGB", (1000, 1500), "white").save(jpg_source, format="JPEG")
            Image.new("RGBA", (1000, 1500), "black").save(png_source, format="PNG")
            export_folder.mkdir()
            existing = export_folder / "product_image_template_01.jpg"
            existing.write_bytes(b"keep-existing-export")
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.set_output_dir_for_mode(str(export_folder), ProjectMode.PINTEREST)
            state.pinterest.pin.product_paths = [str(product_path)]
            state.pinterest.results = [
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="template-01",
                    variant_kind="template",
                    source_product_path=str(product_path),
                    output_path=str(jpg_source),
                    accepted=True,
                    status="success",
                ),
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="ai-scene-01",
                    variant_kind="ai_scene",
                    source_product_path=str(product_path),
                    output_path=str(png_source),
                    accepted=True,
                    status="success",
                ),
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="template-02",
                    variant_kind="template",
                    source_product_path=str(product_path),
                    output_path=str(root / "missing.png"),
                    accepted=True,
                    status="success",
                ),
            ]
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
            page = controller.pages[StepId.RESULTS]

            exported = page.export_accepted()

            self.assertEqual(
                tuple(Path(path).name for path in exported),
                ("product_image_template_01-02.jpg", "product_image_ai-scene_01.png"),
            )
            self.assertTrue(all(Path(path).is_file() for path in exported))
            self.assertEqual(existing.read_bytes(), b"keep-existing-export")
            results = {result.variant_id: result for result in state.pinterest.results}
            self.assertEqual(results["template-01"].export_status, "exported")
            self.assertEqual(results["ai-scene-01"].export_status, "exported")
            self.assertEqual(results["template-02"].export_status, "failed")
            self.assertIn("2", page.export_status_label.text())
            self.assertIn(str(export_folder), page.export_status_label.text())

    def test_export_target_reserves_distinct_names_for_parallel_exports(self):
        """Concurrent exports must not receive the same path and overwrite one another."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-export-reservation-") as temp:
            folder = Path(temp) / "exports"
            barrier = threading.Barrier(4)
            targets: list[Path] = []
            failures: list[BaseException] = []

            def reserve_target() -> None:
                try:
                    barrier.wait()
                    targets.append(
                        v3_pinterest_flow._pinterest_export_target(
                            folder,
                            product_path="product image.png",
                            variant_id="template-01",
                            suffix=".png",
                        )
                    )
                except BaseException as error:  # pragma: no cover - assertion below reports it
                    failures.append(error)

            threads = [threading.Thread(target=reserve_target) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(failures, [])
            self.assertEqual(len({target.name for target in targets}), 4)
            self.assertEqual(
                {target.name for target in targets},
                {
                    "product_image_template_01.png",
                    "product_image_template_01-02.png",
                    "product_image_template_01-03.png",
                    "product_image_template_01-04.png",
                },
            )
            self.assertTrue(all(target.is_file() for target in targets))

    def test_regeneration_keeps_successful_result_when_preflight_fails(self):
        """A preflight rejection must not discard an accepted exportable result."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-regeneration-preflight-") as temp:
            state = self.make_state(temp)
            previous = v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                variant_kind="template",
                source_product_path=state.pinterest.pin.product_paths[0],
                output_path="old-result.png",
                accepted=True,
                status="success",
                product_layer_digest="protected-digest",
                export_status="exported",
            )
            state.pinterest.results = [previous]
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: (), authorization_provider=lambda: None))

            self.assertIsNone(controller.regenerate_variant("template-01"))

        self.assertEqual(previous.status, "success")
        self.assertEqual(previous.output_path, "old-result.png")
        self.assertTrue(previous.accepted)
        self.assertEqual(previous.product_layer_digest, "protected-digest")
        self.assertEqual(previous.export_status, "exported")

    def test_regeneration_keeps_successful_result_when_authorization_fails(self):
        """A failed authorization must not discard an accepted exportable result."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-regeneration-authorization-") as temp:
            state = self.make_state(temp)
            previous = v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                variant_kind="template",
                source_product_path=state.pinterest.pin.product_paths[0],
                output_path="old-result.png",
                accepted=True,
                status="success",
                product_layer_digest="protected-digest",
                export_status="exported",
            )
            state.pinterest.results = [previous]
            shell = AppShell(state)

            def reject_authorization() -> None:
                raise v3_pinterest_flow.LicenseError("authorization failed")

            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=reject_authorization))

            self.assertIsNone(controller.regenerate_variant("template-01"))

        self.assertEqual(previous.status, "success")
        self.assertEqual(previous.output_path, "old-result.png")
        self.assertTrue(previous.accepted)
        self.assertEqual(previous.product_layer_digest, "protected-digest")
        self.assertEqual(previous.export_status, "exported")

    def test_regeneration_keeps_successful_result_when_worker_creation_fails(self):
        """A worker-construction failure must not discard an accepted exportable result."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-regeneration-worker-") as temp:
            state = self.make_state(temp)
            previous = v3_pinterest_flow.PinterestPinResultData(
                variant_id="template-01",
                variant_kind="template",
                source_product_path=state.pinterest.pin.product_paths[0],
                output_path="old-result.png",
                accepted=True,
                status="success",
                product_layer_digest="protected-digest",
                export_status="exported",
            )
            state.pinterest.results = [previous]
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None))

            def fail_worker_creation(_: PinterestPinRunRequest) -> PinterestPinWorkerAdapter:
                raise OSError("worker creation failed")

            controller.create_worker_for_request = fail_worker_creation  # type: ignore[method-assign]

            self.assertIsNone(controller.regenerate_variant("template-01"))

        self.assertEqual(previous.status, "success")
        self.assertEqual(previous.output_path, "old-result.png")
        self.assertTrue(previous.accepted)
        self.assertEqual(previous.product_layer_digest, "protected-digest")
        self.assertEqual(previous.export_status, "exported")

    def test_regeneration_controller_uses_english_registry_status(self):
        """Hard-coded Russian regeneration status would leave the English flow untranslated."""
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-regeneration-locale-") as temp:
            state = self.make_state(temp)
            state.pinterest.results = [
                v3_pinterest_flow.PinterestPinResultData(
                    variant_id="template-01",
                    variant_kind="template",
                    source_product_path=state.pinterest.pin.product_paths[0],
                )
            ]
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None), locale='en')
            controller.create_worker_for_request = (  # type: ignore[method-assign]
                lambda _: FakeWorker()
            )

            self.assertIsNotNone(controller.regenerate_variant("template-01"))

        self.assertEqual(
            controller.review_page.run_status_label.text(),
            "✓ Regenerating selected Pinterest variant.",
        )

    def test_worker_adapter_completion_populates_preview_slots_from_shared_queue(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-completion-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None))

            shell.go_next()
            self.assertTrue(self.wait_for_worker(controller.worker))

            self.assertEqual(
                [result.status for result in state.pinterest.results],
                ["success"] * 6,
            )
            self.assertTrue(
                all(result.output_path for result in state.pinterest.results)
            )
            self.assertEqual(
                [Path(result.output_path).name for result in state.pinterest.results[:3]],
                ["pinterest-template-01.png", "pinterest-template-02.png", "pinterest-template-03.png"],
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
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', authorization_provider=lambda: None))

            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)
            controller.start()
            controller.worker.error.emit("provider failed")
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
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))

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
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
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
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
        page = controller.pages[StepId.RESULTS]

        warning_copy = " ".join(
            label.text() for label in page.findChildren(QLabel)
        )
        self.assertIn("точность товара", warning_copy.casefold())

    def test_pinterest_pages_omit_clipart_transparency_and_background_cleanup_controls(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
        pages = (
            controller.pages[StepId.PROJECT],
            controller.pages[StepId.PROMPTS],
            controller.pages[StepId.PIN_FORMAT_MODEL],
            controller.pages[StepId.RESULTS],
        )
        state.set_step(StepId.PIN_FORMAT_MODEL)
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
        state.set_step(StepId.RESULTS)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, "pinterest"))

        controller.run_queue.process_more()
        self.app.processEvents()

        self.assertEqual(state.current_step, StepId.PROJECT)
        self.assertIs(shell.current_page, controller.pages[StepId.PROJECT])
        self.assertIsInstance(
            controller.pages[StepId.REVIEW_RUN],
            PinterestReviewRunPage,
        )

    def test_pinterest_route_omits_legacy_prompt_review_page(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
        self.assertNotIn(StepId.PROMPT_REVIEW, controller.pages)

    def test_vertical_ratio_is_default_and_supported_ratio_can_change(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        self.assertEqual(state.pinterest.generation.ratio, "9:16")
        self.assertEqual(state.pinterest.generation.reference_ratio, "9:16")
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
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
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: {'kie_api_key': 'test-key'}, worker_factory=WorkerFactory()))
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
        self.assertEqual(request.mode, "pinterest_pins")
        self.assertEqual(len(request.queue_items), 6)
        self.assertIn(
            "2:3 1000×1500",
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
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
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
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: {'kie_api_key': 'test-key'}, worker_factory=WorkerFactory()))
            page = controller.pages[StepId.PIN_FORMAT_MODEL]
            self.assertFalse(page.reference_advanced.isVisible())

            for index in range(page.model_combo.count()):
                page.model_combo.setCurrentIndex(index)
                text_model = str(page.model_combo.currentData())
                request = build_pinterest_run_request(
                    state,
                    {"kie_api_key": "test-key"},
                )
                review = controller.pages[StepId.REVIEW_RUN]
                review.refresh_from_state()
                self.assertIsInstance(request, PinterestPinRunRequest)
                self.assertIn(text_model, review.summary_label.text())

    def test_request_uses_dedicated_pinterest_orchestrator_without_provider_settings(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-request-") as temp:
            state = self.make_state(temp)
            request = build_pinterest_run_request(
                state,
                {"kie_api_key": "test-key"},
            )
            estimate = estimate_pinterest_cost(state)

        self.assertIsInstance(request, PinterestPinRunRequest)
        self.assertEqual(request.mode, "pinterest_pins")
        self.assertEqual(len(request.queue_items), 6)
        self.assertEqual(request.settings, {"output_dir": temp})
        self.assertEqual(estimate.request_count, 0)
        self.assertEqual(estimate.estimated_usd, Decimal("0"))

    def test_pinterest_processing_is_not_part_of_the_route(self):
        self.assertFalse(
            workflow_for_mode(ProjectMode.PINTEREST).processing_operations
        )

    def test_pinterest_state_does_not_expose_processing_page(self):
        state = ProjectState(mode=ProjectMode.PINTEREST)
        shell = AppShell(state)
        controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
        self.assertNotIn(StepId.PROCESSING_OPTIONS, controller.pages)

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
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: {'kie_api_key': 'test-key'}, worker_factory=WorkerFactory(), authorization_provider=lambda: None))

            shell._run_request_key = (ProjectMode.PINTEREST, StepId.REVIEW_RUN)
            controller.start()
            self.assertTrue(self.wait_for_worker(controller.worker))

            result = next(
                item
                for item in state.pinterest.results
                if item.variant_id == "template-01"
            )
            self.assertEqual(result.status, "success")
            self.assertFalse(result.accepted)
            self.assertNotEqual(result.product_layer_digest, "old-protected-digest")
            self.assertEqual(result.export_status, "not_exported")

    def test_request_keeps_six_slots_when_legacy_prompt_references_exist(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-reference-") as temp:
            image_path = Path(temp) / "reference.png"
            Image.new("RGB", (4, 6), "white").save(image_path)
            state = self.make_state(temp)
            request = build_pinterest_run_request(
                state,
                {"kie_api_key": "test-key"},
            )

        self.assertEqual(
            [item["variant_id"] for item in request.queue_items],
            [
                "template-01", "template-02", "template-03",
                "ai-scene-01", "ai-scene-02", "ai-scene-03",
            ],
        )

    def test_navigation_preserves_project_prompts_and_format(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-nav-") as temp:
            state = ProjectState(mode=ProjectMode.PINTEREST)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: {'kie_api_key': 'test-key'}, worker_factory=WorkerFactory()))
            state.common.work_dir = temp
            self.assertEqual(shell.go_next(), StepId.PROMPTS)
            prompts = controller.pages[StepId.PROMPTS]
            prompts.title_edit.setText("Kitchen collection")
            self.assertEqual(shell.go_next(), StepId.PIN_FORMAT_MODEL)
            format_page = controller.pages[StepId.PIN_FORMAT_MODEL]
            format_page.variants_spin.setValue(3)
            selected_ratio = format_page.ratio_combo.currentText()
            self.assertEqual(shell.go_back(), StepId.PROMPTS)

        self.assertEqual(state.common.project_name, "")
        self.assertEqual(state.pinterest.pin.pin_title, "Kitchen collection")
        self.assertEqual(state.pinterest.generation.variants, 3)
        self.assertEqual(state.pinterest.generation.ratio, selected_ratio)

    def test_review_is_generation_only_and_run_requires_explicit_action(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-run-") as temp:
            state = self.make_state(temp)
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: {'kie_api_key': 'test-key'}, worker_factory=factory, authorization_provider=lambda: None))

            self.assertEqual(factory.workers, [])
            review_copy = " ".join(
                label.text()
                for label in controller.review_page.findChildren(QLabel)
            )
            self.assertNotIn("API-ключи не сохраняются", review_copy)
            shell.go_next()

        self.assertEqual(factory.workers, [])
        self.assertIsInstance(controller.worker, PinterestPinWorkerAdapter)

    def test_missing_product_blocks_before_pinterest_adapter_starts(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-guard-") as temp:
            state = ProjectState(mode=ProjectMode.PINTEREST)
            state.common.work_dir = temp
            state.set_step(StepId.REVIEW_RUN)
            factory = WorkerFactory()
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', runtime_settings_provider=lambda: {}, worker_factory=factory))
            self.assertIn("фотографию товара", controller.review_page.preflight_status_label.text())
            shell.go_next()
            self.assertEqual(factory.workers, [])

    def test_offscreen_route_keeps_navigation_visible_at_minimum_size(self):
        with tempfile.TemporaryDirectory(prefix="pinterest-v3-ui-") as temp:
            state = self.make_state(temp)
            shell = AppShell(state)
            controller = install_pinterest_flow(WorkflowHost(shell, 'pinterest', worker_factory=WorkerFactory()))
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

    def test_module_has_dedicated_worker_adapter_without_network_client(self):
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
        self.assertIn("PinterestPinWorkerAdapter", class_names)
        self.assertNotIn("WorkerThread", class_names)
        self.assertTrue(
            imported_roots.isdisjoint(
                {"requests", "urllib", "httpx", "aiohttp", "socket"}
            )
        )


if __name__ == "__main__":
    unittest.main()
