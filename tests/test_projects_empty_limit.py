from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from studio_projects import MAX_SAVED_PROJECTS, ProjectStore, ProjectStoreError
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode, StepId


class ProjectLimitTests(unittest.TestCase):
    def test_limit_constant_is_twenty(self):
        self.assertEqual(MAX_SAVED_PROJECTS, 20)

    def test_prune_removes_oldest_and_keeps_open_project(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            ids = []
            for index in range(MAX_SAVED_PROJECTS + 3):
                ids.append(store.create("clipart", f"P{index}", {"n": index}).project_id)
                time.sleep(0.002)
            # The oldest project is open now: it must survive, the next oldest go.
            removed = store.prune(MAX_SAVED_PROJECTS, keep=ids[0])
            remaining = {record.project_id for record in store.recent(limit=None)}
            self.assertEqual(len(remaining), MAX_SAVED_PROJECTS)
            self.assertIn(ids[0], remaining)
            self.assertEqual(set(removed), set(ids[1:4]))
            self.assertTrue(all(not (store.root / f"{pid}.json").exists() for pid in removed))

    def test_prune_below_limit_and_damaged_files_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            store.create("clipart", "A", {})
            broken = store.root / "00000000-0000-4000-8000-000000000000.json"
            broken.write_text("{not json", encoding="utf-8")
            self.assertEqual(store.prune(MAX_SAVED_PROJECTS), [])
            self.assertTrue(broken.exists())
            with self.assertRaises(ProjectStoreError):
                store.prune(0)


class EmptyProjectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _view(self, temp):
        return V3ApplicationView(draft_path=Path(temp) / "project_state.json")

    def test_untouched_first_step_is_not_saved_but_progress_is(self):
        with tempfile.TemporaryDirectory() as temp:
            view = self._view(temp)
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            self.assertEqual(view._project_store.recent(limit=None), [])
            self.assertTrue(view._save_draft())
            self.assertEqual(view._project_store.recent(limit=None), [])
            # Leaving without doing anything still leaves no record.
            self.assertTrue(view._save_before_leaving())
            self.assertEqual(view._project_store.recent(limit=None), [])
            # Real content: the project is remembered.
            view.shell.state.common.project_name = "Garden"
            self.assertTrue(view._save_draft())
            records = view._project_store.recent(limit=None)
            self.assertEqual([record.name for record in records], ["Garden"])

    def test_going_past_first_step_is_content(self):
        with tempfile.TemporaryDirectory() as temp:
            view = self._view(temp)
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            first = view.shell.state.current_step
            view.shell.state.set_step(StepId.PROMPTS)
            self.assertNotEqual(first, view.shell.state.current_step)
            view._save_draft()
            self.assertEqual(len(view._project_store.recent(limit=None)), 1)

    def test_header_continue_button_is_always_visible_icon(self):
        with tempfile.TemporaryDirectory() as temp:
            view = self._view(temp)
            view.show()
            try:
                button = view.mode_selection.header_continue_button
                self.assertTrue(button.isVisible())
                self.assertEqual(button.text(), "")
                self.assertEqual(button.accessibleName(), "Продолжить")
                self.assertEqual(button.toolTip(), "Продолжить")
                view._handle_mode_selected(ProjectMode.CLIPART.value)
                self.assertTrue(button.isVisible())
                for name in ("studio_home_button", "diagnostics_button", "module_updates_button", "license_button"):
                    icon_button = getattr(view.mode_selection, name)
                    self.assertEqual(icon_button.text(), "")
                    self.assertFalse(icon_button.icon().isNull())
                    self.assertTrue(icon_button.toolTip())
            finally:
                view.close()


if __name__ == "__main__":
    unittest.main()


class _FakeWorker:
    def __init__(self, stops: bool):
        self._running = True
        self._stops = stops
        self.stop_calls = 0

    def isRunning(self):
        return self._running

    def stop(self):
        self.stop_calls += 1
        if self._stops:
            self._running = False

    def wait(self, _ms):
        return not self._running


class _FakeController:
    def __init__(self, worker):
        self.worker = worker


class ShutdownWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_close_stops_running_worker_and_reports_stuck_one(self):
        with tempfile.TemporaryDirectory() as temp:
            view = V3ApplicationView(draft_path=Path(temp) / "project_state.json")
            view._handle_mode_selected(ProjectMode.CLIPART.value)
            good, stuck = _FakeWorker(True), _FakeWorker(False)
            view.shell._workflow_controllers = {"a": _FakeController(good), "b": _FakeController(stuck)}
            self.assertEqual(view._stop_leftover_workers(wait_ms=1), 1)
            self.assertEqual((good.stop_calls, stuck.stop_calls), (1, 1))
            self.assertFalse(good.isRunning())


class HeaderLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_header_order_title_and_removed_duplicates(self):
        with tempfile.TemporaryDirectory() as temp:
            view = V3ApplicationView(draft_path=Path(temp) / "project_state.json")
            view.show()
            try:
                screen = view.mode_selection
                row = screen.account_card.layout()
                order = [row.itemAt(i).widget() for i in range(row.count()) if row.itemAt(i).widget()]
                right = [screen.studio_home_button, screen.header_continue_button, screen.api_settings_button,
                         screen.diagnostics_button, screen.module_updates_button, screen.license_button]
                self.assertEqual([w for w in order if w in right], right)
                self.assertEqual(order[-1], screen.license_button)  # License last, in the corner
                self.assertEqual(screen.api_settings_button.text(), "API")
                self.assertTrue(screen.all_projects_button.isHidden())  # duplicate removed
                self.assertEqual(screen.active_module_label.text(), "Модули")
                view._handle_mode_selected(ProjectMode.CLIPART.value)
                self.assertNotEqual(screen.active_module_label.text(), "Модули")
                self.assertTrue(screen.studio_home_button.isVisible())
                screen.set_brand_text("VIBIX Studio v3.2.32")
                self.assertEqual(screen.brand_label.text(), "VIBIX Studio v3.2.32")
            finally:
                view.close()
