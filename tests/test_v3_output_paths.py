from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtWidgets import QApplication, QToolButton

from main import WorkerThread
from v3_processing_flow import (
    ProcessingFilesPage,
    build_processing_run_request,
    install_processing_flow,
)
from v3_project_state import ProjectMode, ProjectState, StepId
from v3_wizard import AppShell


class V3OutputPathsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_files_page_removes_one_file_without_clearing_the_rest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="processing-remove-") as temp:
            first = Path(temp) / "first.png"
            second = Path(temp) / "second.png"
            Image.new("RGB", (8, 8), "red").save(first)
            Image.new("RGB", (8, 8), "blue").save(second)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            state.processing.selected_files = [str(first), str(second)]
            shell = AppShell(state)
            controller = install_processing_flow(shell)
            page = controller.pages[StepId.FILES]
            page.refresh_from_state()

            card = page.files_layout.itemAt(0).widget()
            remove_button = card.findChild(QToolButton)
            self.assertIsNotNone(remove_button)
            remove_button.click()

            self.assertEqual(state.processing.selected_files, [str(second)])
            self.assertEqual(len(page.thumbnail_labels), 1)

    def test_output_selector_is_visible_and_updates_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="processing-output-") as temp:
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = temp
            shell = AppShell(state)
            controller = install_processing_flow(shell)
            page = controller.pages[StepId.FILES]

            expected_default = str(Path(temp) / "output")
            self.assertEqual(page.output_selector.path(), expected_default)
            self.assertEqual(state.common.output_dir, expected_default)

            custom_output = Path(temp) / "exports"
            page.output_selector.edit.setText(str(custom_output))
            self.assertEqual(state.common.output_dir, str(custom_output))

    def test_processing_worker_uses_output_directory_and_keeps_source_intact(self) -> None:
        with tempfile.TemporaryDirectory(prefix="processing-worker-") as temp:
            work_dir = Path(temp)
            source = work_dir / "source.png"
            Image.new("RGBA", (12, 12), (10, 20, 30, 255)).save(source)
            output_dir = work_dir / "exports"
            output_dir.mkdir()

            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = str(work_dir)
            state.common.output_dir = str(output_dir)
            state.processing.selected_files = [str(source)]
            state.processing.operations.upscale_before = False
            state.processing.operations.upscale_after = False
            state.processing.operations.unsharp = False
            state.processing.operations.remove_background = False
            state.processing.operations.trim = True
            state.processing.operations.edge_shrink = False

            request = build_processing_run_request(
                state,
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )
            worker = WorkerThread(**request.worker_kwargs())
            source_bytes = source.read_bytes()
            worker._mode2_process_files(emit_final=False)

            produced = list(output_dir.glob("source_processed*.png"))
            self.assertTrue(produced)
            self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()
