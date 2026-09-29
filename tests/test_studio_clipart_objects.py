import tempfile
import unittest
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from studio_clipart_objects import fill_recipe, validate_objects, compile_objects
from studio_clipart_recipe import ClipartRecipe, ROLES
from studio_clipart_builder_ui import ClipartBuilderDialog
from v3_project_state import ProjectState, PromptEntry, PromptGeneratorData, save_project_draft, load_project_draft


class ObjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_recipe_changes_keep_edits_and_ids(self):
        recipe = ClipartRecipe()
        items = fill_recipe([], recipe.counts)
        items[0]['name'] = 'Тедди'
        again = fill_recipe(items, dict.fromkeys(ROLES, 0))
        self.assertEqual(again, items)
        bigger = fill_recipe(items, {role: n + 1 for role, n in recipe.counts.items()})
        self.assertEqual(bigger[:len(items)], items)
        self.assertEqual(len({item['id'] for item in bigger}), len(bigger))

    def test_compile_uses_existing_chroma_path_and_preserves_details(self):
        recipe = ClipartRecipe(theme='Мишки', context='День рождения')
        recipe.select(1)
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.objects[0].update(name='Тедди', action='держит самолёт', details='Красный шарф')
        prompts = compile_objects(recipe, PromptGeneratorData(style='Гуашь', chroma_key_enabled=True))
        self.assertEqual(len(prompts), 1)
        self.assertIn('самолёт', prompts[0].prompt)
        self.assertIn('Красный шарф', prompts[0].prompt)
        self.assertEqual(prompts[0].result_kind, 'clipart')
        self.assertTrue(prompts[0].chroma_key_color)
        self.assertEqual(prompts[0].references, [])
        self.assertEqual(prompts[0].object_id, recipe.objects[0]['id'])

    def test_gui_handoff_roundtrip_and_validation_atomicity(self):
        state = ProjectState()
        state.clipart.prompts = [PromptEntry('Existing prompt')]
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.theme.setText('Мишки')
        dialog.total.setValue(1)
        for _ in range(4):
            dialog._navigate(1)
        dialog.make_prompts.setChecked(True)
        dialog._apply()
        self.assertIsNone(state.clipart.recipe)
        self.assertEqual(len(state.clipart.prompts), 1)
        dialog.object_editor.fields['name'].setText('Тедди')
        dialog.object_editor.fields['action'].setText('сидит в машинке')
        dialog._apply()
        self.assertEqual(len(state.clipart.prompts), 2)
        self.assertEqual(state.clipart.prompts[0].prompt, 'Existing prompt')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'draft.json'
            save_project_draft(state, path)
            restored = load_project_draft(path)
            self.assertEqual(restored.clipart.recipe, state.clipart.recipe)
            self.assertIn('сидит в машинке', restored.clipart.prompts[1].prompt)
        dialog.close()

    def test_duplicate_gets_new_id_and_delete_preserves_remaining(self):
        from studio_object_editor import ObjectEditor
        recipe = ClipartRecipe()
        editor = ObjectEditor(fill_recipe([], recipe.counts))
        editor.fields['name'].setText('Венок')
        original = dict(editor.items[0])
        editor.duplicate()
        self.assertEqual(editor.items[-1]['name'], 'Венок')
        self.assertNotEqual(editor.items[-1]['id'], original['id'])
        editor.remove()
        self.assertEqual(editor.items[0], original)
        editor.close()

    def test_paper_free_rules_are_scoped_to_automatic_clipart_with_chroma(self):
        from clipart_prompt_generator import generate_clipart_prompt_series
        from chroma_key import parse_key_color
        recipe = ClipartRecipe(theme='Christmas teddy bear')
        recipe.select(1)
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.objects[0].update(name='Brown teddy bear', extras='Green pine needles and red berries',
                                 details='Cream knitted stocking')
        data = PromptGeneratorData(style='watercolor', chroma_key_enabled=True)
        entry = compile_objects(recipe, data)[0]
        color = '#%02X%02X%02X' % parse_key_color(entry.chroma_key_color)
        self.assertIn('no paper filling enclosed openings', entry.prompt)
        self.assertIn(f'open gaps show the same solid {color} background', entry.prompt)
        self.assertIn('without adding any new materials', entry.prompt)
        self.assertIn('knitted stocking', entry.prompt)
        ordinary = PromptGeneratorData(style='watercolor', subjects=['Teddy'], chroma_key_enabled=True)
        self.assertNotIn('no paper filling enclosed openings', generate_clipart_prompt_series(ordinary)[0].prompt)
        data.chroma_key_enabled = False
        self.assertNotIn('no paper filling enclosed openings', compile_objects(recipe, data)[0].prompt)

    def test_compile_adds_commercial_cutout_quality_without_background_method(self):
        recipe = ClipartRecipe(theme='Мишки')
        recipe.select(1)
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.objects[0].update(name='Тедди', action='сидит')
        prompt = compile_objects(recipe, PromptGeneratorData(style='Акварель'))[0].prompt.casefold()
        self.assertIn('полностью видим', prompt)
        self.assertIn('читаемый силуэт', prompt)
        self.assertIn('без обрезания', prompt)
        self.assertIn('без случайных лишних объектов', prompt)
        self.assertIn('все части объекта полностью непрозрачны', prompt)
        self.assertIn('акварель только как текстура непрозрачной краски', prompt)
        self.assertIn('без стекла, просвечивающих лепестков', prompt)
        self.assertIn('каждый лепесток и лист различим', prompt)
        self.assertIn('не лист миниатюр', prompt)
        self.assertIn('без размытия, расфокуса', prompt)
        self.assertNotIn('pure white background', prompt)

    def test_commercial_guidance_preserves_english_prompt_language(self):
        recipe = ClipartRecipe(theme='Christmas teddy bears')
        recipe.select(1)
        recipe.objects = fill_recipe([], recipe.counts)
        recipe.objects[0].update(name='Teddy bear', action='sitting')
        prompt = compile_objects(recipe, PromptGeneratorData(style='soft watercolor'))[0].prompt
        self.assertIn('Object: Teddy bear.', prompt)
        self.assertIn('fully visible', prompt.casefold())
        self.assertIn('no cropping', prompt.casefold())
        self.assertIn('all parts of the subject fully opaque', prompt)
        self.assertIn('watercolor only as an opaque painted texture', prompt)
        self.assertIn('no glass, see-through petals', prompt)
        self.assertIn('distinct petals and leaves', prompt)
        self.assertIn('not a contact sheet', prompt)
        self.assertIn('no blur, defocus', prompt)
        self.assertNotIn('Объект:', prompt)
        self.assertNotIn('без обрезания', prompt.casefold())


    def test_compile_adds_role_specific_wreath_and_decor_guidance(self):
        recipe = ClipartRecipe(theme='Рождество')
        recipe.total = 2
        recipe.counts = dict(hero=0, composition=0, wreath=1, border=0, decor=1)
        recipe.objects = fill_recipe([], recipe.counts)
        for item in recipe.objects:
            item['name'] = 'Венок' if item['role'] == 'wreath' else 'Бант'
        prompts = compile_objects(recipe, PromptGeneratorData(style='Акварель'))
        by_role = {item['role']: prompt.prompt.casefold() for item, prompt in zip(recipe.objects, prompts)}
        self.assertIn('чистое внутреннее отверстие', by_role['wreath'])
        self.assertIn('без случайных плавающих фрагментов', by_role['decor'])


    def test_invalid_records_rejected(self):
        items = fill_recipe([], ClipartRecipe().counts)
        items[1]['id'] = items[0]['id']
        with self.assertRaises(ValueError):
            validate_objects(items)

    def test_back_next_does_not_resurrect_deleted_object(self):
        dialog = ClipartBuilderDialog(ProjectState().clipart)
        dialog.theme.setText('Звери')
        dialog.total.setValue(3)
        for _ in range(4):
            dialog._navigate(1)
        dialog.object_editor.remove()
        remaining = dialog.object_editor.value()
        dialog._navigate(-1)
        dialog._navigate(1)
        self.assertEqual(dialog.object_editor.value(), remaining)
        dialog.close()
