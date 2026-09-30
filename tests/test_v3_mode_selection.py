import os
import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from license_client import LicenseAuthorization, ModuleEntitlement
from v3_components import V3_WINDOW_DEFAULT_SIZE, V3_WINDOW_MINIMUM_SIZE
from v3_mode_selection import (
    MODE_CARD_SPECS,
    ModeSelectionScreen,
    SelectionIntent,
    V3ApplicationView,
)
from v3_project_state import (
    CommonProjectData,
    PinterestPinData,
    PinterestModeData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
    route_for_mode,
    ProjectStateError,
)


class V3ModeSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_results_handoff_preserves_source_and_never_starts_worker(self):
        from PIL import Image
        from tests.test_v3_run_queue import generation_request
        from v3_run_queue import RunQueueSession, RunItemStatus
        with tempfile.TemporaryDirectory() as temp:
            worker = Mock()
            view = V3ApplicationView(worker_factory=worker)
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            source = view.shell
            controller = source.workflow_controller(ProjectMode.CLIPART.value)
            page = controller.run_queue.page
            session = RunQueueSession(generation_request(temp, 1), ProjectMode.CLIPART)
            session.output_dir.mkdir(parents=True, exist_ok=True)
            image = session.output_dir / 'example.png'
            Image.new('RGB', (20, 20), 'white').save(image)
            original = image.read_bytes()
            session.items[0].output_path = str(image)
            session.items[0].status = RunItemStatus.FAILED
            session.running = False
            page.set_session(session)
            page.queue.setCurrentRow(0)
            self.assertEqual(page.processing_selection(), [str(image)])
            with patch.object(view, '_save_draft', return_value=False):
                self.assertFalse(view._open_results_in_processing(source, [str(image)]))
            self.assertIs(view.shell, source)
            session.running = True
            self.assertFalse(page.processing_selection())
            self.assertFalse(view._open_results_in_processing(source, [str(image)]))
            session.running = False
            with patch.object(controller, 'is_busy', return_value=True, create=True):
                self.assertFalse(view._open_results_in_processing(source, [str(image)]))
            with patch.object(view, '_replace_shell', return_value=False):
                view._active_project_id = 'original-project'
                self.assertFalse(view._open_results_in_processing(source, [str(image)]))
                self.assertEqual(view._active_project_id, 'original-project')
            view._active_project_id = None
            image.unlink()
            self.assertFalse(page.processing_selection())
            image.write_bytes(original)
            page.refresh_from_state()
            page.send_to_processing_button.click()
            self.assertIsNot(view.shell, source)
            self.assertIs(view.shell.state.mode, ProjectMode.PROCESSING)
            self.assertEqual(view.shell.state.processing.selected_files, [str(image)])
            self.assertFalse(view.shell.state.processing.overwrite_existing)
            self.assertEqual(image.read_bytes(), original)
            worker.assert_not_called()
            self.assertFalse(view._open_results_in_processing(source, [str(image)]))
            view.close()

    def tearDown(self):
        self.app.processEvents()

    def test_application_uses_one_default_and_minimum_window_size(self):
        view = V3ApplicationView()

        self.assertEqual((view.width(), view.height()), V3_WINDOW_DEFAULT_SIZE)
        self.assertEqual(
            (view.minimumWidth(), view.minimumHeight()),
            V3_WINDOW_MINIMUM_SIZE,
        )
        view.resize(1, 1)
        self.assertEqual((view.width(), view.height()), V3_WINDOW_MINIMUM_SIZE)

    def test_clipart_card_describes_mass_image_generation(self):
        spec = MODE_CARD_SPECS[ProjectMode.CLIPART]

        self.assertIn("Массов", spec.description)
        self.assertIn("клипарт", spec.description.lower())
        self.assertIn("изображен", spec.result.lower())

    def test_user_resized_window_size_survives_screen_and_step_changes(self):
        view = V3ApplicationView()
        view.resize(1037, 733)
        view.show()
        self.app.processEvents()
        expected = (1037, 733)

        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()
        self.assertEqual((view.width(), view.height()), expected)

        view.shell.state.set_step(StepId.PROMPTS)
        view.shell.refresh()
        self.app.processEvents()
        self.assertEqual((view.width(), view.height()), expected)

        view.show_mode_switcher()
        self.app.processEvents()
        self.assertEqual((view.width(), view.height()), expected)
        self.assertTrue(view.cancel_mode_switch())
        self.app.processEvents()
        self.assertEqual((view.width(), view.height()), expected)

    def test_shell_tracks_arbitrary_workflow_controller_by_module_id(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        shell = view.shell
        controller = Mock()
        controller.worker = Mock()
        controller.worker.isRunning = Mock(return_value=True)
        controller.run_queue.session = None

        shell.register_workflow_controller("text-probe", controller)
        self.assertIs(shell.workflow_controller("text-probe"), controller)
        self.assertIs(shell.active_run_controller(), controller)
        self.assertFalse(hasattr(shell, "text_probe_flow_controller"))
        view.close()
        view.deleteLater()

    def test_mode_switch_is_blocked_while_any_run_is_active(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()
        controller = view.shell.workflow_controller("clipart")
        controller.worker = Mock()
        controller.worker.isRunning = Mock(return_value=True)

        view.show_mode_switcher()
        self.app.processEvents()

        self.assertIs(view.stack.currentWidget(), view.shell)
        self.assertFalse(view.shell.save_error_label.isHidden())
        self.assertIn("текущее задание", view.shell.save_error_label.text())
        view.close()
        view.deleteLater()

    def test_window_size_is_stable_across_every_mode_route(self):
        for mode in ProjectMode:
            with self.subTest(mode=mode):
                view = V3ApplicationView()
                view.resize(1093, 747)
                view.show()
                view.mode_selection.mode_cards[mode].start_button.click()
                self.app.processEvents()

                for step in view.shell.state.route:
                    view.shell.state.set_step(step)
                    view.shell.refresh()
                    self.app.processEvents()
                    self.assertEqual((view.width(), view.height()), (1093, 747))

                view.close()
                view.deleteLater()

    def test_screen_change_preserves_maximized_state_and_restore_geometry(self):
        view = V3ApplicationView()
        view.resize(1037, 733)
        view.show()
        self.app.processEvents()
        restore_geometry = view.geometry()
        view.showMaximized()
        self.app.processEvents()
        self.assertEqual(view.normalGeometry(), restore_geometry)

        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()

        self.assertTrue(view.isMaximized())
        self.assertEqual(view.normalGeometry(), restore_geometry)

        view.showNormal()
        self.app.processEvents()
        self.assertFalse(view.isMaximized())
        self.assertEqual(view.geometry(), restore_geometry)

    def test_each_mode_card_starts_a_fresh_project_on_the_correct_route(self):
        for mode in ProjectMode:
            with self.subTest(mode=mode):
                view = V3ApplicationView()
                started = []
                view.new_project_started.connect(started.append)

                view.mode_selection.mode_cards[mode].start_button.click()
                state = view.project_state

                self.assertIsNotNone(state)
                self.assertEqual(state.mode, mode)
                self.assertEqual(state.route, route_for_mode(mode))
                self.assertEqual(state.current_step, route_for_mode(mode)[0])
                self.assertEqual(started, [mode.value])
                self.assertIs(view.stack.currentWidget(), view.shell)
                view.close()
                view.deleteLater()

    def test_first_screen_shows_license_and_api_controls_before_mode_selection(self):
        screen = ModeSelectionScreen()
        license_requests = []
        api_requests = []
        screen.license_requested.connect(lambda: license_requests.append(True))
        screen.api_settings_requested.connect(lambda: api_requests.append(True))

        screen.set_license_status(
            "Лицензия активна",
            "Проверено онлайн: 15.08.2026 10:30",
        )
        screen.license_button.click()
        screen.api_settings_button.click()

        self.assertFalse(screen.account_card.isHidden())
        self.assertEqual(screen.license_status_label.text(), "Лицензия активна")
        self.assertEqual(
            screen.license_verification_label.text(),
            "Проверено онлайн: 15.08.2026 10:30",
        )
        self.assertEqual(screen.license_button.text(), "Лицензия")
        self.assertTrue(screen.license_status_label.isHidden())
        self.assertEqual(screen.api_settings_button.text(), "Настройки API")
        self.assertEqual(license_requests, [True])
        self.assertEqual(api_requests, [True])
        screen.close()
        screen.deleteLater()

    def test_provider_concurrency_preferences_override_runtime_settings(self):
        with tempfile.TemporaryDirectory(prefix="clipart-provider-concurrency-") as temp:
            draft_path = Path(temp) / "project_state.json"
            preferences_path = Path(temp) / "preferences.json"
            preferences_path.write_text(
                json.dumps(
                    {
                        "kie_concurrency": 10,
                        "photoroom_concurrency": 2,
                        "fal_concurrency": 35,
                    }
                ),
                encoding="utf-8",
            )

            view = V3ApplicationView(
                draft_path=draft_path,
                runtime_settings_provider=lambda: {
                    "kie_concurrency": 1,
                    "photoroom_concurrency": 1,
                    "fal_concurrency": 1,
                },
            )

            self.assertEqual(view._runtime_settings()["kie_concurrency"], 3)
            self.assertEqual(view._runtime_settings()["photoroom_concurrency"], 2)
            self.assertEqual(view._runtime_settings()["fal_concurrency"], 3)
            view.close()
            view.deleteLater()

    def test_pinterest_flow_uses_current_application_locale_for_inherited_pages(self):
        """Omitting the locale at the real installer call must make this fail."""
        with tempfile.TemporaryDirectory(prefix="clipart-pinterest-locale-") as temp:
            draft_path = Path(temp) / "project_state.json"
            preferences_path = Path(temp) / "preferences.json"
            preferences_path.write_text(
                json.dumps({"app_language": "en-US"}),
                encoding="utf-8",
            )

            view = V3ApplicationView(draft_path=draft_path)
            view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
            self.app.processEvents()

            controller = view.shell.workflow_controller("pinterest")
            self.assertEqual(
                controller.pages[StepId.PROJECT].card.title_label.text(),
                "Work folder",
            )
            self.assertEqual(
                controller.pages[StepId.PROMPTS].card.title_label.text(),
                "Pinterest prompts",
            )
            view.close()
            view.deleteLater()

    def test_new_project_defaults_to_pictures_instead_of_process_directory(self):
        with tempfile.TemporaryDirectory(prefix="clipart-default-folder-") as temp:
            default_folder = Path(temp) / "Pictures" / "Vibix Images"
            draft_path = Path(temp) / "app-data" / "project_state.json"
            with patch(
                "v3_mode_selection.default_work_directory",
                return_value=default_folder,
            ):
                view = V3ApplicationView(draft_path=draft_path)
                view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

            self.assertEqual(view.project_state.common.work_dir, str(default_folder))
            self.assertTrue(default_folder.is_dir())
            self.assertNotEqual(view.project_state.common.work_dir, os.getcwd())
            view.close()
            view.deleteLater()

    def test_last_selected_work_and_output_folders_are_reused(self):
        with tempfile.TemporaryDirectory(prefix="clipart-last-folder-") as temp:
            root = Path(temp)
            default_folder = root / "Pictures" / "Vibix Images"
            selected_work = root / "selected-work"
            selected_output = root / "selected-output"
            selected_work.mkdir()
            selected_output.mkdir()
            draft_path = root / "app-data" / "project_state.json"

            with patch(
                "v3_mode_selection.default_work_directory",
                return_value=default_folder,
            ):
                clipart = V3ApplicationView(draft_path=draft_path)
                clipart.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
                clipart.shell.current_page.work_dir_edit.setText(str(selected_work))
                self.app.processEvents()
                clipart.close()
                clipart.deleteLater()

                processing = V3ApplicationView(draft_path=draft_path)
                processing.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
                processing.shell.current_page.output_selector.edit.setText(
                    str(selected_output)
                )
                self.app.processEvents()
                processing.close()
                processing.deleteLater()

                intervening_clipart = V3ApplicationView(draft_path=draft_path)
                intervening_clipart.mode_selection.mode_cards[
                    ProjectMode.CLIPART
                ].start_button.click()
                intervening_clipart.close()
                intervening_clipart.deleteLater()

                restored = V3ApplicationView(draft_path=draft_path)
                restored.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()

            self.assertEqual(restored.project_state.common.work_dir, str(selected_work))
            self.assertEqual(
                restored.project_state.output_dir_for_mode(ProjectMode.PROCESSING),
                str(selected_output),
            )
            restored.close()
            restored.deleteLater()

    def test_pinterest_card_promises_only_images_from_prompts(self):
        screen = ModeSelectionScreen()
        spec = MODE_CARD_SPECS[ProjectMode.PINTEREST]
        card = screen.mode_cards[ProjectMode.PINTEREST]
        promise = f"{spec.description} {spec.result}".lower()

        self.assertIn("только", promise)
        self.assertIn("изображения", promise)
        self.assertIn("по промптам", promise)
        self.assertIn("без публикации", promise)
        self.assertIn("без публикации", card.accessibleDescription().lower())
        self.assertNotIn("публикуем", promise)
        screen.close()
        screen.deleteLater()

    def test_new_projects_do_not_inherit_another_modes_values(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        clipart_state = view.project_state
        clipart_state.clipart.prompts.append(PromptEntry("private clipart prompt"))

        view.show_new_project()
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        pinterest_state = view.project_state
        self.assertIsNot(pinterest_state, clipart_state)
        self.assertEqual(pinterest_state.clipart.prompts, [])
        self.assertEqual(pinterest_state.pinterest.pin.product_paths, [])
        self.assertEqual(pinterest_state.processing.selected_files, [])
        pinterest_state.pinterest.pin.pin_title = "vertical pin"

        view.show_new_project()
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        processing_state = view.project_state
        self.assertIsNot(processing_state, pinterest_state)
        self.assertEqual(processing_state.clipart.prompts, [])
        self.assertEqual(processing_state.pinterest.pin.product_paths, [])
        self.assertEqual(processing_state.processing.selected_files, [])
        view.close()
        view.deleteLater()

    def test_last_project_is_snapshotted_and_can_be_continued(self):
        recent = ProjectState(
            mode=ProjectMode.PINTEREST,
            common=CommonProjectData(project_name="Summer Pins"),
            pinterest=PinterestModeData(
                pin=PinterestPinData(pin_title="vertical beach pin"),
            ),
        )
        recent.set_step(StepId.PROMPTS)
        view = V3ApplicationView(recent)
        continued = []
        view.project_continued.connect(continued.append)

        self.assertFalse(view.mode_selection.recent_project_card.isHidden())
        self.assertIn(
            "Summer Pins",
            view.mode_selection.continue_button.accessibleDescription(),
        )

        recent.pinterest.pin.pin_title = "mutated outside"
        view.mode_selection.continue_button.click()
        state = view.project_state
        self.assertEqual(state.mode, ProjectMode.PINTEREST)
        self.assertEqual(state.current_step, StepId.PROMPTS)
        self.assertEqual(
            state.pinterest.pin.pin_title,
            "vertical beach pin",
        )
        self.assertEqual(continued, [ProjectMode.PINTEREST.value])
        view.close()
        view.deleteLater()

    def test_recent_project_draft_is_restored_from_disk(self):
        with tempfile.TemporaryDirectory(prefix="clipart-v3-draft-") as temp:
            draft_path = Path(temp) / "project_state.json"
            view = V3ApplicationView(draft_path=draft_path)
            view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
            state = view.project_state
            state.common.work_dir = temp
            state.clipart.prompts.append(PromptEntry("restored clipart prompt"))
            state.pinterest.pin.pin_title = "restored pinterest prompt"
            view.shell.mark_dirty()
            view.close()
            view.deleteLater()

            restored = V3ApplicationView(draft_path=draft_path)
            self.assertFalse(restored.mode_selection.saved_projects_card.isHidden())
            self.assertTrue(
                restored.mode_selection.saved_project_buttons[0].accessibleName()
            )
            restored.mode_selection.saved_project_buttons[0].click()
            restored_state = restored.project_state
            self.assertEqual(
                restored_state.clipart.prompts[0].prompt,
                "restored clipart prompt",
            )
            self.assertEqual(
                restored_state.pinterest.pin.pin_title,
                "restored pinterest prompt",
            )
            restored.close()
            restored.deleteLater()

    def test_autosave_failure_is_visible_and_success_clears_warning(self):
        with tempfile.TemporaryDirectory(prefix="clipart-autosave-") as temp:
            draft_path = Path(temp) / "app-data" / "project_state.json"
            view = V3ApplicationView(draft_path=draft_path)
            view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

            with patch(
                "v3_mode_selection.save_project_draft",
                side_effect=ProjectStateError("private path must not be shown"),
            ):
                view.shell.mark_dirty()

            self.assertFalse(view.shell.save_error_label.isHidden())
            self.assertEqual(
                view.shell.save_error_label.text(),
                "Не удалось сохранить изменения",
            )
            self.assertNotIn("private", view.shell.save_error_label.text())

            view._save_draft()
            self.assertTrue(view.shell.save_error_label.isHidden())
            view.close()
            view.deleteLater()

    def test_three_recent_projects_retain_four_and_resume_without_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project_state.json"
            factory = Mock(side_effect=AssertionError("resume must not create paid work"))
            view = V3ApplicationView(draft_path=path, worker_factory=factory)
            for number in range(4):
                view._handle_mode_selected(ProjectMode.CLIPART.value)
                view.project_state.common.project_name = f"Набор {number}"
                view.project_state.clipart.prompts = [PromptEntry(f"subject {number}")]
                view.shell.mark_dirty()
                view.show_new_project()
            self.assertEqual(len(view.mode_selection.saved_project_buttons), 3)
            self.assertEqual(len(view._project_store.recent(limit=None)), 4)
            oldest = view._project_store.recent(limit=None)[-1]
            view.close()
            view.deleteLater()
            restored = V3ApplicationView(draft_path=path, worker_factory=factory)
            self.assertEqual(len(restored.mode_selection.saved_project_buttons), 3)
            self.assertTrue(restored.continue_saved_project(oldest.project_id))
            self.assertEqual(restored.project_state.clipart.prompts[0].prompt, "subject 0")
            restored.project_state.common.project_name = "Исправлено"
            restored.shell.mark_dirty()
            self.assertEqual(len(restored._project_store.recent(limit=None)), 4)
            self.assertEqual(restored._project_store.load(oldest.project_id).name, "Исправлено")
            factory.assert_not_called()
            restored.close()
            restored.deleteLater()

    def test_store_failure_does_not_write_a_newer_hidden_legacy_draft(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project_state.json"
            view = V3ApplicationView(draft_path=path)
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            previous = path.read_bytes()
            view.project_state.common.project_name = "Несохранённые изменения"
            with patch.object(view._project_store, "save", side_effect=OSError("disk")):
                view.shell.mark_dirty()
            self.assertEqual(path.read_bytes(), previous)
            self.assertFalse(view.shell.save_error_label.isHidden())
            view.close()
            view.deleteLater()

    def test_composed_image_gateway_enriches_secret_only_at_worker_factory(self):
        from v3_flow_runtime import FlowRunRequest

        raw_worker = Mock()
        factory = Mock(return_value=raw_worker)
        gate = Mock()
        now = datetime.now(timezone.utc)
        gate.authorize_run = Mock(return_value=LicenseAuthorization(
            license_id="fixture", product_id="clipart-generator", device_key="device",
            issued_at=now, expires_at=now + timedelta(minutes=5),
            module_entitlements=(ModuleEntitlement("clipart", now, now + timedelta(days=1)),),
        ))
        view = V3ApplicationView(
            runtime_settings_provider=lambda: {"kie_api_key": "core-secret"},
            worker_factory=factory,
            license_gate=gate,
        )
        view._handle_mode_selected(ProjectMode.CLIPART.value)
        controller = view.shell.workflow_controller("clipart")
        request = FlowRunRequest(
            mode="mode1_generate_only",
            work_dir=".",
            settings={"text_generation_model": "gpt-image-2"},
            generated_prompts=[{"prompt": "test", "references": []}],
        )

        self.assertEqual(controller.shell.image_run_preflight(request), ())
        handle = controller.shell.image_run_launch(request)

        self.assertIsNotNone(handle)
        self.assertEqual(factory.call_args.kwargs["settings"]["kie_api_key"], "core-secret")
        self.assertNotIn("kie_api_key", request.settings)
        gate.authorize_run.assert_called_once_with()
        view.close()
        view.deleteLater()

    def test_worker_factory_uses_saved_project_identity_for_all_modes(self):
        with tempfile.TemporaryDirectory() as temp:
            factory = Mock()
            view = V3ApplicationView(draft_path=Path(temp) / "draft.json", worker_factory=factory)
            identities = []
            for mode in (ProjectMode.CLIPART, ProjectMode.PROCESSING, ProjectMode.PINTEREST):
                view._handle_mode_selected(mode.value)
                controller = view._ensure_mode_controller(view.shell, mode)
                controller.shell.create_worker_job(mode="test", work_dir=temp, settings={})
                first = factory.call_args.kwargs
                self.assertEqual(first["project_id"], view._active_project_id)
                self.assertNotIn("project_id", first["settings"])
                controller.shell.create_worker_job(mode="test", work_dir=temp, settings={})
                self.assertEqual(factory.call_args.kwargs["project_id"], first["project_id"])
                identities.append(first["project_id"])
                view.show_new_project()
            self.assertEqual(len(set(identities)), 3)
            self.assertTrue(view.continue_saved_project(identities[0]))
            view._ensure_mode_controller(view.shell, ProjectMode.CLIPART).shell.create_worker_job(
                mode="test", work_dir=temp, settings={})
            self.assertEqual(factory.call_args.kwargs["project_id"], identities[0])
            with patch.object(view._project_store, "save", side_effect=OSError("disk")):
                factory.reset_mock()
                with self.assertRaises(OSError):
                    view._create_project_worker(view.shell, mode="test", work_dir=temp, settings={})
                factory.assert_not_called()
            view.close()
            view.deleteLater()

    def test_saved_v3_project_uses_document_adapter_across_mode_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "project_state.json"
            factory = Mock(side_effect=AssertionError("resume must not create paid work"))
            view = V3ApplicationView(draft_path=path, worker_factory=factory)
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            project_id = view._active_project_id
            self.assertIsNotNone(project_id)
            view.project_state.switch_mode(ProjectMode.PROCESSING)
            view.shell.mark_dirty()
            record = view._project_store.load(project_id)
            self.assertEqual(record.module_id, ProjectMode.CLIPART.value)
            self.assertEqual(record.document_type, "project")
            self.assertEqual(record.document_version, 1)
            self.assertEqual(record.state["mode"], ProjectMode.PROCESSING.value)
            view.close()
            view.deleteLater()

            restored = V3ApplicationView(draft_path=path, worker_factory=factory)
            self.assertTrue(restored.continue_saved_project(project_id))
            self.assertEqual(restored.project_state.mode, ProjectMode.PROCESSING)
            factory.assert_not_called()
            restored.close()
            restored.deleteLater()


    def test_continue_is_unavailable_without_a_recent_project(self):
        view = V3ApplicationView()
        self.assertTrue(view.mode_selection.recent_project_card.isHidden())
        self.assertFalse(view.continue_last_project())
        self.assertIsNone(view.project_state)
        view.close()
        view.deleteLater()

    def test_mode_switcher_reuses_project_and_switches_immediately(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        state = view.project_state
        state.clipart.prompts.append(PromptEntry("kept clipart prompt"))
        view.shell.mark_dirty()

        view.shell.change_mode_button.click()
        self.assertEqual(view.selection_intent, SelectionIntent.SWITCH_MODE)
        self.assertIs(view.stack.currentWidget(), view.mode_selection)
        self.assertTrue(view.mode_selection.recent_project_card.isHidden())
        self.assertTrue(view.mode_selection.cancel_button.isHidden())

        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        self.assertIs(view.stack.currentWidget(), view.shell)
        self.assertEqual(state.mode, ProjectMode.PINTEREST)
        self.assertEqual(
            state.clipart.prompts[0].prompt,
            "kept clipart prompt",
        )
        self.assertTrue(view.shell.mode_switch_banner.isHidden())
        view.close()
        view.deleteLater()

    def test_mode_switcher_restarts_after_results_instead_of_reopening_results(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        view.shell.state.set_step(StepId.RESULTS)
        view.shell.refresh()

        view.shell.change_mode_button.click()
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()

        self.assertEqual(view.project_state.mode, ProjectMode.PINTEREST)
        self.assertEqual(
            view.project_state.current_step,
            route_for_mode(ProjectMode.PINTEREST)[0],
        )
        self.assertIs(view.stack.currentWidget(), view.shell)
        results_page = view.shell.workflow_controller("pinterest").pages[StepId.RESULTS]
        self.assertIsNot(view.shell.current_page, results_page)
        view.close()
        view.deleteLater()

    def test_starting_same_mode_from_results_opens_a_fresh_first_step(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        completed_shell = view.shell
        completed_shell.state.clipart.prompts.append(PromptEntry("old prompt"))
        completed_shell.state.set_step(StepId.RESULTS)
        completed_shell.refresh()

        completed_shell.change_mode_button.click()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

        self.assertIs(view.shell, completed_shell)
        self.assertEqual(view.project_state.mode, ProjectMode.CLIPART)
        self.assertEqual(
            view.project_state.current_step,
            route_for_mode(ProjectMode.CLIPART)[0],
        )
        self.assertEqual(view.project_state.clipart.prompts, [])
        self.assertIs(view.stack.currentWidget(), view.shell)
        view.close()
        view.deleteLater()

    def test_starting_same_mode_from_an_intermediate_step_opens_a_fresh_first_step(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        view.shell.state.clipart.prompts.append(PromptEntry("old prompt"))
        view.shell.state.set_step(StepId.GENERATION)
        view.shell.refresh()

        view.shell.change_mode_button.click()
        view.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()

        self.assertEqual(view.project_state.current_step, StepId.PROJECT)
        self.assertEqual(view.project_state.clipart.prompts, [])
        self.assertIs(view.stack.currentWidget(), view.shell)
        view.close()
        view.deleteLater()

    def test_done_returns_to_mode_selection_without_reusing_completed_shell(self):
        view = V3ApplicationView()
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        completed_shell = view.shell
        completed_shell.state.set_step(StepId.RESULTS)
        completed_shell.refresh()

        completed_shell.finish_requested.emit(ProjectMode.PROCESSING.value)
        self.app.processEvents()

        self.assertIs(view.stack.currentWidget(), view.mode_selection)
        self.assertIs(view.shell, completed_shell)
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        self.assertIsNot(view.shell, completed_shell)
        self.assertEqual(view.shell.state.processing.selected_files, [])
        view.close()
        view.deleteLater()

    def test_offscreen_selection_layout_and_keyboard_flow_at_980_by_700(self):
        screen = ModeSelectionScreen()
        screen.resize(980, 700)
        screen.show()
        self.app.processEvents()

        cards = list(screen.module_cards.values())
        self.assertEqual((screen.width(), screen.height()), (980, 700))
        self.assertTrue(screen.isVisible())
        self.assertLessEqual(
            screen.cards_container.geometry().right(),
            screen.contentsRect().right(),
        )
        for card in cards:
            self.assertGreater(card.width(), 0)
            self.assertLessEqual(
                card.geometry().bottom(),
                screen.cards_container.contentsRect().bottom(),
            )
        widths = [card.width() for card in cards]
        self.assertLessEqual(max(widths) - min(widths), 1)

        from studio_catalog import ModuleAvailability
        for card in cards:
            card.set_availability(ModuleAvailability(entitled=True, download_supported=True))
        cards[0].start_button.setFocus()
        self.app.processEvents()
        self.assertTrue(cards[0].start_button.hasFocus())
        QTest.keyClick(screen, Qt.Key.Key_Tab)
        self.app.processEvents()
        self.assertIs(self.app.focusWidget(), cards[1].start_button)

        screen.close()
        screen.deleteLater()


if __name__ == "__main__":
    unittest.main()
