import unittest

from PIL import Image

from chroma_key import (
    ChromaKeyAmbiguousError,
    chroma_key_prompt_block,
    parse_key_color,
    remove_chroma_key,
    remove_chroma_key_automatic,
)


class ChromaKeyTests(unittest.TestCase):
    def test_automatic_keyer_measures_the_rendered_border_color(self):
        background = (8, 35, 240, 255)
        image = Image.new("RGBA", (9, 9), background)
        image.putpixel((4, 4), (230, 80, 40, 255))
        result = remove_chroma_key_automatic(image, "blue")

        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertEqual(result.getpixel((8, 8))[3], 0)
        self.assertEqual(result.getpixel((4, 4)), (230, 80, 40, 255))

    def test_automatic_keyer_rejects_a_border_that_does_not_match_selected_key(self):
        image = Image.new("RGB", (9, 9), (0, 245, 10))

        with self.assertRaises(ValueError):
            remove_chroma_key_automatic(image, "blue")

    def test_automatic_keyer_recovers_partial_alpha_and_unmixed_edge_rgb(self):
        image = Image.new("RGBA", (9, 9), (0, 0, 255, 255))
        image.putpixel((4, 4), (50, 50, 178, 255))

        result = remove_chroma_key_automatic(image, "blue")

        red, green, blue, alpha = result.getpixel((4, 4))
        self.assertGreaterEqual(alpha, 124)
        self.assertLessEqual(alpha, 132)
        self.assertLessEqual(abs(red - 100), 3)
        self.assertLessEqual(abs(green - 100), 3)
        self.assertLessEqual(abs(blue - 100), 4)

    def test_automatic_keyer_preserves_small_key_colored_details_inside_subject(self):
        examples = (
            ("blue", (0, 0, 255, 255), (0, 100, 220, 255)),
            ("green", (0, 255, 0, 255), (30, 150, 50, 255)),
            ("red", (255, 0, 0, 255), (180, 40, 30, 255)),
        )
        for key_name, background, detail in examples:
            with self.subTest(key_name=key_name):
                image = Image.new("RGBA", (15, 15), background)
                for y in range(3, 12):
                    for x in range(3, 12):
                        image.putpixel((x, y), (185, 185, 185, 255))
                image.putpixel((7, 7), detail)

                result = remove_chroma_key_automatic(image, key_name)

                self.assertEqual(result.getpixel((7, 7)), detail)

    def test_automatic_keyer_does_not_block_when_key_color_touches_subject_edge(self):
        examples = (
            ("blue", (0, 0, 255, 255), (0, 100, 220, 255)),
            ("green", (0, 255, 0, 255), (30, 150, 50, 255)),
            ("red", (255, 0, 0, 255), (180, 40, 30, 255)),
        )
        for key_name, background, detail in examples:
            with self.subTest(key_name=key_name):
                image = Image.new("RGBA", (15, 15), background)
                for y in range(3, 12):
                    for x in range(3, 12):
                        image.putpixel((x, y), (185, 185, 185, 255))
                for y in range(6, 9):
                    for x in range(3, 6):
                        image.putpixel((x, y), detail)

                result = remove_chroma_key_automatic(image, key_name)

                self.assertEqual(result.getpixel((0, 0))[3], 0)
                self.assertLess(result.getpixel((4, 7))[3], 255)

    def test_automatic_keyer_rejects_broad_interior_background_gradient(self):
        size = 65
        center = (size - 1) / 2
        image = Image.new("RGBA", (size, size))
        for y in range(size):
            for x in range(size):
                edge_distance = min(x, y, size - 1 - x, size - 1 - y)
                blue = 255 - round(95 * edge_distance / center)
                image.putpixel((x, y), (0, 0, blue, 255))

        with self.assertRaises(ChromaKeyAmbiguousError):
            remove_chroma_key_automatic(image, "blue")

    def test_automatic_keyer_rejects_excessively_fragmented_background(self):
        image = Image.new("RGBA", (64, 64), (0, 0, 255, 255))
        for y in range(2, 63, 3):
            for x in range(2, 63, 3):
                image.putpixel((x, y), (0, 30, 230, 255))

        with self.assertRaises(ChromaKeyAmbiguousError):
            remove_chroma_key_automatic(image, "blue")

    def test_automatic_keyer_rejects_smoothly_nonuniform_background(self):
        image = Image.new("RGBA", (32, 16))
        for x in range(image.width):
            blue = 215 + round(40 * x / (image.width - 1))
            for y in range(image.height):
                image.putpixel((x, y), (0, 0, blue, 255))

        with self.assertRaises(ChromaKeyAmbiguousError):
            remove_chroma_key_automatic(image, "blue")

    def test_automatic_keyer_rejects_zero_sized_image(self):
        image = Image.new("RGBA", (0, 1))

        with self.assertRaises(ValueError):
            remove_chroma_key_automatic(image, "blue")

    def test_automatic_keyer_preserves_existing_alpha_and_input_bytes(self):
        image = Image.new("RGBA", (9, 9), (0, 0, 255, 255))
        image.putpixel((4, 4), (180, 180, 180, 80))
        original = image.tobytes()

        result = remove_chroma_key_automatic(image, "blue")

        self.assertEqual(result.getpixel((4, 4)), (180, 180, 180, 80))
        self.assertEqual(image.tobytes(), original)

    def test_removes_key_color_and_preserves_object_rgb(self):
        image = Image.new("RGBA", (3, 1), (0, 0, 255, 255))
        image.putpixel((1, 0), (240, 20, 30, 255))

        result = remove_chroma_key(image, "#0000ff", tolerance=10, softness=0)

        self.assertEqual(result.getpixel((0, 0)), (0, 0, 255, 0))
        self.assertEqual(result.getpixel((1, 0)), (240, 20, 30, 255))
        self.assertEqual(image.getpixel((0, 0)), (0, 0, 255, 255))

    def test_softness_creates_partial_alpha_and_existing_alpha_is_respected(self):
        image = Image.new("RGBA", (2, 1), (0, 0, 255, 100))
        image.putpixel((1, 0), (0, 20, 255, 255))

        result = remove_chroma_key(image, "blue", tolerance=0, softness=40)

        self.assertEqual(result.getpixel((0, 0))[3], 0)
        self.assertGreater(result.getpixel((1, 0))[3], 0)
        self.assertLessEqual(result.getpixel((1, 0))[3], 255)

    def test_prompt_block_contains_key_color_and_watercolor_rule(self):
        prompt = chroma_key_prompt_block("red", watercolor=True)
        self.assertIn("fully opaque and solid", prompt)
        self.assertIn("no transparency", prompt)

        self.assertIn("#FF0000", prompt)
        self.assertIn("chroma-key", prompt)
        self.assertIn("no paper texture", prompt)

    def test_prompt_block_adds_only_selected_material_clauses(self):
        prompt = chroma_key_prompt_block(
            "blue",
            materials=("thin_leaves", "metal"),
        )

        self.assertIn("thick flat blades", prompt)
        self.assertIn("matte brushed metal", prompt)
        self.assertNotIn("paper texture", prompt)
        self.assertNotIn("unlit", prompt)

    def test_transparent_material_is_rejected_by_opaque_prompt_contract(self):
        prompt = chroma_key_prompt_block(
            "blue",
            materials=("transparent_details",),
        )

        self.assertIn("fully opaque and solid", prompt)
        self.assertNotIn("genuinely semi-transparent", prompt)
        self.assertNotIn("Whatever lies behind them", prompt)

    def test_prompt_block_sets_silhouette_quality_standard_only_for_auto_clipart(self):
        # Other generators must not receive the silhouette standard.
        plain = chroma_key_prompt_block("blue", watercolor=True)
        self.assertIn("fully opaque and solid", plain)
        self.assertIn("no stray fragments", plain)
        self.assertNotIn("Crisply resolved forms", plain)
        self.assertNotIn("one continuous closed silhouette", plain)
        self.assertNotIn("saw-tooth fringe", plain)
        self.assertNotIn("Crisp hard edges", plain)

        # Only the Auto Clipart module opts in via edge_quality.
        standard = chroma_key_prompt_block("blue", watercolor=True, edge_quality=True)
        self.assertIn("Crisply resolved forms", standard)
        self.assertIn("individually recognisable", standard)
        self.assertIn("never merged into blotches or mush", standard)
        self.assertIn("one continuous closed silhouette", standard)
        self.assertIn("not a saw-tooth fringe", standard)
        self.assertIn("pale rim reaching into the background", standard)
        self.assertIn("no specks or dots detached from the subject", standard)

    def test_invalid_color_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_key_color("#12")


if __name__ == "__main__":
    unittest.main()
