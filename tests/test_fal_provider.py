import json
import unittest
from unittest.mock import patch

from fal_provider import (
    FalClient,
    FalConfig,
    FalProviderError,
    fal_image_input,
    fal_image_url,
    fal_status_kind,
)
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
    def test_config_requires_key_and_safe_model_identifier(self):
        with self.assertRaises(FalProviderError):
            FalConfig(api_key="", model_id="fal-ai/flux/schnell").validate()
        with self.assertRaises(FalProviderError):
            FalConfig(api_key="secret", model_id="https://evil.example/model").validate()
        self.assertNotIn(
            "fal-secret",
            repr(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell")),
        )

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

    def test_submit_task_uses_shared_provider_contract(self):
        client = FalClient(FalConfig(api_key="fal-secret", model_id="fal-ai/flux/schnell"))
        request = ProviderTaskRequest("fal", "generation", "fal-ai/flux/schnell", {"prompt": "a fox"})
        client.submit = lambda arguments: {"request_id": "req-123", "arguments": dict(arguments)}

        self.assertEqual(client.submit_task(request)["request_id"], "req-123")


if __name__ == "__main__":
    unittest.main()
