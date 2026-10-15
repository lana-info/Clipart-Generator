"""Offline contract and paid-request recovery tests for AtlasCloud and PiAPI."""
import os
import tempfile
import unittest
from unittest.mock import patch

from api_credentials import EnvCredentialStore, SECRET_CONFIG_KEYS
from gpt25_provider import (
    Gpt25ProviderError,
    failure_reason,
    generation_payload,
    piapi_edit_multipart_body,
    prepare_reference_inputs,
    submit_url,
    provider_for_model,
    request_headers,
    status_url,
    submitted_task_id,
    task_result,
)
from model_catalog import generation_provider_id
from runtime_settings import build_runtime_settings


ATLAS = "atlascloud/gpt-image-2.5-flare"
PIAPI = "piapi/gpt-image-2.5-flare"
IMAGE = "https://images.example.org/render.png"


class Gpt25ContractTests(unittest.TestCase):
    def test_models_route_to_independent_providers(self):
        self.assertEqual(provider_for_model(ATLAS), "atlascloud")
        self.assertEqual(provider_for_model(PIAPI), "piapi")
        self.assertEqual(generation_provider_id("gpt-image-2"), "kie")

    def test_atlas_payload_size_and_async_mode(self):
        payload = generation_payload(ATLAS, "cat", "3:2", "1K")
        self.assertEqual(payload["model"], "openai/gpt-image-2.5-flare/text-to-image")
        self.assertEqual(payload["size"], "1536x1024")
        self.assertEqual(payload["quality"], "medium")
        self.assertIs(payload["enable_sync_mode"], False)
        self.assertIs(payload["enable_base64_output"], False)

    def test_piapi_payload_is_async_url(self):
        payload = generation_payload(PIAPI, "cat", "2:3", "1K")
        self.assertEqual(payload["model"], "gpt-image-2.5-flare")
        self.assertEqual(payload["size"], "1024x1536")
        self.assertEqual(payload["response_format"], "url")
        self.assertEqual(payload["n"], 1)

    def test_unsupported_contract_rejected_before_paid_call(self):
        with self.assertRaises(Gpt25ProviderError):
            generation_payload(ATLAS, "cat", "1:1", "4K")
        with self.assertRaises(Gpt25ProviderError):
            generation_payload(PIAPI, "cat", "16:9", "1K")

    def test_reference_edit_payloads_route_to_correct_endpoints(self):
        ref = "https://images.example.org/reference.png"
        for model in ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst"):
            atlas = generation_payload(f"atlascloud/{model}", "Change the style", "1:1", "1K", [ref])
            self.assertEqual(atlas["model"], f"openai/{model}/edit")
            self.assertEqual(atlas["images"], [ref])
            piapi = generation_payload(f"piapi/{model}", "Change the style", "1:1", "1K", [ref])
            self.assertEqual(piapi["model"], model)
            self.assertEqual(piapi["image"], ref)
        self.assertTrue(submit_url("piapi", has_references=True).endswith("/images/edits/async"))
        self.assertTrue(submit_url("piapi").endswith("/images/generations/async"))
        budget = generation_payload("piapi/gpt-image-2.5", "Change it", "auto", "auto", [ref, ref])
        self.assertEqual(budget["image"], [ref, ref])

    def test_piapi_multi_reference_edit_uses_repeated_multipart_image_fields(self):
        import base64
        image_a = b"\x89PNG\r\n\x1a\nfirst-image"
        image_b = b"\x89PNG\r\n\x1a\nsecond-image"
        payload = generation_payload(
            "piapi/gpt-image-2.5", "Use both references", "auto", "auto",
            [f"data:image/png;base64,{base64.b64encode(image_a).decode()}",
             f"data:image/png;base64,{base64.b64encode(image_b).decode()}"],
        )
        body, content_type = piapi_edit_multipart_body(payload)
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertEqual(body.count(b'name="image[]"; filename='), 2)
        self.assertIn(b'name="prompt"', body)
        self.assertIn(image_a, body)
        self.assertIn(image_b, body)
        self.assertNotIn(b"data:image/png;base64,", body)

    def test_piapi_single_reference_edit_uses_image_file_field(self):
        import base64
        image = b"\x89PNG\r\n\x1a\none-image"
        payload = generation_payload(
            "piapi/gpt-image-2.5-flare", "Edit this", "1:1", "1K",
            [f"data:image/png;base64,{base64.b64encode(image).decode()}"]
        )
        body, _ = piapi_edit_multipart_body(payload)
        self.assertIn(b'name="image"; filename="reference-1.png"', body)
        self.assertNotIn(b'name="image[]"', body)

    def test_reference_preflight_checks_local_bytes_and_safe_transport(self):
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "private-name.png"
            file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"small-test-image")
            values = prepare_reference_inputs([str(file)])
            self.assertEqual(len(values), 1)
            self.assertTrue(values[0].startswith("data:image/png;base64,"))
            self.assertNotIn(str(file), values[0])
            self.assertNotIn(file.name, str(generation_payload(ATLAS, "cat", "1:1", "1K", values)))
            file.write_bytes(b"not an image")
            with self.assertRaisesRegex(Gpt25ProviderError, "PNG"):
                prepare_reference_inputs([str(file)])
        for invalid in ("http://images.example.org/a.png", "file:///etc/passwd", "ftp://example.org/img.png"):
            with self.assertRaises(Gpt25ProviderError):
                prepare_reference_inputs([invalid])
        with self.assertRaisesRegex(Gpt25ProviderError, "недоступ"):
            prepare_reference_inputs([r"C:\Users\owner\reference.png"])
        with self.assertRaisesRegex(Gpt25ProviderError, "16"):
            prepare_reference_inputs([IMAGE] * 17)

    def test_reference_edit_expiration_requires_exact_paid_retry_consent(self):
        import hashlib
        import json
        from pathlib import Path
        from fal_provider import FalTaskJournal
        from gpt25_recovery import expired_generation_retries
        with tempfile.TemporaryDirectory() as root:
            file = Path(root) / "reference.png"
            file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"image-content")
            settings = {
                "text_generation_model": "gpt-image-2",
                "reference_generation_model": PIAPI,
                "reference_generation_ratio": "1:1",
                "reference_generation_resolution": "1K",
            }
            entry = {"prompt": "Make a blue owl", "references": [str(file)]}
            payload = generation_payload(PIAPI, entry["prompt"], "1:1", "1K",
                                         prepare_reference_inputs(entry["references"]))
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True,
                         ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
            journal = FalTaskJournal(Path(root) / ".vibix_piapi_tasks.json")
            journal.upsert("expired_edit", "generation:1", PIAPI, "expired", input_fingerprint=digest)
            self.assertEqual(expired_generation_retries(root, settings, [entry]), ("piapi:expired_edit",))
            file.write_bytes(b"\x89PNG\r\n\x1a\n" + b"changed-content")
            self.assertEqual(expired_generation_retries(root, settings, [entry]), ())

    def test_auth_and_urls(self):
        self.assertEqual(request_headers("atlascloud", "abc")["Authorization"], "Bearer abc")
        self.assertEqual(request_headers("piapi", "abc")["X-API-KEY"], "abc")
        self.assertTrue(status_url("piapi", "task_11").endswith("/task/task_11"))
        with self.assertRaises(Gpt25ProviderError):
            status_url("piapi", "x?key=secret")

    def test_provider_responses(self):
        self.assertEqual(submitted_task_id("atlascloud", {"data":{"id":"pred_1"}}), "pred_1")
        self.assertEqual(submitted_task_id("piapi", {"task_id":"task_1"}), "task_1")
        self.assertEqual(task_result("atlascloud", {"data":{"status":"completed","outputs":[IMAGE]}}), ("completed", IMAGE))
        self.assertEqual(task_result("piapi", {"status":"completed","output":{"data":[{"url": IMAGE}]}}), ("completed", IMAGE))
        self.assertEqual(task_result("piapi", {"status":"pending"}), ("pending", None))
        with self.assertRaises(Gpt25ProviderError):
            task_result("piapi", {"status":"completed","output":{"data":[{"url":"http://bad"}]}})

    def test_unknown_or_deferred_status_keeps_polling_paid_task(self):
        # Right after an async submit PiAPI can answer with a bare error
        # envelope; it must never end the paid task early.
        for response in (
            {"status": "waiting"},
            {"task_id": "task_1", "status": "new-provider-word"},
            {"task_id": "task_1", "error": "task not found"},
            {"error": "A task ID is required."},
            {},
        ):
            self.assertEqual(task_result("piapi", response), ("pending", None), response)
        for data in ({"status": "waiting"}, {"status": "unknown-word"}, {}):
            self.assertEqual(task_result("atlascloud", {"data": data}), ("pending", None), data)
        # Truly malformed answers still fail loudly.
        self.assertRaises(Gpt25ProviderError, task_result, "piapi", "oops")
        self.assertRaises(Gpt25ProviderError, task_result, "atlascloud", {"data": None})

    def test_failure_reason_extracts_provider_error_text(self):
        response = {"status": "failed", "error": {"code": 10000, "message": "Internal error."},
                    "output": {"error_body": {"error": {
                        "message": "response handler failed: Our servers are currently overloaded.",
                        "type": "upstream_error", "upstream_status": 500}}}}
        reason = failure_reason("piapi", response)
        self.assertIsNotNone(reason)
        self.assertIn("overloaded", reason)
        self.assertIn("upstream 500", reason)
        self.assertNotIn("\n", reason)
        self.assertLessEqual(len(reason), 220)
        self.assertIsNone(failure_reason("piapi", {"status": "failed"}))
        self.assertIsNone(failure_reason("piapi", {"status": "completed"}))
        self.assertIsNone(failure_reason("atlascloud", response))
        top = {"status": "failed", "error": {"code": 10000, "message": "Provider refused."}}
        self.assertEqual(failure_reason("piapi", top), "Provider refused")

    def test_keys_are_separated_from_regular_settings(self):
        self.assertIn("atlascloud_api_key", SECRET_CONFIG_KEYS)
        self.assertIn("piapi_api_key", SECRET_CONFIG_KEYS)
        with tempfile.TemporaryDirectory() as root:
            store = EnvCredentialStore(os.path.join(root, ".env"))
            store.save({"atlascloud_api_key":"atlas-test", "piapi_api_key":"pi-test"})
            self.assertEqual(store.load()["piapi_api_key"], "pi-test")
            self.assertEqual(store.load()["atlascloud_api_key"], "atlas-test")
        runtime = build_runtime_settings({}, {"atlascloud_api_key":"a", "piapi_api_key":"p"})
        self.assertEqual(runtime["atlascloud_api_key"], "a")
        self.assertEqual(runtime["piapi_api_key"], "p")


if __name__ == "__main__":
    unittest.main()
