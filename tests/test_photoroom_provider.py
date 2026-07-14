import os
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw

import main


DUMMY_PHOTOROOM_KEY = "test-photoroom-secret-must-not-appear-in-logs"


def photoroom_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "photoroom_api_key": DUMMY_PHOTOROOM_KEY,
        "upscale": False,
        "upscale_provider": "kie",
        "unsharp_enabled": False,
        "remove_bg": True,
        "remove_bg_provider": "photoroom",
        "edge_shrink_enabled": False,
        "trim_enabled": False,
        "export_300_dpi": False,
    }
    settings.update(overrides)
    return settings


def create_rgb_source(path, size=(20, 16)):
    image = Image.new("RGB", size, (245, 245, 245))
    ImageDraw.Draw(image).ellipse((3, 2, size[0] - 4, size[1] - 3), fill=(180, 70, 100))
    image.save(path, format="PNG")


def create_photoroom_response_bytes(size=(20, 16)):
    image = Image.new("RGBA", size, (180, 70, 100, 0))
    alpha = Image.new("L", size, 0)
    ImageDraw.Draw(alpha).ellipse((3, 2, size[0] - 4, size[1] - 3), fill=255)
    image.putalpha(alpha)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class PhotoRoomProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def test_standard_request_saves_valid_rgba_png_without_logging_key(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-request-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            output_path = temp_path / "output.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(),
                selected_files=[str(source_path)],
            )
            progress = []
            worker.progress.connect(progress.append)
            captured = {}

            def fake_request(worker_self, req, timeout=None):
                captured["url"] = req.full_url
                captured["method"] = req.get_method()
                captured["headers"] = {key.lower(): value for key, value in req.header_items()}
                captured["body"] = req.data
                captured["timeout"] = timeout
                return create_photoroom_response_bytes()

            worker._request_with_retries = types.MethodType(fake_request, worker)
            result_path = worker._run_photoroom_remove_bg(str(source_path), str(output_path))

            self.assertEqual(result_path, str(output_path))
            self.assertEqual(captured["url"], main.PHOTOROOM_SEGMENT_URL)
            self.assertEqual(captured["method"], "POST")
            self.assertEqual(captured["headers"]["x-api-key"], DUMMY_PHOTOROOM_KEY)
            self.assertIn("multipart/form-data; boundary=", captured["headers"]["content-type"])
            self.assertNotIn(DUMMY_PHOTOROOM_KEY.encode("utf-8"), captured["body"])
            for field_name in (b"format", b"channels", b"size", b"crop", b"despill", b"image_file"):
                self.assertIn(b'name="' + field_name + b'"', captured["body"])
            with Image.open(output_path) as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertEqual(result.getchannel("A").getextrema(), (0, 255))
            self.assertNotIn(DUMMY_PHOTOROOM_KEY, "\n".join(progress))

    def test_missing_key_and_invalid_response_are_actionable(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-errors-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            output_path = temp_path / "output.png"
            create_rgb_source(source_path)

            missing_key_worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(photoroom_api_key=""),
                selected_files=[str(source_path)],
            )
            with self.assertRaisesRegex(ValueError, "PhotoRoom API Key"):
                missing_key_worker._run_photoroom_remove_bg(str(source_path), str(output_path))

            invalid_worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(),
                selected_files=[str(source_path)],
            )
            invalid_worker._request_with_retries = types.MethodType(
                lambda worker_self, req, timeout=None: b'{"error":"invalid image"}',
                invalid_worker,
            )
            with self.assertRaisesRegex(RuntimeError, "PhotoRoom вернул некорректное изображение"):
                invalid_worker._run_photoroom_remove_bg(str(source_path), str(output_path))
            self.assertFalse(output_path.exists())

    def test_process_only_photoroom_does_not_use_kie(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-pipeline-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(kie_api_key=""),
                selected_files=[str(source_path)],
            )
            calls = []

            def fake_photoroom(worker_self, input_path, output_path):
                calls.append("photoroom")
                Path(output_path).write_bytes(create_photoroom_response_bytes())
                return output_path

            def fail_kie_upload(worker_self, file_path):
                raise AssertionError("PhotoRoom process-only must not upload to KIE")

            worker._run_photoroom_remove_bg = types.MethodType(fake_photoroom, worker)
            worker._kie_upload_file = types.MethodType(fail_kie_upload, worker)
            worker._mode2_process_files()

            self.assertEqual(calls, ["photoroom"])
            outputs = list((temp_path / "output").glob("*.png"))
            self.assertEqual(len(outputs), 1)
            with Image.open(outputs[0]) as result:
                self.assertEqual(result.mode, "RGBA")

    def test_settings_lock_validation_and_persistence(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-ui-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)
            config_path = temp_path / "config.json"
            common_patches = (
                patch.object(main, "CONFIG_FILE", str(config_path)),
                patch.object(main, "PROMPTS_STORAGE_FILE", str(temp_path / "prompts.json")),
                patch.object(main, "LICENSE_CACHE_FILE", str(temp_path / "license.json")),
                patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
                patch.object(main.QTimer, "singleShot"),
            )
            with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4]:
                window = main.MainWindow()
                self.assertGreaterEqual(window.remove_bg_provider_combo.findData("photoroom"), 0)
                self.assertTrue(window.photoroom_api_key_locked)
                self.assertTrue(window.photoroom_api_key_input.isReadOnly())
                self.assertEqual(
                    window.photoroom_api_key_input.echoMode(),
                    main.QLineEdit.EchoMode.Password,
                )

                window.toggle_photoroom_api_key_lock()
                self.assertFalse(window.photoroom_api_key_input.isReadOnly())
                self.assertEqual(window.btn_photoroom_api_key_lock.text(), "🔓")

                window.work_dir = temp_dir
                window.selected_files = [str(source_path)]
                window.radio_run_process.setChecked(True)
                window.chk_upscale.setChecked(False)
                window.chk_unsharp.setChecked(False)
                window.chk_remove_bg.setChecked(True)
                window.chk_edge_shrink.setChecked(False)
                window.chk_trim.setChecked(False)
                window.remove_bg_provider_combo.setCurrentIndex(
                    window.remove_bg_provider_combo.findData("photoroom")
                )
                window.kie_api_key_input.setText("")
                window.photoroom_api_key_input.setText("")
                window.persist_ui_settings()

                with (
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                    patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                ):
                    window.start_work()
                    warning_mock.assert_called_once()
                    self.assertIn("PhotoRoom API Key", str(warning_mock.call_args.args[2]))
                    start_mock.assert_not_called()

                window.photoroom_api_key_input.setText(DUMMY_PHOTOROOM_KEY)
                window.toggle_photoroom_api_key_lock()
                self.assertTrue(window.photoroom_api_key_input.isReadOnly())
                self.assertEqual(window.btn_photoroom_api_key_lock.text(), "🔒")
                window.persist_ui_settings()

                with (
                    patch.object(main.QMessageBox, "warning") as warning_mock,
                    patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                ):
                    window.start_work()
                    warning_mock.assert_not_called()
                    start_mock.assert_called_once()

                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

                restored = main.MainWindow()
                self.assertEqual(restored.photoroom_api_key_input.text(), DUMMY_PHOTOROOM_KEY)
                self.assertEqual(restored.remove_bg_provider_combo.currentData(), "photoroom")
                restored.settings_save_timer.stop()
                restored.api_key_mask_timer.stop()
                restored.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
