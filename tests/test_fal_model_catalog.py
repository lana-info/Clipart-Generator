import unittest

from fal_model_catalog import (
    FAL_ENDPOINT_PROFILES,
    fal_generation_payload,
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
        self.assertTrue(
            fal_endpoint_profile("bria/upscale/creative", "upscale").preserves_alpha
        )
        self.assertTrue(
            fal_endpoint_profile("bria/increase-resolution", "upscale").preserves_alpha
        )
        self.assertTrue(
            fal_endpoint_profile(
                "topaz/upscale/image/transparent", "upscale"
            ).preserves_alpha
        )
        self.assertFalse(
            fal_endpoint_profile(
                "topaz/upscale/image/precision", "upscale"
            ).preserves_alpha
        )
        recraft = fal_endpoint_profile("fal-ai/recraft/upscale/crisp", "upscale")
        self.assertFalse(recraft.preserves_alpha)
        self.assertEqual(recraft.output_formats, ("png",))

    def test_profiles_can_be_filtered_without_exposing_unknown_models(self):
        self.assertEqual(
            [profile.model_id for profile in fal_endpoint_profiles("upscale")],
            [
                "bria/upscale/creative",
                "bria/increase-resolution",
                "topaz/upscale/image/precision",
                "topaz/upscale/image/transparent",
                "fal-ai/recraft/upscale/crisp",
            ],
        )
        with self.assertRaises(KeyError):
            fal_endpoint_profile("fal-ai/unknown", "generation")

    def test_requested_generation_endpoints_have_explicit_fal_profiles(self):
        for model_id in (
            "fal-ai/recraft/v4/text-to-image",
            "ideogram/v4/fast",
            "fal-ai/flux-2/klein/4b",
            "fal-ai/kling-image/o3/text-to-image",
            "bria/fibo-gen-1.5/text-to-image",
        ):
            self.assertEqual(
                fal_endpoint_profile(model_id, "generation").operation,
                "generation",
            )

    def test_generation_payload_uses_each_endpoint_size_parameter(self):
        self.assertEqual(
            fal_generation_payload(
                "fal-ai/recraft/v4/text-to-image", "fox", "3:4", "1K"
            ),
            {"prompt": "fox", "image_size": "portrait_4_3"},
        )
        self.assertEqual(
            fal_generation_payload(
                "fal-ai/kling-image/o3/text-to-image", "fox", "3:4", "2K"
            ),
            {"prompt": "fox", "aspect_ratio": "3:4", "resolution": "2K"},
        )
        self.assertEqual(
            fal_generation_payload(
                "bria/fibo-gen-1.5/text-to-image", "fox", "4:5", "4MP"
            ),
            {"prompt": "fox", "aspect_ratio": "4:5", "resolution": "4MP"},
        )

    def test_background_profiles_expose_model_specific_settings(self):
        profiles = fal_endpoint_profiles("remove_background")
        self.assertEqual(
            [profile.model_id for profile in profiles],
            [
                "fal-ai/bria/background/remove",
                "fal-ai/birefnet/v2",
                "fal-ai/imageutils/rembg",
                "fal-ai/ideogram/remove-background",
                "fal-ai/pixelcut/background-removal",
            ],
        )
        self.assertIn("refine_foreground", profiles[1].parameter_names)
        self.assertIn("crop_to_bbox", profiles[2].parameter_names)


if __name__ == "__main__":
    unittest.main()
