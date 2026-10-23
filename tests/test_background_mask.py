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

    def test_hard_brush_has_antialiased_alpha_on_a_diagonal_edge(self):
        before = Image.new("L", (61, 61), 255)
        after = apply_mask_stroke(before, (30, 30), radius=13, action="remove", hardness=100)
        self.assertEqual(after.getpixel((30, 30)), 0)
        self.assertTrue(any(0 < pixel < 255 for pixel in after.getdata()))

    def test_soft_stroke_overlap_does_not_harden_edge(self):
        from v3_transparency_preview import MaskEditDocument
        original = Image.new("RGBA", (120, 100), (100, 80, 50, 255))
        doc = MaskEditDocument(original)
        doc.begin_stroke()
        doc.extend_stroke([(20, 40)], radius=14, action="remove", hardness=50)
        doc.extend_stroke([(20, 40), (60, 40)], radius=14, action="remove", hardness=50)
        doc.extend_stroke([(60, 40), (100, 40)], radius=14, action="remove", hardness=50)
        doc.end_stroke()
        middle = doc.mask.getpixel((60, 52))
        fresh = apply_mask_stroke(Image.new("L", (120, 100), 255),
                                  (60, 40), radius=14, action="remove", hardness=50)
        self.assertEqual(middle, fresh.getpixel((60, 52)))
        doc.undo()
        self.assertEqual(doc.mask.getpixel((60, 52)), 255)
        doc.redo()
        self.assertEqual(doc.mask.getpixel((60, 52)), middle)

    def test_soft_brush_fades_more_than_hard_brush(self):
        before = Image.new("L", (61, 61), 255)
        hard = apply_mask_stroke(before, (30, 30), radius=13, action="remove", hardness=100)
        soft = apply_mask_stroke(before, (30, 30), radius=13, action="remove", hardness=50)
        self.assertEqual(soft.getpixel((30, 30)), 0)
        self.assertGreater(sum(0 < x < 255 for x in soft.getdata()),
                           sum(0 < x < 255 for x in hard.getdata()))

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

    def test_single_pixel_stamp_changes_only_target_for_every_hardness(self):
        for action, initial, expected in (("add", 0, 255), ("remove", 255, 0)):
            for hardness in (0, 50, 85, 100):
                with self.subTest(action=action, hardness=hardness):
                    before = Image.new("L", (9, 9), initial)
                    after = apply_mask_stroke(before, (4, 4), radius=0,
                                              action=action, hardness=hardness)
                    self.assertEqual(after.getpixel((4, 4)), expected)
                    self.assertEqual(sum(a != b for a, b in zip(before.tobytes(), after.tobytes())), 1)

    def test_single_pixel_path_is_continuous_and_does_not_widen(self):
        before = Image.new("L", (12, 9), 255)
        after = apply_mask_path(before, ((2, 4), (9, 4)), radius=0,
                                action="remove", hardness=85)
        changed = {(x, y) for y in range(9) for x in range(12)
                   if before.getpixel((x, y)) != after.getpixel((x, y))}
        self.assertEqual(changed, {(x, 4) for x in range(2, 10)})

    def test_invalid_stroke_is_rejected(self):
        mask = Image.new("L", (3, 3), 0)

        with self.assertRaises(ValueError):
            apply_mask_stroke(mask, (1, 1), radius=-1, action="add")
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
