import unittest

from studio_style_profiles import (
    all_style_profiles,
    all_style_modifiers,
    get_style_profile,
    recommended_style_profiles,
    style_planning_hints,
)


class StyleProfileTests(unittest.TestCase):
    def test_library_is_generic_valid_and_unique(self):
        profiles = all_style_profiles()
        self.assertGreaterEqual(len(profiles), 15)
        self.assertEqual(len({p.key for p in profiles}), len(profiles))
        self.assertEqual(len({p.title for p in profiles}), len(profiles))
        copy = ' '.join((p.title + ' ' + p.prompt_phrase) for p in profiles).casefold()
        self.assertNotIn('disney', copy)
        for profile in profiles:
            profile.validate()
            self.assertTrue(profile.prompt_phrase)
            self.assertTrue(profile.best_for)

    def test_aliases_resolve_russian_and_english(self):
        self.assertEqual(get_style_profile('Акварель').key, 'watercolor')
        self.assertEqual(get_style_profile('watercolor').key, 'watercolor')
        self.assertEqual(get_style_profile('Скандинавский folk').key, 'scandinavian-folk')
        self.assertIsNone(get_style_profile('мой авторский стиль'))

    def test_recommendations_are_theme_and_context_aware(self):
        baby = [p.key for p in recommended_style_profiles('Мишка', 'Baby Shower')]
        christmas = [p.key for p in recommended_style_profiles('Woodland animals', 'Christmas')]
        halloween = [p.key for p in recommended_style_profiles('Cute ghosts', 'Halloween')]
        self.assertIn('pastel-nursery', baby)
        self.assertIn('scandinavian-folk', christmas)
        self.assertTrue({'whimsical', 'gothic-dark'} & set(halloween))

    def test_modifiers_are_generic_and_unique(self):
        modifiers = all_style_modifiers()
        self.assertGreaterEqual(len(modifiers), 8)
        self.assertEqual(len({m.key for m in modifiers}), len(modifiers))
        self.assertNotIn('disney', ' '.join(m.title for m in modifiers).casefold())

    def test_planning_hints_are_bounded_and_keep_custom_style(self):
        known = style_planning_hints('Акварель', mood='Нежное')
        self.assertEqual(known['key'], 'watercolor')
        self.assertIn('watercolor', known['prompt_phrase'].casefold())
        self.assertIn('gentle', known['modifiers'])
        custom = style_planning_hints('Мой авторский штрих', mood='Спокойное')
        self.assertEqual(custom['key'], 'custom')
        self.assertEqual(custom['title'], 'Мой авторский штрих')
        self.assertLessEqual(len(str(custom)), 4000)


if __name__ == '__main__':
    unittest.main()
