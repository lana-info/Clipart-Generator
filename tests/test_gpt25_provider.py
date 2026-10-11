"""Offline contract and paid-request recovery tests for AtlasCloud and PiAPI."""
import os
import tempfile
import unittest
from unittest.mock import patch

from api_credentials import EnvCredentialStore, SECRET_CONFIG_KEYS
from gpt25_provider import (
    Gpt25ProviderError,
    generation_payload,
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
