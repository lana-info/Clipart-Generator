import unittest

from PIL import Image, ImageDraw

from pinterest_pin_templates import (
    pinterest_template_specs,
    render_template_pin,
)


class PinterestPinTemplatesTests(unittest.TestCase):
    @staticmethod
    def make_product() -> Image.Image:
        product = Image.new("RGBA", (120, 160), (0, 0, 0, 0))
        draw = ImageDraw.Draw(product)
        draw.rectangle((18, 22, 101, 137), fill=(227, 116, 84, 255))
        draw.ellipse((36, 44, 84, 93), fill=(249, 215, 112, 255))
        return product

    def test_exposes_exactly_three_stable_safe_template_specs(self):
        specs = pinterest_template_specs()

        self.assertEqual(
            tuple(spec.template_id for spec in specs),
            ("product-hero", "editorial-card", "collage"),
        )
        self.assertEqual(len(specs), 3)
        for spec in specs:
            self.assertIsInstance(spec.product_box, tuple)
            self.assertIsInstance(spec.text_box, tuple)
            self.assertEqual(len(spec.product_box), 4)
            self.assertEqual(len(spec.text_box), 4)
            self.assertTrue(
                spec.product_box[0] < spec.product_box[2]
                and spec.product_box[1] < spec.product_box[3]
            )
            self.assertTrue(
                spec.text_box[0] < spec.text_box[2]
                and spec.text_box[1] < spec.text_box[3]
            )
            self.assertFalse(
                spec.product_box[0] < spec.text_box[2]
                and spec.text_box[0] < spec.product_box[2]
                and spec.product_box[1] < spec.text_box[3]
                and spec.text_box[1] < spec.product_box[3]
            )

    def test_default_render_is_a_vertical_rgba_pin(self):
        result = render_template_pin(
            self.make_product(),
            title="A long title that must fit inside its safe text area",
            subtitle="A supporting subtitle",
            cta="Save for later",
            template_id="product-hero",
        )

        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.size, (1000, 1500))

    def test_rendering_is_deterministic_for_same_inputs(self):
        product = self.make_product()
        kwargs = {
            "title": "Garden ideas",
            "subtitle": "Simple details for a calm home",
            "cta": "Save for later",
            "template_id": "collage",
        }

        first = render_template_pin(product, **kwargs)
        second = render_template_pin(product, **kwargs)

        self.assertEqual(first.tobytes(), second.tobytes())

    def test_rendering_does_not_mutate_product_layer(self):
        product = self.make_product()
        before = product.tobytes()

        render_template_pin(
            product,
            title="Editorial product story",
            subtitle="A carefully bounded subtitle",
            cta="Learn more",
            template_id="editorial-card",
        )

        self.assertEqual(product.tobytes(), before)

    def test_long_text_ink_is_contained_in_text_box_on_small_canvas(self):
        product = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
        long_text = "A very long Pinterest title subtitle and call to action " * 8
        width, height = 300, 450

        for spec in pinterest_template_specs():
            with self.subTest(template_id=spec.template_id):
                result = render_template_pin(
                    product,
                    title=long_text,
                    subtitle=long_text,
                    cta=long_text,
                    template_id=spec.template_id,
                    width=width,
                    height=height,
                )
                text_box = tuple(
                    round(value * (width / 1000 if index % 2 == 0 else height / 1500))
                    for index, value in enumerate(spec.text_box)
                )
                ink = Image.new("1", result.size, 0)
                result_pixels = result.load()
                ink_pixels = ink.load()
                for y in range(height):
                    for x in range(width):
                        red, green, blue, alpha = result_pixels[x, y]
                        ink_pixels[x, y] = alpha > 0 and max(red, green, blue) < 120

                ink_box = ink.getbbox()
                self.assertIsNotNone(ink_box)
                self.assertGreaterEqual(ink_box[0], text_box[0])
                self.assertGreaterEqual(ink_box[1], text_box[1])
                self.assertLessEqual(ink_box[2], text_box[2])
                self.assertLessEqual(ink_box[3], text_box[3])


if __name__ == "__main__":
    unittest.main()
