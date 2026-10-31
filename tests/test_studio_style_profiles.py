import unittest

from studio_style_profiles import (
    all_style_profiles,
    all_style_modifiers,
    get_style_profile,
    recommended_style_profiles,
    style_planning_hints,
    style_prompt_text,
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

    def test_gentle_modifier_pins_softness_to_colour_and_opaque_paint(self):
        """Мягкость — только цвет и фактура; краска полностью непрозрачна (вердикт владельца 2026-10-30)."""
        phrase = next(m.prompt_phrase for m in all_style_modifiers() if m.key == 'gentle')
        self.assertIn('soft visual character in colour and texture', phrase)
        self.assertIn('painted in fully opaque colours', phrase)
        self.assertIn('no translucent washes', phrase)

    def test_vintage_modifier_pins_timeless_shapes_in_opaque_paint(self):
        phrase = next(m.prompt_phrase for m in all_style_modifiers() if m.key == 'vintage')
        self.assertIn('subtle vintage character, timeless rather than distressed', phrase)
        self.assertIn('crisp readable shapes in fully opaque paint', phrase)

    def test_watercolor_profile_pins_opaque_texture_and_dense_coverage(self):
        profile = get_style_profile('watercolor')
        self.assertIn('hand-painted opaque watercolor texture', profile.prompt_phrase)
        self.assertIn('dense paint coverage', profile.prompt_phrase)
        self.assertIn('controlled readable edges', profile.prompt_phrase)

    def test_generation_style_phrase_carries_opacity_anchors(self):
        """Сборка «Стиль» для генерации (profile + модификаторы) несёт якоря непрозрачности."""
        phrase = style_prompt_text('Акварель', 'Нежный Винтажный')
        casefolded = phrase.casefold()
        self.assertIn('fully opaque colours', casefolded)
        self.assertIn('no translucent washes', casefolded)
        self.assertIn('fully opaque paint', casefolded)
        self.assertIn('opaque watercolor texture', casefolded)
        self.assertIn('dense paint coverage', casefolded)


if __name__ == '__main__':
    unittest.main()
