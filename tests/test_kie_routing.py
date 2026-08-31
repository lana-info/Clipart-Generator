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
        worker.completed.connect(finished.append)
        return progress, finished

    def assert_secret_not_logged(self, progress, finished=()):
        messages = "\n".join([*progress, *finished])
        self.assertNotIn(DUMMY_KIE_KEY, messages)

    def test_fal_generation_uses_queue_adapter_and_returns_image_url(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    text_generation_model="fal-ai/flux/schnell",
                    reference_generation_model="gpt-image/1.5-image-to-image",
                ),
                generated_prompts=[{"prompt": "a fox", "references": []}],
            )
            calls = {}

            class FakeFalClient:
                def __init__(self, config):
                    calls["model"] = config.model_id

                def submit_task(self, request):
                    calls["request"] = request
                    return {
                        "request_id": "fal-request-1",
                        "status_url": (
                            "https://queue.fal.run/custom/poll/fal-request-1"
                        ),
                        "response_url": (
                            "https://queue.fal.run/custom/result/fal-request-1"
                        ),
                        "cancel_url": (
                            "https://queue.fal.run/custom/cancel/fal-request-1"
                        ),
                    }

                def wait_for_result(self, request_id, **kwargs):
                    calls["request_id"] = request_id
                    calls["lifecycle_urls"] = {
                        name: kwargs[name]
                        for name in ("status_url", "response_url", "cancel_url")
                    }
                    return {
                        "request_id": request_id,
                        "result": {
                            "images": [{"url": "https://cdn.example/fox.png"}]
                        },
                    }

            with patch.object(main, "FalClient", FakeFalClient):
                result = worker._kie_generate_image("a fox")

            pending = worker.fal_task_journal.pending()
            journal_payload = worker.fal_task_journal.path.read_text(encoding="utf-8")

        self.assertEqual(result, "https://cdn.example/fox.png")
        self.assertEqual(calls["model"], "fal-ai/flux/schnell")
        self.assertEqual(calls["request_id"], "fal-request-1")
        self.assertEqual(calls["request"].provider_id, "fal")
        self.assertEqual(
            calls["lifecycle_urls"]["status_url"],
            "https://queue.fal.run/custom/poll/fal-request-1",
        )
        self.assertEqual(pending, ())
        self.assertIn("https://queue.fal.run/custom/poll/fal-request-1", journal_payload)

    def test_fal_polling_emits_structured_state_events(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            worker._set_diagnostic_context(1, 1, "generation")
            events = []
            worker.diagnostic.connect(events.append)

            worker._record_fal_poll_status(
                "fal-task-1", "generation", "fal-ai/flux/schnell", "waiting"
            )
            worker._record_fal_poll_status(
                "fal-task-1", "generation", "fal-ai/flux/schnell", "running"
            )
            worker._record_fal_poll_status(
                "fal-task-1", "generation", "fal-ai/flux/schnell", "completed"
            )

            self.assertEqual(
                [event["event"] for event in events],
                [
                    "provider_task_polled",
                    "provider_task_polled",
                    "provider_task_polled",
                ],
            )
            self.assertEqual(
                [event["poll_attempt"] for event in events],
                [1, 2, 3],
            )
            self.assertTrue(all(event["provider"] == "fal" for event in events))
            self.assertTrue(all(event["task"] == "fal-task-1" for event in events))

    def test_fal_completed_without_valid_image_is_not_journaled_as_success(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    text_generation_model="fal-ai/flux/schnell",
                ),
            )
            worker._set_diagnostic_context(1, 1, "generation")
            events = []
            worker.diagnostic.connect(events.append)

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def submit_task(self, _request):
                    return {"request_id": "fal-task-malformed"}

                def wait_for_result(self, _request_id, *, on_status, **_kwargs):
                    on_status("completed")
                    return {
                        "request_id": "fal-task-malformed",
                        "status": "completed",
                        "result": {},
                    }

            with patch.object(main, "FalClient", FakeFalClient):
                with self.assertRaises(main.FalProviderError):
                    worker._fal_generate_image("a fox", "fal-ai/flux/schnell")

            event_names = [event["event"] for event in events]
            self.assertNotIn("provider_task_succeeded", event_names)
            self.assertEqual(event_names.count("provider_task_failed"), 1)
            self.assertEqual(worker.fal_task_journal.pending(), ())

    def test_fal_processing_completed_without_valid_image_is_terminal_failed(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            worker._set_diagnostic_context(1, 1, "upscale")
            events = []
            worker.diagnostic.connect(events.append)

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def run_image_operation(
                    self,
                    _operation,
                    _image_url,
                    *,
                    on_submitted_task,
                    on_status,
                    **_kwargs,
                ):
                    on_submitted_task("fal-process-malformed", {})
                    on_status("completed")
                    return {
                        "request_id": "fal-process-malformed",
                        "status": "completed",
                        "result": {},
                    }

            with patch.object(main, "FalClient", FakeFalClient):
                with self.assertRaises(main.FalProviderError):
                    worker._fal_process_image(
                        "https://cdn.example/source.png",
                        operation="upscale",
                        model_id="fal-ai/esrgan",
                    )

            event_names = [event["event"] for event in events]
            self.assertNotIn("provider_task_succeeded", event_names)
            self.assertEqual(event_names.count("provider_task_failed"), 1)
            self.assertEqual(worker.fal_task_journal.pending(), ())

    def test_two_fal_submit_failures_without_task_id_are_both_journaled(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    text_generation_model="fal-ai/flux/schnell",
                ),
            )
            worker._set_diagnostic_context(1, 1, "generation")
            events = []
            worker.diagnostic.connect(events.append)

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def submit_task(self, _request):
                    raise main.FalProviderError("Fal.ai submit unavailable")

            with patch.object(main, "FalClient", FakeFalClient):
                for _attempt in range(2):
                    with self.assertRaises(main.FalProviderError):
                        worker._fal_generate_image("a fox", "fal-ai/flux/schnell")

            failures = [
                event for event in events
                if event["event"] == "provider_task_failed"
            ]
            self.assertEqual(len(failures), 2)

    def test_fal_poll_http_failure_emits_safe_provider_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    text_generation_model="fal-ai/flux/schnell",
                ),
            )
            worker._set_diagnostic_context(1, 1, "generation")
            events = []
            worker.diagnostic.connect(events.append)

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def submit_task(self, _request):
                    return {"request_id": "fal-task-405"}

                def wait_for_result(self, _request_id, **_kwargs):
                    raise main.FalProviderError("Fal.ai HTTP 405")

            with patch.object(main, "FalClient", FakeFalClient):
                with self.assertRaisesRegex(main.FalProviderError, "HTTP 405"):
                    worker._fal_generate_image("a fox", "fal-ai/flux/schnell")

            failed = next(
                event for event in events
                if event["event"] == "provider_task_failed"
            )
            self.assertEqual(failed["provider"], "fal")
            self.assertEqual(failed["model"], "fal-ai/flux/schnell")
            self.assertEqual(failed["task"], "fal-task-405")
            self.assertIn("HTTP 405", failed["error_message"])
            self.assertNotIn("fal-test-secret", json.dumps(failed))

    def test_fal_recovery_continues_after_one_transient_poll_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            worker.fal_task_journal.upsert(
                "req-timeout", "generation", "fal-ai/flux/schnell", "running"
            )
            worker.fal_task_journal.upsert(
                "req-complete", "generation", "fal-ai/flux/schnell", "queued"
            )
            polled = []

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def wait_for_result(self, request_id, *, on_status, **_kwargs):
                    polled.append(request_id)
                    if request_id == "req-timeout":
                        raise TimeoutError("temporary polling outage")
                    on_status("completed")
                    return {
                        "request_id": request_id,
                        "status": "completed",
                        "result": {
                            "images": [{"url": "https://cdn.example/recovered.png"}]
                        },
                    }

            with patch("main.FalClient", FakeFalClient):
                recovered = worker.recover_pending_fal_tasks()

            self.assertEqual(polled, ["req-timeout", "req-complete"])
            self.assertEqual(
                recovered,
                (
                    {
                        "request_id": "req-complete",
                        "status": "completed",
                        "result": {
                            "images": [{"url": "https://cdn.example/recovered.png"}]
                        },
                    },
                ),
            )
            self.assertEqual(
                {record.request_id for record in worker.fal_task_journal.pending()},
                {"req-timeout"},
            )

    def test_new_worker_resumes_existing_fal_task_without_submit(self):
        with tempfile.TemporaryDirectory() as temp:
            model_id = "fal-ai/flux/schnell"
            first = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            first.fal_task_journal.upsert(
                "existing-fal-task",
                "generation",
                model_id,
                "queued",
                status_url=(
                    "https://queue.fal.run/custom/poll/existing-fal-task"
                ),
                response_url=(
                    "https://queue.fal.run/custom/result/existing-fal-task"
                ),
                cancel_url=(
                    "https://queue.fal.run/custom/cancel/existing-fal-task"
                ),
                input_fingerprint=first._paid_task_fingerprint(
                    main.fal_generation_payload(
                        model_id,
                        "same prompt",
                        *first._get_generation_profile(False),
                    )
                ),
            )
            restarted = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            restarted._set_diagnostic_context(1, 1, "generation")
            calls = []

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def submit_task(self, _request):
                    calls.append("POST")
                    raise AssertionError("restart must not submit another paid task")

                def wait_for_result(self, request_id, *, on_status, **_kwargs):
                    calls.append(("GET", request_id))
                    calls.append(
                        (
                            _kwargs["status_url"],
                            _kwargs["response_url"],
                            _kwargs["cancel_url"],
                        )
                    )
                    on_status("completed")
                    return {
                        "request_id": request_id,
                        "status": "completed",
                        "result": {
                            "images": [{"url": "https://cdn.example/recovered.png"}]
                        },
                    }

            with patch("main.FalClient", FakeFalClient):
                result = restarted._fal_generate_image("same prompt", model_id)

            self.assertEqual(result, "https://cdn.example/recovered.png")
            self.assertEqual(
                calls,
                [
                    ("GET", "existing-fal-task"),
                    (
                        "https://queue.fal.run/custom/poll/existing-fal-task",
                        "https://queue.fal.run/custom/result/existing-fal-task",
                        "https://queue.fal.run/custom/cancel/existing-fal-task",
                    ),
                ],
            )

    def test_bria_upscale_recovery_uses_fixed_two_x_fingerprint(self):
        with tempfile.TemporaryDirectory() as temp:
            model_id = "bria/upscale/creative"
            image_url = "https://cdn.example/input.png"
            first = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            first.fal_task_journal.upsert(
                "existing-bria-task",
                "upscale",
                model_id,
                "queued",
                input_fingerprint=first._paid_task_fingerprint(
                    {
                        "image_url": image_url,
                        "scale": 2,
                        "parameters": {},
                    }
                ),
            )
            restarted = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            calls = []

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def run_image_operation(self, *_args, **_kwargs):
                    calls.append("POST")
                    raise AssertionError("restart must not submit another paid task")

                def wait_for_result(self, request_id, *, on_status, **_kwargs):
                    calls.append(("GET", request_id))
                    on_status("completed")
                    return {
                        "request_id": request_id,
                        "status": "completed",
                        "result": {
                            "image": {"url": "https://cdn.example/recovered.png"}
                        },
                    }

            with patch("main.FalClient", FakeFalClient):
                result = restarted._fal_process_image(
                    image_url,
                    operation="upscale",
                    model_id=model_id,
                    scale=4,
                )

            self.assertEqual(result, "https://cdn.example/recovered.png")
            self.assertEqual(calls, [("GET", "existing-bria-task")])

    def test_fal_restart_never_reuses_a_task_for_a_changed_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            model_id = "fal-ai/flux/schnell"
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(fal_api_key="fal-test-secret"),
            )
            worker._set_diagnostic_context(1, 1, "generation")
            ratio, resolution = worker._get_generation_profile(False)
            worker.fal_task_journal.upsert(
                "stale-cat-task",
                "generation:1",
                model_id,
                "queued",
                input_fingerprint=worker._paid_task_fingerprint(
                    main.fal_generation_payload(
                        model_id, "cat", ratio, resolution
                    )
                ),
            )
            calls = []

            class FakeFalClient:
                def __init__(self, _config):
                    pass

                def submit_task(self, _request):
                    calls.append("POST")
                    return {"request_id": "new-dog-task"}

                def wait_for_result(self, request_id, **_kwargs):
                    calls.append(("GET", request_id))
                    return {
                        "request_id": request_id,
                        "status": "completed",
                        "result": {
                            "images": [{"url": "https://cdn.example/dog.png"}]
                        },
                    }

            with patch("main.FalClient", FakeFalClient):
                result = worker._fal_generate_image("DOG", model_id)

            self.assertEqual(result, "https://cdn.example/dog.png")
            self.assertEqual(calls, ["POST", ("GET", "new-dog-task")])

    def test_ideogram_generation_sends_selected_aspect_ratio(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(
                fal_api_key="fal-test-secret",
                text_generation_model="fal-ai/ideogram/v3",
                text_generation_ratio="3:4",
            ),
            generated_prompts=[{"prompt": "a flower", "references": []}],
        )
        calls = {}

        class FakeFalClient:
            def __init__(self, _config):
                pass

            def submit_task(self, request):
                calls["request"] = request
                return {"request_id": "fal-request-ideogram"}

            def wait_for_result(self, request_id, **_kwargs):
                return {
                    "request_id": request_id,
                    "result": {"images": [{"url": "https://cdn.example/flower.png"}]},
                }

        with patch.object(main, "FalClient", FakeFalClient):
            worker._kie_generate_image("a flower")

        self.assertEqual(
            calls["request"].input_payload,
            {"prompt": "a flower", "aspect_ratio": "3:4"},
        )

    def test_nonprefixed_fal_generation_model_routes_to_fal_with_image_size(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(
                fal_api_key="fal-test-secret",
                text_generation_model="ideogram/v4/fast",
                text_generation_ratio="3:4",
            ),
            generated_prompts=[{"prompt": "a flower", "references": []}],
        )
        calls = {}

        class FakeFalClient:
            def __init__(self, config):
                calls["model"] = config.model_id

            def submit_task(self, request):
                calls["request"] = request
                return {"request_id": "fal-request-ideogram-v4"}

            def wait_for_result(self, request_id, **_kwargs):
                return {
                    "request_id": request_id,
                    "result": {"images": [{"url": "https://cdn.example/flower.png"}]},
                }

        with patch.object(main, "FalClient", FakeFalClient):
            worker._kie_generate_image("a flower")

        self.assertEqual(calls["model"], "ideogram/v4/fast")
        self.assertEqual(calls["request"].provider_id, "fal")
        self.assertEqual(
            calls["request"].input_payload,
            {"prompt": "a flower", "image_size": "portrait_4_3"},
        )

    def test_fal_generation_honors_explicit_unconfirmed_cost_gate(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(
                fal_api_key="fal-test-secret",
                fal_cost_confirmed=False,
                text_generation_model="fal-ai/flux/schnell",
            ),
            generated_prompts=[{"prompt": "a fox", "references": []}],
        )
        with self.assertRaisesRegex(RuntimeError, "подтвердите актуальную цену"):
            worker._fal_generate_image("a fox", "fal-ai/flux/schnell")

    def test_fal_bria_upscale_pass_uses_alpha_safe_endpoint_and_downloads_result(self):
        with tempfile.TemporaryDirectory(prefix="fal-upscale-") as temp:
            source = Path(temp) / "source.png"
            create_rgb_source(source)
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(fal_api_key="fal-test-secret", fal_concurrency=1),
            )
            calls = {}
            worker._fal_process_image = types.MethodType(
                lambda _self, image_url, **kwargs: calls.update(
                    {"image_url": image_url, **kwargs}
                ) or "https://cdn.example/upscaled.png",
                worker,
            )
            worker._download_file = types.MethodType(
                lambda _self, _url, output_path: Path(output_path).write_bytes(b"result"),
                worker,
            )
            diagnostics = []
            worker._emit_diagnostic = types.MethodType(
                lambda _self, event, **fields: diagnostics.append((event, fields)),
                worker,
            )

            output_path, output_url, local_result = worker._run_upscale_pass(
                str(source),
                None,
                temp,
                1,
                "gen",
                "upscaled_before",
                "fal",
                2,
                "ignored",
            )

        self.assertEqual(calls["operation"], "upscale")
        self.assertEqual(calls["model_id"], "bria/upscale/creative")
        self.assertEqual(calls["scale"], 2)
        self.assertEqual(diagnostics[0][1]["parameters"]["scale"], 2)
        self.assertTrue(output_path.endswith(".png"))
        self.assertEqual(output_url, "https://cdn.example/upscaled.png")
        self.assertTrue(local_result)

    def test_fal_background_removal_returns_downloaded_local_result(self):
        with tempfile.TemporaryDirectory(prefix="fal-remove-bg-local-result-") as temp:
            source = Path(temp) / "source.png"
            raw_dir = Path(temp) / "raw"
            raw_dir.mkdir()
            create_rgb_source(source)
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    remove_bg=True,
                    remove_bg_provider="fal",
                    fal_remove_bg_model="fal-ai/birefnet/v2",
                ),
            )
            downloads = []
            worker._fal_process_image = types.MethodType(
                lambda _self, _url, **_kwargs: "https://cdn.example/no-bg.png",
                worker,
            )

            def download_alpha(_self, url, output_path):
                downloads.append(url)
                image = Image.new("RGBA", (16, 12), (0, 0, 0, 0))
                ImageDraw.Draw(image).rectangle((3, 2, 12, 9), fill=(180, 70, 100, 255))
                image.save(output_path, format="PNG")

            worker._download_file = types.MethodType(download_alpha, worker)

            result_path = worker._run_processing_pipeline(
                str(source),
                None,
                str(raw_dir),
                1,
                "file",
            )

            self.assertEqual(downloads, ["https://cdn.example/no-bg.png"])
            self.assertTrue(Path(result_path).is_file())
            self.assertEqual(Path(result_path).parent, raw_dir)

    def test_fal_recraft_crisp_routes_fixed_four_x_without_scale_payload(self):
        with tempfile.TemporaryDirectory(prefix="fal-recraft-upscale-") as temp:
            source = Path(temp) / "source.png"
            create_rgb_source(source, size=(64, 64))
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    fal_concurrency=1,
                    fal_upscale_model="fal-ai/recraft/upscale/crisp",
                    fal_upscale_scale=2,
                ),
            )
            calls = {}
            worker._fal_process_image = types.MethodType(
                lambda _self, image_url, **kwargs: calls.update(
                    {"image_url": image_url, **kwargs}
                ) or "https://cdn.example/upscaled.png",
                worker,
            )
            worker._download_file = types.MethodType(
                lambda _self, _url, output_path: shutil.copyfile(source, output_path),
                worker,
            )

            worker._run_upscale_pass(
                str(source),
                None,
                temp,
                1,
                "gen",
                "upscaled_before",
                "fal",
                2,
                "ignored",
            )

        self.assertEqual(calls["model_id"], "fal-ai/recraft/upscale/crisp")
        self.assertEqual(calls["scale"], 4)
        self.assertIsNone(calls.get("parameters"))

    def test_fal_recraft_crisp_rejects_transparent_input_before_paid_call(self):
        with tempfile.TemporaryDirectory(prefix="fal-recraft-alpha-") as temp:
            source = Path(temp) / "source.png"
            image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((4, 4, 27, 27), fill=(180, 70, 100, 255))
            image.save(source, format="PNG")
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    fal_upscale_model="fal-ai/recraft/upscale/crisp",
                ),
            )
            worker._fal_process_image = types.MethodType(
                lambda *_args, **_kwargs: self.fail("paid Fal call must not start"),
                worker,
            )

            with self.assertRaisesRegex(RuntimeError, "Bria"):
                worker._run_upscale_pass(
                    str(source),
                    None,
                    temp,
                    1,
                    "gen",
                    "upscaled_before",
                    "fal",
                    2,
                    "ignored",
                )
            self.assertEqual(worker._diagnostic_context.stage, "upscale_before")
            self.assertEqual(worker._diagnostic_context.provider, "fal")
            self.assertEqual(
                worker._diagnostic_context.model,
                "fal-ai/recraft/upscale/crisp",
            )

    def test_processing_worker_decodes_corrupt_source_before_paid_fal_call(self):
        with tempfile.TemporaryDirectory(prefix="processing-corrupt-worker-") as temp:
            root = Path(temp)
            source = root / "source.jpg"
            Image.new("RGB", (40, 40), "purple").save(source, quality=90)
            source.write_bytes(source.read_bytes()[:-20])
            output = root / "output" / "source_ready.png"
            output.parent.mkdir()
            raw_dir = root / "raw"
            raw_dir.mkdir()
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    upscale=True,
                    upscale_provider="fal",
                ),
                selected_files=[str(source)],
            )
            worker._fal_process_image = types.MethodType(
                lambda *_args, **_kwargs: self.fail("paid Fal call must not start"),
                worker,
            )

            with self.assertRaisesRegex(ValueError, "Local input image is invalid"):
                worker._process_file_entry(
                    1,
                    1,
                    str(source),
                    str(raw_dir),
                    str(output),
                )

    def test_fal_recraft_crisp_normalizes_opaque_jpeg_to_png(self):
        with tempfile.TemporaryDirectory(prefix="fal-recraft-jpeg-") as temp:
            source = Path(temp) / "source.jpg"
            output = Path(temp) / "prepared.png"
            Image.new("RGB", (64, 48), (180, 70, 100)).save(source, format="JPEG")

            result = main.prepare_fal_recraft_crisp_input(source, output)

            self.assertEqual(Path(result), output)
            with Image.open(output) as prepared:
                self.assertEqual(prepared.format, "PNG")
                self.assertEqual(prepared.mode, "RGB")

    def test_bria_usable_alpha_skips_following_paid_background_remover(self):
        with tempfile.TemporaryDirectory(prefix="fal-bria-alpha-") as temp:
            source = Path(temp) / "source.png"
            create_rgb_source(source)
            raw_dir = Path(temp) / "raw"
            raw_dir.mkdir()
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    upscale=True,
                    upscale_provider="fal",
                    fal_upscale_model="bria/upscale/creative",
                    remove_bg=True,
                    remove_bg_provider="fal",
                    skip_remover_for_alpha=True,
                ),
            )
            operations = []
            worker._fal_source_url = types.MethodType(
                lambda _self, _path, current_url: current_url
                or "https://cdn.example/source.png",
                worker,
            )
            worker._fal_process_image = types.MethodType(
                lambda _self, _url, *, operation, **_kwargs: operations.append(operation)
                or f"https://cdn.example/{operation}.png",
                worker,
            )

            def download_alpha(_self, _url, output_path):
                image = Image.new("RGBA", (32, 24), (0, 0, 0, 0))
                ImageDraw.Draw(image).rectangle((6, 4, 25, 19), fill=(180, 70, 100, 255))
                image.save(output_path, format="PNG")

            worker._download_file = types.MethodType(download_alpha, worker)

            result_path = worker._run_processing_pipeline(
                str(source),
                None,
                str(raw_dir),
                1,
                "gen",
            )

            with Image.open(result_path) as result:
                self.assertTrue(main.has_usable_alpha(result))

        self.assertEqual(operations, ["upscale"])

    def test_fal_topaz_upscale_pass_keeps_selected_model_and_scale(self):
        with tempfile.TemporaryDirectory(prefix="fal-topaz-upscale-") as temp:
            source = Path(temp) / "source.png"
            create_rgb_source(source)
            worker = main.WorkerThread(
                "mode2_process",
                temp,
                kie_settings(
                    fal_api_key="fal-test-secret",
                    fal_concurrency=1,
                    fal_upscale_model="topaz/upscale/image/precision",
                    fal_upscale_scale=4,
                ),
            )
            calls = {}
            worker._fal_process_image = types.MethodType(
                lambda _self, image_url, **kwargs: calls.update(
                    {"image_url": image_url, **kwargs}
                ) or "https://cdn.example/upscaled.png",
                worker,
            )
            worker._download_file = types.MethodType(
                lambda _self, _url, output_path: Path(output_path).write_bytes(b"result"),
                worker,
            )
            diagnostics = []
            worker._emit_diagnostic = types.MethodType(
                lambda _self, event, **fields: diagnostics.append((event, fields)),
                worker,
            )

            worker._run_upscale_pass(
                str(source),
                None,
                temp,
                1,
                "gen",
                "upscaled_before",
                "fal",
                2,
                "ignored",
            )

        self.assertEqual(calls["model_id"], "topaz/upscale/image/precision")
        self.assertEqual(calls["scale"], 4)
        self.assertEqual(diagnostics[0][1]["parameters"]["scale"], 4)

    def test_topaz_uses_current_model_and_documented_payload(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            kie_settings(
                kie_api_key=DUMMY_KIE_KEY,
                upscale=True,
                upscale_factor=4,
                kie_upscale_model="topaz/upscale",
            ),
        )
        captured = {}

        def fake_create(worker_self, model, input_payload):
            captured["model"] = model
            captured["input"] = input_payload
            return "task-topaz"

        worker._kie_create_task = types.MethodType(fake_create, worker)
        worker._kie_wait_result = types.MethodType(
            lambda worker_self, task_id: "mock://topaz-result",
            worker,
        )
        worker._download_file = types.MethodType(
            lambda worker_self, url, output_path: None,
            worker,
        )

        factor = worker._resolve_upscale_factor(worker.kie_upscale_model)
        worker._upscale_pipeline_step(
            "https://example.invalid/source.png",
            ".",
            1,
            "probe",
            "upscaled",
            factor,
            model_name=worker.kie_upscale_model,
        )

        self.assertEqual(worker.kie_upscale_model, "topaz/image-upscale")
        self.assertEqual(factor, 4)
        self.assertEqual(captured["model"], "topaz/image-upscale")
        self.assertEqual(
            captured["input"],
            {
                "image_url": "https://example.invalid/source.png",
                "upscale_factor": "4",
            },
        )

    def test_topaz_rejects_oversized_source_before_upload(self):
        with tempfile.TemporaryDirectory(prefix="clipart-topaz-limit-") as temp_dir:
            source_path = Path(temp_dir) / "too-wide.png"
            Image.new("RGB", (5001, 1), "white").save(source_path, format="PNG")
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(
                    kie_api_key=DUMMY_KIE_KEY,
                    upscale=True,
                    upscale_factor=4,
                    kie_upscale_model="topaz/image-upscale",
                ),
            )
            uploads = []
            worker._kie_upload_file = types.MethodType(
                lambda worker_self, path: uploads.append(path) or "mock://uploaded",
                worker,
            )
            with self.assertRaisesRegex(ValueError, "20 000"):
                worker._run_processing_pipeline(
                    str(source_path),
                    None,
                    temp_dir,
                    1,
                    "probe",
                )
            self.assertEqual(uploads, [])

    def test_topaz_rejects_file_over_ten_megabytes_before_upload(self):
        with tempfile.TemporaryDirectory(prefix="clipart-topaz-bytes-") as temp_dir:
            source_path = Path(temp_dir) / "too-large.png"
            with source_path.open("wb") as stream:
                stream.truncate(10_000_001)
            worker = main.WorkerThread(
                "mode2_process",
                temp_dir,
                kie_settings(
                    kie_api_key=DUMMY_KIE_KEY,
                    upscale=True,
                    upscale_factor=2,
                    kie_upscale_model="topaz/image-upscale",
                ),
            )
            uploads = []
            worker._kie_upload_file = types.MethodType(
                lambda worker_self, path: uploads.append(path) or "mock://uploaded",
                worker,
            )
            with self.assertRaisesRegex(ValueError, "10 МБ"):
                worker._run_processing_pipeline(
                    str(source_path),
                    None,
                    temp_dir,
                    1,
                    "probe",
                )
            self.assertEqual(uploads, [])

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
        events = []
        worker.diagnostic.connect(events.append)
        worker._set_diagnostic_context(1, 1, "upscale_before")
        with self.assertRaisesRegex(
            RuntimeError,
            r"taskId=task-123; errorCode=501; message=provider could not process image",
        ):
            worker._kie_wait_result("task-123")
        failed = next(event for event in events if event["event"] == "provider_task_failed")
        polled = next(event for event in events if event["event"] == "provider_task_polled")
        self.assertEqual(failed["task"], "task-123")
        self.assertEqual(failed["error_code"], "501")
        self.assertEqual(failed["error_message"], "provider could not process image")
        self.assertEqual(polled["provider_state"], "fail")

    def test_kie_create_task_emits_safe_model_and_task_without_request_payload(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        events = []
        worker.diagnostic.connect(events.append)
        worker._set_diagnostic_context(2, 4, "generation")
        worker._request_json = types.MethodType(
            lambda self, *args, **kwargs: {
                "code": 200,
                "data": {"taskId": "task-safe-789"},
            },
            worker,
        )

        task_id = worker._kie_create_task(
            "gpt-image-2-text-to-image",
            {"prompt": "private prompt", "aspect_ratio": "1:1"},
        )

        self.assertEqual(task_id, "task-safe-789")
        submitted = next(event for event in events if event["event"] == "provider_task_submitted")
        encoded = json.dumps(submitted)
        self.assertEqual(submitted["model"], "gpt-image-2-text-to-image")
        self.assertEqual(submitted["task"], "task-safe-789")
        self.assertEqual(submitted["item_index"], 2)
        self.assertNotIn("private prompt", encoded)
        self.assertNotIn(DUMMY_KIE_KEY, encoded)

    def test_kie_task_id_is_journaled_and_polling_resumes_without_resubmit(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            worker.status_poll_interval = 0
            worker.generation_wait_timeout = 5
            create_calls = 0
            polled_urls = []

            def fake_request_json(worker_self, url, *, method, **_kwargs):
                nonlocal create_calls
                if method == "POST":
                    create_calls += 1
                    return {"code": 200, "data": {"taskId": "task-resume-1"}}
                polled_urls.append(url)
                if len(polled_urls) == 1:
                    worker_self._diagnostic_context.last_http_status = None
                    raise RuntimeError("temporary polling transport failure")
                return {
                    "code": 200,
                    "data": {
                        "state": "success",
                        "resultJson": json.dumps(
                            {"resultUrls": ["https://cdn.example/result.png"]}
                        ),
                    },
                }

            worker._request_json = types.MethodType(fake_request_json, worker)

            result = worker._kie_generate_generic_model("z-image", "private prompt")

            self.assertEqual(result, "https://cdn.example/result.png")
            self.assertEqual(create_calls, 1)
            self.assertEqual(len(polled_urls), 2)
            self.assertTrue(
                all("taskId=task-resume-1" in url for url in polled_urls)
            )
            self.assertEqual(worker.kie_task_journal.pending(), ())
            journal_text = (Path(temp) / ".vibix_kie_tasks.json").read_text(
                encoding="utf-8"
            )
            self.assertIn("task-resume-1", journal_text)
            self.assertNotIn("private prompt", journal_text)

    def test_new_worker_resumes_existing_kie_task_without_post(self):
        with tempfile.TemporaryDirectory() as temp:
            model_id = main.resolve_kie_generation_model("z-image", False)
            first = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            first.kie_task_journal.upsert(
                "existing-task",
                "generation",
                model_id,
                "queued",
                input_fingerprint=first._paid_task_fingerprint(
                    first._build_documented_model_input(
                        "z-image", "same prompt", []
                    )
                ),
            )
            restarted = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            restarted.status_poll_interval = 0
            restarted._set_diagnostic_context(1, 1, "generation")
            methods = []

            def fake_request_json(_self, _url, *, method, **_kwargs):
                methods.append(method)
                if method == "POST":
                    raise AssertionError("restart must not submit another paid task")
                return {
                    "code": 200,
                    "data": {
                        "state": "success",
                        "resultJson": json.dumps(
                            {"resultUrls": ["https://cdn.example/recovered.png"]}
                        ),
                    },
                }

            restarted._request_json = types.MethodType(fake_request_json, restarted)

            result = restarted._kie_generate_generic_model("z-image", "same prompt")

            self.assertEqual(result, "https://cdn.example/recovered.png")
            self.assertEqual(methods, ["GET"])

    def test_kie_restart_matches_local_reference_when_upload_url_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "reference.png"
            create_rgb_source(source)
            model_name = "gpt-image/1.5-image-to-image"
            model_id = main.resolve_kie_generation_model(model_name, True)

            first = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            first._set_diagnostic_context(1, 1, "generation")
            first._request_with_retries = lambda *_args, **_kwargs: json.dumps(
                {"success": True, "data": {"downloadUrl": "https://cdn.example/token-A"}}
            ).encode("utf-8")
            first_urls = first._resolve_reference_urls([str(source)])
            first_payload = first._build_documented_model_input(
                model_name,
                "same prompt",
                first_urls,
            )
            first.kie_task_journal.upsert(
                "existing-reference-task",
                "generation:1",
                model_id,
                "queued",
                input_fingerprint=first._paid_task_fingerprint(first_payload),
            )

            restarted = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            restarted.status_poll_interval = 0
            restarted._set_diagnostic_context(1, 1, "generation")
            restarted._request_with_retries = lambda *_args, **_kwargs: json.dumps(
                {"success": True, "data": {"downloadUrl": "https://cdn.example/token-B"}}
            ).encode("utf-8")
            restarted_urls = restarted._resolve_reference_urls([str(source)])
            methods = []

            def fake_request_json(_self, _url, *, method, **_kwargs):
                methods.append(method)
                if method == "POST":
                    raise AssertionError("restart must not submit another paid task")
                return {
                    "code": 200,
                    "data": {
                        "state": "success",
                        "resultJson": json.dumps(
                            {"resultUrls": ["https://cdn.example/recovered.png"]}
                        ),
                    },
                }

            restarted._request_json = types.MethodType(fake_request_json, restarted)

            result = restarted._kie_generate_generic_model(
                model_name,
                "same prompt",
                reference_urls=restarted_urls,
            )

            self.assertEqual(result, "https://cdn.example/recovered.png")
            self.assertEqual(methods, ["GET"])

    def test_kie_restart_never_reuses_a_task_for_a_changed_prompt(self):
        with tempfile.TemporaryDirectory() as temp:
            model_id = main.resolve_kie_generation_model("z-image", False)
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            worker._set_diagnostic_context(1, 1, "generation")
            old_payload = worker._build_documented_model_input(
                "z-image", "cat", []
            )
            worker.kie_task_journal.upsert(
                "stale-cat-task",
                "generation:1",
                model_id,
                "queued",
                input_fingerprint=worker._paid_task_fingerprint(old_payload),
            )
            methods = []

            def fake_request_json(_self, _url, *, method, **_kwargs):
                methods.append(method)
                if method == "POST":
                    return {"code": 200, "data": {"taskId": "new-dog-task"}}
                return {
                    "code": 200,
                    "data": {
                        "state": "success",
                        "resultJson": json.dumps(
                            {"resultUrls": ["https://cdn.example/dog.png"]}
                        ),
                    },
                }

            worker._request_json = types.MethodType(fake_request_json, worker)

            result = worker._kie_generate_generic_model("z-image", "DOG")

            self.assertEqual(result, "https://cdn.example/dog.png")
            self.assertEqual(methods, ["POST", "GET"])

    def test_kie_result_parse_failure_keeps_completed_task_recoverable(self):
        with tempfile.TemporaryDirectory() as temp:
            worker = main.WorkerThread(
                "mode1_generate_only",
                temp,
                kie_settings(kie_api_key=DUMMY_KIE_KEY),
            )
            worker.kie_task_journal.upsert(
                "task-result-pending",
                "generation",
                "z-image",
                "queued",
            )
            worker._request_json = types.MethodType(
                lambda _self, *_args, **_kwargs: {
                    "code": 200,
                    "data": {"state": "success", "resultJson": "not-json"},
                },
                worker,
            )

            with self.assertRaises(Exception):
                worker._kie_wait_result("task-result-pending")

            self.assertEqual(
                {record.request_id for record in worker.kie_task_journal.pending()},
                {"task-result-pending"},
            )

    def test_status_transport_errors_emit_failure_without_masking_original_error(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        worker._request_json = types.MethodType(
            lambda self, *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("network unavailable")
            ),
            worker,
        )
        events = []
        worker.diagnostic.connect(events.append)
        worker._set_diagnostic_context(1, 1, "generation")

        with self.assertRaisesRegex(RuntimeError, "network unavailable"):
            worker._kie_wait_result("task-current")
        with self.assertRaisesRegex(RuntimeError, "network unavailable"):
            worker._kie_wait_4o_result("task-legacy")

        failed_tasks = [
            event.get("task")
            for event in events
            if event["event"] == "provider_task_failed"
        ]
        self.assertEqual(failed_tasks, ["task-current", "task-legacy"])

    def test_provider_error_cannot_echo_current_prompt_into_diagnostics(self):
        private_prompt = "private watercolor fox prompt"
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        worker._diagnostic_context.prompt_text = private_prompt
        worker._request_json = types.MethodType(
            lambda self, *args, **kwargs: {
                "code": 200,
                "data": {
                    "state": "fail",
                    "failCode": 422,
                    "failMsg": f"invalid prompt: {private_prompt}",
                },
            },
            worker,
        )
        events = []
        worker.diagnostic.connect(events.append)

        with self.assertRaises(RuntimeError):
            worker._kie_wait_result("task-prompt-redaction")

        self.assertNotIn(private_prompt, json.dumps(events))

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

    def test_gpt_image_2_payload_preserves_extended_ratio(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(
                text_generation_ratio="2:1",
                text_generation_resolution="2K",
            ),
        )
        payload = worker._build_documented_model_input(
            "gpt-image-2",
            "valid prompt",
            [],
        )
        self.assertEqual(payload["aspect_ratio"], "2:1")

    def test_qwen_two_routes_exact_model_and_single_reference_payload(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(
                text_generation_ratio="16:9",
                reference_generation_ratio="16:9",
            ),
        )
        calls = []
        worker._kie_create_task = types.MethodType(
            lambda worker_self, model, payload: calls.append((model, payload)) or "task-qwen",
            worker,
        )
        worker._kie_wait_result = types.MethodType(
            lambda worker_self, task_id: f"mock://{task_id}",
            worker,
        )

        worker._kie_generate_generic_model("qwen-image-2", "text prompt")
        worker._kie_generate_generic_model(
            "qwen-image-2",
            "edit prompt",
            ["mock://reference.png"],
        )

        self.assertEqual(calls[0][0], "qwen2/text-to-image")
        self.assertNotIn("image_url", calls[0][1])
        self.assertEqual(calls[1][0], "qwen2/image-edit")
        self.assertEqual(calls[1][1]["image_url"], "mock://reference.png")

    def test_worker_rejects_model_reference_limit_before_upload(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(
                kie_api_key=DUMMY_KIE_KEY,
                reference_generation_model="qwen-image-2",
                reference_generation_ratio="1:1",
                reference_generation_resolution="1K",
            ),
        )
        worker._kie_upload_file = types.MethodType(
            lambda worker_self, path: self.fail("upload must not start"),
            worker,
        )
        with self.assertRaisesRegex((RuntimeError, ValueError), "1 референс"):
            worker._kie_generate_image(
                "valid prompt",
                ["one.png", "two.png"],
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

            raw_outputs = list((Path(temp_dir) / "rough").glob("*.png"))
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
            create_rgb_source(source_path, size=(300, 300))
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
            raw_outputs = list((temp_path / "rough").glob("*.png"))
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

    def test_post_rate_limit_is_retried_with_a_small_bound(self):
        worker = main.WorkerThread(
            "mode1_generate_only",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY, retries=5),
        )
        req = main.request.Request(
            "https://api.kie.ai/api/v1/jobs/createTask",
            data=b"{}",
            method="POST",
        )
        rate_limited = main.urlerror.HTTPError(
            req.full_url,
            429,
            "Too Many Requests",
            {},
            BytesIO(b"rate limited"),
        )
        response = BytesIO(b"ok")
        response.headers = {}

        with (
            patch.object(main, "open_url_secure", side_effect=[rate_limited, response]) as request_mock,
            patch.object(main.time, "sleep"),
        ):
            self.assertEqual(worker._request_with_retries(req), b"ok")

        self.assertEqual(request_mock.call_count, 2)

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
                with self.assertRaisesRegex(
                    RuntimeError,
                    "задача KIE не была создана",
                ):
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
                with self.assertRaisesRegex(
                    RuntimeError,
                    "задача KIE не была создана",
                ) as raised:
                    worker._kie_upload_file(str(source_path))

            self.assertIn("size limit", str(raised.exception))
            request_mock.assert_not_called()

    def test_missing_upload_file_explains_that_no_kie_task_was_created(self):
        worker = main.WorkerThread(
            "mode2_process",
            ".",
            kie_settings(kie_api_key=DUMMY_KIE_KEY),
        )
        events = []
        worker.diagnostic.connect(events.append)
        with self.assertRaisesRegex(
            RuntimeError,
            "задача KIE не была создана",
        ):
            worker._kie_upload_file("/definitely/missing/topaz-source.png")
        failed = next(event for event in events if event["event"] == "stage_finished")
        self.assertEqual(failed["provider"], "kie")
        self.assertEqual(failed["outcome"], "failed")
        self.assertNotIn("/definitely/missing", json.dumps(events))

    def test_recraft_crisp_input_limits_are_checked_before_upload(self):
        with tempfile.TemporaryDirectory(prefix="clipart-recraft-crisp-limits-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            create_rgb_source(source_path, size=(64, 64))

            with patch.object(main, "RECRAFT_CRISP_MAX_BYTES", 8):
                with self.assertRaisesRegex(RuntimeError, "10 MB|file size"):
                    main.validate_recraft_crisp_upscale_input(str(source_path))

    def test_recraft_crisp_does_not_apply_undocumented_dimension_limit(self):
        with tempfile.TemporaryDirectory(prefix="clipart-recraft-crisp-large-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            create_rgb_source(source_path, size=(5000, 1000))
            self.assertIsNone(main.validate_recraft_crisp_upscale_input(str(source_path)))

    def test_recraft_processing_limits_match_current_documentation(self):
        self.assertEqual(main.RECRAFT_CRISP_MAX_BYTES, 10 * 1024 * 1024)
        self.assertEqual(main.RECRAFT_REMOVE_BG_MAX_BYTES, 5 * 1024 * 1024)
        with tempfile.TemporaryDirectory(prefix="clipart-recraft-remove-limits-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            create_rgb_source(source_path, size=(255, 300))
            with self.assertRaisesRegex(RuntimeError, "256"):
                main.validate_recraft_remove_background_input(str(source_path))

    def test_recraft_crisp_input_accepts_opaque_chatgpt_style_png(self):
        with tempfile.TemporaryDirectory(prefix="clipart-recraft-crisp-valid-") as temp_dir:
            source_path = Path(temp_dir) / "source.png"
            create_rgb_source(source_path, size=(1024, 1024))

            self.assertIsNone(main.validate_recraft_crisp_upscale_input(str(source_path)))

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
