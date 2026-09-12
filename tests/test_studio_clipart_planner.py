import copy
import unittest

from studio_clipart_recipe import ClipartRecipe
from studio_clipart_objects import fill_recipe, TEXT_FIELDS
from studio_clipart_planner import planning_request, apply_suggestions


class PlannerTests(unittest.TestCase):
    def setUp(self):
        self.recipe = ClipartRecipe(theme='Мишки на детском празднике', motifs=['самолёты'])
        self.recipe.objects = fill_recipe([], self.recipe.counts)
        self.recipe.objects[0].update(name='Любимый мишка', pinned=True)
        self.request = planning_request(self.recipe)
        self.response = [dict(id=row['id'], **dict.fromkeys(TEXT_FIELDS, ''),)
                         for row in self.request['targets']]
        for n, row in enumerate(self.response):
            row['name'] = f'Идея {n}'

    def test_atomic_apply_preserves_pins_identity_and_roles(self):
        before = copy.deepcopy(self.recipe.objects)
        result = apply_suggestions(self.recipe, self.request, self.response)
        self.assertEqual(before, self.recipe.objects)
        self.assertEqual(result[0], before[0])
        for old, new in zip(before, result):
            for field in ('id', 'ordinal', 'role'):
                self.assertEqual(old[field], new[field])

    def test_invalid_responses_never_change_draft(self):
        before = copy.deepcopy(self.recipe.objects)
        for mutate in (lambda r: r.pop(), lambda r: r.append(r[0]),
                       lambda r: r[0].update(name=' '),
                       lambda r: r[0].update(id=r[1]['id']),
                       lambda r: r[0].update(role='hero')):
            response = copy.deepcopy(self.response)
            mutate(response)
            with self.assertRaises(ValueError):
                apply_suggestions(self.recipe, self.request, response)
            self.assertEqual(before, self.recipe.objects)

    def test_stale_response_rejected(self):
        self.recipe.motifs.append('машинки')
        with self.assertRaises(ValueError):
            apply_suggestions(self.recipe, self.request, self.response)

    def test_single_replace_and_pin_guard(self):
        key = self.recipe.objects[1]['id']
        request = planning_request(self.recipe, replace_ids=[key])
        result = apply_suggestions(self.recipe, request, [self.response[0]])
        self.assertEqual(result[2:], self.recipe.objects[2:])
        with self.assertRaises(ValueError):
            planning_request(self.recipe, replace_ids=[self.recipe.objects[0]['id']])

    def test_pins_roundtrip_and_legacy(self):
        restored = ClipartRecipe.from_dict(self.recipe.to_dict())
        self.assertTrue(restored.objects[0]['pinned'])
        self.assertNotIn('pinned', restored.objects[1])
        restored.objects[1]['pinned'] = 'yes'
        with self.assertRaises(ValueError):
            restored.validate()

    def test_holiday_profile_is_added_to_request_without_replacing_main_theme(self):
        self.recipe.theme = 'Мишки Тедди'
        self.recipe.context = 'Christmas'
        request = planning_request(self.recipe)
        self.assertEqual(request['brief']['theme'], 'Мишки Тедди')
        self.assertEqual(request['brief']['context'], 'Christmas')
        self.assertEqual(request['holiday']['holiday'], 'Рождество')
        self.assertIn('Santa hat', request['holiday']['character_accessories'])
        self.assertIn('gift box', request['holiday']['props'])

    def test_non_holiday_context_does_not_invent_profile(self):
        self.recipe.context = 'Мой праздник'
        request = planning_request(self.recipe)
        self.assertIsNone(request['holiday'])

    def test_style_profile_is_local_bounded_guidance_in_request(self):
        self.recipe.visual = {"technique": "Акварель", "mood": "Нежное"}
        request = planning_request(self.recipe)
        self.assertEqual(request["style"]["key"], "watercolor")
        self.assertIn("watercolor", request["style"]["prompt_phrase"].casefold())
        self.assertIn("gentle", request["style"]["modifiers"])
        self.assertNotIn("provider", request["style"])

    def test_local_reference_paths_not_in_request(self):
        self.recipe.references = [dict(path='/private/reference.png', roles=['mood'], notes='Радостное')]
        request = planning_request(self.recipe)
        self.assertEqual(request['reference_observations'], [dict(roles=['mood'], notes='Радостное')])
        self.assertNotIn('/private', str(request))
