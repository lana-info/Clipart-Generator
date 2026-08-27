import unittest

from fal_model_catalog import (
    FAL_ENDPOINT_PROFILES,
    fal_endpoint_profile,
    fal_endpoint_profiles,
)


class FalModelCatalogTests(unittest.TestCase):
    def test_initial_profiles_are_operation_specific(self):
        self.assertEqual(
            {profile.operation for profile in FAL_ENDPOINT_PROFILES},
            {"generation", "remove_background", "upscale"},
        )
        self.assertEqual(
            fal_endpoint_profile("fal-ai/bria/background/remove", "remove_background").output_formats,
            ("png",),
        )
        self.assertIsNone(fal_endpoint_profile("fal-ai/esrgan", "upscale").preserves_alpha)

    def test_profiles_can_be_filtered_without_exposing_unknown_models(self):
        self.assertEqual(
            [profile.model_id for profile in fal_endpoint_profiles("upscale")],
            ["fal-ai/esrgan"],
        )
        with self.assertRaises(KeyError):
            fal_endpoint_profile("fal-ai/unknown", "generation")

    def test_background_profiles_expose_model_specific_settings(self):
        profiles = fal_endpoint_profiles("remove_background")
        self.assertEqual(
            [profile.model_id for profile in profiles],
            [
                "fal-ai/bria/background/remove",
                "fal-ai/birefnet",
                "fal-ai/imageutils/rembg",
            ],
        )
        self.assertIn("refine_foreground", profiles[1].parameter_names)
        self.assertIn("crop_to_bbox", profiles[2].parameter_names)


if __name__ == "__main__":
    unittest.main()
