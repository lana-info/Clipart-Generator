import json
import os
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main


class MainUiAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def isolated_paths(self, root):
        return (
            patch.object(main, "CONFIG_FILE", str(root / "config.json")),
            patch.object(main, "ENV_FILE", str(root / ".env")),
            patch.object(main, "PROMPTS_STORAGE_FILE", str(root / "prompts.json")),
            patch.object(main, "LICENSE_CACHE_FILE", str(root / "license_cache.json")),
            patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
            patch.object(main.QTimer, "singleShot"),
        )

    def test_work_folder_key_lock_and_processing_settings_persist(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-settings-") as temp_dir:
            temp_path = Path(temp_dir)
            work_dir = temp_path / "work"
            work_dir.mkdir()
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                self.assertTrue(window.windowTitle().startswith("Vibix Images v"))
                self.assertTrue(window.api_key_locked)
                self.assertTrue(window.kie_api_key_input.isReadOnly())
                self.assertEqual(window.kie_api_key_input.echoMode(), main.QLineEdit.EchoMode.Password)
                self.assertEqual(window.btn_api_key_lock.text(), "🔒")

                window.toggle_api_key_lock()
                self.assertFalse(window.api_key_locked)
                self.assertFalse(window.kie_api_key_input.isReadOnly())
                self.assertEqual(window.kie_api_key_input.echoMode(), main.QLineEdit.EchoMode.Normal)
                self.assertEqual(window.btn_api_key_lock.text(), "🔓")

                window.toggle_api_key_lock()
                self.assertTrue(window.api_key_locked)
                self.assertTrue(window.kie_api_key_input.isReadOnly())
                self.assertEqual(window.kie_api_key_input.echoMode(), main.QLineEdit.EchoMode.Password)

                with patch.object(main.QFileDialog, "getExistingDirectory", return_value=str(work_dir)):
                    window.select_work_dir()
                self.assertEqual(window.work_dir, str(work_dir))
                self.assertTrue((work_dir / "raw").is_dir())
                self.assertTrue((work_dir / "output").is_dir())

                window.radio_run_process.setChecked(True)
                window.chk_upscale.setChecked(False)
                window.chk_unsharp.setChecked(True)
                window.unsharp_amount_spin.setValue(42)
                window.unsharp_radius_spin.setValue(75)
                window.unsharp_threshold_spin.setValue(3)
                window.chk_remove_bg.setChecked(True)
                window.remove_bg_provider_combo.setCurrentIndex(
                    window.remove_bg_provider_combo.findData("local_ben2")
                )
                window.local_ben2_alpha_threshold_spin.setValue(31)
                window.chk_edge_shrink.setChecked(True)
                window.edge_shrink_pixels_combo.setCurrentIndex(
                    window.edge_shrink_pixels_combo.findData(2)
                )
                window.chk_trim.setChecked(True)
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.persist_ui_settings()
                saved_config = json.loads(
                    (temp_path / "config.json").read_text(encoding="utf-8")
                )
                self.assertEqual(saved_config["last_work_dir"], str(work_dir))
                window.deleteLater()

                restored = main.MainWindow()
                self.assertEqual(restored.work_dir, str(work_dir))
                self.assertTrue(restored.radio_run_process.isChecked())
                self.assertFalse(restored.chk_upscale.isChecked())
                self.assertTrue(restored.chk_unsharp.isChecked())
                self.assertEqual(restored.unsharp_amount_spin.value(), 42)
                self.assertEqual(restored.unsharp_radius_spin.value(), 75)
                self.assertEqual(restored.unsharp_threshold_spin.value(), 3)
                self.assertTrue(restored.chk_remove_bg.isChecked())
                self.assertEqual(restored.remove_bg_provider_combo.currentData(), "local_ben2")
                self.assertEqual(restored.local_ben2_alpha_threshold_spin.value(), 31)
                self.assertTrue(restored.chk_edge_shrink.isChecked())
                self.assertEqual(restored.edge_shrink_pixels_combo.currentData(), 2)
                self.assertTrue(restored.chk_trim.isChecked())
                restored.settings_save_timer.stop()
                restored.api_key_mask_timer.stop()
                restored.deleteLater()
                self.app.processEvents()

    def test_validation_and_output_dialog_rules(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-dialogs-") as temp_dir:
            temp_path = Path(temp_dir)
            work_dir = temp_path / "work"
            output_dir = work_dir / "output"
            output_dir.mkdir(parents=True)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                window.work_dir = str(work_dir)
                window.radio_run_process.setChecked(True)
                window.chk_upscale.setChecked(False)
                window.chk_unsharp.setChecked(False)
                window.chk_remove_bg.setChecked(True)
                window.remove_bg_provider_combo.setCurrentIndex(
                    window.remove_bg_provider_combo.findData("local_ben2")
                )
                window.chk_edge_shrink.setChecked(False)
                window.chk_trim.setChecked(False)
                window.selected_files = []

                with (
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                    patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                ):
                    window.start_work()
                    warning_mock.assert_called_once()
                    self.assertIn("выберите файлы", str(warning_mock.call_args.args[2]))
                    start_mock.assert_not_called()

                with patch.object(
                    main.QMessageBox,
                    "question",
                    return_value=main.QMessageBox.StandardButton.No,
                ) as question_mock:
                    window.offer_open_output_folder("Операция не завершена")
                    question_mock.assert_not_called()
                    window.offer_open_output_folder("Mode 2: Готово (1/1)")
                    question_mock.assert_called_once()

                    question_mock.reset_mock()
                    window.has_generated_output_in_run = False
                    window.offer_open_output_folder_after_stop()
                    question_mock.assert_not_called()
                    window.log("  Итог сохранён: test.png")
                    window.offer_open_output_folder_after_stop()
                    question_mock.assert_called_once()

                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_stop_is_non_blocking_and_finishes_after_worker_exits(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-stop-") as temp_dir:
            temp_path = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            scheduled = []
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                worker = types.SimpleNamespace(running=True, stopped=False)

                def stop():
                    worker.stopped = True

                def is_running():
                    return worker.running

                worker.stop = stop
                worker.isRunning = is_running
                worker.wait = lambda: self.fail("stop_work must not block on wait()")
                window.worker = worker
                window.btn_start.setEnabled(False)
                window.btn_stop.setEnabled(True)

                with patch.object(
                    main.QTimer,
                    "singleShot",
                    side_effect=lambda delay, callback: scheduled.append((delay, callback)),
                ):
                    window.stop_work()
                    self.assertTrue(worker.stopped)
                    self.assertIs(window.worker, worker)
                    self.assertFalse(window.btn_start.isEnabled())
                    self.assertFalse(window.btn_stop.isEnabled())
                    self.assertEqual(len(scheduled), 1)

                    worker.running = False
                    scheduled.pop()[1]()

                self.assertIsNone(window.worker)
                self.assertTrue(window.btn_start.isEnabled())
                self.assertFalse(window.btn_stop.isEnabled())
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()


    def test_balance_request_protects_key_and_never_logs_provider_body(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-balance-") as temp_dir:
            temp_path = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            provider_marker = "private-provider-response-body"
            api_key = "test-balance-secret"
            captured = {}

            def fail_request(req, **_kwargs):
                captured["regular"] = {
                    key.lower(): value for key, value in req.headers.items()
                }
                captured["protected"] = {
                    key.lower(): value for key, value in req.unredirected_hdrs.items()
                }
                raise main.urlerror.HTTPError(
                    req.full_url,
                    500,
                    "Server Error",
                    {},
                    BytesIO(f"{provider_marker} {api_key}".encode("utf-8")),
                )

            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                window.kie_api_key_input.setText(api_key)
                logs = []
                window.log = logs.append
                with (
                    patch.object(main, "open_url_secure", side_effect=fail_request),
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                ):
                    window.check_kie_balance()

                rendered = "\n".join(logs + [str(warning_mock.call_args)])
                self.assertNotIn("authorization", captured["regular"])
                self.assertNotIn("x-api-key", captured["regular"])
                self.assertEqual(
                    captured["protected"]["authorization"], f"Bearer {api_key}"
                )
                self.assertEqual(captured["protected"]["x-api-key"], api_key)
                self.assertNotIn(provider_marker, rendered)
                self.assertNotIn(api_key, rendered)
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_main_window_model_probe_uses_worker_probe(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-probe-") as temp_dir:
            temp_path = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                window.kie_api_key_input.setText("test-probe-key")
                with patch.object(
                    main.WorkerThread,
                    "_probe_model_with_ratio",
                    return_value=(True, "OK", "task-probe"),
                ) as probe_mock:
                    result = window._probe_model_with_ratio(
                        "gpt-image-2",
                        "1:1",
                        {"Authorization": "Bearer test-probe-key"},
                        10,
                    )

                self.assertEqual(result, (True, "OK", "task-probe"))
                probe_mock.assert_called_once()
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_model_preflight_fails_closed_on_transport_error(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-probe-closed-") as temp_dir:
            temp_path = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                window.kie_api_key_input.setText("test-probe-key")
                with (
                    patch.object(
                        main.WorkerThread,
                        "_probe_model_with_ratio",
                        return_value=(False, "request timed out", "-"),
                    ),
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                ):
                    allowed = window._probe_model_with_fallback_prompt(
                        window.text_generation_model_combo,
                        "gpt-image-2",
                        "gpt-image/1.5-text-to-image",
                        "1:1",
                        {"Authorization": "Bearer test-probe-key"},
                        10,
                    )

                self.assertFalse(allowed)
                warning_mock.assert_called_once()
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_reference_model_preflight_soft_allows_classified_schema_error(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-probe-schema-") as temp_dir:
            temp_path = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                window.kie_api_key_input.setText("test-probe-key")
                with (
                    patch.object(
                        main.WorkerThread,
                        "_probe_model_with_ratio",
                        return_value=(False, "schema_required", "-"),
                    ),
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                ):
                    allowed = window._probe_model_with_fallback_prompt(
                        window.reference_generation_model_combo,
                        "gpt-image/1.5-image-to-image",
                        "gpt-image/1.5-image-to-image",
                        "1:1",
                        {"Authorization": "Bearer test-probe-key"},
                        10,
                        probe_reference_urls=[main.MODEL_PROBE_SAMPLE_IMAGE_URL],
                    )

                self.assertTrue(allowed)
                warning_mock.assert_not_called()
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_check_generation_model_runs_text_and_reference_probes(self):
        with tempfile.TemporaryDirectory(prefix="clipart-ui-check-models-") as temp_dir:
            temp_path = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                window.kie_api_key_input.setText("test-probe-key")
                window.text_ratio_combo.setCurrentText("1:1")
                window.reference_ratio_combo.setCurrentText("1:1")
                with (
                    patch.object(
                        window,
                        "_probe_model_with_ratio",
                        side_effect=[
                            (True, "OK", "text-task"),
                            (True, "OK", "reference-task"),
                        ],
                    ) as probe_mock,
                    patch.object(main.QMessageBox, "information") as info_mock,
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                ):
                    window.check_generation_model()

                self.assertEqual(probe_mock.call_count, 2)
                self.assertNotIn("reference_urls", probe_mock.call_args_list[0].kwargs)
                self.assertEqual(
                    probe_mock.call_args_list[1].kwargs["reference_urls"],
                    ["https://picsum.photos/768/768"],
                )
                info_mock.assert_called_once()
                warning_mock.assert_not_called()
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
