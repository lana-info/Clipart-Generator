import hashlib
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QMimeData, QObject, QUrl, Qt, pyqtSignal
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel

import v3_processing_flow

from v3_mode_selection import V3ApplicationView
from v3_processing_flow import (
    MAX_PROCESSING_FILES,
    LocalImageInfo,
    ProcessingFilesPage,
    ProcessingPipelinePage,
    ProcessingRecipePage,
    ProcessingReviewRunPage,
    apply_processing_recipe,
    build_processing_run_request,
    estimate_processing_cost,
    estimate_processing_cost_breakdown,
    inspect_local_image,
    install_processing_flow,
    missing_processing_runtime_requirements,
    operation_validation_issues,
    processing_change_summary,
    processing_fal_endpoint_quantities,
    processing_pipeline_steps,
    uses_external_processing,
    validate_processing_providers,
)
from v3_project_state import (
    ImageOperationData,
    ProjectMode,
    ProjectState,
    StepId,
    route_for_mode,
)
from v3_wizard import AppShell


class FakeDropEvent:
    def __init__(self, paths):
        self._mime = QMimeData()
        self._mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
        self.accepted = False

    def mimeData(self):
        return self._mime

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


class ProcessingCopyTests(unittest.TestCase):
    def test_cleanup_summary_is_fully_localized(self):
        operations = ImageOperationData(
            remove_comments_text=True,
            remove_embedded_thumbnail=True,
            remove_generator_fields=True,
        )

        removed, _preserved = processing_change_summary(operations)

        self.assertIn("текстовые комментарии", removed)
        self.assertIn("встроенную миниатюру", removed)
        self.assertIn("поля программы-создателя", removed)
        self.assertNotIn("comments/text", removed)
        self.assertNotIn("embedded thumbnail", removed)
        self.assertNotIn("generator fields", removed)

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


class V3ProcessingFlowTests(unittest.TestCase):
    def test_processing_validation_rejects_after_model_without_alpha_support(self):
        operations = ImageOperationData()
        operations.remove_background = True
        operations.upscale_after = True
        operations.upscale_after_provider = "fal"
        operations.fal_upscale_after_model = "topaz/upscale/image/precision"

        with self.assertRaisesRegex(
            v3_processing_flow.ProcessingFlowError,
            "прозрач",
        ):
            validate_processing_providers(operations)

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_state(self, work_dir):
        source = Path(work_dir) / "source.png"
        Image.new("RGB", (12, 8), (120, 80, 30)).save(source)
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.common.work_dir = str(work_dir)
        state.processing.selected_files = [str(source)]
        apply_processing_recipe(state, "basic_enhancement")
        return state, source

    def test_local_image_summary_shows_only_requested_metadata(self):
        info = LocalImageInfo(
            path="/tmp/flower.png",
            name="flower.png",
            width=1024,
            height=1024,
            color_mode="RGBA",
            size_bytes=3 * 1024 * 1024,
            dpi=300,
        )
        self.assertEqual(
            info.summary,
            "flower.png · 1024×1024 · 300 DPI · 3.0 МБ",
        )

    def test_local_image_summary_handles_missing_dpi(self):
        info = LocalImageInfo(
            path="/tmp/flower.png",
            name="flower.png",
            width=1024,
            height=1024,
            color_mode="RGB",
            size_bytes=1024,
            dpi=None,
        )
        self.assertIn("DPI не указан", info.summary)

    def test_application_view_installs_c1_to_c6_route(self):
        view = V3ApplicationView(worker_factory=WorkerFactory())
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        self.app.processEvents()

        pages = view.shell.processing_flow_controller.pages
        self.assertEqual(
            set(step for step in pages if step in route_for_mode(ProjectMode.PROCESSING)),
            set(route_for_mode(ProjectMode.PROCESSING)),
        )
        self.assertIsInstance(pages[StepId.FILES], ProcessingFilesPage)
        self.assertIsInstance(pages[StepId.GOAL], ProcessingRecipePage)
        self.assertIsInstance(pages[StepId.PIPELINE], ProcessingPipelinePage)
        self.assertIsInstance(pages[StepId.REVIEW_RUN], ProcessingReviewRunPage)

    def test_processing_review_has_no_duplicate_transfer_checkbox_or_ready_message(self):
        with tempfile.TemporaryDirectory(prefix="processing-review-copy-") as temp:
            state, _ = self.make_state(temp)
            state.processing.operations.upscale_before = True
            state.processing.operations.upscale_before_provider = "kie"
            state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.REVIEW_RUN
            shell = AppShell(state)
            runtime_settings: dict[str, str] = {}
            controller = install_processing_flow(
                shell,
                runtime_settings_provider=lambda: runtime_settings,
                worker_factory=WorkerFactory(),
            )
            page = controller.review_page
            controller._refresh_preflight()
            self.assertFalse(page.requirements_label.isHidden())
            self.assertIn("KIE API Key", page.requirements_label.text())

            runtime_settings["kie_api_key"] = "test-key"
            controller._refresh_preflight()

            checkbox_copy = " ".join(
                checkbox.text() for checkbox in page.findChildren(QCheckBox)
            )
            self.assertNotIn("Разрешаю передачу файлов", checkbox_copy)
            self.assertFalse(page.requirements_label.isHidden())
            self.assertEqual(page.requirements_label.text(), "✓ Готово к запуску.")
            self.assertIn("внешнему сервису", page.warning_label.text())

    def test_processing_review_uses_approved_top_aligned_sections(self):
        with tempfile.TemporaryDirectory(prefix="processing-review-layout-") as temp:
            state, _ = self.make_state(temp)
            page = ProcessingReviewRunPage(
                state,
                ProcessingFilesPage(state, lambda: None),
                ProcessingPipelinePage(state, lambda: None),
            )
            page.resize(980, 700)
            page.show()
            self.app.processEvents()

            self.assertTrue(page.card.layout().alignment() & Qt.AlignmentFlag.AlignTop)
            self.assertTrue(
                page.card.content_layout.alignment() & Qt.AlignmentFlag.AlignTop
            )
            section_copy = " ".join(
                label.text() for label in page.findChildren(QLabel)
            )
            self.assertIn("Файлы и результат", section_copy)
            self.assertIn("Порядок", section_copy)
            self.assertIn("API-вызовы и стоимость", section_copy)
            self.assertLess(page.files_section_label.geometry().top(), 40)
            self.assertNotIn("Mode 2", section_copy)
            self.assertNotIn("pipeline 2.0", section_copy)
            page.set_preflight_status("Mode 2: Готово (3/3)", ready=True)
            self.assertEqual(page.requirements_label.text(), "✓ Готово к запуску.")
            page.resize(760, 700)
            self.app.processEvents()
            self.assertEqual(page.horizontalScrollBar().maximum(), 0)

    def test_process_more_clears_old_inputs_and_returns_to_files_step(self):
        with tempfile.TemporaryDirectory(prefix="processing-more-") as temp:
            state, source = self.make_state(temp)
            shell = AppShell(state)
            controller = install_processing_flow(shell, worker_factory=WorkerFactory())
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )
            session = controller.run_queue.start_new(request)
            session.running = False
            controller.run_queue.page.refresh_from_state()

            controller.run_queue.page.process_more_button.click()
            self.app.processEvents()

            self.assertEqual(state.current_step, StepId.FILES)
            self.assertEqual(state.processing.selected_files, [])
            self.assertEqual(state.processing.verification_records, [])
            self.assertIs(shell.current_page, controller.files_page)
            self.assertEqual(controller.files_page.file_count_label.text(), "Выбрано изображений: 0")
            self.assertEqual(
                controller.files_page.validation_issues(),
                ("selected_files_required",),
            )
            self.assertEqual(len(controller.files_page.thumbnail_labels), 0)

    def test_processing_start_rejects_second_signal_while_session_is_already_running(self):
        """Catch a second start signal before the worker reports isRunning()."""
        with tempfile.TemporaryDirectory(prefix="processing-start-race-") as temp:
            state, _ = self.make_state(temp)
            state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.REVIEW_RUN
            shell = AppShell(state)

            class DeferredStartWorker(FakeWorker):
                def start(self):
                    self.started = False

            class DeferredStartFactory(WorkerFactory):
                def __call__(self, **kwargs):
                    worker = DeferredStartWorker(**kwargs)
                    self.workers.append(worker)
                    return worker

            factory = DeferredStartFactory()
            controller = install_processing_flow(
                shell,
                worker_factory=factory,
                authorization_provider=lambda: None,
            )
            shell._run_request_key = (ProjectMode.PROCESSING, StepId.REVIEW_RUN)

            first = controller.start()
            second = controller.start()

            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertEqual(len(factory.workers), 1)
            self.assertIn(
                "уже выполняется",
                controller.review_page.run_status_label.text(),
            )

    def test_standalone_synthid_consent_is_disabled_and_marked_unavailable(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        page = ProcessingPipelinePage(state, lambda: None)

        self.assertIsNotNone(page.cleanup_checkbox)
        self.assertFalse(page.allow_full_image_changes.isEnabled())
        self.assertFalse(page.allow_full_image_changes.isChecked())
        self.assertIn("недоступно", page.allow_full_image_changes.text().lower())


    def test_file_card_validates_content_and_reports_safe_metadata(self):
        with tempfile.TemporaryDirectory(prefix="processing-files-") as temp:
            state = ProjectState(mode=ProjectMode.PROCESSING)
            shell = AppShell(state)
            controller = install_processing_flow(shell)
            source = Path(temp) / "sample.png"
            Image.new("RGBA", (7, 9), (1, 2, 3, 255)).save(source)

            page = controller.pages[StepId.FILES]
            accepted = page.add_files([str(source)])
            self.assertEqual(len(accepted), 1)
            self.assertEqual(accepted[0].name, "sample.png")
            self.assertEqual((accepted[0].width, accepted[0].height), (7, 9))
            self.assertIn("DPI не указан", accepted[0].summary)
            self.assertFalse(page.thumbnail_labels[0].pixmap().isNull())
            self.assertEqual(page.validation_issues(), ())

    def test_add_files_reuses_inspection_during_refresh(self):
        with tempfile.TemporaryDirectory(prefix="processing-inspection-cache-") as temp:
            source = Path(temp) / "sample.png"
            Image.new("RGB", (7, 9), "green").save(source)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            page = ProcessingFilesPage(state, lambda: None)

            with patch(
                "v3_processing_flow.inspect_local_image",
                wraps=inspect_local_image,
            ) as inspect:
                page.add_files([str(source)])

            self.assertEqual(inspect.call_count, 1)

    def test_large_batch_add_does_not_decode_pixels_synchronously(self):
        with tempfile.TemporaryDirectory(prefix="processing-large-import-") as temp:
            root = Path(temp)
            sources = []
            for index in range(81):
                source = root / f"source-{index:03d}.png"
                Image.new("RGB", (8, 8), (index, 40, 90)).save(source)
                sources.append(str(source))
            state = ProjectState(mode=ProjectMode.PROCESSING)
            page = ProcessingFilesPage(state, lambda: None)

            with patch.object(
                Image.Image,
                "load",
                side_effect=AssertionError("pixel decode must be deferred"),
            ) as load:
                accepted = page.add_files(sources)

            self.assertEqual(len(accepted), 81)
            load.assert_not_called()
            self.assertEqual(len(page.thumbnail_labels), 81)
            self.assertTrue(
                all(label.text() == "Загрузка…" for label in page.thumbnail_labels)
            )

    def test_large_batch_run_request_does_not_decode_pixels_synchronously(self):
        with tempfile.TemporaryDirectory(prefix="processing-large-request-") as temp:
            root = Path(temp)
            state, _ = self.make_state(root)
            sources = []
            for index in range(40):
                source = root / f"request-{index:03d}.png"
                Image.new("RGB", (8, 8), (index, 40, 90)).save(source)
                sources.append(str(source))
            state.processing.selected_files = sources

            with patch.object(
                Image.Image,
                "load",
                side_effect=AssertionError("request validation must stay header-only"),
            ) as load:
                request = build_processing_run_request(
                    state,
                    {},
                    allow_full_image_changes=True,
                    external_transfer_consent=False,
                )

            self.assertEqual(len(request.selected_files), 40)
            load.assert_not_called()

    def test_large_batch_thumbnails_load_from_event_queue(self):
        with tempfile.TemporaryDirectory(prefix="processing-lazy-thumbnails-") as temp:
            root = Path(temp)
            sources = []
            for index in range(21):
                source = root / f"thumb-{index:03d}.png"
                Image.new("RGB", (8, 8), (index, 40, 90)).save(source)
                sources.append(str(source))
            page = ProcessingFilesPage(
                ProjectState(mode=ProjectMode.PROCESSING),
                lambda: None,
            )

            page.add_files(sources)
            self.assertTrue(
                all(label.text() == "Загрузка…" for label in page.thumbnail_labels)
            )

            QTest.qWait(400)

            self.assertTrue(
                all(not label.pixmap().isNull() for label in page.thumbnail_labels)
            )

    def test_drag_and_drop_accepts_only_valid_local_images(self):
        with tempfile.TemporaryDirectory(prefix="processing-drop-") as temp:
            source = Path(temp) / "drop.png"
            Image.new("RGB", (4, 4), "green").save(source)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            shell = AppShell(state)
            controller = install_processing_flow(shell)
            page = controller.files_page
            event = FakeDropEvent([source])

            page.dragEnterEvent(event)
            self.assertTrue(event.accepted)
            page.dropEvent(event)

            self.assertTrue(event.accepted)
            self.assertEqual(state.processing.selected_files, [str(source.resolve())])
            self.assertFalse(page.thumbnail_labels[0].pixmap().isNull())

    def test_files_screen_uses_single_overwrite_toggle_and_visible_drop_zone(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        shell = AppShell(state)
        controller = install_processing_flow(shell)
        page = controller.files_page

        self.assertFalse(page.overwrite_checkbox.isChecked())
        self.assertEqual(page.overwrite_checkbox.text(), "Перезаписывать существующие файлы")
        self.assertEqual(page.clear_button.text(), "Очистить всё")
        self.assertFalse(page.clear_button.isEnabled())
        self.assertGreaterEqual(page.drop_label.minimumHeight(), 64)
        self.assertEqual(page.drop_label.alignment(), Qt.AlignmentFlag.AlignCenter)
    def test_invalid_and_animated_files_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="processing-invalid-") as temp:
            invalid = Path(temp) / "not-image.png"
            invalid.write_text("not an image", encoding="utf-8")
            with self.assertRaises(ValueError):
                inspect_local_image(invalid)

            animated = Path(temp) / "animated.gif"
            first = Image.new("RGB", (3, 3), "red")
            second = Image.new("RGB", (3, 3), "blue")
            first.save(animated, save_all=True, append_images=[second], loop=0)
            with self.assertRaises(ValueError):
                inspect_local_image(animated)

    def test_truncated_single_frame_image_is_rejected_before_pipeline(self):
        with tempfile.TemporaryDirectory(prefix="processing-truncated-") as temp:
            source = Path(temp) / "truncated.jpg"
            Image.new("RGB", (40, 40), "purple").save(source, quality=90)
            payload = source.read_bytes()
            source.write_bytes(payload[:-20])

            with self.assertRaises(ValueError):
                inspect_local_image(source)

    def test_unsharp_and_upscale_do_not_require_deep_watermark_consent(self):
        for operations in (
            ImageOperationData(
                upscale_before=False,
                remove_background=False,
                unsharp=True,
            ),
            ImageOperationData(
                upscale_before=True,
                remove_background=False,
                unsharp=False,
            ),
        ):
            self.assertEqual(
                operation_validation_issues(operations, allow_full_image_changes=False),
                (),
            )
    def test_recipes_are_editable_presets_on_one_operation_model(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        operation_identity = id(state.processing.operations)
        apply_processing_recipe(state, "prepare_clipart")

        self.assertEqual(id(state.processing.operations), operation_identity)
        self.assertTrue(state.processing.operations.remove_background)
        self.assertEqual(
            state.processing.operations.remove_background_provider,
            "local_rembg",
        )
        state.processing.operations.trim = False
        self.assertFalse(state.processing.operations.trim)

        apply_processing_recipe(state, "check_cleanup")
        self.assertTrue(state.processing.operations.remove_generator_fields)
        self.assertFalse(state.processing.operations.remove_background)

    def test_pipeline_order_is_deterministic_and_explains_invalid_settings(self):
        operations = ImageOperationData(
            visible_mark_cleanup=True,
            upscale_before=True,
            unsharp=True,
            remove_background=True,
            upscale_after=True,
            edge_shrink=True,
            trim=True,
            export_300_dpi=True,
        )
        steps = processing_pipeline_steps(operations)
        self.assertLess(steps.index("Апскейл до удаления фона"), steps.index("Удаление фона"))
        self.assertLess(steps.index("Удаление фона"), steps.index("Апскейл после удаления фона"))
        self.assertEqual(
            operation_validation_issues(operations, allow_full_image_changes=False),
            (),
        )

        operations.visible_mark_cleanup_mode = "confirmed_area"
        self.assertIn(
            "confirmed_area_unavailable",
            operation_validation_issues(
                operations,
                allow_full_image_changes=True,
            ),
        )

    def test_local_request_uses_process_only_worker_without_api_key(self):
        with tempfile.TemporaryDirectory(prefix="processing-request-") as temp:
            state, source = self.make_state(temp)
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )

            self.assertEqual(request.mode, "mode2_process")
            self.assertEqual(request.settings["run_mode"], "process_only")
            self.assertEqual(request.selected_files, [str(source)])
            self.assertNotIn(str(source), repr(request))
            self.assertEqual(missing_processing_runtime_requirements(request), ())

    def test_local_chroma_run_plan_keeps_only_the_selected_preset_color(self):
        with tempfile.TemporaryDirectory(prefix="processing-chroma-request-") as temp:
            state, _ = self.make_state(temp)
            operations = state.processing.operations
            operations.upscale_before = False
            operations.unsharp = False
            operations.remove_background = True
            operations.remove_background_provider = "local_chroma_key"
            operations.chroma_key_color = "red"
            operations.chroma_key_tolerance = 255
            operations.chroma_key_softness = 255
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )

            self.assertEqual(request.settings["chroma_key_color"], "red")
            self.assertNotIn("chroma_key_custom_color", request.settings)
            self.assertNotIn("chroma_key_tolerance", request.settings)
            self.assertNotIn("chroma_key_softness", request.settings)
            self.assertEqual(missing_processing_runtime_requirements(request), ())

    def test_processing_request_preserves_selected_output_directory(self):
        with tempfile.TemporaryDirectory(prefix="processing-output-") as temp:
            state, _ = self.make_state(temp)
            selected_output = Path(temp) / "output_trim"
            state.common.output_dir = str(selected_output)
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )
            self.assertEqual(request.settings["run_mode"], "process_only")
            self.assertEqual(
                request.settings["output_dir"],
                str(selected_output / "output"),
            )

    def test_external_action_requires_consent_and_matching_key(self):
        with tempfile.TemporaryDirectory(prefix="processing-external-") as temp:
            state, _ = self.make_state(temp)
            state.processing.operations.upscale_before = True
            state.processing.operations.upscale_before_provider = "kie"
            with self.assertRaisesRegex(ValueError, "разрешение"):
                build_processing_run_request(
                    state,
                    {},
                    allow_full_image_changes=True,
                    external_transfer_consent=False,
                )
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )
            self.assertEqual(
                missing_processing_runtime_requirements(request),
                ("KIE API Key",),
            )

    def test_fal_upscale_requires_fal_key_in_processing_mode(self):
        with tempfile.TemporaryDirectory(prefix="processing-fal-key-") as temp:
            state, _ = self.make_state(temp)
            operations = state.processing.operations
            operations.upscale_before = True
            operations.upscale_before_provider = "fal"
            operations.fal_upscale_model = "bria/upscale/creative"
            operations.remove_background = False
            request = build_processing_run_request(
                state,
                {"fal_api_key": "fal-test-key"},
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )

            self.assertEqual(missing_processing_runtime_requirements(request), ())

            missing = build_processing_run_request(
                state,
                {"kie_api_key": "kie-test-key"},
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )
            self.assertEqual(
                missing_processing_runtime_requirements(missing),
                ("Fal.ai API Key",),
            )

    def test_fal_remove_background_rejects_oversized_batch_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="processing-fal-size-") as temp:
            root = Path(temp)
            accepted = root / "accepted.png"
            first_oversized = root / "rough_52_upscaled-before.png"
            second_oversized = root / "rough_44_upscaled-before.png"
            for path in (accepted, first_oversized, second_oversized):
                Image.new("RGB", (12, 8), (120, 80, 30)).save(path)
            with first_oversized.open("ab") as handle:
                handle.truncate(9 * 1024 * 1024)
            with second_oversized.open("ab") as handle:
                handle.truncate(10 * 1024 * 1024)

            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [
                str(first_oversized),
                str(accepted),
                str(second_oversized),
            ]
            operations = state.processing.operations
            operations.upscale_before = False
            operations.unsharp = False
            operations.remove_background = True
            operations.remove_background_provider = "fal"
            operations.fal_remove_bg_model = "fal-ai/ideogram/remove-background"

            with self.assertRaises(ValueError) as raised:
                build_processing_run_request(
                    state,
                    {"fal_api_key": "fal-test-key"},
                    allow_full_image_changes=True,
                    external_transfer_consent=True,
                )

            message = str(raised.exception)
            self.assertIn("Fal.ai Ideogram", message)
            self.assertIn("2 из 3", message)
            self.assertIn(first_oversized.name, message)
            self.assertIn(second_oversized.name, message)
            self.assertIn("8 МБ", message)

    def test_fal_oversized_preflight_disables_run_without_creating_worker(self):
        with tempfile.TemporaryDirectory(prefix="processing-fal-preflight-") as temp:
            source = Path(temp) / "oversized.png"
            Image.new("RGB", (12, 8), (120, 80, 30)).save(source)
            with source.open("ab") as handle:
                handle.truncate(9 * 1024 * 1024)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [str(source)]
            state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.REVIEW_RUN
            operations = state.processing.operations
            operations.upscale_before = False
            operations.remove_background = True
            operations.remove_background_provider = "fal"
            operations.fal_remove_bg_model = "fal-ai/ideogram/remove-background"
            shell = AppShell(state)
            factory = WorkerFactory()
            controller = install_processing_flow(
                shell,
                runtime_settings_provider=lambda: {"fal_api_key": "fal-test-key"},
                worker_factory=factory,
            )

            controller._refresh_preflight()

            self.assertFalse(shell.next_button.isEnabled())
            self.assertIn("oversized.png", controller.review_page.requirements_label.text())
            self.assertIsNone(controller.start())
            self.assertEqual(factory.workers, [])

    def test_leaving_failed_fal_preflight_reenables_next_step(self):
        with tempfile.TemporaryDirectory(prefix="processing-fal-back-") as temp:
            source = Path(temp) / "oversized.png"
            Image.new("RGB", (12, 8), (120, 80, 30)).save(source)
            with source.open("ab") as handle:
                handle.truncate(9 * 1024 * 1024)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [str(source)]
            state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.REVIEW_RUN
            operations = state.processing.operations
            operations.upscale_before = False
            operations.remove_background = True
            operations.remove_background_provider = "fal"
            operations.fal_remove_bg_model = "fal-ai/ideogram/remove-background"
            shell = AppShell(state)
            controller = install_processing_flow(
                shell,
                runtime_settings_provider=lambda: {"fal_api_key": "fal-test-key"},
                worker_factory=WorkerFactory(),
            )
            controller._refresh_preflight()
            self.assertFalse(shell.next_button.isEnabled())

            shell.go_back()

            self.assertIs(state.current_step, StepId.PIPELINE)
            self.assertTrue(shell.next_button.isEnabled())

    def test_fal_size_preflight_allows_oversized_file_with_usable_alpha(self):
        with tempfile.TemporaryDirectory(prefix="processing-fal-alpha-") as temp:
            source = Path(temp) / "already-transparent.png"
            image = Image.new("RGBA", (12, 8), (120, 80, 30, 255))
            image.putpixel((0, 0), (120, 80, 30, 0))
            image.save(source)
            with source.open("ab") as handle:
                handle.truncate(9 * 1024 * 1024)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [str(source)]
            operations = state.processing.operations
            operations.upscale_before = False
            operations.remove_background = True
            operations.remove_background_provider = "fal"
            operations.fal_remove_bg_model = "fal-ai/ideogram/remove-background"

            request = build_processing_run_request(
                state,
                {"fal_api_key": "fal-test-key"},
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )

            self.assertEqual(request.selected_files, [str(source)])

    def test_fal_remove_size_preflight_allows_https_result_from_kie_upscale(self):
        with tempfile.TemporaryDirectory(prefix="processing-kie-fal-size-") as temp:
            source = Path(temp) / "large-source.png"
            Image.new("RGB", (12, 8), (120, 80, 30)).save(source)
            with source.open("ab") as handle:
                handle.truncate(9 * 1024 * 1024)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [str(source)]
            operations = state.processing.operations
            operations.upscale_before = True
            operations.upscale_before_provider = "kie"
            operations.remove_background = True
            operations.remove_background_provider = "fal"
            operations.fal_remove_bg_model = "fal-ai/ideogram/remove-background"

            request = build_processing_run_request(
                state,
                {"kie_api_key": "kie-test-key", "fal_api_key": "fal-test-key"},
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )

            self.assertEqual(request.selected_files, [str(source)])

    def test_processing_fal_cost_never_claims_zero(self):
        operations = ImageOperationData(
            upscale_before=True,
            upscale_before_provider="fal",
            fal_upscale_model="topaz/upscale/image/precision",
            upscale_after=True,
            upscale_after_provider="fal",
            fal_upscale_after_model="topaz/upscale/image/transparent",
            remove_background=False,
        )

        text = estimate_processing_cost(operations, 3)

        self.assertEqual(text, "Fal.ai: стоимость не рассчитана")
        self.assertNotIn("$0.000", text)

    def test_processing_cost_breakdown_keeps_known_cost_with_fal_pending(self):
        operations = ImageOperationData(
            upscale_before=True,
            upscale_before_provider="kie",
            kie_upscale_model="recraft/crisp-upscale",
            remove_background=True,
            remove_background_provider="fal",
            fal_remove_bg_model="fal-ai/bria/background/remove",
        )

        estimate = estimate_processing_cost_breakdown(operations, 4)

        self.assertEqual(estimate.request_count, 8)
        self.assertEqual(estimate.provider_usd["kie"], Decimal("0.0100"))
        self.assertEqual(estimate.provider_usd["fal"], Decimal("0"))
        self.assertEqual(estimate.incomplete_providers, ("fal",))
        self.assertFalse(estimate.complete)

    def test_processing_review_describes_local_work_without_api_charge(self):
        with tempfile.TemporaryDirectory(prefix="processing-local-cost-") as temp:
            state, _ = self.make_state(temp)
            operations = state.processing.operations
            operations.upscale_before = False
            operations.remove_background = False
            page = ProcessingReviewRunPage(
                state,
                ProcessingFilesPage(state, lambda: None),
                ProcessingPipelinePage(state, lambda: None),
            )

            self.assertIn("всего: 0 вызовов", page.requests_label.text())
            self.assertEqual(
                page.cost_breakdown_label.text(),
                "Локальная обработка — без оплаты API.",
            )

    def test_processing_fal_endpoint_quantities_include_every_selected_stage(self):
        operations = ImageOperationData(
            upscale_before=True,
            upscale_before_provider="fal",
            fal_upscale_model="topaz/upscale/image/precision",
            upscale_after=True,
            upscale_after_provider="fal",
            fal_upscale_after_model="topaz/upscale/image/transparent",
            remove_background=True,
            remove_background_provider="fal",
            fal_remove_bg_model="fal-ai/bria/background/remove",
        )

        self.assertEqual(
            processing_fal_endpoint_quantities(operations, 17),
            {
                "topaz/upscale/image/precision": 17,
                "topaz/upscale/image/transparent": 17,
                "fal-ai/bria/background/remove": 17,
            },
        )

    def test_processing_review_refreshes_fal_and_keeps_kie_subtotal(self):
        with tempfile.TemporaryDirectory(prefix="processing-review-cost-") as temp:
            state, _ = self.make_state(temp)
            operations = state.processing.operations
            operations.upscale_before = True
            operations.upscale_before_provider = "kie"
            operations.kie_upscale_model = "recraft/crisp-upscale"
            operations.remove_background = True
            operations.remove_background_provider = "fal"
            operations.fal_remove_bg_model = "fal-ai/bria/background/remove"
            page = ProcessingReviewRunPage(
                state,
                ProcessingFilesPage(state, lambda: None),
                ProcessingPipelinePage(state, lambda: None),
                fal_cost_refresh=lambda: (0.033, "USD"),
            )

            before = page.cost_breakdown_label.text()
            self.assertIn("KIE — 0.003 USD", before)
            self.assertIn("Fal.ai — требуется обновить", before)
            self.assertIn("Итого — не рассчитано полностью", before)

            page.refresh_fal_cost()

            after = page.cost_breakdown_label.text()
            self.assertIn("KIE — 0.003 USD", after)
            self.assertIn("Fal.ai — 0.033 USD", after)
            self.assertIn("Итого — 0.036 USD", after)

    def test_processing_controller_uses_live_fal_estimate_for_selected_endpoints(self):
        with tempfile.TemporaryDirectory(prefix="processing-controller-cost-") as temp:
            state, _ = self.make_state(temp)
            operations = state.processing.operations
            operations.upscale_before = True
            operations.upscale_before_provider = "fal"
            operations.fal_upscale_model = "topaz/upscale/image/precision"
            operations.remove_background = False
            shell = AppShell(state)
            controller = install_processing_flow(
                shell,
                runtime_settings_provider=lambda: {"fal_api_key": "test-key"},
            )

            with patch.object(
                v3_processing_flow,
                "estimate_fal_cost",
                return_value=(1.25, "USD"),
            ) as estimate:
                result = controller._refresh_fal_cost()

            self.assertEqual(result, (1.25, "USD"))
            estimate.assert_called_once_with(
                "test-key",
                {"topaz/upscale/image/precision": 1},
            )

    def test_visible_mark_cleanup_is_local_but_requires_full_image_opt_in(self):
        with tempfile.TemporaryDirectory(prefix="processing-visible-mark-") as temp:
            state, _ = self.make_state(temp)
            operations = state.processing.operations
            operations.unsharp = False
            operations.visible_mark_cleanup = True
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )
            self.assertEqual(missing_processing_runtime_requirements(request), ())

    def test_duplicate_output_names_are_rejected_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="processing-collision-") as temp:
            first_dir = Path(temp) / "one"
            second_dir = Path(temp) / "two"
            first_dir.mkdir()
            second_dir.mkdir()
            first = first_dir / "same.png"
            second = second_dir / "same.png"
            Image.new("RGB", (2, 2), "red").save(first)
            Image.new("RGB", (2, 2), "blue").save(second)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [str(first), str(second)]
            apply_processing_recipe(state, "basic_enhancement")

            with self.assertRaisesRegex(ValueError, "Одинаковые имена"):
                build_processing_run_request(
                    state,
                    {},
                    allow_full_image_changes=False,
                    external_transfer_consent=False,
                )

    def test_pipeline_validation_is_explained_in_plain_russian(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.PIPELINE
        operations = state.processing.operations
        for field in (
            "visible_mark_cleanup",
            "upscale_before",
            "upscale_after",
            "unsharp",
            "remove_background",
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
            setattr(operations, field, False)
        shell = AppShell(state)
        install_processing_flow(shell, worker_factory=WorkerFactory())

        shell.go_next()

        self.assertIn("Включите хотя бы одну операцию", shell.validation_label.text())
        self.assertNotIn("processing_operation_required", shell.validation_label.text())

    def test_processing_batch_has_practical_ui_limit(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.processing.selected_files = [
            f"C:/images/{index}.png" for index in range(MAX_PROCESSING_FILES + 1)
        ]
        shell = AppShell(state)
        controller = install_processing_flow(shell, worker_factory=WorkerFactory())
        self.assertIn(
            "processing_file_limit_exceeded",
            controller.files_page.validation_issues(),
        )
    def test_unknown_providers_fail_closed_before_worker(self):
        with tempfile.TemporaryDirectory(prefix="processing-provider-") as temp:
            for field, enabled_field in (
                ("upscale_before_provider", "upscale_before"),
                ("upscale_after_provider", "upscale_after"),
                ("remove_background_provider", "remove_background"),
            ):
                state, _ = self.make_state(temp)
                operations = state.processing.operations
                operations.upscale_before = False
                operations.upscale_after = False
                operations.remove_background = False
                setattr(operations, enabled_field, True)
                setattr(operations, field, "rogue")
                self.assertTrue(uses_external_processing(operations))
                with self.assertRaisesRegex(ValueError, "Неизвестный провайдер"):
                    build_processing_run_request(
                        state,
                        {"kie_api_key": "saved-key"},
                        allow_full_image_changes=True,
                        external_transfer_consent=True,
                    )
    def test_controller_starts_only_after_explicit_review_run(self):
        with tempfile.TemporaryDirectory(prefix="processing-controller-") as temp:
            state, _ = self.make_state(temp)
            state.current_step_by_mode[ProjectMode.PROCESSING] = StepId.REVIEW_RUN
            shell = AppShell(state)
            factory = WorkerFactory()
            controller = install_processing_flow(
                shell,
                runtime_settings_provider=lambda: {},
                worker_factory=factory,
                authorization_provider=lambda: None,
            )
            shell.go_next()
            self.assertEqual(len(factory.workers), 1)
            self.assertTrue(factory.workers[0].started)
            self.assertEqual(factory.workers[0].kwargs["mode"], "mode2_process")

    def test_real_local_pipeline_creates_new_file_without_touching_source(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="processing-output-") as temp:
            state, source = self.make_state(temp)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )
            worker = WorkerThread(**request.worker_kwargs())
            worker._mode2_process_files()
            after = hashlib.sha256(source.read_bytes()).hexdigest()
            outputs = list((Path(temp) / "output").glob("source_ready*.png"))

            self.assertEqual(before, after)
            self.assertEqual(len(outputs), 1)
            self.assertNotEqual(outputs[0].resolve(), source.resolve())

    def test_real_local_pipeline_processes_readme_jpg_in_batch(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="processing-readme- batch-") as temp:
            root = Path(temp)
            readme = root / "README.jpg"
            sibling = root / "sibling.jpg"
            Image.new("RGB", (12, 8), (90, 40, 20)).save(readme, format="JPEG")
            Image.new("RGB", (10, 6), (20, 40, 90)).save(sibling, format="JPEG")
            state, _ = self.make_state(temp)
            state.processing.selected_files = [str(readme), str(sibling)]
            before = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (readme, sibling)
            }
            request = build_processing_run_request(
                state,
                {},
                allow_full_image_changes=True,
                external_transfer_consent=False,
            )
            worker = WorkerThread(**request.worker_kwargs())
            worker._mode2_process_files()

            outputs = list((root / "output").glob("*_ready*.png"))
            after = {
                path: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (readme, sibling)
            }
            self.assertEqual(before, after)
            self.assertEqual(
                {path.name.split("_ready", 1)[0] for path in outputs},
                {"README", "sibling"},
            )


if __name__ == "__main__":
    unittest.main()
