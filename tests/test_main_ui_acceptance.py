import json
import os
import tempfile
import unittest
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
            config_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()
                self.assertTrue(window.windowTitle().startswith("Clipart Generator v"))
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
            config_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, prompts_patch, license_patch, migration_patch, timer_patch:
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


if __name__ == "__main__":
    unittest.main()
