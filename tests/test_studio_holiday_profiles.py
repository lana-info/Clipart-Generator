import unittest

from studio_holiday_profiles import (
    FIRST_WAVE_HOLIDAYS,
    get_holiday_profile,
    holiday_palette_presets,
    holiday_planning_hints,
)


class HolidayProfileTests(unittest.TestCase):
    def test_first_wave_and_exclusions(self):
        self.assertEqual(len(FIRST_WAVE_HOLIDAYS), 10)
        self.assertNotIn("Mother's Day", FIRST_WAVE_HOLIDAYS)
        self.assertNotIn("Father's Day", FIRST_WAVE_HOLIDAYS)
        self.assertIsNone(get_holiday_profile("Mother's Day"))
        self.assertIsNone(get_holiday_profile("Father's Day"))

    def test_aliases_and_every_palette_has_exactly_five_colors(self):
        self.assertEqual(get_holiday_profile('Рождество').key, 'christmas')
        self.assertEqual(get_holiday_profile('Independence Day').key, 'independence-day')
        self.assertEqual(get_holiday_profile('4th of July').key, 'independence-day')
        for context in FIRST_WAVE_HOLIDAYS:
            profile = get_holiday_profile(context)
            self.assertIsNotNone(profile)
            self.assertEqual(len(profile.palette), 5)
            self.assertTrue(all(color.startswith('#') and len(color) == 7 for color in profile.palette))

    def test_christmas_and_halloween_have_canonical_theme_colors(self):
        christmas = get_holiday_profile('Christmas')
        halloween = get_holiday_profile('Halloween')
        self.assertIn('#C62828', christmas.palette)  # classic Christmas red
        self.assertIn('#1F5D42', christmas.palette)  # evergreen
        self.assertIn('#F47C20', halloween.palette)  # pumpkin orange
        self.assertIn('#1B1B1B', halloween.palette)  # charcoal/black
        self.assertIn('#6B3FA0', halloween.palette)  # Halloween purple

    def test_planning_hints_cover_visual_dimensions_without_replacing_theme(self):
        hints = holiday_planning_hints('Christmas')
        self.assertEqual(hints['holiday'], 'Рождество')
        for key in ('palette', 'character_accessories', 'props', 'decor',
                    'composition_ideas', 'moods', 'background_hints'):
            self.assertTrue(hints[key])
        self.assertIn('Santa hat', hints['character_accessories'])
        self.assertIn('gift box', hints['props'])
        self.assertIsNone(holiday_planning_hints('Мой праздник'))

    def test_palette_preset_is_plain_local_data(self):
        presets = holiday_palette_presets('Halloween')
        self.assertEqual(len(presets), 1)
        self.assertEqual(presets[0]['colors'], list(get_holiday_profile('Halloween').palette))
        self.assertEqual(presets[0]['category'], 'Праздники')


if __name__ == '__main__':
    unittest.main()
