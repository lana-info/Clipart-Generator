import unittest

from studio_bundle_planner import propose_bundle_plan, validate_bundle_plan
from studio_clipart_objects import fill_recipe
from studio_clipart_recipe import ClipartRecipe


class BundlePlannerTests(unittest.TestCase):
    def _objects(self, total):
        recipe = ClipartRecipe()
        recipe.select(total)
        return fill_recipe([], recipe.counts)

    def test_tiers_are_nested_and_small_collections_avoid_duplicate_levels(self):
        expected = {
            3: ['bundle'],
            8: ['mini', 'bundle'],
            15: ['mini', 'standard', 'bundle'],
            30: ['mini', 'standard', 'maxi', 'bundle'],
        }
        for total, tiers in expected.items():
            with self.subTest(total=total):
                plan = propose_bundle_plan(self._objects(total))
                self.assertEqual([item['tier'] for item in plan['sets']], tiers)
                sizes = [len(item['item_ids']) for item in plan['sets']]
                self.assertEqual(sizes[-1], total)
                self.assertTrue(all(a < b for a, b in zip(sizes, sizes[1:])))
                previous = set()
                for item in plan['sets']:
                    current = set(item['item_ids'])
                    self.assertTrue(previous <= current)
                    previous = current

    def test_role_aware_prefix_and_stable_set_ids(self):
        recipe = ClipartRecipe()
        recipe.select(30, 'balanced')
        objects = fill_recipe([], recipe.counts)
        plan = propose_bundle_plan(objects)
        mini = plan['sets'][0]
        roles = {item['id']: item['role'] for item in objects}
        mini_roles = {roles[item_id] for item_id in mini['item_ids']}
        self.assertIn('hero', mini_roles)
        self.assertIn('decor', mini_roles)
        before_ids = {item['tier']: item['set_id'] for item in plan['sets']}
        objects[-1]['role'] = 'hero'
        replanned = propose_bundle_plan(objects, existing=plan)
        self.assertEqual({item['tier']: item['set_id'] for item in replanned['sets']}, before_ids)
        validate_bundle_plan(replanned, objects)

    def test_recipe_roundtrip_preserves_bundle_plan(self):
        recipe = ClipartRecipe(theme='Garden party')
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.bundle_plan = propose_bundle_plan(recipe.objects)
        restored = ClipartRecipe.from_dict(recipe.to_dict())
        self.assertEqual(restored.bundle_plan, recipe.bundle_plan)
        self.assertEqual(validate_bundle_plan(restored.bundle_plan, restored.objects), restored.bundle_plan)


if __name__ == '__main__':
    unittest.main()
