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
from model_catalog import generation_provider_id


class ModelCatalogTests(unittest.TestCase):
    def test_requested_fal_text_models_are_visible_without_references(self):
        expected = {
            "fal-ai/recraft/v4/text-to-image": "Fal.ai — Recraft V4",
            "ideogram/v4/fast": "Fal.ai — Ideogram V4 Fast",
            "fal-ai/flux-2/klein/4b": "Fal.ai — FLUX.2 Klein 4B",
            "fal-ai/kling-image/o3/text-to-image": "Fal.ai — Kling O3 Image",
            "bria/fibo-gen-1.5/text-to-image": "Fal.ai — Bria Fibo Gen 1.5",
        }

        for model_id, label in expected.items():
            self.assertIn(model_id, VISIBLE_GENERATION_MODEL_IDS)
            self.assertEqual(model_spec(model_id).label, label)
            self.assertNotIn(model_id, REFERENCE_MODEL_SHORTLIST)

    def test_ideogram_models_are_visible_fal_generation_choices(self):
        for model_id in ("fal-ai/ideogram/v3", "fal-ai/ideogram/v3/generate-transparent"):
            self.assertIn(model_id, VISIBLE_GENERATION_MODEL_IDS)
            self.assertTrue(model_spec(model_id).label.startswith("Fal.ai — Ideogram"))

    def test_every_visible_model_has_an_explicit_provider_label(self):
        for model_id in VISIBLE_GENERATION_MODEL_IDS:
            label = model_spec(model_id).label
            expected_prefix = {"fal": "Fal.ai — ", "kie": "KIE — ", "atlascloud": "AtlasCloud — ", "piapi": "PiAPI — "}[generation_provider_id(model_id)]
            self.assertTrue(label.startswith(expected_prefix), label)

    def test_catalog_is_immutable_and_preserves_visible_snapshot(self):
        # A new model joins the catalog consciously, one at a time: 39 models with Midjourney
        # connected through PiAPI for the owner on 2026-10-30 (not verified live yet).
        self.assertEqual(len(GENERATION_MODELS), 39)
        self.assertEqual(len(VISIBLE_GENERATION_MODEL_IDS), 24)
        self.assertEqual(model_spec("gpt-image-2").resolutions, {"1K", "2K", "4K"})
        with self.assertRaises(TypeError):
            MODEL_SPECS["new-model"] = model_spec("gpt-image-2")
        for model_id in VISIBLE_GENERATION_MODEL_IDS:
            spec = model_spec(model_id)
            self.assertEqual(spec.model_id, model_id)
            if model_id not in {"fal-ai/flux/schnell", "atlascloud/gpt-image-2.5-flare", "piapi/gpt-image-2.5-flare", "atlascloud/gpt-image-2.5-sunburst", "piapi/gpt-image-2.5-sunburst", "piapi/gpt-image-2.5"}:
                self.assertIsNotNone(spec.pricing)
            self.assertIsInstance(spec.ratios, frozenset)

    def test_unknown_model_is_an_explicit_error(self):
        with self.assertRaisesRegex(KeyError, "Unknown generation model"):
            model_spec("does-not-exist")

    def test_all_external_gpt25_models_are_reference_compatible(self):
        from model_catalog import MODEL_SPECS, reference_limits
        models = (
            "atlascloud/gpt-image-2.5-flare", "atlascloud/gpt-image-2.5-sunburst",
            "piapi/gpt-image-2.5-flare", "piapi/gpt-image-2.5-sunburst",
            "piapi/gpt-image-2.5",
        )
        for model in models:
            with self.subTest(model=model):
                self.assertTrue(MODEL_SPECS[model].reference_compatible_text)
                self.assertEqual(reference_limits(model), (16, 10 * 1024 * 1024))

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
