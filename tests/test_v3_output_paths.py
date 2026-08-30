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

            expected_default = str(Path(temp))
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
            workspace_root = work_dir / "workspace"
            workspace_root.mkdir()

            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = str(work_dir)
            state.common.output_dir = str(workspace_root)
            state.processing.selected_files = [str(source)]
            state.processing.operations.upscale_before = False
            state.processing.operations.upscale_after = False
            state.processing.operations.unsharp = True
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

            produced = list((workspace_root / "output").glob("source_ready*.png"))
            self.assertTrue(produced)
            rough_names = [path.name for path in (workspace_root / "rough").glob("*.png")]
            self.assertTrue(rough_names)
            self.assertFalse(any(worker.run_stamp in name for name in rough_names))
            self.assertFalse((workspace_root / ".run").exists())
            worker._mode2_process_files(emit_final=False)
            self.assertGreater(
                len(list((workspace_root / "rough").glob("*.png"))),
                len(rough_names),
            )
            self.assertFalse((workspace_root / ".run").exists())
            self.assertEqual(source.read_bytes(), source_bytes)

    def test_processing_intermediates_do_not_use_stale_root_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="processing-root-workspace-") as temp:
            source = Path(temp) / "source.png"
            output_dir = Path(temp) / "exports"
            output_dir.mkdir()
            Image.new("RGB", (12, 12), "green").save(source)

            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = os.path.abspath(os.sep)
            state.common.output_dir = str(output_dir)
            state.processing.selected_files = [str(source)]
            state.processing.operations.trim = True
            state.processing.operations.upscale_before = False
            state.processing.operations.upscale_after = False
            state.processing.operations.unsharp = False
            state.processing.operations.remove_background = False
            state.processing.operations.edge_shrink = False

            request = build_processing_run_request(
                state,
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )
            worker = WorkerThread(**request.worker_kwargs())
            raw_dirs: list[str] = []
            original_create = worker._create_run_raw_dir
            worker._create_run_raw_dir = lambda: (
                raw_dirs.append(original_create()) or raw_dirs[-1]
            )

            worker._mode2_process_files(emit_final=False)

            self.assertTrue(list((output_dir / "output").glob("source_ready*.png")))
            self.assertEqual(len(raw_dirs), 1)
            self.assertNotEqual(Path(raw_dirs[0]).parent, Path(state.common.work_dir))

    def test_each_worker_owns_an_isolated_run_directory_and_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="processing-run-isolation-") as temp:
            workspace = Path(temp) / "workspace"
            output = workspace / "output"
            output.mkdir(parents=True)
            settings = {
                "workspace_root": str(workspace),
                "output_dir": str(output),
            }
            first = WorkerThread("mode2_process", str(workspace), settings)
            second = WorkerThread("mode2_process", str(workspace), settings)

            first_run = Path(first._create_run_raw_dir())
            second_run = Path(second._create_run_raw_dir())

            self.assertNotEqual(first_run, second_run)
            self.assertEqual(first_run.parent, workspace / ".run")
            self.assertEqual(second_run.parent, workspace / ".run")
            Image.new("RGB", (4, 4), "red").save(
                first_run / f"gen_001_{first.run_stamp}.png"
            )
            second_marker = second_run / f"gen_001_{second.run_stamp}.png"
            Image.new("RGB", (4, 4), "blue").save(second_marker)

            first._persist_rough_outputs(first_run)

            self.assertFalse(first_run.exists())
            self.assertTrue(second_marker.exists())
            self.assertEqual(
                len(list((workspace / "rough").glob("*.png"))),
                1,
            )

    def test_rough_generation_stage_excludes_internal_pipeline_copies(self) -> None:
        with tempfile.TemporaryDirectory(prefix="rough-stage-classification-") as temp:
            workspace = Path(temp) / "workspace"
            output = workspace / "output"
            output.mkdir(parents=True)
            worker = WorkerThread(
                "mode1_generate_and_process",
                str(workspace),
                {"workspace_root": str(workspace), "output_dir": str(output)},
            )
            raw_dir = Path(worker._create_run_raw_dir())
            stamp = worker.run_stamp
            files = {
                f"gen_001_{stamp}.png": "red",
                f"gen_002_{stamp}.png": "blue",
                f"gen_metadata_001_{stamp}.png": "red",
                f"gen_existing_alpha_002_{stamp}.png": "blue",
                f"gen_chroma_key_nobg_001_{stamp}.png": "green",
            }
            for name, color in files.items():
                Image.new("RGBA", (4, 4), color).save(raw_dir / name)

            worker._persist_rough_outputs(raw_dir)

            self.assertEqual(
                sorted(path.name for path in (workspace / "rough").glob("*.png")),
                [
                    "rough_01_bg-removed.png",
                    "rough_01_generated.png",
                    "rough_02_generated.png",
                ],
            )

    def test_invalid_work_dir_falls_back_to_writable_output_dir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="processing-invalid-workspace-") as temp:
            output_dir = Path(temp) / "exports"
            output_dir.mkdir()
            source = Path(temp) / "source.png"
            Image.new("RGB", (4, 4), "green").save(source)
            state = ProjectState(mode=ProjectMode.PROCESSING)
            state.common.work_dir = str(Path(temp) / "missing-workspace")
            state.common.output_dir = str(output_dir)
            state.processing.selected_files = [str(source)]
            request = build_processing_run_request(
                state,
                allow_full_image_changes=True,
                external_transfer_consent=True,
            )
            self.assertEqual(Path(request.work_dir), output_dir)
            self.assertEqual(Path(request.settings["output_dir"]), output_dir / "output")


if __name__ == "__main__":
    unittest.main()
