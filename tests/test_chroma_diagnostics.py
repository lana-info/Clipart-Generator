import unittest
from unittest.mock import patch

from PIL import Image

import chroma_key
from chroma_benchmark import load_golden_fixture, load_manifest
from chroma_diagnostics import diagnose_chroma_key


class ChromaDiagnosticsTests(unittest.TestCase):
    def source(self):
        image = Image.new("RGB", (32, 32), "blue")
        image.paste((200, 120, 90), (8, 8, 24, 24))
        return image

    def test_trace_matches_untraced_engine_on_all_independent_goldens(self):
        manifest = load_manifest("benchmarks/chroma/manifest.json")
        for case in manifest["cases"]:
            fixture = load_golden_fixture(manifest, case)
            truth = fixture.expected_foreground.convert("RGBA")
            truth.putalpha(fixture.expected_mask)
            source_before = fixture.input_image.tobytes()
            with self.subTest(case=fixture.case_id):
                report, result = diagnose_chroma_key(
                    fixture.input_image, fixture.key_color, truth=truth,
                )
                expected = chroma_key.remove_chroma_key_automatic(
                    fixture.input_image, fixture.key_color, subject_profile="opaque_clipart",
                )
                self.assertEqual(result.tobytes(), expected.tobytes())
                self.assertEqual(source_before, fixture.input_image.tobytes())
                self.assertEqual(report["status"], "processed")
                stages = report["stages"]
                self.assertEqual([item["stage"] for item in stages], [
                    "precise_result", "opaque_spill", "source_rgb_restore",
                ])
                self.assertTrue(all("quality" in item for item in stages))
                self.assertTrue(all(item["changed_alpha_pixels"] == 0 for item in stages[1:]))

    def test_no_truth_means_no_quality_claim(self):
        report, result = diagnose_chroma_key(self.source(), "blue")
        self.assertIsNotNone(result)
        self.assertEqual(report["quality_status"], "not_evaluated")
        self.assertTrue(all("quality" not in stage for stage in report["stages"]))
        self.assertNotIn("path", str(report))

    def test_legacy_keeps_its_translucent_stage(self):
        report, _ = diagnose_chroma_key(self.source(), "blue", subject_profile="legacy")
        self.assertEqual([s["stage"] for s in report["stages"]], [
            "precise_result", "opaque_spill", "translucent_complement", "source_rgb_restore",
        ])

    def test_trace_rejects_oversize_before_running_engine(self):
        with patch("chroma_diagnostics.remove_chroma_key_automatic") as engine:
            with self.assertRaises(ValueError):
                diagnose_chroma_key(self.source(), "blue", max_pixels=10)
            engine.assert_not_called()

    def test_mismatched_truth_is_rejected_before_engine(self):
        with patch("chroma_diagnostics.remove_chroma_key_automatic") as engine:
            with self.assertRaises(ValueError):
                diagnose_chroma_key(self.source(), "blue", truth=Image.new("RGBA", (1, 1)))
            engine.assert_not_called()

    def test_ambiguous_background_has_safe_reason_not_fake_success(self):
        report, result = diagnose_chroma_key(Image.new("RGB", (32, 32), "red"), "blue")
        self.assertIsNone(result)
        self.assertEqual(report["status"], "review")
        self.assertEqual(report["reason"], "ChromaKeyAmbiguousError")
        self.assertEqual(report["stages"], [])

    def test_observer_cannot_modify_pipeline_pixels(self):
        source = self.source()
        expected = chroma_key.remove_chroma_key_automatic(source)
        def observer(stage, snapshot):
            snapshot.paste((255, 0, 255, 0), (0, 0, *snapshot.size))
        actual = chroma_key.remove_chroma_key_automatic(source, stage_observer=observer)
        self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_fallback_trace_reports_only_completed_pixel_stages(self):
        for profile in ("legacy", "opaque_clipart"):
            with self.subTest(profile=profile), patch(
                "chroma_key._remove_chroma_key_precise",
                side_effect=chroma_key.ChromaKeyAmbiguousError("private details"),
            ):
                report, result = diagnose_chroma_key(self.source(), "blue", subject_profile=profile)
            self.assertIsNotNone(result)
            expected = ["staged_result", "opaque_spill"]
            if profile == "legacy":
                expected.append("translucent_complement")
            expected.append("source_rgb_restore")
            self.assertEqual([s["stage"] for s in report["stages"]], expected)
            self.assertNotIn("private details", str(report))


if __name__ == "__main__":
    unittest.main()
