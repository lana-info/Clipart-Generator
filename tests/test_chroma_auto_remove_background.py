import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from v3_clipart_flow import ClipartPromptInputPage, build_clipart_run_request
from v3_project_state import ProjectMode, ProjectState


class ChromaAutoRemoveBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_series_transparency_enables_removal_and_disabling_stops_it(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.operations.remove_background = False
        page = ClipartPromptInputPage(state, lambda: None)
        self.addCleanup(page.close)
        page.chroma_key_enabled.setChecked(True)
        self.assertTrue(state.clipart.operations.remove_background)
        self.assertEqual(state.clipart.operations.remove_background_provider, "local_chroma_key")
        page.chroma_key_enabled.setChecked(False)
        self.assertFalse(state.clipart.operations.remove_background)

    def test_pasted_transparent_prompt_enables_removal_before_save(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.operations.remove_background = False
        saved = []
        page = ClipartPromptInputPage(state, lambda: saved.append(state.to_dict()))
        self.addCleanup(page.close)
        page.paste_chroma_enabled.setChecked(True)
        page.paste_edit.setPlainText("Watercolor fox")
        page._apply_paste()
        operations = saved[-1]["clipart"]["operations"]
        self.assertTrue(operations["remove_background"])
        self.assertEqual(operations["remove_background_provider"], "local_chroma_key")
        self.assertTrue(saved[-1]["clipart"]["prompts"][0]["chroma_key_color"])
        with tempfile.TemporaryDirectory() as directory:
            state.common.work_dir = directory
            request = build_clipart_run_request(state, {})
            self.assertTrue(request.settings["remove_bg"])
            self.assertEqual(request.settings["remove_bg_provider"], "local_chroma_key")

    def test_plain_prompt_preserves_manual_background_provider(self):
        state = ProjectState(mode=ProjectMode.CLIPART)
        state.clipart.operations.remove_background = True
        state.clipart.operations.remove_background_provider = "fal"
        page = ClipartPromptInputPage(state, lambda: None)
        self.addCleanup(page.close)
        page.paste_chroma_enabled.setChecked(False)
        page.paste_edit.setPlainText("Ordinary illustration")
        page._apply_paste()
        self.assertTrue(state.clipart.operations.remove_background)
        self.assertEqual(state.clipart.operations.remove_background_provider, "fal")
