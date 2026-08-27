import unittest

from clipart_prompt_schema import (
    ClipartPromptFields,
    render_clipart_prompt,
)
from v3_project_state import PromptGeneratorData


class ClipartPromptSchemaTests(unittest.TestCase):
    def test_provider_renderer_uses_stable_english_sections(self):
        fields = ClipartPromptFields(
            object="a cute fox",
            scene="a spring meadow",
            style="soft watercolor clipart",
            palette="peach, sage green, cream",
            composition="centered isolated object",
            background="transparent",
            details="delicate flowers",
            restrictions=("no text", "no watermark"),
            technical_requirements="clean edges, high detail",
        )

        prompt = render_clipart_prompt(fields, language="en")

        self.assertLess(prompt.index("Object:"), prompt.index("Scene:"))
        self.assertIn("Color palette: peach, sage green, cream.", prompt)
        self.assertIn("Restrictions: no text; no watermark.", prompt)
        self.assertIn("Technical requirements: clean edges, high detail.", prompt)

    def test_preview_uses_russian_labels_without_changing_values(self):
        fields = ClipartPromptFields(object="лиса", scene="весенний сад")

        preview = render_clipart_prompt(fields, language="ru")

        self.assertIn("Объект: лиса.", preview)
        self.assertIn("Сцена: весенний сад.", preview)
        self.assertNotIn("Object:", preview)

    def test_empty_optional_fields_are_omitted_and_input_is_normalized(self):
        fields = ClipartPromptFields(
            object="  fox  ",
            scene="",
            restrictions=(" no text ", "", "no text"),
        )

        prompt = render_clipart_prompt(fields, language="en")

        self.assertEqual(fields.object, "fox")
        self.assertNotIn("Scene:", prompt)
        self.assertEqual(prompt.count("Restrictions:"), 1)
        self.assertIn("Restrictions: no text.", prompt)

    def test_legacy_generator_data_maps_without_touching_pinterest_schema(self):
        legacy = PromptGeneratorData(
            theme="spring animals",
            subjects=["fox"],
            style="watercolor",
            palette="pastel",
            composition="centered",
            background="transparent",
            restrictions=["no text"],
        )

        fields = ClipartPromptFields.from_legacy(legacy)

        self.assertEqual(fields.object, "fox")
        self.assertEqual(fields.scene, "spring animals")
        self.assertEqual(fields.restrictions, ("no text",))


if __name__ == "__main__":
    unittest.main()
