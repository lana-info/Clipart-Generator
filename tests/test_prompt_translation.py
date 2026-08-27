import unittest

from prompt_translation import (
    NoopPromptTranslationBackend,
    PromptTranslationError,
    translate_prompt_fields,
)


class PromptTranslationTests(unittest.TestCase):
    def test_same_language_is_explicitly_complete_without_rewrite(self):
        result = translate_prompt_fields(
            {"object": "лиса", "restrictions": ("без текста",)},
            source_language="ru",
            target_language="ru",
        )

        self.assertTrue(result.translated)
        self.assertEqual(result.fields["object"], "лиса")
        self.assertEqual(result.backend_id, "none")
        self.assertFalse(result.warning)

    def test_different_language_never_fakes_translation(self):
        result = translate_prompt_fields(
            {"object": "лиса"},
            source_language="ru",
            target_language="en",
            backend=NoopPromptTranslationBackend(),
        )

        self.assertFalse(result.translated)
        self.assertEqual(result.fields["object"], "лиса")
        self.assertIn("Перевод недоступен", result.warning)

    def test_invalid_input_fails_before_backend(self):
        with self.assertRaises(PromptTranslationError):
            translate_prompt_fields({}, source_language="", target_language="en")


if __name__ == "__main__":
    unittest.main()
