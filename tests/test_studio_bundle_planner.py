import copy
import unittest

from studio_bundle_planner import propose_bundle_plan, validate_bundle_plan
from studio_clipart_objects import fill_recipe
from studio_clipart_recipe import ClipartRecipe


class BundlePlannerTests(unittest.TestCase):
    def test_new_titles_are_english_and_saved_custom_titles_are_not_translated(self):
        objects = self._objects(80)
        plan = propose_bundle_plan(objects)
        expected = {'mini': 'Mini', 'standard': 'Standard', 'maxi': 'Maxi',
                    'bundle': 'Full Bundle', 'characters': 'Characters',
                    'compositions': 'Compositions', 'frames-wreaths': 'Frames and Wreaths',
                    'decor': 'Decor'}
        self.assertEqual({item['key']: item['title'] for item in plan['sets']}, expected)
        plan['sets'][0]['title'] = 'Мои утята'
        replanned = propose_bundle_plan(objects, existing=plan)
        self.assertEqual(replanned['sets'][0]['title'], 'Мои утята')

    def _objects(self, total, preset='balanced'):
        recipe = ClipartRecipe()
        recipe.select(total, preset)
        return fill_recipe([], recipe.counts)

    def test_small_collections_keep_only_useful_nested_commercial_sets(self):
        expected = {
            3: ['bundle'],
            8: ['mini', 'bundle'],
            15: ['mini', 'standard', 'bundle'],
        }
        for total, keys in expected.items():
            with self.subTest(total=total):
                plan = propose_bundle_plan(self._objects(total))
                commercial = [item for item in plan['sets'] if item['kind'] == 'commercial']
                self.assertEqual([item['key'] for item in commercial], keys)
                sizes = [len(item['item_ids']) for item in commercial]
                self.assertEqual(sizes[-1], total)
                self.assertTrue(all(a < b for a, b in zip(sizes, sizes[1:])))
                previous = set()
                for item in commercial:
                    current = set(item['item_ids'])
                    self.assertTrue(previous <= current)
                    previous = current

    def test_thirty_images_produce_six_useful_sets_with_two_thematic_sets(self):
        objects = self._objects(30)
        plan = propose_bundle_plan(objects)
        self.assertEqual(plan['schema_version'], 2)
        self.assertEqual(len(plan['sets']), 6)
        commercial = [item for item in plan['sets'] if item['kind'] == 'commercial']
        thematic = [item for item in plan['sets'] if item['kind'] == 'thematic']
        self.assertEqual([item['key'] for item in commercial], ['mini', 'standard', 'maxi', 'bundle'])
        self.assertEqual(len(thematic), 2)
        object_roles = {item['id']: item['role'] for item in objects}
        role_groups = {
            'characters': {'hero'},
            'compositions': {'composition'},
            'frames-wreaths': {'wreath', 'border'},
            'decor': {'decor'},
        }
        for entry in thematic:
            self.assertIn(entry['key'], role_groups)
            self.assertGreaterEqual(len(entry['item_ids']), 2)
            self.assertTrue({object_roles[i] for i in entry['item_ids']} <= role_groups[entry['key']])
        memberships = sum(len(entry['item_ids']) for entry in plan['sets'])
        self.assertGreater(memberships, len(objects))
        validate_bundle_plan(plan, objects)

    def test_larger_collections_can_add_more_thematic_sets_without_duplicates(self):
        expected_minimums = {40: 7, 80: 8}
        for total, expected_count in expected_minimums.items():
            with self.subTest(total=total):
                objects = self._objects(total)
                plan = propose_bundle_plan(objects)
                self.assertEqual(len(plan['sets']), expected_count)
                frozen = [frozenset(item['item_ids']) for item in plan['sets']]
                self.assertEqual(len(frozen), len(set(frozen)))
                self.assertTrue(all(entry['item_ids'] for entry in plan['sets']))

    def test_replan_preserves_ids_and_user_titles_for_existing_keys(self):
        objects = self._objects(30)
        plan = propose_bundle_plan(objects)
        plan['sets'][0]['title'] = 'Мой мини'
        identities = {item['key']: (item['set_id'], item['title']) for item in plan['sets']}
        objects[-1]['role'] = 'hero'
        replanned = propose_bundle_plan(objects, existing=plan)
        for item in replanned['sets']:
            if item['key'] in identities:
                self.assertEqual((item['set_id'], item['title']), identities[item['key']])
        validate_bundle_plan(replanned, objects)

    def test_legacy_v1_plan_is_accepted_and_migrates_without_changing_tier_ids(self):
        objects = self._objects(30)
        current = propose_bundle_plan(objects)
        commercial = [item for item in current['sets'] if item['kind'] == 'commercial']
        legacy = {'schema_version': 1, 'sets': [
            {'tier': item['key'], 'set_id': item['set_id'], 'title': item['title'],
             'item_ids': list(item['item_ids'])} for item in commercial
        ]}
        accepted = validate_bundle_plan(copy.deepcopy(legacy), objects)
        self.assertEqual(accepted['schema_version'], 1)
        replanned = propose_bundle_plan(objects, existing=legacy)
        old_ids = {item['tier']: item['set_id'] for item in legacy['sets']}
        new_ids = {item['key']: item['set_id'] for item in replanned['sets'] if item['kind'] == 'commercial'}
        self.assertEqual({key: new_ids[key] for key in old_ids}, old_ids)

    def test_recipe_roundtrip_preserves_v2_bundle_plan(self):
        recipe = ClipartRecipe(theme='Garden party')
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.bundle_plan = propose_bundle_plan(recipe.objects)
        restored = ClipartRecipe.from_dict(recipe.to_dict())
        self.assertEqual(restored.bundle_plan, recipe.bundle_plan)
        self.assertEqual(validate_bundle_plan(restored.bundle_plan, restored.objects), restored.bundle_plan)


if __name__ == '__main__':
    unittest.main()
