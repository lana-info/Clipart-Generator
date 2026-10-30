import copy
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from PyQt6.QtWidgets import QApplication
from studio_clipart_references import extract_palette, validate_references
from studio_clipart_builder_ui import ClipartBuilderDialog
from v3_project_state import ProjectState, save_project_draft, load_project_draft


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_palette_ignores_transparent_padding_and_keeps_source(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'sample.png'
            im = Image.new('RGBA', (40, 40), (0, 0, 255, 0))
            for x in range(15, 25):
                for y in range(15, 25):
                    im.putpixel((x, y), (255, 0, 0, 255))
            im.save(path)
            before = path.read_bytes()
            self.assertEqual(extract_palette(path), ['#FF0000'])
            self.assertEqual(path.read_bytes(), before)

    def test_reference_roles_notes_palette_roundtrip_and_cancel(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'reference.png'
            Image.new('RGB', (30, 30), (50, 100, 150)).save(path)
            state = ProjectState()
            dialog = ClipartBuilderDialog(state.clipart)
            dialog.theme.setText('Звери')
            editor = dialog.reference_editor
            editor.add_reference(path)
            editor.roles['technique'].setChecked(True)
            editor.roles['mood'].setChecked(True)
            editor.notes.setPlainText('Карандаш; спокойное настроение')
            editor._palette()
            dialog._apply()
            destination = Path(folder) / 'draft.json'
            save_project_draft(state, destination)
            restored = load_project_draft(destination)
            before = copy.deepcopy(restored.to_dict())
            again = ClipartBuilderDialog(restored.clipart)
            self.assertTrue(again.reference_editor.roles['technique'].isChecked())
            self.assertEqual(again.palette.text(), '#326496')
            again.reference_editor._remove()
            again.reject()
            self.assertEqual(restored.to_dict(), before)
            self.assertTrue(path.exists())
            self.assertEqual(restored.clipart.prompts, [])
            dialog.close()
            again.close()

    def test_missing_reference_does_not_block_reopening(self):
        from studio_reference_editor import ReferenceEditor
        editor = ReferenceEditor([{'path': '/missing/example.png', 'roles': ['pose'], 'notes': 'Сидит'}])
        self.assertFalse(editor.palette.isEnabled())
        self.assertEqual(editor.notes.toPlainText(), 'Сидит')
        editor.close()

    def test_invalid_metadata_rejected(self):
        for roles in (['unknown'], ['mood', 'mood'], [1], 'palette'):
            with self.assertRaises(ValueError):
                validate_references([{'path': '/a.png', 'roles': roles, 'notes': ''}])


    def test_reference_image_consent_is_ephemeral_and_not_persisted(self):
        from studio_reference_editor import ReferenceEditor
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'consent.png'
            Image.new('RGB', (24, 24), (10, 20, 30)).save(path)
            editor = ReferenceEditor([])
            editor.add_reference(path)
            self.assertEqual(editor.selected_ai_image_paths(), ())
            editor.send_image_radio.setChecked(True)
            self.assertEqual(editor.selected_ai_image_paths(), (str(path.resolve()),))
            saved = editor.value()
            self.assertEqual(set(saved[0]), {'path', 'roles', 'notes', 'enabled'})
            self.assertNotIn('send', str(saved).casefold())
            self.assertEqual(editor.consume_ai_image_paths(), (str(path.resolve()),))
            self.assertEqual(editor.selected_ai_image_paths(), ())
            reopened = ReferenceEditor(saved)
            self.assertEqual(reopened.selected_ai_image_paths(), ())
            reopened.close(); editor.close()

    def test_reference_upload_preflight_builds_data_url_without_path(self):
        from studio_clipart_references import prepare_reference_image_for_model
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'private-name.png'
            Image.new('RGB', (20, 20), (1, 2, 3)).save(path)
            prepared = prepare_reference_image_for_model(path)
            self.assertEqual(prepared['mime_type'], 'image/png')
            self.assertTrue(prepared['data_url'].startswith('data:image/png;base64,'))
            self.assertNotIn(str(path), str(prepared))
            self.assertNotIn('private-name', str(prepared))


    def test_model_handoff_revalidates_actual_bytes_after_preflight(self):
        from studio_clipart_references import (
            prepare_reference_image_for_model, reference_image_upload_info,
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'changed.png'
            Image.new('RGB', (20, 20), (10, 20, 30)).save(path)
            expected = reference_image_upload_info(path)
            Image.new('RGB', (20, 20), (200, 20, 30)).save(path)
            with self.assertRaisesRegex(ValueError, 'измен'):
                prepare_reference_image_for_model(
                    path, expected_sha256=expected['sha256']
                )

    def test_reference_editor_shows_file_info_and_preflight_explanation(self):
        from studio_reference_editor import ReferenceEditor
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'info.png'
            Image.new('RGB', (120, 80), (10, 20, 30)).save(path)
            editor = ReferenceEditor([])
            editor.add_reference(path)
            self.assertIn('PNG', editor.reference_info.text())
            self.assertIn('120×80', editor.reference_info.text())
            note = editor.ai_preflight_note.text().casefold()
            self.assertIn('модел', note)
            self.assertIn('формат', note)
            self.assertIn('размер', note)
            editor.close()

    def test_missing_reference_upload_preflight_is_plain_value_error(self):
        from studio_clipart_references import reference_image_upload_info
        with self.assertRaisesRegex(ValueError, 'недоступ'):
            reference_image_upload_info('/missing/private-reference.png')


    def test_reference_editor_ai_selection_count_is_visible_and_one_shot(self):
        from studio_reference_editor import ReferenceEditor
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'count.png'
            Image.new('RGB', (20, 20), (1, 2, 3)).save(path)
            editor = ReferenceEditor([])
            editor.add_reference(path)
            self.assertIn('0', editor.ai_selection_count.text())
            self.assertIn('4', editor.ai_selection_count.text())
            editor.send_image_radio.setChecked(True)
            self.assertIn('1', editor.ai_selection_count.text())
            editor.consume_ai_image_paths()
            self.assertIn('0', editor.ai_selection_count.text())
            editor.close()


    def test_local_reference_preview_does_not_depend_on_ai_upload_limit(self):
        from unittest.mock import patch
        from studio_reference_editor import ReferenceEditor
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'local-only.png'
            Image.new('RGB', (30, 20), (20, 40, 60)).save(path)
            with patch('studio_clipart_references.reference_image_upload_info',
                       side_effect=ValueError('AI upload too large')):
                editor = ReferenceEditor([])
                editor.add_reference(path)
                self.assertFalse(editor.preview.pixmap().isNull())
                self.assertTrue(editor.palette.isEnabled())
                self.assertIn('PNG', editor.reference_info.text())
                editor.close()

    def test_reference_sources_and_disabled_reference_preserve_selected_direction(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'solid-red.png'
            Image.new('RGB', (30, 30), 'red').save(path)
            dialog = ClipartBuilderDialog(ProjectState().clipart)
            dialog._select_style_profile('watercolor')
            dialog.palette.setText('#112233 #445566')
            editor = dialog.reference_editor
            editor.add_reference(path)
            self.assertEqual(editor.value()[0]['roles'], ['subject'])
            self.assertTrue(editor.roles['subject'].isChecked())
            style, palette = dialog._effective_visual(editor.value())
            self.assertIn('watercolor', style)
            self.assertEqual(palette, '#112233 #445566')
            editor.style_from_reference.setChecked(True)
            editor.palette_from_reference.setChecked(True)
            style, palette = dialog._effective_visual(editor.value())
            self.assertIn('reference image 1', style)
            self.assertEqual(palette, '#FF0000')
            self.assertEqual(dialog.technique.currentText(), 'Акварель')
            self.assertEqual(dialog.palette.text(), '#112233 #445566')
            editor.use_for_generation.setChecked(False)
            style, palette = dialog._effective_visual(editor.value())
            self.assertIn('watercolor', style)
            self.assertEqual(palette, '#112233 #445566')
            self.assertEqual(editor.active_generation_paths(), ())
            dialog.close()

    def test_generation_prompt_scopes_reference_to_selected_attributes(self):
        from studio_clipart_objects import attach_reference_guidance
        from v3_project_state import PromptEntry
        path = '/private/reference.png'
        result = attach_reference_guidance(
            [PromptEntry(prompt='Watercolor fox', result_kind='clipart')],
            [dict(path=path, roles=['pose'], notes='Сидит боком', enabled=True)],
        )
        self.assertEqual(result[0].references, [path])
        self.assertIn('use only for pose', result[0].prompt)
        self.assertIn('Keep the selected collection style and palette', result[0].prompt)
        self.assertIn('Сидит боком', result[0].prompt)
