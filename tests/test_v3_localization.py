import unittest

from v3_localization import (
    DEFAULT_LOCALE,
    SUPPORTED_LOCALES,
    app_locale_from_settings,
    normalize_locale,
    with_app_locale,
)


class V3LocalizationTests(unittest.TestCase):
    def test_supported_locales_and_default_are_stable(self):
        self.assertEqual(DEFAULT_LOCALE, "ru")
        self.assertEqual(SUPPORTED_LOCALES, ("ru", "en"))

    def test_normalize_locale_accepts_language_tags_and_falls_back_to_russian(self):
        self.assertEqual(normalize_locale("en-US"), "en")
        self.assertEqual(normalize_locale("RU_ru"), "ru")
        self.assertEqual(normalize_locale("de-DE"), "ru")
        self.assertEqual(normalize_locale(None), "ru")

    def test_locale_is_read_and_written_without_mixing_with_prompt_language(self):
        settings = {"app_language": "en-US", "prompt_language": "ru"}

        self.assertEqual(app_locale_from_settings(settings), "en")
        updated = with_app_locale(settings, "en")
        self.assertEqual(updated["app_language"], "en")
        self.assertEqual(updated["prompt_language"], "ru")
        self.assertEqual(settings["app_language"], "en-US")


if __name__ == "__main__":
    unittest.main()
