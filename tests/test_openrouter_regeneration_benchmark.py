import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image

from scripts import run_openrouter_regeneration_benchmark as benchmark


class OpenRouterRegenerationBenchmarkTests(unittest.TestCase):
    def test_candidate_snapshot_and_fixture_match_task39_rubric(self):
        self.assertEqual(benchmark.MODEL_ID, "recraft/recraft-v4.1-utility")
        self.assertEqual(benchmark.LISTED_COST_USD, 0.035)
        self.assertEqual(
            benchmark.CANDIDATE_SNAPSHOT["provider_watermark_policy"],
            "not_documented",
        )
        with tempfile.TemporaryDirectory(prefix="clipart-task40-fixture-") as temp_dir:
            root = Path(temp_dir)
            photo = root / "photo.png"
            face = root / "face.png"
            Image.new("RGB", (480, 320), (80, 130, 170)).save(photo)
            Image.new("RGB", (320, 480), (210, 165, 145)).save(face)

            board, fixture = benchmark.common.build_fixture_board(photo, face)

            self.assertEqual(board.size, (1024, 1024))
            self.assertEqual(
                set(fixture["classes"]),
                {"photo", "face", "illustration", "clipart", "text_heavy"},
            )
            self.assertGreater(fixture["input_transparent_pixels"], 0)
            self.assertTrue(np.any(np.asarray(board.getchannel("A")) < 255))

    def test_closed_live_gate_does_not_reserve_or_call_network(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task40-closed-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            Image.new("RGBA", (16, 16), (20, 30, 40, 255)).save(source)
            with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-secret"}), mock.patch.object(
                benchmark.urllib.request, "urlopen"
            ) as urlopen:
                with self.assertRaisesRegex(
                    benchmark.OpenRouterBenchmarkError, "pending separate user authorization"
                ):
                    benchmark.run_live_generation(source, output, state_path=state)

            self.assertFalse(state.exists())
            self.assertFalse(output.exists())
            urlopen.assert_not_called()

    def test_global_one_shot_reservation_blocks_a_second_process_like_call(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task40-state-") as temp_dir:
            state = Path(temp_dir) / "shared" / "state.json"

            self.assertEqual(
                benchmark.reserve_live_attempt(state, authorized_attempts=1),
                1,
            )
            with self.assertRaisesRegex(
                benchmark.OpenRouterBenchmarkError, "budget is exhausted"
            ):
                benchmark.reserve_live_attempt(state, authorized_attempts=1)

            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["used_attempts"], 1)

    def test_missing_key_does_not_consume_an_authorized_attempt(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task40-no-key-") as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            output = root / "output.provider"
            state = root / "state.json"
            Image.new("RGBA", (16, 16), (20, 30, 40, 255)).save(source)
            with mock.patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(
                    benchmark.OpenRouterBenchmarkError, "OPENROUTER_API_KEY"
                ):
                    benchmark.run_live_generation(
                        source,
                        output,
                        state_path=state,
                        authorized_attempts=1,
                    )
            self.assertFalse(state.exists())

    def test_response_parser_keeps_only_validated_image_and_cost(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task40-response-") as temp_dir:
            image_path = Path(temp_dir) / "image.png"
            Image.new("RGB", (16, 16), (120, 80, 40)).save(image_path)
            secret = "openrouter-secret-must-not-leak"
            response = {
                "data": [
                    {
                        "b64_json": base64.b64encode(image_path.read_bytes()).decode("ascii"),
                        "media_type": "image/png",
                        "provider_debug": secret,
                    }
                ],
                "usage": {"cost": 0.035, "debug": secret},
                "prompt": secret,
            }

            parsed = benchmark.parse_provider_response(response)
            report = {
                "billed_cost_usd_response": parsed["billed_cost_usd"],
                "response_media_type": parsed["media_type"],
            }
            serialized = benchmark.serialize_report(report, api_key=secret)

            self.assertEqual(parsed["provider_bytes"], image_path.read_bytes())
            self.assertEqual(parsed["billed_cost_usd"], 0.035)
            self.assertNotIn(secret, serialized)
            self.assertNotIn("provider_debug", parsed)

    def test_existing_result_analysis_cannot_claim_watermark_removal(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task40-analysis-") as temp_dir:
            root = Path(temp_dir)
            photo = root / "photo.png"
            face = root / "face.png"
            source = root / "source.png"
            result = root / "result.png"
            comparison = root / "comparison.png"
            Image.new("RGB", (480, 320), (80, 130, 170)).save(photo)
            Image.new("RGB", (320, 480), (210, 165, 145)).save(face)
            board, fixture = benchmark.common.build_fixture_board(photo, face)
            board.save(source)
            board.convert("RGB").save(result)

            metrics = benchmark.common.analyze_result(source, result, fixture, comparison)

            synthid = metrics["pixel_watermark_status"]["synthid"]
            self.assertEqual(synthid["pixel_evidence"]["status"], "not_verified")
            self.assertEqual(synthid["pixel_evidence"]["removal_claim"], "not_claimed")
            self.assertTrue(comparison.is_file())


if __name__ == "__main__":
    unittest.main()
