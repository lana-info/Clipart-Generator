import unittest

from PIL import Image
from native_alpha import preserve_native_alpha


class NativeAlphaTests(unittest.TestCase):
    def test_preserves_every_nonzero_coverage_and_visible_rgb(self):
        source = Image.new("RGBA", (256, 1))
        source.putdata([(30, 70, 220, alpha) for alpha in range(256)])
        before = source.tobytes()
        result = preserve_native_alpha(source)
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(result.crop((1, 0, 256, 1)).tobytes(), source.crop((1, 0, 256, 1)).tobytes())
        self.assertEqual(source.tobytes(), before)

    def test_rejects_empty_image(self):
        with self.assertRaisesRegex(ValueError, "полностью прозрачное"):
            preserve_native_alpha(Image.new("RGBA", (8, 8), (0, 0, 255, 0)))

    def test_palette_transparency_is_respected(self):
        source = Image.new("P", (2, 1))
        source.putpalette([0, 0, 255, 200, 60, 80] + [0] * 762)
        source.putpixel((1, 0), 1)
        source.info["transparency"] = 0
        result = preserve_native_alpha(source)
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0, 0))
        self.assertEqual(result.getpixel((1, 0)), (200, 60, 80, 255))
