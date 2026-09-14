import tempfile
import unittest
from pathlib import Path

from studio_clipart_recipe import ClipartRecipe, ROLES, propose_recipes
from clipart_project_state import ClipartProjectStateExtension
from v3_project_state import ProjectState, ProjectStateError, load_project_draft, save_project_draft

CLIPART_EXTENSIONS = (ClipartProjectStateExtension(),)


class RecipeTests(unittest.TestCase):
    def test_all_supported_totals_are_exact_and_deterministic(self):
        for total in range(1, 1001):
            recipes = propose_recipes(total)
            self.assertEqual(recipes, propose_recipes(total))
            for counts in recipes.values():
                self.assertEqual(sum(counts.values()), total)
                self.assertEqual(set(counts), set(ROLES))
                self.assertTrue(all(type(n) is int and n >= 0 for n in counts.values()))

    def test_edit_preserves_zero_roles_and_updates_total(self):
        recipe = ClipartRecipe()
        counts = dict.fromkeys(ROLES, 0)
        counts['hero'] = 7
        recipe.edit_counts(counts)
        counts['hero'] = 3
        self.assertEqual(recipe.total, 7)
        self.assertEqual(recipe.counts['hero'], 7)

    def test_invalid_edits_leave_recipe_intact(self):
        recipe = ClipartRecipe()
        before = recipe.to_dict()
        for counts in ({}, {'hero': 5}, dict.fromkeys(ROLES, -1),
                       dict.fromkeys(ROLES, True), dict.fromkeys(ROLES, 0)):
            with self.assertRaises(ValueError):
                recipe.edit_counts(counts)
            self.assertEqual(recipe.to_dict(), before)
        for total in (0, -1, 1001, True, 1.5, '20'):
            with self.assertRaises(ValueError):
                recipe.select(total)
            self.assertEqual(recipe.to_dict(), before)

    def test_actual_draft_roundtrip_and_corrupt_recipe(self):
        state = ProjectState()
        recipe = ClipartRecipe(theme='Мишки Тедди', context='Первый день рождения',
                               motifs=['самолёты', 'машинки'])
        recipe.select(37, 'characters')
        state.clipart.recipe = recipe.to_dict()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.json'
            save_project_draft(state, path, extensions=CLIPART_EXTENSIONS)
            restored = load_project_draft(path, extensions=CLIPART_EXTENSIONS)
            self.assertEqual(restored.clipart.recipe, recipe.to_dict())
            self.assertEqual(restored.clipart.prompts, [])
            state.clipart.recipe['counts']['hero'] += 1
            with self.assertRaises((ProjectStateError, ValueError)):
                save_project_draft(state, path, extensions=CLIPART_EXTENSIONS)
            self.assertEqual(load_project_draft(path, extensions=CLIPART_EXTENSIONS).clipart.recipe, recipe.to_dict())

    def test_legacy_draft_has_no_new_recipe(self):
        value = ProjectState().to_dict()
        self.assertNotIn('recipe', value['clipart'])
        self.assertIsNone(ProjectState.from_dict(value).clipart.recipe)
