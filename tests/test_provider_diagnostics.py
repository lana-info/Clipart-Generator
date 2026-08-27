import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from provider_diagnostics import (
    build_provider_event,
    count_provider_results,
    inspect_image_metadata,
    safe_provider_message,
)


SECRET = "sk-live-diagnostic-secret123"
PROMPT = "private watercolor fox prompt"
SIGNED_URL = "https://files.example/result.png?token=private-token"


class ProviderDiagnosticsTests(unittest.TestCase):
    def test_image_metadata_contains_no_private_directory_or_pixels(self):
        with tempfile.TemporaryDirectory(prefix="private-diagnostic-") as temp:
            source = Path(temp) / "Лисёнок.png"
            Image.new("RGBA", (37, 21), (10, 20, 30, 40)).save(source)

            metadata = inspect_image_metadata(source)
            encoded = json.dumps(metadata, ensure_ascii=False)

            self.assertEqual(metadata["filename"], "Лисёнок.png")
            self.assertEqual(metadata["image_format"], "PNG")
            self.assertEqual(metadata["width"], 37)
            self.assertEqual(metadata["height"], 21)
            self.assertEqual(metadata["color_mode"], "RGBA")
            self.assertTrue(metadata["has_alpha"])
            self.assertGreater(metadata["input_bytes"], 0)
            self.assertNotIn(temp, encoded)
            self.assertNotIn("pixel", encoded.casefold())

    def test_event_builder_keeps_allowlisted_values_and_drops_private_values(self):
        event = build_provider_event(
            "provider_task_failed",
            provider="kie",
            model="recraft/crisp-upscale",
            stage="upscale_before",
            task="task-123",
            http_status=200,
            provider_state="fail",
            error_code="501",
            error_message=f"provider failed; api_key={SECRET}",
            elapsed_ms=1234,
            poll_attempt=3,
            prompt=PROMPT,
            request_headers={"Authorization": f"Bearer {SECRET}"},
            raw_response={"resultJson": SIGNED_URL},
            result_url=SIGNED_URL,
            private_path="C:\\Users\\Owner\\private.png",
        )
        encoded = json.dumps(event, ensure_ascii=False)

        self.assertEqual(event["event"], "provider_task_failed")
        self.assertEqual(event["provider"], "kie")
        self.assertEqual(event["task"], "task-123")
        self.assertEqual(event["http_status"], 200)
        self.assertEqual(event["poll_attempt"], 3)
        self.assertNotIn(SECRET, encoded)
        self.assertNotIn(PROMPT, encoded)
        self.assertNotIn(SIGNED_URL, encoded)
        self.assertNotIn("Authorization", encoded)
        self.assertNotIn("private.png", encoded)

    def test_unknown_event_is_reduced_to_safe_parse_failure(self):
        event = build_provider_event(
            "unknown_network_dump",
            provider="kie",
            raw_response=SIGNED_URL,
        )

        self.assertEqual(event["event"], "diagnostic_parse_failed")
        self.assertEqual(event["severity"], "warning")
        self.assertNotIn(SIGNED_URL, json.dumps(event))

    def test_provider_message_is_bounded_and_redacted(self):
        message = safe_provider_message(
            f"KIE failed api_key={SECRET} at C:\\Users\\Owner\\input.png " + "x" * 1000
        )

        self.assertLessEqual(len(message), 500)
        self.assertNotIn(SECRET, message)
        self.assertNotIn("C:\\Users\\Owner", message)
        self.assertIn("KIE failed", message)

    def test_provider_message_redacts_unc_and_posix_paths_with_spaces(self):
        message = safe_provider_message(
            "failed at /home/Jane Doe/Customer A/input.png; "
            r"mirror \\server\private share\Customer A\input.png"
        )

        self.assertNotIn("Jane Doe", message)
        self.assertNotIn("Customer A", message)
        self.assertNotIn("private share", message)
        self.assertNotIn("server", message)
        self.assertIn("input.png", message)

    def test_result_counter_understands_kie_json_without_returning_urls(self):
        result_json = json.dumps(
            {"resultUrls": [SIGNED_URL, "https://files.example/second.png?sig=secret"]}
        )

        self.assertEqual(count_provider_results(result_json), 2)
        self.assertEqual(count_provider_results({"resultUrls": ["one"]}), 1)
        self.assertEqual(count_provider_results("not-json"), 0)


if __name__ == "__main__":
    unittest.main()
