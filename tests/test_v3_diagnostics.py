import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication

from diagnostics import DiagnosticJournal
from v3_diagnostics import DiagnosticJournalDialog
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode
from v3_run_queue import RunQueueSession


class V3DiagnosticJournalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_journal_is_visible_before_and_during_mode_work(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            view = V3ApplicationView(
                draft_path=root / "project_state.json",
                diagnostic_journal=journal,
            )
            self.assertEqual(view.mode_selection.diagnostics_button.text(), "Журнал диагностики")
            self.assertEqual(
                view.mode_selection.receivers(view.mode_selection.diagnostics_requested),
                1,
            )
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            self.assertEqual(view.shell.diagnostics_button.text(), "Диагностика")
            self.assertEqual(view.shell.receivers(view.shell.diagnostics_requested), 1)
            view._show_diagnostics()
            self.assertIsInstance(view._diagnostics_dialog, DiagnosticJournalDialog)
            self.assertGreater(view._diagnostics_dialog.event_list.count(), 0)
            view._diagnostics_dialog.close()
            view.close()

    def test_run_queue_writes_terminal_events_without_source_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            request = SimpleNamespace(
                work_dir=str(root),
                settings={"output_dir": str(root / "output")},
                generated_prompts=[],
                selected_files=[str(root / "private-source.png")],
            )
            session = RunQueueSession(
                request,
                ProjectMode.PROCESSING,
                diagnostic_journal=journal,
            )
            session._event("item_failed", item=1, reason="timeout")
            raw = journal.session_path.read_text(encoding="utf-8")
            self.assertIn("item_failed", raw)
            self.assertIn("timeout", raw)
            self.assertNotIn(str(root), raw)


if __name__ == "__main__":
    unittest.main()
