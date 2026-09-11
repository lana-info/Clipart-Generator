import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
from v3_transparency_preview import ClipartTransparencyEditorPage


class ContourIntegrationTests(unittest.TestCase):
    def test_contour_copy_becomes_current_result_and_zip_source(self):
        from types import SimpleNamespace
        from zipfile import ZipFile
        from v3_wizard import AppShell
        from v3_project_state import ProjectState, ProjectMode, StepId
        from v3_clipart_flow import install_clipart_flow
        from v3_run_queue import RunQueueSession, RunItem, RunItemStatus
        from studio_set_export import export_clipart_sets

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output_dir = root / 'output'
            output_dir.mkdir()
            source = output_dir / '001_ready.png'
            # The user may explicitly save the edited copy outside output_dir.
            copy = root / 'corrected.png'
            Image.new('RGBA', (24, 24), (30, 60, 90, 255)).save(source)
            original = source.read_bytes()
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.clipart.export_membership[str(source)] = {'title': 'Garden', 'included': True}
            shell = AppShell(state)
            controller = install_clipart_flow(shell)
            request = SimpleNamespace(work_dir=str(root), settings={}, generated_prompts=[{'prompt': 'flower'}])
            session = RunQueueSession(request, ProjectMode.CLIPART)
            session.items = [RunItem(1, source.name, status=RunItemStatus.SUCCEEDED, output_path=str(source))]
            session.running = False
            controller.run_queue.session = session
            controller.run_queue.page.set_session(session)
            unrelated = root / 'unrelated.png'
            Image.new('RGBA', (24, 24), (10, 20, 30, 255)).save(unrelated)
            controller.run_queue.page.use_edited_output(unrelated, unrelated)
            self.assertEqual(session.items[0].output_path, str(source))
            controller._open_transparency_editor(0)
            editor = controller.pages[StepId.TRANSPARENCY]
            editor.document.mask.putpixel((5, 5), 0)
            QTimer.singleShot(0, lambda: QApplication.activeModalWidget().reject())
            editor.contour_button.click()
            self.assertEqual(session.items[0].output_path, str(source))
            self.assertEqual(editor.document.mask.getpixel((5, 5)), 0)
            failures = []
            def save_copy():
                dialog = QApplication.activeModalWidget()
                try:
                    dialog.save_button.click()
                except Exception as error:
                    failures.append(error)
                    dialog.reject()
            with patch('studio_contour_editor.QFileDialog.getSaveFileName', return_value=(str(copy), 'PNG')):
                QTimer.singleShot(0, save_copy)
                editor.contour_button.click()
            self.assertEqual(failures, [])
            controller._close_transparency_editor()
            results = controller.run_queue.page
            self.assertEqual(results._export_paths(), [copy])
            self.assertEqual(session.items[0].output_path, str(copy))
            from studio_export_membership import validate_export_membership
            expected = validate_export_membership({str(source): {'title': 'Garden', 'included': True}})[str(source)]
            self.assertEqual(state.clipart.export_membership[str(copy)], expected)
            archives = export_clipart_sets([{'title': 'Garden', 'images': results._export_paths()}], root)
            with ZipFile(archives[0]) as archive:
                pngs = [name for name in archive.namelist() if name.endswith('.png')]
                self.assertEqual(len(pngs), 1)
                self.assertEqual(archive.read(pngs[0]), copy.read_bytes())
            self.assertEqual(source.read_bytes(), original)
            controller._open_transparency_editor(0)
            self.assertEqual(editor.current_path, copy)
            second = root / 'second-copy.png'
            with patch('studio_contour_editor.QFileDialog.getSaveFileName', return_value=(str(second), 'PNG')):
                QTimer.singleShot(0, save_copy)
                editor.contour_button.click()
            self.assertEqual(failures, [])
            self.assertEqual(results._export_paths(), [second])
            self.assertEqual(state.clipart.export_membership[str(second)], expected)
            from studio_projects import ProjectStore
            store = ProjectStore(root / 'projects')
            record = store.create('clipart', 'Garden', state.to_dict())
            restored = ProjectState.from_dict(store.load(record.project_id).state)
            self.assertEqual(restored.clipart.export_membership, state.clipart.export_membership)
            shell.deleteLater()

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_cancel_keeps_unsaved_alpha_and_save_opens_separate_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.png"
            result = Path(folder) / "source-contour.png"
            Image.new("RGBA", (24, 24), (30, 60, 90, 255)).save(source)
            original = source.read_bytes()
            page = ClipartTransparencyEditorPage()
            page.set_files([source])
            page.document.mask.putpixel((5, 5), 0)
            document = page.document
            module = MagicMock()
            dialog = module.ContourEditorDialog.return_value
            dialog.saved_path = None
            with patch.dict("sys.modules", {"studio_contour_editor": module}):
                page.contour_button.click()
                self.assertEqual(module.ContourEditorDialog.call_args.kwargs["rgba"][5, 5, 3], 0)
                self.assertIs(page.document, document)
                self.assertEqual(page.document.mask.getpixel((5, 5)), 0)
                self.assertEqual(source.read_bytes(), original)
                Image.new("RGBA", (24, 24), (30, 60, 90, 128)).save(result)
                dialog.saved_path = result
                page.contour_button.click()
            self.assertEqual(page.current_path, result)
            self.assertEqual(source.read_bytes(), original)
            self.assertIn(source, page._draft_masks)
            page.deleteLater()

    def test_no_file_disables_entry(self):
        page = ClipartTransparencyEditorPage()
        self.assertFalse(page.contour_button.isEnabled())
        page.deleteLater()

    def test_actual_modal_editor_round_trip_keeps_source_and_current_alpha(self):
        from studio_contour_editor import ContourEditorDialog

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.png"
            output = Path(folder) / "copy.png"
            Image.new("RGBA", (24, 24), (30, 60, 90, 255)).save(source)
            source_bytes = source.read_bytes()
            page = ClipartTransparencyEditorPage()
            page.set_files([source])
            page.document.mask.putpixel((5, 5), 0)
            failures = []

            def interact():
                dialog = QApplication.activeModalWidget()
                try:
                    self.assertIsInstance(dialog, ContourEditorDialog)
                    self.assertEqual(int(dialog.canvas.alpha[5, 5]), 0)
                    dialog.save_button.click()
                except Exception as error:
                    failures.append(error)
                    if dialog is not None:
                        dialog.reject()

            with patch("studio_contour_editor.QFileDialog.getSaveFileName", return_value=(str(output), "PNG")):
                QTimer.singleShot(0, interact)
                page.contour_button.click()
            self.assertEqual(failures, [])
            self.assertEqual(page.current_path, output)
            self.assertEqual(source.read_bytes(), source_bytes)
            with Image.open(output) as saved:
                self.assertEqual(saved.getpixel((5, 5)), (30, 60, 90, 0))
            page.deleteLater()
