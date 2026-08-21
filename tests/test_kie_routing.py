import json
import os
import shutil
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image, ImageDraw, PngImagePlugin

import main
from metadata_inspector import inspect_image_metadata
from network_security import NetworkSecurityError


DUMMY_KIE_KEY = "test-kie-secret-must-not-appear-in-logs"


def kie_settings(**overrides):
    settings = {
        "kie_api_key": "",
        "upscale": False,
        "upscale_provider": "kie",
        "local_realesrgan_scale": 2,
        "unsharp_enabled": False,
        "remove_bg": False,
        "remove_bg_provider": "kie",
        "kie_remove_bg_model": "recraft/remove-background",
        "edge_shrink_enabled": False,
        "edge_shrink_pixels": 1,
        "trim_enabled": False,
        "export_300_dpi": False,
    }
    settings.update(overrides)
    return settings


def create_rgb_source(path, size=(16, 12)):
    image = Image.new("RGB", size, (235, 235, 235))
    ImageDraw.Draw(image).rectangle((3, 2, size[0] - 4, size[1] - 3), fill=(180, 70, 100))
    image.save(path, format="PNG")
    return image


def create_rgb_png_bytes(size=(16, 12)):
    output = BytesIO()
    create_rgb_source(output, size=size)
    return output.getvalue()


class KieRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def connect_messages(self, worker):
        progress = []
        finished = []
        worker.progress.connect(progress.append)
        worker.finished.connect(finished.append)
        return progress, finished

    def assert_secret_not_logged(self, progress, finished=()):
        messages = "\n".join([*progress, *finished])
        self.assertNotIn(DUMMY_KIE_KEY, messages)

    def test_kie_failed_task_error_contains_safe_task_id_and_code(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        worker._request_json = types.MethodType(
            lambda self, *args, **kwargs: {
                "code": 200,
                "data": {
                    "state": "fail",
                    "failCode": 501,
                    "failMsg": "provider could not process image",
                },
            },
            worker,
        )
        with self.assertRaisesRegex(
            RuntimeError,
            r"taskId=task-123; errorCode=501; message=provider could not process image",
        ):
            worker._kie_wait_result("task-123")

    def test_gpt_image_2_routes_documented_task_models(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        task_models = []

        def fake_create_task(worker_self, model, input_payload):
            task_models.append(model)
            self.assertIsInstance(input_payload, dict)
            return f"task-{len(task_models)}"

        def fake_wait_result(worker_self, task_id):
            return f"mock://{task_id}"

        worker._kie_create_task = types.MethodType(fake_create_task, worker)
        worker._kie_wait_result = types.MethodType(fake_wait_result, worker)

        worker._kie_generate_generic_model("gpt-image-2", "text prompt")
        worker._kie_generate_generic_model(
            "gpt-image-2",
            "reference prompt",
            ["mock://reference.png"],
        )

        self.assertEqual(
            task_models,
            ["gpt-image-2-text-to-image", "gpt-image-2-image-to-image"],
        )
        self.assertEqual(
            main.resolve_kie_generation_model("nano-banana-2", False),
            "nano-banana-2",
        )

    def test_gpt_image_2_probe_and_saved_ids_use_the_same_routing(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )

        text_variant = worker._build_text_probe_variants(
            "gpt-image-2", "test", "1:1", "1024x1024"
        )[0]
        reference_variant = worker._build_reference_probe_variants(
            "gpt-image-2",
            "test",
            "mock://reference.png",
            "1:1",
            "1024x1024",
        )[0]

        self.assertEqual(text_variant["model"], "gpt-image-2-text-to-image")
        self.assertEqual(reference_variant["model"], "gpt-image-2-image-to-image")
        for endpoint_id in (
            "gpt-image-2-text-to-image",
            "gpt-image-2-image-to-image",
        ):
            self.assertEqual(worker._normalize_generation_model(endpoint_id), "gpt-image-2")
            self.assertEqual(
                main.MainWindow._normalize_generation_model_id(None, endpoint_id),
                "gpt-image-2",
            )

    def test_provider_combinations_require_key_only_for_kie_steps(self):
        cases = [
            (
                "local_only",
                kie_settings(
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    remove_bg=True,
                    remove_bg_provider="local_ben2",
                ),
                False,
            ),
            ("kie_upscale", kie_settings(upscale=True, upscale_provider="kie"), True),
            ("kie_remove", kie_settings(remove_bg=True, remove_bg_provider="kie"), True),
            (
                "local_to_kie",
                kie_settings(
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    remove_bg=True,
                    remove_bg_provider="kie",
                ),
                True,
            ),
            (
                "kie_to_local",
                kie_settings(
                    upscale=True,
                    upscale_provider="kie",
                    remove_bg=True,
                    remove_bg_provider="local_ben2",
                ),
                True,
            ),
        ]

        for name, settings, expected in cases:
            with self.subTest(name=name):
                worker = main.WorkerThread("mode2_process", ".", settings)
                requires_kie = worker._uses_kie_upscale() or worker._uses_kie_remove_bg()
                self.assertEqual(requires_kie, expected)
                if expected:
                    with self.assertRaisesRegex(ValueError, "KIE API Key"):
                        worker._mode2_process_files(emit_final=False)

    def test_start_button_uses_the_same_key_routing_rules(self):
        cases = [
            ("local_remove", False, "kie", True, "local_ben2", False),
            ("kie_upscale", True, "kie", False, "kie", True),
            ("kie_remove", False, "kie", True, "kie", True),
            ("local_to_kie", True, "local_realesrgan", True, "kie", True),
            ("kie_to_local", True, "kie", True, "local_ben2", True),
        ]

        with tempfile.TemporaryDirectory(prefix="clipart-kie-ui-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)

            for name, upscale, upscale_provider, remove_bg, remove_provider, expects_warning in cases:
                with self.subTest(name=name):
                    case_dir = temp_path / name
                    case_dir.mkdir()
                    with (
                        patch.object(main, "CONFIG_FILE", str(case_dir / "config.json")),
                        patch.object(main, "ENV_FILE", str(case_dir / ".env")),
                        patch.object(main, "PROMPTS_STORAGE_FILE", str(case_dir / "prompts.json")),
                        patch.object(main, "LICENSE_CACHE_FILE", str(case_dir / "license_cache.json")),
                        patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
                        patch.object(main.QTimer, "singleShot"),
                        patch.object(main.QMessageBox, "warning") as warning_mock,
                        patch.object(main.WorkerThread, "start", autospec=True) as start_mock,
                    ):
                        window = main.MainWindow()
                        window.work_dir = str(case_dir)
                        window.selected_files = [str(source_path)]
                        window.radio_run_process.setChecked(True)
                        window.kie_api_key_input.setText("")
                        window.chk_upscale.setChecked(upscale)
                        window.upscale_provider_combo.setCurrentIndex(
                            window.upscale_provider_combo.findData(upscale_provider)
                        )
                        window.chk_unsharp.setChecked(False)
                        window.chk_remove_bg.setChecked(remove_bg)
                        window.remove_bg_provider_combo.setCurrentIndex(
                            window.remove_bg_provider_combo.findData(remove_provider)
                        )
                        window.chk_edge_shrink.setChecked(False)
                        window.chk_trim.setChecked(False)

                        window.start_work()

                        if expects_warning:
                            warning_mock.assert_called_once()
                            self.assertIn("KIE API Key", str(warning_mock.call_args.args[2]))
                            start_mock.assert_not_called()
                        else:
                            warning_mock.assert_not_called()
                            start_mock.assert_called_once()
                        window.settings_save_timer.stop()
                        window.api_key_mask_timer.stop()
                        window.deleteLater()
                        self.app.processEvents()

    def test_generate_only_saves_raw_and_output_without_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-generate-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
                generated_prompts=[{"prompt": "test clipart", "references": []}],
            )
            progress, finished = self.connect_messages(worker)
            calls = []

            def fake_generate(self, prompt, references=None):
                calls.append(("generate", prompt, tuple(references or [])))
                return "mock://generated"

            def fake_download(self, url, output_path):
                calls.append(("download", url))
                create_rgb_source(output_path)

            worker._kie_generate_image = types.MethodType(fake_generate, worker)
            worker._download_file = types.MethodType(fake_download, worker)

            worker._mode1_generate(process_generated=False)

            raw_outputs = list((Path(temp_dir) / "output" / ".run").glob("*.png"))
            final_outputs = list((Path(temp_dir) / "output").glob("*.png"))
            self.assertEqual([call[0] for call in calls], ["generate", "download", "download"])
            self.assertEqual(len(raw_outputs), 1)
            self.assertEqual(len(final_outputs), 1)
            self.assertTrue(any("Готово (1/1)" in message for message in finished))
            self.assert_secret_not_logged(progress, finished)

    def test_local_to_kie_mixed_pipeline_saves_intermediates_and_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-mixed-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path, size=(20, 16))
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(
                    kie_api_key=DUMMY_KIE_KEY,
                    upscale=True,
                    upscale_provider="local_realesrgan",
                    remove_bg=True,
                    remove_bg_provider="kie",
                    cleanup_remove_comments_text=True,
                    cleanup_remove_generator_fields=True,
                ),
                selected_files=[str(source_path)],
            )
            progress, finished = self.connect_messages(worker)
            calls = []

            def fake_local_upscale(self, input_path, raw_dir, idx, prefix, step_name):
                calls.append("local_upscale")
                output_path = Path(raw_dir) / f"{prefix}_{step_name}_{idx:03d}_{self.run_stamp}.png"
                shutil.copyfile(input_path, output_path)
                return str(output_path)

            def fake_upload(self, file_path):
                calls.append("upload")
                if not Path(file_path).is_file():
                    raise AssertionError(f"Upload source does not exist: {file_path}")
                return "mock://uploaded"

            def fake_run_model(self, model, image_url, extra_input=None):
                calls.append("kie_remove")
                if model != "recraft/remove-background":
                    raise AssertionError(f"Unexpected KIE model: {model}")
                if image_url != "mock://uploaded":
                    raise AssertionError(f"Unexpected KIE input: {image_url}")
                return "mock://removed"

            def fake_download(self, url, output_path):
                calls.append("download_removed")
                image = Image.new("RGBA", (20, 16), (180, 70, 100, 0))
                alpha = Image.new("L", image.size, 0)
                ImageDraw.Draw(alpha).rectangle((3, 2, 16, 13), fill=255)
                image.putalpha(alpha)
                pnginfo = PngImagePlugin.PngInfo()
                pnginfo.add_text("Comment", "provider fixture")
                pnginfo.add_text("parameters", "provider generator fixture")
                image.save(
                    output_path,
                    format="PNG",
                    pnginfo=pnginfo,
                    icc_profile=b"kie-provider-icc",
                    dpi=(300, 300),
                )

            worker._local_realesrgan_pipeline_step = types.MethodType(fake_local_upscale, worker)
            worker._kie_upload_file = types.MethodType(fake_upload, worker)
            worker._kie_run_model_task = types.MethodType(fake_run_model, worker)
            worker._download_file = types.MethodType(fake_download, worker)

            worker._mode2_process_files()

            self.assertEqual(
                calls,
                [
                    "local_upscale",
                    "upload",
                    "kie_remove",
                    "download_removed",
                    "download_removed",
                ],
            )
            raw_outputs = list((temp_path / "output" / ".run").glob("*.png"))
            final_outputs = list((temp_path / "output").glob("*.png"))
            self.assertGreaterEqual(len(raw_outputs), 2)
            self.assertEqual(len(final_outputs), 1)
            provider_raw = None
            provider_icc = None
            provider_dpi = None
            for candidate in raw_outputs:
                with Image.open(candidate) as raw_image:
                    if raw_image.mode == "RGBA" and raw_image.size == (20, 16):
                        provider_raw = raw_image.convert("RGBA").tobytes()
                        provider_icc = raw_image.info.get("icc_profile")
                        provider_dpi = raw_image.info.get("dpi")
                        break
            self.assertIsNotNone(provider_raw)
            with Image.open(final_outputs[0]) as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertNotEqual(result.getchannel("A").getextrema(), (0, 0))
                self.assertEqual(result.convert("RGBA").tobytes(), provider_raw)
                self.assertEqual(provider_icc, b"kie-provider-icc")
                self.assertEqual(result.info.get("icc_profile"), b"kie-provider-icc")
                self.assertAlmostEqual(provider_dpi[0], 300, places=1)
                self.assertAlmostEqual(result.info["dpi"][0], 300, places=1)
            inspection = inspect_image_metadata(final_outputs[0])
            self.assertFalse(inspection["categories"]["comments_text"]["present"])
            self.assertFalse(inspection["categories"]["generator_fields"]["present"])
            self.assertTrue(any("Готово (1/1)" in message for message in finished))
            self.assert_secret_not_logged(progress, finished)

    def test_provider_error_is_visible_without_exposing_key(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-error-") as temp_dir:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
                generated_prompts=["test clipart"],
            )
            progress, finished = self.connect_messages(worker)

            def fail_generate(self, prompt, references=None):
                raise RuntimeError("provider unavailable")

            worker._kie_generate_image = types.MethodType(fail_generate, worker)

            worker._mode1_generate(process_generated=False)

            self.assertTrue(any("provider unavailable" in message for message in progress))
            self.assertTrue(any("Готово (0/1)" in message for message in finished))
            self.assertFalse(list((Path(temp_dir) / "output").glob("*.png")))
            self.assert_secret_not_logged(progress, finished)

    def test_download_credentials_are_limited_to_exact_kie_domains(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-download-host-") as temp_dir:
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            captured_headers = []

            def fake_request(worker_self, req, timeout=None):
                captured_headers.append(
                    {key.lower(): value for key, value in req.header_items()}
                )
                return create_rgb_png_bytes()

            worker._request_with_retries = types.MethodType(fake_request, worker)
            worker._download_file(
                "https://kie.ai.attacker.example/output.png",
                str(Path(temp_dir) / "untrusted.png"),
            )
            worker._download_file(
                "https://cdn.kie.ai/output.png",
                str(Path(temp_dir) / "trusted.png"),
            )
            with self.assertRaisesRegex(RuntimeError, "must use HTTPS"):
                worker._download_file(
                    "http://cdn.kie.ai/output.png",
                    str(Path(temp_dir) / "insecure.png"),
                )
            with self.assertRaisesRegex(RuntimeError, "must not contain credentials"):
                worker._download_file(
                    "https://user:password@cdn.kie.ai/output.png",
                    str(Path(temp_dir) / "credentials.png"),
                )

            self.assertNotIn("authorization", captured_headers[0])
            self.assertNotIn("x-api-key", captured_headers[0])
            self.assertNotIn("referer", captured_headers[0])
            self.assertEqual(
                captured_headers[1]["authorization"],
                f"Bearer {DUMMY_KIE_KEY}",
            )
            self.assertEqual(captured_headers[1]["x-api-key"], DUMMY_KIE_KEY)
            self.assertEqual(len(captured_headers), 2)

    def test_authenticated_request_does_not_forward_secrets_on_redirect(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        req = main.request.Request(
            "https://api.kie.ai/api/v1/jobs/createTask",
            headers={
                "Authorization": f"Bearer {DUMMY_KIE_KEY}",
                "x-api-key": DUMMY_KIE_KEY,
                "Accept": "application/json",
            },
            method="GET",
        )

        worker._protect_secret_headers_from_redirects(req)
        for destination in (
            "https://attacker.example/output.png",
            "http://attacker.example/output.png",
            "https://user:password@attacker.example/output.png",
        ):
            with self.assertRaises(NetworkSecurityError):
                main.HttpsOnlyRedirectHandler().redirect_request(
                    req,
                    None,
                    302,
                    "Found",
                    {},
                    destination,
                )

    def test_worker_probe_uses_redirect_safe_secret_headers(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        headers = {
            "Authorization": f"Bearer {DUMMY_KIE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        def fake_urlopen(req, **_kwargs):
            regular = {key.lower(): value for key, value in req.headers.items()}
            protected = {
                key.lower(): value for key, value in req.unredirected_hdrs.items()
            }
            self.assertNotIn("authorization", regular)
            self.assertEqual(protected["authorization"], f"Bearer {DUMMY_KIE_KEY}")
            return BytesIO(
                json.dumps({"code": 200, "data": {"taskId": "probe"}}).encode("utf-8")
            )

        with patch.object(main, "open_url_secure", side_effect=fake_urlopen):
            ok, message, task_id = worker._probe_model_with_ratio(
                "gpt-image-2", "1:1", headers, 10
            )

        self.assertTrue(ok, message)
        self.assertEqual(task_id, "probe")

    def test_worker_probe_classifies_required_schema_without_exposing_provider_body(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        headers = {
            "Authorization": f"Bearer {DUMMY_KIE_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response_body = BytesIO(
            json.dumps(
                {
                    "code": 422,
                    "msg": "image_urls is required; internal provider detail",
                }
            ).encode("utf-8")
        )
        provider_error = main.urlerror.HTTPError(
            "https://api.kie.ai/api/v1/jobs/createTask",
            422,
            "Unprocessable Entity",
            {},
            response_body,
        )

        with patch.object(main, "open_url_secure", side_effect=provider_error):
            ok, message, task_id = worker._probe_model_with_ratio(
                "gpt-image/1.5-image-to-image",
                "1:1",
                headers,
                10,
                reference_urls=[main.MODEL_PROBE_SAMPLE_IMAGE_URL],
            )

        self.assertFalse(ok)
        self.assertEqual(message, "schema_required")
        self.assertEqual(task_id, "-")
        self.assertNotIn("internal provider detail", message)

    def test_png_signature_without_decodable_image_is_not_published(self):
        with tempfile.TemporaryDirectory(prefix="clipart-invalid-png-") as temp_dir:
            output_path = Path(temp_dir) / "output.png"
            worker = main.WorkerThread("mode2_process", temp_dir, kie_settings())

            with self.assertRaisesRegex(RuntimeError, "невалидный контент"):
                worker._save_png_from_any_image_bytes(
                    b"\x89PNG\r\n\x1a\nnot-a-decodable-png",
                    str(output_path),
                )

            self.assertFalse(output_path.exists())

    def test_api_response_read_is_bounded(self):
        worker = main.WorkerThread("mode2_process", ".", kie_settings())
        req = main.request.Request("https://example.invalid/image.png", method="GET")
        response = BytesIO(b"123456789")
        response.headers = {}

        with (
            patch.object(main, "MAX_API_RESPONSE_BYTES", 8, create=True),
            patch.object(main, "open_url_secure", return_value=response),
        ):
            with self.assertRaisesRegex(RuntimeError, "size limit"):
                worker._request_with_retries(req)

    def test_multiframe_or_oversized_provider_image_is_not_published(self):
        with tempfile.TemporaryDirectory(prefix="clipart-provider-limits-") as temp_dir:
            output_path = Path(temp_dir) / "output.png"
            worker = main.WorkerThread("mode2_process", temp_dir, kie_settings())
            frames = [
                Image.new("RGBA", (8, 8), (255, 0, 0, 255)),
                Image.new("RGBA", (8, 8), (0, 0, 255, 255)),
            ]
            payload = BytesIO()
            frames[0].save(
                payload,
                format="PNG",
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
            )

            with self.assertRaisesRegex(RuntimeError, "single-frame"):
                worker._save_png_from_any_image_bytes(payload.getvalue(), str(output_path))
            self.assertFalse(output_path.exists())

            with patch.object(main, "MAX_PROVIDER_IMAGE_DIMENSION", 10):
                with self.assertRaisesRegex(RuntimeError, "dimension limit"):
                    worker._save_png_from_any_image_bytes(
                        create_rgb_png_bytes(size=(16, 12)),
                        str(output_path),
                    )
            self.assertFalse(output_path.exists())

    def test_post_error_is_not_retried_and_cannot_echo_api_key(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY, retries=3),
        )
        req = main.request.Request(
            "https://api.kie.ai/api/v1/jobs/createTask",
            data=b"{}",
            method="POST",
        )
        provider_error = main.urlerror.HTTPError(
            req.full_url,
            500,
            "Server Error",
            {},
            BytesIO(f"echoed={DUMMY_KIE_KEY}".encode("utf-8")),
        )

        with patch.object(main, "open_url_secure", side_effect=provider_error) as request_mock:
            with self.assertRaises(RuntimeError) as raised:
                worker._request_with_retries(req)

        self.assertEqual(request_mock.call_count, 1)
        self.assertNotIn(DUMMY_KIE_KEY, str(raised.exception))

    def test_ambiguous_upload_failure_does_not_try_another_post_endpoint(self):
        with tempfile.TemporaryDirectory(prefix="clipart-upload-once-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )

            with (
                patch.object(
                    worker,
                    "_request_with_retries",
                    side_effect=TimeoutError("ambiguous upload timeout"),
                ) as post_mock,
                patch.object(worker, "_request_json") as fallback_mock,
            ):
                with self.assertRaises(RuntimeError):
                    worker._kie_upload_file(str(source_path))

            self.assertEqual(post_mock.call_count, 1)
            fallback_mock.assert_not_called()

    def test_oversized_upload_is_rejected_before_kie_request(self):
        with tempfile.TemporaryDirectory(prefix="clipart-kie-upload-limit-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )

            with (
                patch.object(main, "MAX_API_UPLOAD_BYTES", 8),
                patch.object(worker, "_request_with_retries") as request_mock,
            ):
                with self.assertRaisesRegex(RuntimeError, "size limit"):
                    worker._kie_upload_file(str(source_path))

            request_mock.assert_not_called()

    def test_top_level_worker_error_redacts_all_configured_secrets(self):
        extra_secret = "test-license-secret-must-not-appear"
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY, license_key=extra_secret),
        )
        errors = []
        worker.error.connect(errors.append)

        def fail_with_secrets(_worker_self):
            raise RuntimeError(f"failure {DUMMY_KIE_KEY} {extra_secret}")

        worker._mode2_process_files = types.MethodType(fail_with_secrets, worker)
        worker.run()

        self.assertEqual(len(errors), 1)
        self.assertNotIn(DUMMY_KIE_KEY, errors[0])
        self.assertNotIn(extra_secret, errors[0])

    def test_cancellation_after_pipeline_does_not_publish_current_item(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cancel-publish-") as temp_dir:
            temp_path = Path(temp_dir)
            source_path = temp_path / "source.png"
            create_rgb_source(source_path)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(unsharp_enabled=True),
                selected_files=[str(source_path)],
            )
            progress, _ = self.connect_messages(worker)

            def cancel_after_pipeline(worker_self, source, source_url, raw_dir, idx, prefix):
                result_path = Path(raw_dir) / "completed-after-stop.png"
                create_rgb_source(result_path)
                worker_self.stop()
                return str(result_path)

            worker._run_processing_pipeline = types.MethodType(cancel_after_pipeline, worker)
            worker._mode2_process_files(emit_final=False)

            self.assertFalse(list((temp_path / "output").glob("*.png")))
            self.assertTrue(any("Остановлено пользователем" in message for message in progress))


    def test_cancellation_during_metadata_cleanup_preserves_previous_output(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cancel-cleanup-") as temp_dir:
            temp_path = Path(temp_dir)
            stage_path = temp_path / "stage.png"
            output_path = temp_path / "output.png"
            create_rgb_source(stage_path)
            output_path.write_bytes(b"previous-output")
            previous_output = output_path.read_bytes()
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(cleanup_remove_comments_text=True),
            )
            real_cleanup = main.cleanup_image_metadata

            def cleanup_then_cancel(source, destination, options):
                result = real_cleanup(source, destination, options)
                worker.stop()
                return result

            with patch.object(main, "cleanup_image_metadata", side_effect=cleanup_then_cancel):
                with self.assertRaises(main.ProcessingCancelled):
                    worker._publish_final_output(str(stage_path), str(output_path))

            self.assertEqual(output_path.read_bytes(), previous_output)
            self.assertFalse(list(temp_path.glob(".clipart-publish-*.png")))


if __name__ == "__main__":
    unittest.main()
