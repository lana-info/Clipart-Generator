import unittest

from model_catalog import (
    GENERATION_MODELS,
    MODEL_SPECS,
    REFERENCE_MODEL_SHORTLIST,
    VISIBLE_GENERATION_MODEL_IDS,
    model_spec,
    resolve_generation_endpoint,
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


if __name__ == "__main__":
    unittest.main()
