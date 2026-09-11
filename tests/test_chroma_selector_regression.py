import unittest

import numpy as np
from PIL import Image
from chroma_benchmark import load_golden_fixture, load_manifest

from chroma_key import (
    ChromaKeyAmbiguousError,
    _recover_enclosed_transition_matte,
    remove_chroma_key_automatic,
)


_KEY_NAMES = ("red", "green", "blue")
_PALETTES = (
    (120, 80, 180),
    (102, 145, 190),
    (155, 115, 195),
)


def _composite_on_key(
    foreground: np.ndarray,
    alpha: int,
    key: np.ndarray,
) -> np.ndarray:
    return np.rint(
        foreground * (alpha / 255.0) + key * (1.0 - alpha / 255.0)
    ).astype(np.uint8)


class ChromaSelectorRegressionTests(unittest.TestCase):
    def test_legitimate_opaque_key_tinted_highlight_is_preserved(self):
        for name, key, base in (("blue", (0, 0, 255), (205, 190, 132)),
                                ("green", (0, 255, 0), (205, 132, 190))):
            with self.subTest(key=name):
                key_rgb = np.asarray(key, dtype=np.float32)
                base_rgb = np.asarray(base, dtype=np.float32)
                highlight = np.rint(.78 * base_rgb + .22 * key_rgb).astype(np.uint8)
                pixels = np.broadcast_to(key_rgb.astype(np.uint8), (128, 128, 3)).copy()
                pixels[20:108, 20:108] = base_rgb
                pixels[48:80, 48:80] = highlight
                result = remove_chroma_key_automatic(
                    Image.fromarray(pixels), name, subject_profile="opaque_clipart",
                )
                expected = np.broadcast_to(np.append(highlight, 255), (32, 32, 4))
                np.testing.assert_array_equal(np.asarray(result)[48:80, 48:80], expected)

    def test_opaque_profile_does_not_recolour_edge_as_translucent_material(self):
        manifest = load_manifest("benchmarks/chroma/manifest.json")
        case = next(case for case in manifest["cases"] if case["id"] == "soft-edge-red")
        fixture = load_golden_fixture(manifest, case)
        before = fixture.input_image.tobytes()
        legacy = remove_chroma_key_automatic(fixture.input_image, fixture.key_color)
        opaque = remove_chroma_key_automatic(
            fixture.input_image, fixture.key_color, subject_profile="opaque_clipart",
        )
        # Known-truth pixel: foreground (75,172,226), coverage163. The existing
        # matte still overestimates coverage here. The material-specific repair
        # must not additionally replace R107 with R142 in the opaque profile.
        self.assertEqual(legacy.getpixel((79, 53)), (142, 142, 185, 255))
        self.assertEqual(opaque.getpixel((79, 53)), (107, 142, 185, 255))
        self.assertEqual(opaque.getchannel("A").tobytes(), legacy.getchannel("A").tobytes())
        self.assertEqual(fixture.input_image.tobytes(), before)

    def test_nearby_rendered_key_colours_recover_opaque_subject_and_partial_edge(self):
        """A rendered secondary key value must not select a lossy matte path."""
        for key_index, key_name in enumerate(_KEY_NAMES):
            secondary_index = (key_index + 1) % 3
            remaining_index = (key_index + 2) % 3
            for secondary_value in (30, 36, 37, 42):
                key = np.full(3, 2, dtype=np.float32)
                key[key_index] = 250
                key[secondary_index] = secondary_value
                for other_first, other_second, primary in _PALETTES:
                    foreground = np.empty(3, dtype=np.float32)
                    foreground[key_index] = primary
                    foreground[secondary_index] = other_first
                    foreground[remaining_index] = other_second
                    source_pixels = np.broadcast_to(
                        key.astype(np.uint8), (96, 96, 3)
                    ).copy()
                    source_pixels[20:76, 20:76] = foreground.astype(np.uint8)
                    source_pixels[20, 20:76] = _composite_on_key(
                        foreground,
                        128,
                        key,
                    )
                    source = Image.fromarray(source_pixels, mode="RGB")
                    before = source.tobytes()

                    result = remove_chroma_key_automatic(
                        source,
                        key_name,
                        subject_profile="opaque_clipart",
                    )
                    actual = np.asarray(result, dtype=np.int16)
                    expected = foreground.astype(np.int16)

                    np.testing.assert_allclose(
                        actual[48, 48, :3], expected, atol=3,
                        err_msg=(key_name, secondary_value, tuple(foreground)),
                    )
                    self.assertGreaterEqual(
                        int(actual[48, 48, 3]), 250,
                        (key_name, secondary_value, tuple(foreground)),
                    )
                    np.testing.assert_allclose(
                        actual[20, 48, :3], expected, atol=4,
                        err_msg=(key_name, secondary_value, tuple(foreground)),
                    )
                    self.assertAlmostEqual(
                        int(actual[20, 48, 3]), 128, delta=4,
                        msg=(key_name, secondary_value, tuple(foreground)),
                    )
                    self.assertEqual(source.tobytes(), before)

    def test_legacy_profile_does_not_infer_opaque_alpha_from_a_flat_composite(self):
        key = np.asarray((2, 30, 250), dtype=np.float32)
        foreground = np.asarray((120, 80, 180), dtype=np.float32)
        source_pixels = np.broadcast_to(key.astype(np.uint8), (96, 96, 3)).copy()
        source_pixels[20:76, 20:76] = _composite_on_key(foreground, 178, key)
        source_pixels[20, 20:76] = _composite_on_key(foreground, 89, key)
        source = Image.fromarray(source_pixels, mode="RGB")
        before = source.tobytes()

        with self.assertRaises(ChromaKeyAmbiguousError):
            remove_chroma_key_automatic(source, "blue")
        with self.assertRaises(ChromaKeyAmbiguousError):
            remove_chroma_key_automatic(
                source,
                "blue",
                subject_profile="opaque_clipart",
            )
        self.assertEqual(source.tobytes(), before)

    def test_opaque_profile_never_increases_source_alpha(self):
        key = np.asarray((2, 37, 250), dtype=np.float32)
        foreground = np.asarray((120, 80, 180), dtype=np.float32)
        source_pixels = np.broadcast_to(key.astype(np.uint8), (96, 96, 3)).copy()
        source_pixels[20:76, 20:76] = foreground.astype(np.uint8)
        source_pixels[20, 20:76] = _composite_on_key(foreground, 128, key)
        source_alpha = np.full((96, 96), 211, dtype=np.uint8)
        source_alpha[20, 20:76] = 97
        source = Image.fromarray(
            np.dstack((source_pixels, source_alpha)),
            mode="RGBA",
        )
        before = source.tobytes()

        result = np.asarray(
            remove_chroma_key_automatic(
                source,
                "blue",
                subject_profile="opaque_clipart",
            )
        )

        self.assertLessEqual(int(result[48, 48, 3]), 211)
        self.assertLessEqual(int(result[20, 48, 3]), 97)
        self.assertEqual(source.tobytes(), before)

    def test_enclosed_recovery_caps_cumulative_nested_roi_work(self):
        key = np.asarray((2, 30, 250), dtype=np.float32)
        foreground = np.asarray((120, 80, 180), dtype=np.float32)
        raw_matte = np.zeros((96, 96), dtype=np.float32)
        rgb = np.broadcast_to(key, (96, 96, 3)).copy()
        for inset in range(4, 40, 3):
            raw_matte[inset, inset : 96 - inset] = 0.7
            raw_matte[95 - inset, inset : 96 - inset] = 0.7
            raw_matte[inset : 96 - inset, inset] = 0.7
            raw_matte[inset : 96 - inset, 95 - inset] = 0.7
        rgb[raw_matte > 0] = foreground

        recovered = _recover_enclosed_transition_matte(rgb, key, raw_matte)

        self.assertGreaterEqual(recovered[4, 48], 0.99)
        self.assertAlmostEqual(float(recovered[37, 48]), 0.7, places=6)


if __name__ == "__main__":
    unittest.main()
