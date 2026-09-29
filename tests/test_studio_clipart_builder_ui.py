import tempfile
import unittest
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QDialog
from studio_clipart_builder_ui import ClipartBuilderDialog, PALETTES
from v3_project_state import ProjectState, save_project_draft, load_project_draft


class BuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_edit_save_reopen(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.theme.setText('Мишки Тедди')
        dialog.context.setCurrentText('Мой праздник')
        dialog.motifs.setText('машинки, самолёты')
        dialog.total.setValue(31)
        dialog._navigate(1)
        self.assertEqual(sum(w.value() for w in dialog.counts.values()), 31)
        dialog.technique.setCurrentText('Гуашь')
        dialog.mood.setCurrentText('Уютное')
        dialog.palette.setText(PALETTES[0][1])
        dialog._navigate(1)
        dialog._navigate(1)
        dialog.counts['hero'].setValue(7)
        dialog._navigate(1)
        dialog._navigate(1)
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'project.json'
            save_project_draft(state, path)
            restored = load_project_draft(path)
            reopened = ClipartBuilderDialog(restored.clipart)
            self.assertEqual(reopened.theme.text(), 'Мишки Тедди')
            self.assertEqual(reopened.counts['hero'].value(), 7)
            self.assertEqual(reopened.technique.currentText(), 'Гуашь')
            self.assertEqual(reopened.mood.currentText(), 'Уютное')
            self.assertEqual(reopened.palette.text(), PALETTES[0][1])
            reopened._apply()
            self.assertEqual(restored.to_dict(), state.to_dict())
            reopened.close()
        self.assertEqual(state.clipart.prompts, [])
        dialog.close()

    def test_style_page_fits_1120_width_without_horizontal_scroll(self):
        dialog = ClipartBuilderDialog(ProjectState().clipart)
        dialog.resize(1120, 780)
        dialog.pages.setCurrentIndex(1)
        dialog.show()
        self.app.processEvents()
        page = dialog.pages.currentWidget()
        self.assertEqual(page.horizontalScrollBar().maximum(), 0)
        dialog.close()

    def test_style_library_all_view_contains_every_profile(self):
        dialog = ClipartBuilderDialog(ProjectState().clipart)
        dialog.style_category.setCurrentText('Все')
        dialog._refresh_style_library()
        from studio_style_profiles import all_style_profiles
        self.assertEqual(len(dialog.style_cards), len(all_style_profiles()))
        self.assertEqual(
            [card['key'] for card in dialog.style_cards],
            [profile.key for profile in all_style_profiles()],
        )
        dialog.close()

    def test_style_library_has_previews_and_filters_categories(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        self.assertFalse(hasattr(dialog, 'recommended_style_grid'))
        self.assertTrue(all(not card['preview'].pixmap().isNull() for card in dialog.style_cards))
        dialog.style_category.setCurrentText('Персонажи')
        dialog._refresh_style_library()
        self.assertTrue(dialog.style_cards)
        self.assertTrue(all(card['category'] == 'Персонажи' for card in dialog.style_cards))
        dialog.close()

    def test_style_selection_modifiers_and_roundtrip_keep_collection_profile(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.theme.setText('Teddy Bear')
        dialog._select_style_profile('watercolor')
        self.assertEqual(dialog.technique.currentText(), 'Акварель')
        self.assertTrue(dialog.style_modifier_buttons['gentle'].isChecked())
        dialog.style_modifier_buttons['cozy'].click()
        self.assertIn('Нежный', dialog.mood.currentText())
        self.assertIn('Уютный', dialog.mood.currentText())
        dialog._apply()
        self.assertIn('watercolor', state.clipart.prompt_generator.style.casefold())
        restored = ClipartBuilderDialog(state.clipart)
        self.assertEqual(restored.technique.currentText(), 'Акварель')
        self.assertTrue(restored.style_modifier_buttons['gentle'].isChecked())
        self.assertTrue(restored.style_modifier_buttons['cozy'].isChecked())
        restored.close()
        dialog.close()

    def test_manual_custom_style_clears_known_style_card_selection(self):
        dialog = ClipartBuilderDialog(ProjectState().clipart)
        dialog._select_style_profile('watercolor')
        self.assertTrue(any(card['button'].isChecked() for card in dialog.style_cards
                            if card['key'] == 'watercolor'))
        dialog.technique.setCurrentText('Мой авторский штрих')
        self.app.processEvents()
        self.assertFalse(any(card['button'].isChecked() for card in dialog.style_cards))
        dialog.close()

    def test_custom_style_text_is_preserved_without_forcing_known_profile(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.theme.setText('Botanical objects')
        dialog.technique.setCurrentText('Мой авторский штрих')
        dialog.mood.setCurrentText('')
        dialog._apply()
        self.assertEqual(state.clipart.recipe['visual']['technique'], 'Мой авторский штрих')
        self.assertIn('Мой авторский штрих', state.clipart.prompt_generator.style)
        dialog.close()

    def test_palette_library_uses_five_swatch_cards_and_holiday_recommendation(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.theme.setText('Мишки Тедди')
        dialog.context.setCurrentText('Christmas')
        dialog._refresh_palette_recommendations()
        self.assertEqual(dialog.recommended_palette_cards[0]['key'], 'holiday-christmas')
        self.assertTrue(dialog.palette_cards)
        self.assertTrue(all(len(card['colors']) == 5 for card in dialog.palette_cards))
        from studio_clipart_builder_ui import PalettePreview
        self.assertTrue(all(card['widget'].findChild(PalettePreview) is not None
                            for card in dialog.palette_cards + dialog.recommended_palette_cards))
        self.assertEqual(dialog.palette_reference_button.text(), 'Взять из референса')
        dialog.close()

    def test_palette_category_filter_and_selection_keep_plain_palette_value(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.palette_category.setCurrentText('Природа')
        dialog._refresh_palette_library()
        self.assertTrue(dialog.palette_cards)
        self.assertTrue(all(card['category'] == 'Природа' for card in dialog.palette_cards))
        dialog._select_palette(dialog.palette_cards[0]['colors'])
        self.assertEqual(len(dialog.palette.text().split()), 5)
        dialog.close()

    def test_cancel_does_not_mutate_state(self):
        state = ProjectState()
        before = state.to_dict()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog.theme.setText('Проба')
        dialog.total.setValue(99)
        dialog._suggest()
        dialog.reject()
        self.assertEqual(state.to_dict(), before)

    def test_collection_builder_is_not_exposed_by_ordinary_generation(self):
        from v3_clipart_flow import ClipartProjectPage
        from v3_pinterest_flow import PinterestProjectPage
        state = ProjectState()
        clipart = ClipartProjectPage(state, lambda: None)
        pinterest = PinterestProjectPage(state, lambda: None)
        self.assertFalse(hasattr(clipart, 'builder_button'))
        self.assertFalse(hasattr(pinterest, 'builder_button'))
        clipart.close()
        pinterest.close()

    def test_validation_blocks_empty_theme_and_zero_total(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state.clipart)
        dialog._navigate(1)
        self.assertEqual(dialog.pages.currentIndex(), 0)
        self.assertTrue(dialog.error.text())
        for spin in dialog.counts.values():
            spin.setValue(0)
        dialog._apply()
        self.assertIsNone(state.clipart.recipe)
        dialog.close()


def test_texture_control_is_removed_and_legacy_texture_does_not_reach_prompts():
    app = QApplication.instance() or QApplication([])
    from studio_clipart_recipe import ClipartRecipe
    state = ProjectState()
    state.clipart.recipe = ClipartRecipe(theme='Мишки', visual={'technique': 'Акварель', 'material': 'Бумага'}).to_dict()
    dialog = ClipartBuilderDialog(state.clipart)
    assert 'material' not in dialog.visual_fields
    assert not hasattr(dialog, 'material')
    assert dialog._visual_values()['material'] == ''
    assert dialog.technique.currentText() == 'Акварель'
    dialog._apply()
    assert state.clipart.recipe['visual']['material'] == ''
    assert 'Без дополнительной фактуры' not in state.clipart.prompt_generator.style
    dialog.close()
    app.processEvents()
