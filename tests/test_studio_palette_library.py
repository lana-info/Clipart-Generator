import unittest

from studio_palette_library import all_palette_presets, recommended_palette_presets


class PaletteLibraryTests(unittest.TestCase):
    def test_every_card_has_five_colors_and_expected_categories(self):
        presets = all_palette_presets()
        self.assertGreaterEqual(len(presets), 18)
        self.assertTrue({'Праздники', 'Сезоны', 'Природа', 'Семейства цветов', 'По назначению'} <=
                        {preset.category for preset in presets})
        for preset in presets:
            self.assertEqual(len(preset.colors), 5)

    def test_christmas_and_halloween_recommend_canonical_holiday_first(self):
        christmas = recommended_palette_presets('Мишки Тедди', 'Christmas')
        halloween = recommended_palette_presets('Котята', 'Halloween')
        self.assertEqual(christmas[0].key, 'holiday-christmas')
        self.assertEqual(halloween[0].key, 'holiday-halloween')
        self.assertEqual(christmas[0].colors[0], '#1F5D42')
        self.assertEqual(halloween[0].colors[0], '#F47C20')

    def test_mothers_and_fathers_day_have_no_holiday_recommendation(self):
        for context in ("Mother's Day", "Father's Day"):
            result = recommended_palette_presets('Teddy', context)
            self.assertFalse(any(item.category == 'Праздники' and 'Mother' in item.title for item in result))
            self.assertFalse(any(item.category == 'Праздники' and 'Father' in item.title for item in result))


if __name__ == '__main__':
    unittest.main()
