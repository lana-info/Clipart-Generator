import math
import unittest
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from chroma_key import KEY_COLORS, remove_chroma_key_automatic


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


class ChromaFineDetailTests(unittest.TestCase):
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
