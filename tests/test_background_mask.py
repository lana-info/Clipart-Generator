import unittest

from PIL import Image

from background_mask import apply_mask_stroke, mask_for_image


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

    def test_invalid_stroke_is_rejected(self):
        mask = Image.new("L", (3, 3), 0)

        with self.assertRaises(ValueError):
            apply_mask_stroke(mask, (1, 1), radius=0, action="add")
        with self.assertRaises(ValueError):
            apply_mask_stroke(mask, (1, 1), radius=1, action="paint")


if __name__ == "__main__":
    unittest.main()
