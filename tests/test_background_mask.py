import unittest

from PIL import Image

from background_mask import (
    apply_mask_path,
    apply_mask_stroke,
    apply_mask_to_image,
    has_usable_alpha,
    mask_for_image,
    save_mask_png,
)


class BackgroundMaskTests(unittest.TestCase):
    def test_new_mask_matches_image_size_and_reuses_existing_alpha(self):
        image = Image.new("RGBA", (5, 3), (255, 0, 0, 128))

        mask = mask_for_image(image)

        self.assertEqual(mask.mode, "L")
        self.assertEqual(mask.size, image.size)
        self.assertEqual(mask.getextrema(), (128, 128))

    def test_rgb_image_gets_an_opaque_mask(self):
        mask = mask_for_image(Image.new("RGB", (5, 3), "red"))

        self.assertEqual(mask.getextrema(), (255, 255))

    def test_usable_alpha_detects_real_transparency_only(self):
        self.assertFalse(has_usable_alpha(Image.new("RGB", (2, 2), "red")))
        self.assertFalse(has_usable_alpha(Image.new("RGBA", (2, 2), (1, 2, 3, 255))))
        self.assertTrue(has_usable_alpha(Image.new("RGBA", (2, 2), (1, 2, 3, 0))))

    def test_add_and_remove_strokes_change_only_mask(self):
        mask = Image.new("L", (9, 9), 0)
        before = mask.copy()

        added = apply_mask_stroke(mask, (4, 4), radius=2, action="add")
        removed = apply_mask_stroke(added, (4, 4), radius=1, action="remove")

        self.assertEqual(before.getpixel((0, 0)), 0)
        self.assertEqual(added.getpixel((4, 4)), 255)
        self.assertEqual(removed.getpixel((4, 4)), 0)
        self.assertEqual(removed.getpixel((1, 1)), 0)
        self.assertIsNot(added, mask)

    def test_soft_brush_keeps_a_solid_center_and_feathers_the_edge(self):
        mask = Image.new("L", (41, 41), 255)

        removed = apply_mask_stroke(
            mask,
            (20, 20),
            radius=10,
            action="remove",
            hardness=50,
        )

        self.assertEqual(removed.getpixel((20, 20)), 0)
        self.assertGreater(removed.getpixel((29, 20)), 0)
        self.assertLess(removed.getpixel((29, 20)), 255)
        self.assertEqual(removed.getpixel((31, 20)), 255)

    def test_path_stroke_fills_the_gap_between_pointer_events(self):
        mask = Image.new("L", (61, 21), 255)

        removed = apply_mask_path(
            mask,
            ((10, 10), (50, 10)),
            radius=3,
            action="remove",
            hardness=100,
        )

        self.assertEqual(removed.getpixel((10, 10)), 0)
        self.assertEqual(removed.getpixel((30, 10)), 0)
        self.assertEqual(removed.getpixel((50, 10)), 0)
        self.assertEqual(removed.getpixel((30, 15)), 255)

    def test_invalid_stroke_is_rejected(self):
        mask = Image.new("L", (3, 3), 0)

        with self.assertRaises(ValueError):
            apply_mask_stroke(mask, (1, 1), radius=0, action="add")
        with self.assertRaises(ValueError):
            apply_mask_stroke(mask, (1, 1), radius=1, action="paint")
        with self.assertRaises(ValueError):
            apply_mask_stroke(
                mask,
                (1, 1),
                radius=1,
                action="add",
                hardness=101,
            )

    def test_apply_mask_preserves_source_rgb_and_rejects_size_mismatch(self):
        source = Image.new("RGBA", (2, 1), (10, 20, 30, 255))
        mask = Image.new("L", (2, 1), 0)

        result = apply_mask_to_image(source, mask)

        self.assertEqual(result.getpixel((0, 0)), (10, 20, 30, 0))
        self.assertEqual(source.getpixel((0, 0)), (10, 20, 30, 255))
        with self.assertRaises(ValueError):
            apply_mask_to_image(source, Image.new("L", (1, 1), 255))

    def test_mask_png_save_is_atomic_and_transparent(self):
        with self.subTest("save"):
            import tempfile
            from pathlib import Path

            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "mask.png"
                save_mask_png(Image.new("L", (2, 2), 128), path)
                with Image.open(path) as saved:
                    self.assertEqual(saved.mode, "L")
                    self.assertEqual(saved.getpixel((0, 0)), 128)


if __name__ == "__main__":
    unittest.main()
