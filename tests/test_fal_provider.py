import json
import tempfile
import unittest
import urllib.error
from io import BytesIO
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


if __name__ == "__main__":
    unittest.main()
