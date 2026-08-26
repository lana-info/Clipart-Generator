import unittest

from model_catalog import (
    GENERATION_MODELS,
    MODEL_SPECS,
    REFERENCE_MODEL_SHORTLIST,
    VISIBLE_GENERATION_MODEL_IDS,
    model_spec,
    ratios_for_mode,
    resolve_generation_endpoint,
    validate_generation_contract,
)


class ModelCatalogTests(unittest.TestCase):
    def test_catalog_is_immutable_and_preserves_visible_snapshot(self):
        self.assertEqual(len(GENERATION_MODELS), 25)
        self.assertEqual(len(VISIBLE_GENERATION_MODEL_IDS), 10)
        self.assertEqual(model_spec("gpt-image-2").resolutions, {"1K", "2K", "4K"})
        with self.assertRaises(TypeError):
            MODEL_SPECS["new-model"] = model_spec("gpt-image-2")
        for model_id in VISIBLE_GENERATION_MODEL_IDS:
            spec = model_spec(model_id)
            self.assertEqual(spec.model_id, model_id)
            self.assertIsNotNone(spec.pricing)
            self.assertIsInstance(spec.ratios, frozenset)

    def test_unknown_model_is_an_explicit_error(self):
        with self.assertRaisesRegex(KeyError, "Unknown generation model"):
            model_spec("does-not-exist")

    def test_gpt_image_two_uses_distinct_reference_endpoints(self):
        self.assertEqual(
            resolve_generation_endpoint("gpt-image-2"),
            "gpt-image-2-text-to-image",
        )
        self.assertEqual(
            resolve_generation_endpoint("gpt-image-2", has_references=True),
            "gpt-image-2-image-to-image",
        )
        self.assertIn("gpt-image-2", REFERENCE_MODEL_SHORTLIST)

    def test_qwen_two_uses_distinct_documented_endpoints(self):
        self.assertEqual(
            resolve_generation_endpoint("qwen-image-2"),
            "qwen2/text-to-image",
        )
        self.assertEqual(
            resolve_generation_endpoint("qwen-image-2", has_references=True),
            "qwen2/image-edit",
        )

    def test_mode_specific_ratios_match_documented_contracts(self):
        self.assertEqual(
            ratios_for_mode("qwen-image-2", has_references=False),
            {"1:1", "3:4", "4:3", "9:16", "16:9"},
        )
        self.assertEqual(
            ratios_for_mode("qwen-image-2", has_references=True),
            {"1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"},
        )
        self.assertNotIn(
            "auto",
            ratios_for_mode("flux-2/pro-text-to-image", has_references=False),
        )
        self.assertIn(
            "auto",
            ratios_for_mode("flux-2/pro-image-to-image", has_references=True),
        )

    def test_gpt_image_two_resolution_ratio_rules_are_checked_locally(self):
        with self.assertRaisesRegex(ValueError, "4K.*1:1|1:1.*4K"):
            validate_generation_contract(
                "gpt-image-2",
                has_references=False,
                ratio="1:1",
                resolution="4K",
                prompt="valid prompt",
            )
        with self.assertRaisesRegex(ValueError, "auto.*1K|1K.*auto"):
            validate_generation_contract(
                "gpt-image-2",
                has_references=False,
                ratio="auto",
                resolution="2K",
                prompt="valid prompt",
            )
        with self.assertRaisesRegex(ValueError, "5:4.*1K|1K.*5:4"):
            validate_generation_contract(
                "gpt-image-2",
                has_references=True,
                ratio="5:4",
                resolution="2K",
                prompt="valid prompt",
                reference_count=1,
            )

    def test_flux_prompt_and_model_reference_limits_are_checked_locally(self):
        with self.assertRaisesRegex(ValueError, "3.*5000"):
            validate_generation_contract(
                "flux-2/pro-text-to-image",
                has_references=False,
                ratio="1:1",
                resolution="1K",
                prompt="x",
            )
        with self.assertRaisesRegex(ValueError, "1 референс"):
            validate_generation_contract(
                "qwen-image-2",
                has_references=True,
                ratio="1:1",
                resolution="1K",
                prompt="valid prompt",
                reference_count=2,
            )
        with self.assertRaisesRegex(ValueError, "10 МБ"):
            validate_generation_contract(
                "qwen-image-2",
                has_references=True,
                ratio="1:1",
                resolution="1K",
                prompt="valid prompt",
                reference_count=1,
                reference_sizes=(10 * 1024 * 1024 + 1,),
            )


if __name__ == "__main__":
    unittest.main()
