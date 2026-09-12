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
        dialog = ClipartBuilderDialog(state)
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
            reopened = ClipartBuilderDialog(restored)
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

    def test_palette_library_uses_five_swatch_cards_and_holiday_recommendation(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state)
        dialog.theme.setText('Мишки Тедди')
        dialog.context.setCurrentText('Christmas')
        dialog._refresh_palette_recommendations()
        self.assertEqual(dialog.recommended_palette_cards[0]['key'], 'holiday-christmas')
        self.assertTrue(dialog.palette_cards)
        self.assertTrue(all(len(card['colors']) == 5 for card in dialog.palette_cards))
        self.assertEqual(dialog.palette_reference_button.text(), 'Взять из референса')
        dialog.close()

    def test_palette_category_filter_and_selection_keep_plain_palette_value(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state)
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
        dialog = ClipartBuilderDialog(state)
        dialog.theme.setText('Проба')
        dialog.total.setValue(99)
        dialog._suggest()
        dialog.reject()
        self.assertEqual(state.to_dict(), before)

    def test_builder_entry_is_only_on_clipart_page(self):
        from v3_clipart_flow import ClipartProjectPage
        from v3_pinterest_flow import PinterestProjectPage
        state = ProjectState()
        clipart = ClipartProjectPage(state, lambda: None)
        pinterest = PinterestProjectPage(state, lambda: None)
        self.assertTrue(hasattr(clipart, 'builder_button'))
        self.assertFalse(hasattr(pinterest, 'builder_button'))
        clipart.close()
        pinterest.close()

    def test_validation_blocks_empty_theme_and_zero_total(self):
        state = ProjectState()
        dialog = ClipartBuilderDialog(state)
        dialog._navigate(1)
        self.assertEqual(dialog.pages.currentIndex(), 0)
        self.assertTrue(dialog.error.text())
        for spin in dialog.counts.values():
            spin.setValue(0)
        dialog._apply()
        self.assertIsNone(state.clipart.recipe)
        dialog.close()
