import json
import multiprocessing
import tempfile
import threading
import time
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fal_provider import (
    FalClient,
    FalConfig,
    FalProviderError,
    FalTaskJournal,
    fal_image_input,
    fal_image_data_uri,
    fal_image_url,
    fal_status_kind,
    validate_fal_image_result,
)
from fal_model_catalog import fal_endpoint_profile
from provider_contract import ProviderTaskRequest


class _SlowProcessJournal(FalTaskJournal):
    def _read(self):
        records = super()._read()
        time.sleep(0.1)
        return records


def _upsert_paid_task_in_process(path, request_id, start):
    journal = _SlowProcessJournal(path)
    start.wait()
    journal.upsert(
        request_id,
        "generation",
        "fal-ai/flux/schnell",
        "queued",
    )


class _Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return json.dumps(self.payload).encode("utf-8")


class _Opener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        return self.response


class FalProviderTests(unittest.TestCase):
    def test_ideogram_generation_profiles_support_png_results(self):
        for model_id in ("fal-ai/ideogram/v3", "fal-ai/ideogram/v3/generate-transparent"):
            profile = fal_endpoint_profile(model_id, "generation")
            self.assertTrue(profile.supports_references is False)
            self.assertIn("png", profile.output_formats)

    def test_config_requires_key_and_safe_model_identifier(self):
        with self.assertRaises(FalProviderError):
            FalConfig(api_key="", model_id="fal-ai/flux/schnell").validate()
        with self.assertRaises(FalProviderError):
            FalConfig(api_key="secret", model_id="https://evil.example/model").validate()
        self.assertNotIn(
            "fal-secret",
            repr(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell")),
        )

    def test_config_can_guard_each_paid_submit_attempt(self):
        self.assertIn("before_paid_submit", FalConfig.__dataclass_fields__)

    def test_status_kind_maps_queue_lifecycle_and_cancel_states(self):
        self.assertEqual(fal_status_kind({"status": "IN_QUEUE"}), "queued")
        self.assertEqual(fal_status_kind({"status": "IN_PROGRESS"}), "running")
        self.assertEqual(fal_status_kind({"status": "COMPLETED"}), "completed")
        self.assertEqual(fal_status_kind({"status": "CANCELLATION_REQUESTED"}), "cancel_requested")
        self.assertEqual(fal_status_kind({"status": "ALREADY_COMPLETED"}), "already_completed")
        self.assertEqual(fal_status_kind({"status": "anything_else"}), "unknown")

    def test_image_input_is_explicit_and_does_not_upload_local_paths(self):
        self.assertEqual(
            fal_image_input("https://example.test/image.png"),
            {"image_url": "https://example.test/image.png"},
        )
        with self.assertRaises(FalProviderError):
            fal_image_input("C:/Users/user/image.png")

    def test_image_url_accepts_known_result_shapes_and_rejects_non_https(self):
        self.assertEqual(
            fal_image_url({"images": [{"url": "https://cdn.example/image.png"}]}),
            "https://cdn.example/image.png",
        )
        with self.assertRaises(FalProviderError):
            fal_image_url({"images": [{"url": "http://cdn.example/image.png"}]})

    def test_image_result_requires_an_image_and_allowed_content_type(self):
        self.assertEqual(
            validate_fal_image_result(
                {"image": {"url": "https://cdn.example/image.png", "content_type": "image/png"}},
                operation="remove_background",
                model_id="fal-ai/bria/background/remove",
            ),
            "https://cdn.example/image.png",
        )
        with self.assertRaisesRegex(FalProviderError, "файл изображения"):
            validate_fal_image_result(
                {},
                operation="remove_background",
                model_id="fal-ai/bria/background/remove",
            )
        with self.assertRaisesRegex(FalProviderError, "неподдерживаемый формат"):
            validate_fal_image_result(
                {"image": {"url": "https://cdn.example/image.jpg", "content_type": "image/jpeg"}},
                operation="remove_background",
                model_id="fal-ai/bria/background/remove",
            )

    def test_local_image_data_uri_is_bounded_and_uses_image_mime_type(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            handle.write(b"png-bytes")
            handle.flush()
            uri = fal_image_data_uri(handle.name)
        self.assertTrue(uri.startswith("data:image/png;base64,"))
        with tempfile.NamedTemporaryFile(suffix=".txt") as handle:
            handle.write(b"text")
            handle.flush()
            with self.assertRaises(FalProviderError):
                fal_image_data_uri(handle.name)

    def test_submit_uses_queue_endpoint_and_key_auth(self):
        opener = _Opener(_Response({"request_id": "req-123", "queue_position": 2}))
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))

        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            result = client.submit({"prompt": "a fox"})

        self.assertEqual(result["request_id"], "req-123")
        self.assertEqual(opener.request.full_url, "https://queue.fal.run/fal-ai/flux/schnell")
        self.assertEqual(opener.request.get_header("Authorization"), "Key fal-secret")
        self.assertEqual(json.loads(opener.request.data), {"prompt": "a fox"})

    def test_submit_requires_request_id(self):
        opener = _Opener(_Response({"queue_position": 2}))
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))
        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(FalProviderError):
                client.submit({"prompt": "a fox"})

    def test_result_fetches_documented_response_route(self):
        opener = _Opener(_Response({"images": [{"url": "https://cdn.example/a.png"}]}))
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))

        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            result = client.result("req-123")

        self.assertEqual(result["images"][0]["url"], "https://cdn.example/a.png")
        self.assertEqual(
            opener.request.full_url,
            "https://queue.fal.run/fal-ai/flux/schnell/requests/req-123/response",
        )

    def test_cancel_accepts_already_completed_http_error_body(self):
        class AlreadyCompletedOpener:
            def open(self, request, timeout):
                raise urllib.error.HTTPError(
                    request.full_url,
                    400,
                    "already completed",
                    {},
                    BytesIO(b'{"status":"ALREADY_COMPLETED"}'),
                )

        client = FalClient(
            FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell")
        )
        with patch(
            "fal_provider.urllib.request.build_opener",
            return_value=AlreadyCompletedOpener(),
        ):
            result = client.cancel("req-123")

        self.assertEqual(result, {"status": "ALREADY_COMPLETED"})

    def test_paid_submit_is_not_retried_after_transient_http_failure(self):
        class FailingOpener:
            calls = 0

            def open(self, _request, timeout):
                self.calls += 1
                raise urllib.error.HTTPError(
                    "https://queue.fal.run", 503, "busy", {}, None
                )

        opener = FailingOpener()
        client = FalClient(
            FalConfig(
                api_key="fal-secret",
                model_id="fal-ai/flux/schnell",
                max_retries=2,
                retry_backoff_seconds=0,
            )
        )
        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(FalProviderError):
                client.submit({"prompt": "a fox"})
        self.assertEqual(opener.calls, 1)

    def test_paid_submit_is_not_retried_after_ambiguous_network_failure(self):
        class FailingOpener:
            calls = 0

            def open(self, _request, timeout):
                self.calls += 1
                raise urllib.error.URLError("connection lost")

        opener = FailingOpener()
        client = FalClient(
            FalConfig(
                api_key="fal-secret",
                model_id="fal-ai/flux/schnell",
                max_retries=2,
                retry_backoff_seconds=0,
            )
        )
        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            with self.assertRaises(FalProviderError):
                client.submit({"prompt": "a fox"})

        self.assertEqual(opener.calls, 1)

    def test_paid_submit_retries_only_http_429_with_bounded_admission_checks(self):
        class RateLimitedOnce:
            def __init__(self):
                self.calls = 0

            def open(self, _request, timeout):
                self.calls += 1
                if self.calls == 1:
                    raise urllib.error.HTTPError(
                        "https://queue.fal.run",
                        429,
                        "rate limited",
                        {},
                        BytesIO(b'{"detail":"slow down"}'),
                    )
                return _Response({"request_id": "req-after-429"})

        opener = RateLimitedOnce()
        admissions = []
        client = FalClient(
            FalConfig(
                api_key="fal-secret",
                model_id="fal-ai/flux/schnell",
                max_retries=2,
                retry_backoff_seconds=0,
                before_paid_submit=lambda: admissions.append(True),
            )
        )

        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            result = client.submit({"prompt": "a fox"})

        self.assertEqual(result["request_id"], "req-after-429")
        self.assertEqual(opener.calls, 2)
        self.assertEqual(admissions, [True, True])

    def test_stop_gate_prevents_network_retry_after_fal_http_429(self):
        class AlwaysRateLimited:
            def __init__(self):
                self.calls = 0

            def open(self, _request, timeout):
                self.calls += 1
                raise urllib.error.HTTPError(
                    "https://queue.fal.run",
                    429,
                    "rate limited",
                    {},
                    BytesIO(b"{}"),
                )

        opener = AlwaysRateLimited()
        admission_count = 0

        def stop_before_second_attempt():
            nonlocal admission_count
            admission_count += 1
            if admission_count == 2:
                raise RuntimeError("stopped before retry")

        client = FalClient(
            FalConfig(
                api_key="fal-secret",
                model_id="fal-ai/flux/schnell",
                max_retries=2,
                retry_backoff_seconds=0,
                before_paid_submit=stop_before_second_attempt,
            )
        )

        with patch("fal_provider.urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(RuntimeError, "stopped before retry"):
                client.submit({"prompt": "a fox"})

        self.assertEqual(opener.calls, 1)
        self.assertEqual(admission_count, 2)

    def test_wait_for_result_polls_by_request_id_without_resubmitting(self):
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))
        statuses = iter([
            {"status": "IN_QUEUE", "request_id": "req-123"},
            {"status": "IN_PROGRESS", "request_id": "req-123"},
            {"status": "COMPLETED", "request_id": "req-123"},
        ])
        client.status = lambda _request_id: next(statuses)
        client.result = lambda _request_id: {"images": [{"url": "https://cdn.example/a.png"}]}

        result = client.wait_for_result("req-123", poll_interval_seconds=0, sleep=lambda _seconds: None)

        self.assertEqual(result["request_id"], "req-123")
        self.assertEqual(result["result"]["images"][0]["url"], "https://cdn.example/a.png")

    def test_wait_for_result_uses_provider_supplied_lifecycle_urls(self):
        client = FalClient(
            FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell")
        )
        requested = []

        def fake_request(url, **_kwargs):
            requested.append(url)
            if url.endswith("/poll/req-123"):
                return {"status": "COMPLETED", "request_id": "req-123"}
            return {"images": [{"url": "https://cdn.example/a.png"}]}

        client._request = fake_request
        result = client.wait_for_result(
            "req-123",
            status_url="https://queue.fal.run/custom/poll/req-123",
            response_url="https://queue.fal.run/custom/result/req-123",
            cancel_url="https://queue.fal.run/custom/cancel/req-123",
            poll_interval_seconds=0,
            sleep=lambda _seconds: None,
        )

        self.assertEqual(
            requested,
            [
                "https://queue.fal.run/custom/poll/req-123",
                "https://queue.fal.run/custom/result/req-123",
            ],
        )
        self.assertEqual(result["request_id"], "req-123")

    def test_provider_lifecycle_urls_reject_cross_host_and_downgrade(self):
        client = FalClient(
            FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell")
        )
        for unsafe_url in (
            "http://queue.fal.run/custom/poll/req-123",
            "https://other.example/custom/poll/req-123",
            "https://queue.fal.run/custom/poll/different-request",
            "https://queue.fal.run/custom/poll/req-123?token=secret",
        ):
            with self.subTest(url=unsafe_url):
                with self.assertRaises(FalProviderError):
                    client.status("req-123", url=unsafe_url)

    def test_wait_for_result_requests_cancellation_without_resubmitting(self):
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))
        client.cancel = lambda _request_id: {"status": "CANCELLATION_REQUESTED"}
        client.status = lambda _request_id: {"status": "CANCELLATION_REQUESTED"}

        with self.assertRaisesRegex(FalProviderError, "cancel_requested"):
            client.wait_for_result(
                "req-123",
                timeout_seconds=10,
                poll_interval_seconds=0,
                is_cancelled=lambda: True,
            )

    def test_submit_task_uses_shared_provider_contract(self):
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))
        request = ProviderTaskRequest("fal", "generation", "fal-ai/flux/schnell", {"prompt": "a fox"})
        client.submit = lambda arguments: {"request_id": "req-123", "arguments": dict(arguments)}

        self.assertEqual(client.submit_task(request)["request_id"], "req-123")

    def test_cancelled_status_is_not_reported_as_success(self):
        self.assertEqual(fal_status_kind({"status": "CANCELLED"}), "cancelled")

    def test_late_completion_after_cancel_remains_traceable(self):
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))
        client.cancel = lambda _request_id: {"status": "CANCELLATION_REQUESTED"}
        client.status = lambda _request_id: {"status": "COMPLETED"}
        client.result = lambda _request_id: {
            "images": [{"url": "https://cdn.example/late.png"}]
        }

        result = client.wait_for_result(
            "req-123",
            timeout_seconds=10,
            poll_interval_seconds=0,
            is_cancelled=lambda: True,
        )

        self.assertEqual(result["status"], "completed_after_cancel")
        self.assertEqual(result["request_id"], "req-123")

    def test_config_bounds_retry_policy(self):
        with self.assertRaises(FalProviderError):
            FalConfig(
                api_key="fal-secret",
                model_id="fal-ai/flux/schnell",
                max_retries=4,
            ).validate()

    def test_task_journal_persists_only_resumable_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = FalTaskJournal(f"{temp}/fal-tasks.json")
            journal.upsert("req-123", "generation", "fal-ai/flux/schnell", "queued")
            journal.upsert("req-123", "generation", "fal-ai/flux/schnell", "completed")
            self.assertEqual(journal.pending(), ())
            payload = open(f"{temp}/fal-tasks.json", encoding="utf-8").read()
            self.assertNotIn("secret", payload.lower())
            self.assertIn("req-123", payload)

    def test_task_journal_round_trips_provider_lifecycle_urls(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = FalTaskJournal(f"{temp}/fal-tasks.json")
            journal.upsert(
                "req-routes",
                "generation",
                "fal-ai/flux/schnell",
                "queued",
                status_url="https://queue.fal.run/custom/poll/req-routes",
                response_url="https://queue.fal.run/custom/result/req-routes",
                cancel_url="https://queue.fal.run/custom/cancel/req-routes",
            )

            record = journal.pending()[0]
            self.assertEqual(
                record.status_url,
                "https://queue.fal.run/custom/poll/req-routes",
            )
            self.assertEqual(
                record.response_url,
                "https://queue.fal.run/custom/result/req-routes",
            )
            self.assertEqual(
                record.cancel_url,
                "https://queue.fal.run/custom/cancel/req-routes",
            )

    def test_completed_status_is_not_emitted_until_result_is_fetched(self):
        client = FalClient(
            FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell")
        )
        client.status = lambda _request_id: {"status": "COMPLETED"}
        client.result = lambda _request_id: (_ for _ in ()).throw(
            FalProviderError("temporary result outage")
        )
        statuses = []

        with self.assertRaisesRegex(FalProviderError, "temporary result outage"):
            client.wait_for_result(
                "req-result-pending",
                timeout_seconds=1,
                poll_interval_seconds=0,
                on_status=statuses.append,
            )

        self.assertNotIn("completed", statuses)

    def test_image_operation_is_not_completed_until_result_schema_is_valid(self):
        model_id = "fal-ai/bria/background/remove"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        client.submit_task = lambda _request: {"request_id": "req-invalid-result"}

        def invalid_result(_request_id, *, on_status, **_kwargs):
            on_status("completed")
            return {
                "request_id": "req-invalid-result",
                "status": "completed",
                "result": {},
            }

        client.wait_for_result = invalid_result
        statuses = []

        with self.assertRaises(FalProviderError):
            client.run_image_operation(
                "remove_background",
                "https://cdn.example/input.png",
                on_status=statuses.append,
            )

        self.assertNotIn("completed", statuses)

    def test_bria_upscale_submits_alpha_safe_fixed_2x_payload(self):
        model_id = "bria/upscale/creative"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        captured = {}

        def submit(request):
            captured.update(request.input_payload)
            return {"request_id": "req-bria-upscale"}

        client.submit_task = submit
        client.wait_for_result = lambda *_args, **_kwargs: {
            "request_id": "req-bria-upscale",
            "status": "completed",
            "result": {"image": {"url": "https://cdn.example/bria.png"}},
        }

        client.run_image_operation(
            "upscale",
            "https://cdn.example/input.png",
            model_id=model_id,
            scale=4,
        )

        self.assertEqual(
            captured,
            {
                "image_url": "https://cdn.example/input.png",
                "preserve_alpha": True,
            },
        )

    def test_bria_increase_resolution_submits_alpha_safe_png_payload(self):
        model_id = "bria/increase-resolution"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        captured = {}

        def submit(request):
            captured.update(request.input_payload)
            return {"request_id": "req-bria-increase"}

        client.submit_task = submit
        client.wait_for_result = lambda *_args, **_kwargs: {
            "request_id": "req-bria-increase",
            "status": "completed",
            "result": {"image": {"url": "https://cdn.example/bria-increase.png"}},
        }

        client.run_image_operation(
            "upscale",
            "https://cdn.example/input.png",
            model_id=model_id,
            scale=4,
        )

        self.assertEqual(
            captured,
            {
                "image_url": "https://cdn.example/input.png",
                "desired_increase": 4,
                "preserve_alpha": True,
                "output_type": "png",
            },
        )

    def test_bria_increase_resolution_normalizes_unsupported_scale(self):
        model_id = "bria/increase-resolution"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        captured = {}
        client.submit_task = lambda request: (
            captured.update(request.input_payload) or {"request_id": "req-bria-scale"}
        )
        client.wait_for_result = lambda *_args, **_kwargs: {
            "request_id": "req-bria-scale",
            "status": "completed",
            "result": {"image": {"url": "https://cdn.example/bria-scale.png"}},
        }

        client.run_image_operation(
            "upscale",
            "https://cdn.example/input.png",
            model_id=model_id,
            scale=3,
        )

        self.assertEqual(captured["desired_increase"], 4)

    def test_topaz_transparent_submits_png_payload(self):
        model_id = "topaz/upscale/image/transparent"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        captured = {}

        def submit(request):
            captured.update(request.input_payload)
            return {"request_id": "req-topaz-transparent"}

        client.submit_task = submit
        client.wait_for_result = lambda *_args, **_kwargs: {
            "request_id": "req-topaz-transparent",
            "status": "completed",
            "result": {"image": {"url": "https://cdn.example/topaz-transparent.png"}},
        }

        client.run_image_operation(
            "upscale",
            "https://cdn.example/input.png",
            model_id=model_id,
            scale=2,
        )

        self.assertEqual(
            captured,
            {
                "image_url": "https://cdn.example/input.png",
                "output_format": "png",
            },
        )

    def test_recraft_crisp_upscale_submits_documented_image_only_payload(self):
        model_id = "fal-ai/recraft/upscale/crisp"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        captured = {}

        def submit(request):
            captured.update(request.input_payload)
            return {"request_id": "req-recraft-upscale"}

        client.submit_task = submit
        client.wait_for_result = lambda *_args, **_kwargs: {
            "request_id": "req-recraft-upscale",
            "status": "completed",
            "result": {"image": {"url": "https://cdn.example/recraft.png"}},
        }

        client.run_image_operation(
            "upscale",
            "https://cdn.example/input.png",
            model_id=model_id,
            scale=2,
        )

        self.assertEqual(
            captured,
            {"image_url": "https://cdn.example/input.png"},
        )

    def test_topaz_precision_upscale_submits_documented_png_payload(self):
        model_id = "topaz/upscale/image/precision"
        client = FalClient(FalConfig(api_key="fal-secret", model_id=model_id))
        captured = {}

        def submit(request):
            captured.update(request.input_payload)
            return {"request_id": "req-topaz-upscale"}

        client.submit_task = submit
        client.wait_for_result = lambda *_args, **_kwargs: {
            "request_id": "req-topaz-upscale",
            "status": "completed",
            "result": {"image": {"url": "https://cdn.example/topaz.png"}},
        }

        client.run_image_operation(
            "upscale",
            "https://cdn.example/input.png",
            model_id=model_id,
            scale=4,
        )

        self.assertEqual(
            captured,
            {
                "image_url": "https://cdn.example/input.png",
                "model": "Standard V2",
                "upscale_factor": 4,
                "output_format": "png",
            },
        )

    def test_task_journal_does_not_recover_completed_after_cancel(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = FalTaskJournal(f"{temp}/fal-tasks.json")
            journal.upsert(
                "req-late",
                "generation",
                "fal-ai/flux/schnell",
                "completed_after_cancel",
            )

            self.assertEqual(journal.pending(), ())

    def test_task_journal_keeps_all_concurrent_request_updates(self):
        class SlowReadJournal(FalTaskJournal):
            def _read(self):
                records = super()._read()
                time.sleep(0.01)
                return records

        with tempfile.TemporaryDirectory() as temp:
            journal = SlowReadJournal(f"{temp}/fal-tasks.json")
            start = threading.Barrier(8)
            threads = []
            for index in range(8):
                thread = threading.Thread(
                    target=lambda item=index: (
                        start.wait(),
                        journal.upsert(
                            f"req-{item}",
                            "generation",
                            "fal-ai/flux/schnell",
                            "queued",
                        ),
                    )
                )
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

            self.assertEqual(
                {record.request_id for record in journal.pending()},
                {f"req-{index}" for index in range(8)},
            )

    def test_task_journal_synchronizes_separate_instances_for_same_path(self):
        class SlowReadJournal(FalTaskJournal):
            def _read(self):
                records = super()._read()
                time.sleep(0.01)
                return records

        with tempfile.TemporaryDirectory() as temp:
            journal_path = f"{temp}/shared-tasks.json"
            journals = [SlowReadJournal(journal_path), SlowReadJournal(journal_path)]
            start = threading.Barrier(8)
            threads = []
            for index in range(8):
                thread = threading.Thread(
                    target=lambda item=index: (
                        start.wait(),
                        journals[item % 2].upsert(
                            f"shared-{item}",
                            "generation",
                            "fal-ai/flux/schnell",
                            "queued",
                        ),
                    )
                )
                threads.append(thread)
                thread.start()
            for thread in threads:
                thread.join(timeout=2)
                self.assertFalse(thread.is_alive())

            self.assertEqual(
                {record.request_id for record in journals[0].pending()},
                {f"shared-{index}" for index in range(8)},
            )

    def test_task_journal_synchronizes_separate_processes_for_same_path(self):
        with tempfile.TemporaryDirectory() as temp:
            journal_path = f"{temp}/shared-process-tasks.json"
            context = multiprocessing.get_context("spawn")
            start = context.Barrier(2)
            processes = [
                context.Process(
                    target=_upsert_paid_task_in_process,
                    args=(journal_path, f"process-{index}", start),
                )
                for index in range(2)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(timeout=5)
                self.assertEqual(process.exitcode, 0)

            self.assertEqual(
                {record.request_id for record in FalTaskJournal(journal_path).pending()},
                {"process-0", "process-1"},
            )

    def test_hidden_journal_uses_a_single_dot_lock_name(self):
        with tempfile.TemporaryDirectory() as temp:
            journal_path = Path(temp) / ".vibix_fal_tasks.json"

            FalTaskJournal(journal_path).pending()

            self.assertTrue(
                journal_path.with_name(".vibix_fal_tasks.json.lock").is_file()
            )
            self.assertFalse(
                journal_path.with_name("..vibix_fal_tasks.json.lock").exists()
            )

    def test_task_journal_retains_new_pending_after_terminal_history_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            journal = FalTaskJournal(f"{temp}/fal-tasks.json")
            for index in range(1000):
                journal.upsert(
                    f"completed-{index}",
                    "generation",
                    "fal-ai/flux/schnell",
                    "completed",
                )

            journal.upsert(
                "paid-new",
                "generation",
                "fal-ai/flux/schnell",
                "queued",
            )

            self.assertEqual(
                {record.request_id for record in journal.pending()},
                {"paid-new"},
            )
            self.assertIsNotNone(journal.update_status("paid-new", "running"))


if __name__ == "__main__":
    unittest.main()
