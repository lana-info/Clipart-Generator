import os
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, PngImagePlugin

import main
from metadata_cleanup import cleanup_image_metadata
from metadata_inspector import inspect_image_metadata


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


def create_photoroom_response_bytes(size=(20, 16), with_metadata=False):
    image = Image.new("RGBA", size, (180, 70, 100, 0))
    alpha = Image.new("L", size, 0)
    ImageDraw.Draw(alpha).ellipse((3, 2, size[0] - 4, size[1] - 3), fill=255)
    image.putalpha(alpha)
    output = BytesIO()
    save_kwargs = {}
    if with_metadata:
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("Comment", "provider fixture")
        pnginfo.add_text("parameters", "provider generator fixture")
        save_kwargs.update(
            pnginfo=pnginfo,
            icc_profile=b"photoroom-provider-icc",
            dpi=(300, 300),
        )
    image.save(output, format="PNG", **save_kwargs)
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
            diagnostics = []
            worker.progress.connect(progress.append)
            worker.diagnostic.connect(diagnostics.append)
            worker._set_diagnostic_context(1, 1, "background_removal")
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
            submitted = next(
                event for event in diagnostics
                if event["event"] == "provider_task_submitted"
            )
            finished = next(
                event for event in diagnostics
                if event["event"] == "stage_finished"
            )
            self.assertEqual(submitted["provider"], "photoroom")
            self.assertEqual(submitted["model"], "remove-background-v1")
            self.assertEqual(finished["width"], 20)
            self.assertEqual(finished["height"], 16)
            self.assertTrue(finished["has_alpha"])
            self.assertNotIn(
                DUMMY_PHOTOROOM_KEY,
                str(diagnostics),
            )

    def test_input_contract_is_checked_before_photoroom_request(self):
        self.assertEqual(main.PHOTOROOM_MAX_BYTES, 50 * 1024 * 1024)
        self.assertEqual(main.PHOTOROOM_MAX_DIMENSION, 6000)
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-limits-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            output_path = Path(temp_dir) / "output.png"
            create_rgb_source(source_path, size=(20, 16))
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(),
                selected_files=[str(source_path)],
            )
            with (
                patch.object(
                    main,
                    "validate_photoroom_input",
                    side_effect=RuntimeError("PhotoRoom input exceeds 50 MB"),
                ) as validate_mock,
                patch.object(worker, "_request_with_retries") as request_mock,
            ):
                with self.assertRaisesRegex(RuntimeError, "50 MB"):
                    worker._run_photoroom_remove_bg(str(source_path), str(output_path))
            validate_mock.assert_called_once_with(str(source_path))
            request_mock.assert_not_called()

    def test_unsupported_heic_is_rejected_before_photoroom_request(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-heic-") as temp_dir:
            source_path = Path(temp_dir) / "source.heic"
            source_path.write_bytes(b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64)
            with self.assertRaisesRegex(RuntimeError, "PNG, JPG, or WEBP"):
                main.validate_photoroom_input(str(source_path))

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
            diagnostics = []
            invalid_worker.diagnostic.connect(diagnostics.append)
            invalid_worker._set_diagnostic_context(1, 1, "background_removal")
            with self.assertRaisesRegex(RuntimeError, "PhotoRoom вернул некорректное изображение"):
                invalid_worker._run_photoroom_remove_bg(str(source_path), str(output_path))
            self.assertFalse(output_path.exists())
            failed = next(
                event for event in diagnostics
                if event["event"] == "provider_task_failed"
            )
            self.assertEqual(failed["provider"], "photoroom")
            self.assertIn("некорректное изображение", failed["error_message"])

    def test_oversized_upload_is_rejected_before_photoroom_request(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-upload-limit-") as temp_dir:
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

            with (
                patch.object(main, "MAX_API_UPLOAD_BYTES", 8),
                patch.object(worker, "_request_with_retries") as request_mock,
            ):
                with self.assertRaisesRegex(main.ResponseLimitError, "size limit"):
                    worker._run_photoroom_remove_bg(str(source_path), str(output_path))

            request_mock.assert_not_called()
            self.assertFalse(output_path.exists())

    def test_photoroom_failure_isolated_to_one_parallel_item(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-isolation-") as temp_dir:
            temp_path = Path(temp_dir)
            sources = []
            for index in range(1, 4):
                source_path = temp_path / f"source-{index}.png"
                create_rgb_source(source_path)
                sources.append(str(source_path))
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(
                    photoroom_concurrency=3,
                    output_dir=str(temp_path / "output"),
                ),
                selected_files=sources,
            )
            item_events = []
            worker.item_progress.connect(item_events.append)

            def fake_request(worker_self, req, timeout=None):
                if worker_self._diagnostic_context.item_index == 2:
                    raise RuntimeError("controlled PhotoRoom failure")
                return create_photoroom_response_bytes()

            worker._request_with_retries = types.MethodType(fake_request, worker)

            worker._mode2_process_files(emit_final=False)

            outputs = list((temp_path / "output").glob("*.png"))
            self.assertEqual(len(outputs), 2)
            failed_indexes = {
                event["item_index"]
                for event in item_events
                if event.get("status") == "failed"
            }
            self.assertEqual(failed_indexes, {2})

    def test_item_entry_clears_reused_thread_diagnostic_fields(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            photoroom_settings(),
        )
        worker._diagnostic_context.model = "stale-model"
        worker._diagnostic_context.provider = "stale-provider"
        worker._diagnostic_context.prompt_text = "stale prompt"
        worker._diagnostic_context.last_http_status = 599

        worker._set_diagnostic_context(2, 3, "processing")

        for field in ("model", "provider", "prompt_text", "last_http_status"):
            self.assertIsNone(getattr(worker._diagnostic_context, field, None))

    def test_photoroom_failure_keeps_exact_stage_provider_and_model_in_item_progress(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-stage-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(
                    photoroom_concurrency=1,
                    output_dir=str(temp_path / "output"),
                ),
                selected_files=[str(source_path)],
            )
            item_events = []
            worker.item_progress.connect(item_events.append)
            forbidden_stale_text = "prior-item-secret-prompt"
            worker._diagnostic_context.prompt_text = forbidden_stale_text
            worker._diagnostic_context.model = "prior-model"
            worker._diagnostic_context.last_http_status = 599

            denied = main.urlerror.HTTPError(
                main.PHOTOROOM_SEGMENT_URL,
                403,
                "Forbidden",
                {},
                BytesIO(b"forbidden"),
            )
            with patch.object(main, "open_url_secure", side_effect=denied):
                worker._mode2_process_files(emit_final=False)

            failed = next(
                event for event in item_events if event.get("status") == "failed"
            )
            self.assertEqual(failed["stage"], "background_removal")
            self.assertEqual(failed["provider"], "photoroom")
            self.assertEqual(failed["model"], "remove-background-v1")
            self.assertNotIn(forbidden_stale_text, str(failed))
            self.assertNotIn("prior-model", str(failed))
            self.assertNotIn("599", str(failed))

    def test_photoroom_429_retry_is_bounded_and_writes_one_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-429-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            output_path = temp_path / "output.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(retries=5),
                selected_files=[str(source_path)],
            )
            rate_limits = [
                main.urlerror.HTTPError(
                    main.PHOTOROOM_SEGMENT_URL,
                    429,
                    "Too Many Requests",
                    {},
                    BytesIO(b"rate limited"),
                )
                for _ in range(2)
            ]
            response = BytesIO(create_photoroom_response_bytes())
            response.headers = {}

            with (
                patch.object(
                    main,
                    "open_url_secure",
                    side_effect=[*rate_limits, response],
                ) as request_mock,
                patch.object(main.time, "sleep"),
            ):
                result = worker._run_photoroom_remove_bg(
                    str(source_path), str(output_path)
                )

            self.assertEqual(request_mock.call_count, 3)
            self.assertEqual(result, str(output_path))
            self.assertEqual(list(temp_path.glob("output*.png")), [output_path])

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

            def fake_request(worker_self, req, timeout=None):
                calls.append("photoroom")
                return create_photoroom_response_bytes()

            def fail_kie_upload(worker_self, file_path):
                raise AssertionError("PhotoRoom process-only must not upload to KIE")

            worker._request_with_retries = types.MethodType(fake_request, worker)
            worker._kie_upload_file = types.MethodType(fail_kie_upload, worker)
            worker._mode2_process_files()

            self.assertEqual(calls, ["photoroom"])
            outputs = list((temp_path / "output").glob("*.png"))
            self.assertEqual(len(outputs), 1)
            with Image.open(outputs[0]) as result:
                self.assertEqual(result.mode, "RGBA")

    def test_photoroom_output_uses_shared_metadata_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-cleanup-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)
            source_bytes = source_path.read_bytes()
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                photoroom_settings(
                    cleanup_remove_comments_text=True,
                    cleanup_remove_generator_fields=True,
                ),
                selected_files=[str(source_path)],
            )
            progress = []
            worker.progress.connect(progress.append)

            def fake_request(worker_self, req, timeout=None):
                return create_photoroom_response_bytes(with_metadata=True)

            def fail_kie_upload(worker_self, file_path):
                raise AssertionError("PhotoRoom cleanup flow must not upload to KIE")

            worker._request_with_retries = types.MethodType(fake_request, worker)
            worker._kie_upload_file = types.MethodType(fail_kie_upload, worker)
            with patch.object(
                main,
                "cleanup_image_metadata",
                wraps=cleanup_image_metadata,
            ) as cleanup_mock:
                worker._mode2_process_files(emit_final=False)

            raw_outputs = list((temp_path / "output" / ".run").glob("*_photoroom_nobg_*.png"))
            final_outputs = list((temp_path / "output").glob("*.png"))
            self.assertEqual(len(raw_outputs), 1)
            self.assertEqual(len(final_outputs), 1)
            cleanup_mock.assert_called_once()
            self.assertEqual(source_path.read_bytes(), source_bytes)

            with Image.open(raw_outputs[0]) as provider_output, Image.open(final_outputs[0]) as final_output:
                provider_rgba = provider_output.convert("RGBA")
                final_rgba = final_output.convert("RGBA")
                self.assertEqual(final_rgba.size, provider_rgba.size)
                self.assertEqual(final_rgba.tobytes(), provider_rgba.tobytes())
                self.assertEqual(
                    final_rgba.getchannel("A").tobytes(),
                    provider_rgba.getchannel("A").tobytes(),
                )
                self.assertEqual(provider_output.info.get("icc_profile"), b"photoroom-provider-icc")
                self.assertEqual(final_output.info.get("icc_profile"), b"photoroom-provider-icc")
                self.assertAlmostEqual(provider_output.info["dpi"][0], 300, places=1)
                self.assertAlmostEqual(final_output.info["dpi"][0], 300, places=1)

            inspection = inspect_image_metadata(final_outputs[0])
            self.assertFalse(inspection["categories"]["comments_text"]["present"])
            self.assertFalse(inspection["categories"]["generator_fields"]["present"])
            self.assertNotIn(DUMMY_PHOTOROOM_KEY, "\n".join(progress))

    def test_settings_lock_validation_and_persistence(self):
        with tempfile.TemporaryDirectory(prefix="clipart-photoroom-ui-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)
            config_path = temp_path / "config.json"
            common_patches = (
                patch.object(main, "CONFIG_FILE", str(config_path)),
                patch.object(main, "ENV_FILE", str(temp_path / ".env")),
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
