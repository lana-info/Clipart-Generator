import math
import unittest
from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from chroma_key import (
    KEY_COLORS,
    ChromaKeyAmbiguousError,
    remove_chroma_key_automatic,
)


SUPERSAMPLE = 3
SIZE = 384


def _scaled(value: float) -> int:
    return int(round(value * SUPERSAMPLE))


def _flatten_on_key(foreground: Image.Image, key_name: str) -> Image.Image:
    key = Image.new("RGBA", foreground.size, (*KEY_COLORS[key_name], 255))
    return Image.alpha_composite(key, foreground).convert("RGB")


def _finish(foreground: Image.Image) -> Image.Image:
    return foreground.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def _metrics(result: Image.Image, expected: Image.Image) -> dict[str, float]:
    actual = np.asarray(result.convert("RGBA"), dtype=np.float32) / 255.0
    reference = np.asarray(expected.convert("RGBA"), dtype=np.float32) / 255.0
    expected_alpha = reference[..., 3]
    actual_alpha = actual[..., 3]
    opaque = expected_alpha >= 0.98
    partial = (expected_alpha > 0.0) & (expected_alpha < 0.98)

    preview_errors = []
    for background in ((0, 0, 0), (255, 255, 255), (255, 0, 170)):
        backdrop = np.asarray(background, dtype=np.float32) / 255.0
        expected_preview = (
            reference[..., :3] * expected_alpha[..., None]
            + backdrop * (1.0 - expected_alpha[..., None])
        )
        actual_preview = (
            actual[..., :3] * actual_alpha[..., None]
            + backdrop * (1.0 - actual_alpha[..., None])
        )
        preview_errors.append(float(np.mean(np.abs(expected_preview - actual_preview))))

    return {
        "alpha_mae": float(np.mean(np.abs(expected_alpha - actual_alpha))),
        "opaque_loss": float(
            np.mean(1.0 - actual_alpha[opaque]) if np.any(opaque) else 0.0
        ),
        "partial_rgb_mae": float(
            np.mean(np.abs(reference[..., :3][partial] - actual[..., :3][partial]))
            if np.any(partial)
            else 0.0
        ),
        "preview_mae": max(preview_errors),
    }


def _rings_and_curls() -> Image.Image:
    foreground = Image.new(
        "RGBA",
        (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(foreground)
    for offset in (0, 34, -34):
        points = []
        for index in range(220):
            angle = index / 219 * math.pi * 4.4
            radius = 84 - index * 0.26
            points.append(
                (
                    _scaled(192 + math.cos(angle) * radius + offset),
                    _scaled(198 + math.sin(angle) * radius * 0.62 - offset * 0.18),
                )
            )
        draw.line(points, fill=(78, 31, 92, 255), width=_scaled(4), joint="curve")
    for x, y, radius in (
        (88, 82, 27),
        (192, 72, 35),
        (298, 90, 25),
        (118, 300, 34),
        (278, 290, 39),
    ):
        draw.ellipse(
            (
                _scaled(x - radius),
                _scaled(y - radius),
                _scaled(x + radius),
                _scaled(y + radius),
            ),
            outline=(221, 147, 46, 255),
            width=_scaled(8),
        )
    return _finish(foreground)


def _thin_branches() -> Image.Image:
    foreground = Image.new(
        "RGBA",
        (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(foreground)
    for branch in range(13):
        angle = -1.25 + branch * 0.19
        points = []
        for index in range(80):
            distance = index / 79
            points.append(
                (
                    _scaled(
                        192
                        + math.sin(angle) * distance * 164
                        + math.sin(distance * 11 + branch) * 7
                    ),
                    _scaled(356 - math.cos(angle) * distance * 292),
                )
            )
        draw.line(
            points,
            fill=(83, 39, 105, 255),
            width=_scaled(2 if branch % 2 else 3),
            joint="curve",
        )
        for fraction in (0.35, 0.58, 0.79):
            x, y = points[int(fraction * 79)]
            radius = _scaled(5 if branch % 3 else 7)
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                fill=(228, 126, 175, 255),
            )
    return _finish(foreground)


def _soft_shape(key_name: str) -> Image.Image:
    foreground = Image.new(
        "RGBA",
        (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE),
        (0, 0, 0, 0),
    )
    mask = Image.new("L", foreground.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        (_scaled(72), _scaled(58), _scaled(312), _scaled(326)),
        fill=255,
    )
    draw.ellipse(
        (_scaled(158), _scaled(116), _scaled(268), _scaled(254)),
        fill=0,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(_scaled(1.2)))
    colors = {
        "blue": (238, 145, 62, 255),
        "green": (175, 79, 215, 255),
        "red": (55, 160, 224, 255),
    }
    foreground.paste(Image.new("RGBA", foreground.size, colors[key_name]), mask=mask)
    return _finish(foreground)


def _fragment_flat_background(
    flattened: Image.Image,
    expected: Image.Image,
    key_name: str,
) -> Image.Image:
    pixels = np.asarray(flattened.convert("RGB"), dtype=np.uint8).copy()
    expected_alpha = np.asarray(expected.convert("RGBA"), dtype=np.uint8)[..., 3]
    y, x = np.indices(expected_alpha.shape)
    fragments = (
        (expected_alpha == 0)
        & (x % 4 == 1)
        & (y % 4 == 1)
    )
    variations = {
        "blue": (14, 6, 235),
        "red": (235, 14, 6),
        "green": (6, 235, 14),
    }
    pixels[fragments] = variations[key_name]
    return Image.fromarray(pixels, mode="RGB")


def _opaque_subject_with_interior_blue_spill() -> tuple[
    Image.Image,
    Image.Image,
    np.ndarray,
]:
    expected = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(expected)
    clean_color = (205, 190, 132, 255)
    draw.rounded_rectangle((70, 70, 314, 314), radius=50, fill=clean_color)
    input_image = np.asarray(
        _flatten_on_key(expected, "blue"),
        dtype=np.uint8,
    ).copy()
    y, x = np.indices((SIZE, SIZE))
    spill = ((x - 190) / 60) ** 2 + ((y - 190) / 45) ** 2 < 1
    key = np.asarray(KEY_COLORS["blue"], dtype=np.float32)
    input_image[spill] = np.rint(
        input_image[spill].astype(np.float32) * 0.78 + key * 0.22
    ).astype(np.uint8)
    return Image.fromarray(input_image, mode="RGB"), expected, spill


def _soft_shape_with_blue_edge_spill() -> tuple[Image.Image, Image.Image]:
    mask = Image.new("L", (SIZE * SUPERSAMPLE, SIZE * SUPERSAMPLE), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse(
        (_scaled(65), _scaled(55), _scaled(319), _scaled(329)),
        fill=255,
    )
    draw.ellipse(
        (_scaled(155), _scaled(112), _scaled(270), _scaled(259)),
        fill=0,
    )
    mask = mask.filter(ImageFilter.GaussianBlur(_scaled(1.2)))
    mask = mask.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    alpha = np.asarray(mask, dtype=np.uint8)

    clean_color = np.asarray((218, 184, 108), dtype=np.float32)
    expected_pixels = np.empty((SIZE, SIZE, 4), dtype=np.uint8)
    expected_pixels[..., :3] = clean_color.astype(np.uint8)
    expected_pixels[..., 3] = alpha
    expected = Image.fromarray(expected_pixels, mode="RGBA")

    inside_distance = cv2.distanceTransform(
        (alpha > 2).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    spill_strength = np.clip((16.0 - inside_distance) / 16.0, 0.0, 1.0) * 0.25
    key = np.asarray(KEY_COLORS["blue"], dtype=np.float32)
    contaminated = (
        clean_color[None, None, :] * (1.0 - spill_strength[..., None])
        + key[None, None, :] * spill_strength[..., None]
    )
    coverage = alpha.astype(np.float32) / 255.0
    flattened = np.rint(
        contaminated * coverage[..., None]
        + key[None, None, :] * (1.0 - coverage[..., None])
    ).astype(np.uint8)
    input_image = _fragment_flat_background(
        Image.fromarray(flattened, mode="RGB"),
        expected,
        "blue",
    )
    return input_image, expected


def _soft_shape_on_rendered_key(
    key_name: str,
) -> tuple[Image.Image, Image.Image]:
    """Model rendered key colors instead of mathematically pure presets."""
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((64, 48, 320, 336), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(1.4))
    alpha = np.asarray(mask, dtype=np.float32) / 255.0

    clean_colors = {
        "blue": (230, 155, 112),
        "green": (185, 95, 205),
        "red": (70, 165, 220),
    }
    rendered_keys = {
        "blue": (8, 124, 243),
        "green": (76, 236, 28),
        "red": (241, 42, 28),
    }
    clean_color = np.asarray(clean_colors[key_name], dtype=np.float32)
    rendered_key = np.asarray(rendered_keys[key_name], dtype=np.float32)
    inside_distance = cv2.distanceTransform(
        (alpha > 0.01).astype(np.uint8),
        cv2.DIST_L2,
        3,
    )
    spill = np.clip((12.0 - inside_distance) / 12.0, 0.0, 1.0) * 0.28
    contaminated = (
        clean_color[None, None, :] * (1.0 - spill[..., None])
        + rendered_key[None, None, :] * spill[..., None]
    )
    flattened = np.rint(
        contaminated * alpha[..., None]
        + rendered_key[None, None, :] * (1.0 - alpha[..., None])
    ).astype(np.uint8)

    expected_pixels = np.empty((SIZE, SIZE, 4), dtype=np.uint8)
    expected_pixels[..., :3] = clean_color.astype(np.uint8)
    expected_pixels[..., 3] = np.rint(alpha * 255.0).astype(np.uint8)
    return (
        Image.fromarray(flattened, mode="RGB"),
        Image.fromarray(expected_pixels, mode="RGBA"),
    )


def _layered_translucent_strip(key_name: str) -> Image.Image:
    key = np.asarray(KEY_COLORS["blue"], dtype=np.float32)
    orange_subject = np.asarray((230, 120, 40), dtype=np.float32)
    translucent_pink = np.asarray((240, 180, 210), dtype=np.float32)
    pixels = np.broadcast_to(key, (160, 160, 3)).copy()
    pixels[30:145, 70:100] = orange_subject
    strip = np.s_[55:120, 20:140]
    pixels[strip] = 0.40 * translucent_pink + 0.60 * pixels[strip]
    for y in range(58, 120, 8):
        line = np.s_[y : y + 1, 20:140]
        pixels[line] = 0.65 * translucent_pink + 0.35 * pixels[line]
    permutations = {
        "blue": (0, 1, 2),
        "green": (0, 2, 1),
        "red": (2, 0, 1),
    }
    return Image.fromarray(
        np.rint(pixels[..., permutations[key_name]]).astype(np.uint8),
        mode="RGB",
    )


class ChromaFineDetailTests(unittest.TestCase):
    def test_broad_light_blue_subject_detail_is_preserved_without_colour_shift(self):
        pixels = np.full((128, 128, 3), KEY_COLORS["blue"], dtype=np.uint8)
        pixels[20:108, 20:108] = (185, 175, 155)
        pixels[48:80, 48:80] = (120, 170, 230)

        result = remove_chroma_key_automatic(
            Image.fromarray(pixels, mode="RGB"),
            "blue",
        )

        result_pixels = np.asarray(result, dtype=np.uint8)
        np.testing.assert_array_equal(
            result_pixels[48:80, 48:80],
            np.broadcast_to((120, 170, 230, 255), (32, 32, 4)),
        )

    def test_broad_near_key_detail_is_preserved_inside_subject(self):
        for key_name, permutation in {
            "blue": (0, 1, 2),
            "green": (0, 2, 1),
            "red": (2, 0, 1),
        }.items():
            with self.subTest(key_name=key_name):
                key = np.asarray((0, 0, 255), dtype=np.uint8)[list(permutation)]
                detail = np.asarray((0, 80, 200), dtype=np.uint8)[list(permutation)]
                pixels = np.broadcast_to(key, (41, 41, 3)).copy()
                pixels[8:33, 8:33] = (180, 180, 180)
                pixels[18:23, 18:23] = detail

                result = remove_chroma_key_automatic(
                    Image.fromarray(pixels, mode="RGB"),
                    key_name,
                )

                self.assertEqual(
                    result.getpixel((20, 20)),
                    (*detail.tolist(), 255),
                )

    def test_translucent_interior_does_not_gain_complementary_key_colour(self):
        for key_name in ("blue", "green", "red"):
            with self.subTest(key_name=key_name):
                result = remove_chroma_key_automatic(
                    _layered_translucent_strip(key_name),
                    key_name,
                )
                pixel = np.asarray(result, dtype=np.uint8)[80, 120]
                key_channel = int(np.argmax(KEY_COLORS[key_name]))
                other_channels = [index for index in range(3) if index != key_channel]

                self.assertEqual(int(pixel[3]), 126)
                self.assertGreaterEqual(
                    int(pixel[key_channel]),
                    0.90
                    * min(
                        int(pixel[other_channels[0]]),
                        int(pixel[other_channels[1]]),
                    ),
                )

    def test_rendered_key_edges_are_recovered_without_complementary_halo(self):
        for key_name in ("blue", "green", "red"):
            with self.subTest(key_name=key_name):
                input_image, expected = _soft_shape_on_rendered_key(key_name)

                result = remove_chroma_key_automatic(input_image, key_name)
                actual = np.asarray(result.convert("RGBA"), dtype=np.float32)
                reference = np.asarray(expected.convert("RGBA"), dtype=np.float32)
                expected_alpha = reference[..., 3] / 255.0
                visible_edge = (expected_alpha >= 0.40) & (expected_alpha < 0.98)
                edge_error = actual[..., :3] - reference[..., :3]
                key_channel = int(np.argmax(KEY_COLORS[key_name]))
                other_channels = [index for index in range(3) if index != key_channel]
                complementary_bias = (
                    edge_error[..., other_channels[0]]
                    + edge_error[..., other_channels[1]]
                    - 2.0 * edge_error[..., key_channel]
                )

                self.assertLessEqual(
                    float(np.mean(np.abs(edge_error[visible_edge]))),
                    18.0,
                )
                self.assertLessEqual(
                    abs(float(np.mean(complementary_bias[visible_edge]))),
                    12.0,
                )
                lost_visible_edge = (reference[..., 3] >= 48.0) & (
                    actual[..., 3] == 0.0
                )
                self.assertLessEqual(
                    int(np.count_nonzero(lost_visible_edge)),
                    64,
                )

    def test_multiscale_reference_cleans_blue_spill_from_soft_edge(self):
        input_image, expected = _soft_shape_with_blue_edge_spill()

        result = remove_chroma_key_automatic(input_image, "blue")
        actual = np.asarray(result.convert("RGBA"), dtype=np.float32) / 255.0
        reference = np.asarray(expected.convert("RGBA"), dtype=np.float32) / 255.0
        reference_alpha = reference[..., 3]
        visible_edge = (reference_alpha >= (96.0 / 255.0)) & (
            reference_alpha < (224.0 / 255.0)
        )
        actual_on_black = actual[..., :3] * actual[..., 3, None]
        expected_on_black = reference[..., :3] * reference_alpha[..., None]
        channel_error = actual_on_black - expected_on_black
        blue_bias = channel_error[..., 2] - 0.5 * (
            channel_error[..., 0] + channel_error[..., 1]
        )

        self.assertLessEqual(float(np.mean(blue_bias[visible_edge])), 0.08)

    def test_opaque_blue_detail_is_preserved_when_spill_is_not_provable(self):
        input_image, expected, spill = _opaque_subject_with_interior_blue_spill()

        result = remove_chroma_key_automatic(input_image, "blue")
        actual = np.asarray(result.convert("RGBA"), dtype=np.float32)
        source = np.asarray(input_image.convert("RGB"), dtype=np.float32)
        reference = np.asarray(expected.convert("RGBA"), dtype=np.float32)
        subject = reference[..., 3] == 255

        np.testing.assert_array_equal(actual[..., :3][spill], source[spill])
        np.testing.assert_array_equal(
            actual[..., :3][subject & ~spill],
            source[subject & ~spill],
        )
        self.assertGreaterEqual(float(np.mean(actual[..., 3][spill])), 254.0)

    def test_complex_openings_and_curls_are_cut_without_rejection(self):
        expected = _rings_and_curls()

        result = remove_chroma_key_automatic(
            _flatten_on_key(expected, "green"),
            "green",
        )
        metrics = _metrics(result, expected)

        self.assertLessEqual(metrics["alpha_mae"], 0.015)
        self.assertLessEqual(metrics["opaque_loss"], 0.01)
        self.assertLessEqual(metrics["preview_mae"], 0.015)

    def test_thin_curved_branches_are_preserved_without_rejection(self):
        expected = _thin_branches()

        result = remove_chroma_key_automatic(
            _flatten_on_key(expected, "green"),
            "green",
        )
        metrics = _metrics(result, expected)

        self.assertLessEqual(metrics["alpha_mae"], 0.02)
        self.assertLessEqual(metrics["opaque_loss"], 0.02)
        self.assertLessEqual(metrics["preview_mae"], 0.02)

    def test_smooth_contours_have_no_stair_steps_or_key_colored_halo(self):
        for key_name in ("blue", "red", "green"):
            with self.subTest(key_name=key_name):
                expected = _soft_shape(key_name)
                result = remove_chroma_key_automatic(
                    _flatten_on_key(expected, key_name),
                    key_name,
                )
                metrics = _metrics(result, expected)

                self.assertLessEqual(metrics["alpha_mae"], 0.02)
                self.assertLessEqual(metrics["partial_rgb_mae"], 0.12)
                self.assertLessEqual(metrics["preview_mae"], 0.02)

    def test_fragmented_key_background_keeps_openings_and_thin_edges_clean(self):
        for expected in (_rings_and_curls(), _thin_branches()):
            with self.subTest(fixture=expected.getbbox()):
                input_image = _fragment_flat_background(
                    _flatten_on_key(expected, "green"),
                    expected,
                    "green",
                )

                result = remove_chroma_key_automatic(input_image, "green")
                metrics = _metrics(result, expected)

                self.assertLessEqual(metrics["alpha_mae"], 0.01)
                self.assertLessEqual(metrics["opaque_loss"], 0.01)
                self.assertLessEqual(metrics["preview_mae"], 0.01)

    def test_detailed_path_removes_every_supported_key_color_cleanly(self):
        for key_name in ("blue", "red", "green"):
            with self.subTest(key_name=key_name):
                expected = _soft_shape(key_name)
                input_image = _fragment_flat_background(
                    _flatten_on_key(expected, key_name),
                    expected,
                    key_name,
                )

                result = remove_chroma_key_automatic(input_image, key_name)
                metrics = _metrics(result, expected)

                self.assertLessEqual(metrics["alpha_mae"], 0.01)
                self.assertLessEqual(metrics["opaque_loss"], 0.01)
                self.assertLessEqual(metrics["preview_mae"], 0.01)

    def test_jpeg_compression_keeps_smooth_edges_without_visible_halo(self):
        for key_name in ("blue", "red", "green"):
            with self.subTest(key_name=key_name):
                expected = _soft_shape(key_name)
                encoded = BytesIO()
                _flatten_on_key(expected, key_name).save(
                    encoded,
                    format="JPEG",
                    quality=90,
                    subsampling=2,
                )
                encoded.seek(0)
                with Image.open(encoded) as compressed:
                    input_image = compressed.convert("RGB")

                result = remove_chroma_key_automatic(input_image, key_name)
                metrics = _metrics(result, expected)

                self.assertLessEqual(metrics["alpha_mae"], 0.012)
                self.assertLessEqual(metrics["opaque_loss"], 0.01)
                self.assertLessEqual(metrics["preview_mae"], 0.01)


if __name__ == "__main__":
    unittest.main()
