from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from v3_project_state import ProjectMode
from v3_run_queue import ProgressEvent, RunQueueSession


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


if __name__ == "__main__":
    unittest.main()
