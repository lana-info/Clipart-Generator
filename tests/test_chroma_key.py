import unittest

from PIL import Image

from chroma_key import chroma_key_prompt_block, parse_key_color, remove_chroma_key


class ChromaKeyTests(unittest.TestCase):
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

        self.assertIn("#FF0000", prompt)
        self.assertIn("chroma-key", prompt)
        self.assertIn("no paper texture", prompt)

    def test_invalid_color_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_key_color("#12")


if __name__ == "__main__":
    unittest.main()
