from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from v3_project_state import ProjectMode
from v3_run_queue import ProgressEvent, RunItemStatus, RunQueueSession
from v3_runtime_adapter import legacy_progress_stage


class StructuredProgressTests(unittest.TestCase):
    def _session(self) -> RunQueueSession:
        with tempfile.TemporaryDirectory() as directory:
            self.directory = directory
            request = SimpleNamespace(
                work_dir=directory,
                generated_prompts=[],
                selected_files=[str(Path(directory) / "one.png")],
            )
            return RunQueueSession(request, ProjectMode.PROCESSING)

    def test_structured_event_exposes_stage_and_indeterminate_activity(self) -> None:
        session = self._session()
        session.handle_progress(
            ProgressEvent(item_index=1, total_items=1, stage="upscale", indeterminate=True)
        )
        self.assertEqual(session.current_stage, "upscale")
        self.assertTrue(session.activity_indeterminate)
        self.assertEqual(session.progress_percent, 0)

    def test_known_progress_is_monotonic_and_never_stuck_at_zero(self) -> None:
        session = self._session()
        session.handle_progress("[1/1] Обработка файла: one.png")
        session.handle_progress_value(42)
        self.assertEqual(session.progress_percent, 42)
        session.handle_progress_value(10)
        self.assertEqual(session.progress_percent, 42)

    def test_machine_stage_markers_distinguish_upscale_positions(self) -> None:
        self.assertEqual(
            legacy_progress_stage("Этап обработки: upscale_before; status=running"),
            ("upscale_before", "running"),
        )
        self.assertEqual(
            legacy_progress_stage("Этап обработки: upscale_after; status=complete"),
            ("upscale_after", "complete"),
        )

    def test_indexed_events_can_keep_three_rows_running_and_finish_out_of_order(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "output"
            output.mkdir()
            request = SimpleNamespace(
                work_dir=directory,
                settings={"output_dir": str(output)},
                generated_prompts=[],
                selected_files=[
                    str(root / "one.png"),
                    str(root / "two.png"),
                    str(root / "three.png"),
                ],
            )
            session = RunQueueSession(request, ProjectMode.PROCESSING)

            for item_index in (1, 2, 3):
                session.handle_item_progress(
                    ProgressEvent(
                        item_index=item_index,
                        total_items=3,
                        stage="upscale_before",
                        status="running",
                    )
                )

            self.assertEqual(
                [item.status for item in session.items],
                [RunItemStatus.RUNNING] * 3,
            )

            second = output / "two.png"
            Image.new("RGB", (4, 4), "blue").save(second)
            session.handle_item_progress(
                ProgressEvent(
                    item_index=2,
                    total_items=3,
                    stage="export",
                    status="succeeded",
                    output_path=str(second),
                )
            )
            session.handle_item_progress(
                ProgressEvent(
                    item_index=1,
                    total_items=3,
                    stage="upscale_before",
                    status="failed",
                    message="provider failed",
                )
            )

            self.assertIs(session.items[0].status, RunItemStatus.FAILED)
            self.assertIs(session.items[1].status, RunItemStatus.SUCCEEDED)
            self.assertIs(session.items[2].status, RunItemStatus.RUNNING)
            self.assertEqual(session.items[1].output_path, str(second.resolve()))
            self.assertFalse(session.items[0].output_path)

    def test_indexed_progress_updates_the_named_row_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = SimpleNamespace(
                work_dir=directory,
                settings={},
                generated_prompts=[],
                selected_files=[str(root / "one.png"), str(root / "two.png")],
            )
            session = RunQueueSession(request, ProjectMode.PROCESSING)
            session.handle_item_progress(
                ProgressEvent(
                    item_index=2,
                    total_items=2,
                    stage="background_removal",
                    status="running",
                    percent=45,
                )
            )

            self.assertEqual(session._item_progress, {1: 45})
            self.assertIs(session.items[0].status, RunItemStatus.PENDING)
            self.assertIs(session.items[1].status, RunItemStatus.RUNNING)


if __name__ == "__main__":
    unittest.main()
