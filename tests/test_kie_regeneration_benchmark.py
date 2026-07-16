import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from scripts import run_kie_regeneration_benchmark as benchmark


class KieRegenerationBenchmarkTests(unittest.TestCase):
    def test_flux_fallback_keeps_the_provider_safety_checker_enabled(self):
        flux_input = benchmark.MODEL_CONFIG["flux-2/pro-image-to-image"]["input"]
        self.assertIs(flux_input["nsfw_checker"], True)

    def test_model_cost_snapshots_include_credits(self):
        self.assertEqual(benchmark.MODEL_CONFIG["gpt-image-2-image-to-image"]["listed_credits"], 6)
        self.assertEqual(benchmark.MODEL_CONFIG["flux-2/pro-image-to-image"]["listed_credits"], 5)

    def test_fixture_covers_required_classes_and_has_real_alpha(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task39-fixture-") as temp_dir:
            temp_path = Path(temp_dir)
            photo = temp_path / "photo.png"
            face = temp_path / "face.png"
            Image.new("RGB", (480, 320), (80, 130, 170)).save(photo)
            Image.new("RGB", (320, 480), (210, 165, 145)).save(face)

            board, fixture = benchmark.build_fixture_board(photo, face)

            self.assertEqual(board.size, (1024, 1024))
            self.assertEqual(board.mode, "RGBA")
            self.assertEqual(
                set(fixture["classes"]),
                {"photo", "face", "illustration", "clipart", "text_heavy"},
            )
            self.assertGreater(int(fixture["input_transparent_pixels"]), 0)
            self.assertTrue(np.any(np.asarray(board.getchannel("A")) < 255))

    def test_exhausted_budget_blocks_live_generation_globally(self):
        self.assertEqual(
            benchmark.TASK33_PRIOR_PROVIDER_ATTEMPTS
            + benchmark.TASK39_COMPLETED_GENERATION_ATTEMPTS,
            benchmark.TOTAL_AUTHORIZED_PROVIDER_ATTEMPTS,
        )
        with self.assertRaisesRegex(RuntimeError, "budget is exhausted"):
            benchmark.ensure_live_generation_budget()

    def test_analysis_never_claims_pixel_marker_removal_without_evidence(self):
        with tempfile.TemporaryDirectory(prefix="clipart-task39-analysis-") as temp_dir:
            temp_path = Path(temp_dir)
            photo = temp_path / "photo.png"
            face = temp_path / "face.png"
            source = temp_path / "source.png"
            result = temp_path / "result.png"
            comparison = temp_path / "comparison.png"
            Image.new("RGB", (480, 320), (80, 130, 170)).save(photo)
            Image.new("RGB", (320, 480), (210, 165, 145)).save(face)
            board, fixture = benchmark.build_fixture_board(photo, face)
            board.save(source)
            board.convert("RGB").save(result)

            metrics = benchmark.analyze_result(source, result, fixture, comparison)

            synthid = metrics["pixel_watermark_status"]["synthid"]
            self.assertEqual(synthid["processing"]["status"], "succeeded")
            self.assertEqual(synthid["pixel_evidence"]["status"], "not_verified")
            self.assertEqual(synthid["pixel_evidence"]["removal_claim"], "not_claimed")
            self.assertFalse(metrics["provider_output"]["has_alpha"])
            self.assertTrue(comparison.is_file())


if __name__ == "__main__":
    unittest.main()
