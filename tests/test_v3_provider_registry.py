from __future__ import annotations

import unittest

from chroma_key import KEY_COLORS
from v3_provider_registry import (
    CHROMA_KEY_COLOR_OPTIONS,
    KIE_REMOVE_BG_MODEL_OPTIONS,
    KIE_MODEL_OPTIONS,
    LOCAL_REMBG_MODEL_OPTIONS,
    LOCAL_REMBG_PROFILE_OPTIONS,
    known_provider_ids,
    processing_provider_options,
    provider_label,
    provider_preserves_alpha,
    provider_requires_api_key,
    provider_requires_cost,
    provider_requires_network,
    provider_spec,
    provider_supports_operation,
    provider_visible_controls,
    upscale_model_preserves_alpha,
)


class ProviderRegistryTests(unittest.TestCase):
    def test_known_provider_ids_and_specs(self) -> None:
        self.assertEqual(
            known_provider_ids(),
            ("fal", "kie", "photoroom", "local_rembg", "local_ben2", "local_chroma_key", "local_realesrgan"),
        )
        self.assertEqual(provider_label("kie"), "KIE")
        self.assertEqual(provider_label("photoroom"), "PhotoRoom")
        self.assertTrue(provider_spec("local_rembg").preserves_alpha)

    def test_provider_capabilities_match_expected_contract(self) -> None:
        self.assertTrue(provider_supports_operation("kie", "upscale_before"))
        self.assertTrue(provider_supports_operation("kie", "remove_background"))
        self.assertTrue(provider_supports_operation("photoroom", "remove_background"))
        self.assertFalse(provider_supports_operation("photoroom", "upscale_before"))
        self.assertTrue(provider_supports_operation("local_realesrgan", "upscale_after"))
        self.assertFalse(provider_supports_operation("local_realesrgan", "remove_background"))
        self.assertTrue(provider_requires_api_key("kie"))
        self.assertTrue(provider_requires_api_key("photoroom"))
        self.assertFalse(provider_requires_api_key("local_rembg"))
        self.assertTrue(provider_requires_network("kie"))
        self.assertTrue(provider_requires_cost("kie"))
        self.assertFalse(provider_requires_network("local_realesrgan"))
        self.assertFalse(provider_requires_cost("local_ben2"))
        self.assertTrue(provider_preserves_alpha("local_ben2"))
        self.assertFalse(upscale_model_preserves_alpha("kie", "recraft/crisp-upscale"))
        self.assertTrue(upscale_model_preserves_alpha("kie", "topaz/image-upscale"))
        self.assertTrue(upscale_model_preserves_alpha("local_realesrgan", ""))

    def test_field_options_are_shared_and_deterministic(self) -> None:
        self.assertEqual(
            processing_provider_options("upscale_before_provider"),
            (("KIE", "kie"), ("Fal.ai", "fal"), ("Local Real-ESRGAN", "local_realesrgan")),
        )
        self.assertEqual(
            processing_provider_options("remove_background_provider"),
            (
                ("KIE", "kie"),
                ("Fal.ai", "fal"),
                ("PhotoRoom", "photoroom"),
                ("Local rembg", "local_rembg"),
                ("Local BEN2", "local_ben2"),
                ("Local Chroma Key", "local_chroma_key"),
            ),
        )
        self.assertEqual(KIE_MODEL_OPTIONS, (("Topaz", "topaz/image-upscale"), ("Recraft Crisp", "recraft/crisp-upscale")))
        self.assertEqual(
            KIE_REMOVE_BG_MODEL_OPTIONS,
            (("Recraft Remove Background", "recraft/remove-background"),),
        )
        self.assertEqual(
            LOCAL_REMBG_PROFILE_OPTIONS,
            (("Клипарт", "clipart"), ("Люди", "people"), ("Аниме", "anime"), ("Запасной", "fallback")),
        )
        self.assertEqual(
            LOCAL_REMBG_MODEL_OPTIONS,
            (
                ("BiRefNet — общий (~928 МБ при первом запуске)", "birefnet-general"),
                ("BiRefNet — портрет (~928 МБ при первом запуске)", "birefnet-portrait"),
                ("IS-Net — аниме (~168 МБ при первом запуске)", "isnet-anime"),
                ("IS-Net — общий (~170 МБ при первом запуске)", "isnet-general-use"),
            ),
        )

    def test_provider_visible_controls_cover_expected_widgets(self) -> None:
        self.assertIn("kie_upscale_model", provider_visible_controls("kie"))
        self.assertIn("kie_upscale_after_model", provider_visible_controls("kie"))
        self.assertIn("local_realesrgan_profile", provider_visible_controls("local_realesrgan"))
        self.assertIn("local_ben2_alpha_threshold", provider_visible_controls("local_ben2"))
        self.assertEqual(
            provider_visible_controls("local_chroma_key"),
            ("chroma_key_color",),
        )
        self.assertEqual(provider_visible_controls("photoroom"), ())

    def test_chroma_ui_colors_are_derived_from_the_engine_registry(self) -> None:
        self.assertEqual(
            tuple(value for _label, value in CHROMA_KEY_COLOR_OPTIONS),
            tuple(KEY_COLORS),
        )

    def test_unknown_field_or_provider_raises(self) -> None:
        with self.assertRaises(KeyError):
            provider_spec("unknown")
        with self.assertRaises(KeyError):
            processing_provider_options("unknown_field")


if __name__ == "__main__":
    unittest.main()
