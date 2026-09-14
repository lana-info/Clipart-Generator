from studio_workflow_host import WorkflowHost
import hashlib
import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QMimeData, QObject, QUrl, Qt, pyqtSignal
from PyQt6.QtWidgets import QApplication, QCheckBox

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
    inspect_local_image,
    install_processing_flow,
    missing_processing_runtime_requirements,
    operation_validation_issues,
    processing_change_summary,
    processing_pipeline_steps,
    uses_external_processing,
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

        pages = view.shell.workflow_controller("processing").pages
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
                WorkflowHost(shell, "processing"),
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
            self.assertTrue(page.requirements_label.isHidden())
            self.assertEqual(page.requirements_label.text(), "")
            self.assertIn("внешнему сервису", page.warning_label.text())

    def test_process_more_clears_old_inputs_and_returns_to_files_step(self):
        with tempfile.TemporaryDirectory(prefix="processing-more-") as temp:
            state, source = self.make_state(temp)
            shell = AppShell(state)
            controller = install_processing_flow(WorkflowHost(shell, "processing"), worker_factory=WorkerFactory())
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
            controller = install_processing_flow(WorkflowHost(shell, "processing"))
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

    def test_drag_and_drop_accepts_only_valid_local_images(self):
        with tempfile.TemporaryDirectory(prefix="processing-drop-") as temp:
            source = Path(temp) / "drop.png"
            Image.new("RGB", (4, 4), "green").save(source)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            shell = AppShell(state)
            controller = install_processing_flow(WorkflowHost(shell, "processing"))
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
        controller = install_processing_flow(WorkflowHost(shell, "processing"))
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

    def test_processing_fal_cost_never_claims_zero(self):
        operations = ImageOperationData(
            upscale_before=True,
            upscale_before_provider="fal",
            fal_upscale_model="topaz/upscale/image/precision",
            remove_background=False,
        )

        text = estimate_processing_cost(operations, 3)

        self.assertEqual(text, "Fal.ai: стоимость не рассчитана")
        self.assertNotIn("$0.000", text)

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
        install_processing_flow(WorkflowHost(shell, "processing"), worker_factory=WorkerFactory())

        shell.go_next()

        self.assertIn("Включите хотя бы одну операцию", shell.validation_label.text())
        self.assertNotIn("processing_operation_required", shell.validation_label.text())

    def test_processing_batch_has_practical_ui_limit(self):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        state.processing.selected_files = [
            f"C:/images/{index}.png" for index in range(MAX_PROCESSING_FILES + 1)
        ]
        shell = AppShell(state)
        controller = install_processing_flow(WorkflowHost(shell, "processing"), worker_factory=WorkerFactory())
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
                WorkflowHost(shell, "processing"),
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
