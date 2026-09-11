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
            dialog = ClipartBuilderDialog(state)
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
            again = ClipartBuilderDialog(restored)
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
