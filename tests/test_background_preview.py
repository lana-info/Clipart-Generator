import unittest

from PIL import Image

from background_preview import (
    PREVIEW_BACKGROUND_OPTIONS,
    composite_on_preview,
    preview_background_color,
)


class BackgroundPreviewTests(unittest.TestCase):
    def test_exposes_the_six_approved_backgrounds(self):
        self.assertEqual(
            tuple(label for label, _ in PREVIEW_BACKGROUND_OPTIONS),
            ("Шахматный", "Чёрный", "Белый", "Зелёный", "Ярко-розовый", "Голубой"),
        )

    def test_solid_preview_preserves_rgb_and_composites_alpha(self):
        source = Image.new("RGBA", (2, 1), (10, 20, 30, 128))

        result = composite_on_preview(source, "Белый")

        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.getpixel((0, 0)), (132, 137, 142, 255))
        self.assertEqual(source.getpixel((0, 0)), (10, 20, 30, 128))

    def test_checkerboard_preview_has_alternating_tiles(self):
        source = Image.new("RGBA", (4, 4), (255, 0, 0, 0))

        result = composite_on_preview(source, "Шахматный", tile_size=2)

        self.assertEqual(result.getpixel((0, 0)), (238, 238, 238, 255))
        self.assertEqual(result.getpixel((2, 0)), (204, 204, 204, 255))

    def test_unknown_background_is_rejected(self):
        with self.assertRaises(ValueError):
            preview_background_color("Фиолетовый")


if __name__ == "__main__":
    unittest.main()
