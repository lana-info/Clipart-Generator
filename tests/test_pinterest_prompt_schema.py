import unittest

from pinterest_prompt_schema import PinterestPromptFields, render_pinterest_prompt


class PinterestPromptSchemaTests(unittest.TestCase):
    def test_renderer_uses_vertical_pin_sections_in_stable_order(self):
        fields = PinterestPromptFields(
            topic="spring garden ideas",
            object="a cottage garden gate",
            background="soft morning light",
            text_safe_area="clean upper third with generous negative space",
            headline="Spring garden ideas",
            cta="Save for later",
            aspect_ratio="2:3",
            branding="warm, handmade editorial mood",
            visual_hierarchy="gate first, flowers second, text area clearly separated",
        )

        prompt = render_pinterest_prompt(fields, language="en")

        self.assertLess(prompt.index("Topic:"), prompt.index("Object:"))
        self.assertLess(prompt.index("Text-safe area:"), prompt.index("Headline:"))
        self.assertIn("Aspect ratio: 2:3.", prompt)
        self.assertIn("CTA: Save for later.", prompt)

    def test_russian_labels_do_not_claim_to_translate_values(self):
        fields = PinterestPromptFields(
            topic="идеи для сада",
            object="садовые ворота",
            text_safe_area="свободное место сверху",
            cta="Сохранить",
        )

        prompt = render_pinterest_prompt(fields, language="ru")

        self.assertIn("Тема: идеи для сада.", prompt)
        self.assertIn("Безопасная зона для текста: свободное место сверху.", prompt)
        self.assertNotIn("Topic:", prompt)

    def test_optional_fields_are_omitted_and_values_are_normalized(self):
        fields = PinterestPromptFields(
            topic="  garden  ",
            object="  gate\n  ",
            aspect_ratio=" 2:3 ",
            restrictions=(" no watermark ", "", "no watermark"),
        )

        prompt = render_pinterest_prompt(fields)

        self.assertEqual(fields.topic, "garden")
        self.assertEqual(fields.object, "gate")
        self.assertEqual(fields.restrictions, ("no watermark",))
        self.assertNotIn("Headline:", prompt)
        self.assertIn("Restrictions: no watermark.", prompt)

    def test_schema_has_no_clipart_specific_fields(self):
        fields = PinterestPromptFields(topic="flowers")

        self.assertEqual(
            set(fields.to_dict()),
            {
                "topic",
                "object",
                "background",
                "text_safe_area",
                "headline",
                "cta",
                "aspect_ratio",
                "branding",
                "visual_hierarchy",
                "style",
                "restrictions",
            },
        )


if __name__ == "__main__":
    unittest.main()
