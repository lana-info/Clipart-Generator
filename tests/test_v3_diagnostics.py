import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from PyQt6.QtWidgets import QApplication

import main
from diagnostics import (
    DEFAULT_SESSION_MAX_BYTES,
    DEFAULT_TOTAL_MAX_BYTES,
    DiagnosticJournal,
)
from v3_diagnostics import DiagnosticJournalDialog
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode, StepId
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

    def test_structured_provider_event_uses_v2_schema_and_safe_details(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")

            journal.record_structured(
                {
                    "event": "provider_task_failed",
                    "provider": "kie",
                    "model": "recraft/crisp-upscale",
                    "stage": "upscale_before",
                    "task": "task-safe-123",
                    "http_status": 200,
                    "provider_state": "fail",
                    "error_code": "501",
                    "error_message": "provider failed; api_key=sk-secret-value",
                    "item_index": 2,
                    "item_total": 8,
                    "attempt": 1,
                    "elapsed_ms": 950,
                    "prompt": "private prompt",
                    "result_url": "https://example.test/file?token=secret",
                },
                operation_id="operation-123",
            )

            event = journal.read_events()[0]
            raw = journal.session_path.read_text(encoding="utf-8")
            self.assertEqual(event["schema_version"], 2)
            self.assertEqual(event["operation_id"], "operation-123")
            self.assertEqual(event["details"]["provider"], "kie")
            self.assertEqual(event["details"]["task"], "task-safe-123")
            self.assertEqual(event["details"]["item_index"], 2)
            self.assertNotIn("private prompt", raw)
            self.assertNotIn("sk-secret-value", raw)
            self.assertNotIn("example.test", raw)
            archive_path = journal.export_zip(root / "diagnostics.zip")
            with zipfile.ZipFile(archive_path) as archive:
                exported = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                )
            self.assertIn("task-safe-123", exported)
            self.assertNotIn("private prompt", exported)
            self.assertNotIn("sk-secret-value", exported)
            self.assertNotIn("example.test", exported)

    def test_detailed_journal_limits_cover_large_image_batches(self) -> None:
        self.assertEqual(DEFAULT_SESSION_MAX_BYTES, 8 * 1024 * 1024)
        self.assertEqual(DEFAULT_TOTAL_MAX_BYTES, 24 * 1024 * 1024)

    def test_read_events_keeps_legacy_v1_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            journal.session_path.write_text(
                '{"schema_version":1,"timestamp":"2026-08-26T00:00:00+00:00",'
                '"sequence":1,"event":"legacy","summary":"old"}\n',
                encoding="utf-8",
            )

            events = journal.read_events()

            self.assertEqual(events[0]["event"], "legacy")

    def test_dialog_filters_by_severity_provider_and_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            journal.record_structured(
                {
                    "event": "provider_task_polled",
                    "provider": "kie",
                    "model": "gpt-image-2-text-to-image",
                    "task": "task-1",
                    "provider_state": "waiting",
                    "item_index": 1,
                    "item_total": 2,
                    "filename": "first.png",
                    "stage": "generation",
                    "elapsed_ms": 100,
                },
                operation_id="run-1",
            )
            journal.record_structured(
                {
                    "event": "provider_task_failed",
                    "provider": "photoroom",
                    "model": "remove-background-v1",
                    "error_code": "invalid_image",
                    "error_message": "provider failed",
                    "item_index": 2,
                    "item_total": 2,
                    "filename": "second.png",
                    "stage": "background_removal",
                    "elapsed_ms": 250,
                },
                operation_id="run-1",
            )
            dialog = DiagnosticJournalDialog(journal)

            self.assertEqual(dialog.event_list.count(), 2)
            dialog.source_filter.setCurrentIndex(
                dialog.source_filter.findData("kie")
            )
            self.app.processEvents()
            self.assertEqual(dialog.event_list.count(), 1)
            self.assertIn("KIE", dialog.event_list.item(0).text())

            dialog.source_filter.setCurrentIndex(
                dialog.source_filter.findData("all")
            )
            dialog.severity_filter.setCurrentIndex(
                dialog.severity_filter.findData("error")
            )
            self.app.processEvents()
            self.assertEqual(dialog.event_list.count(), 1)
            self.assertIn("second.png", dialog.event_list.item(0).text())

            dialog.severity_filter.setCurrentIndex(
                dialog.severity_filter.findData("all")
            )
            image_index = next(
                index
                for index in range(dialog.item_filter.count())
                if "first.png" in dialog.item_filter.itemText(index)
            )
            dialog.item_filter.setCurrentIndex(image_index)
            self.app.processEvents()
            self.assertEqual(dialog.event_list.count(), 1)
            dialog.close()

    def test_dialog_details_use_russian_labels_and_fit_minimum_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            journal.record_structured(
                {
                    "event": "provider_task_failed",
                    "provider": "kie",
                    "model": "recraft/crisp-upscale",
                    "task": "task-123",
                    "http_status": 503,
                    "provider_state": "failed",
                    "error_message": "temporarily unavailable",
                    "item_index": 1,
                    "item_total": 1,
                    "filename": "source.png",
                    "stage": "upscale_before",
                    "width": 1000,
                    "height": 800,
                    "input_bytes": 12345,
                    "elapsed_ms": 950,
                },
                operation_id="run-1",
            )
            dialog = DiagnosticJournalDialog(journal)
            dialog.resize(980, 700)
            dialog.show()
            self.app.processEvents()

            details = dialog.detail.toPlainText()
            self.assertIn("Провайдер: kie", details)
            self.assertIn("Модель: recraft/crisp-upscale", details)
            self.assertIn("HTTP-статус: 503", details)
            self.assertIn("Размер изображения: 1000 × 800", details)
            self.assertIn("Длительность: 950 мс", details)
            self.assertLessEqual(dialog.minimumWidth(), 980)
            self.assertLessEqual(dialog.minimumHeight(), 700)
            dialog.close()

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

    def test_run_start_identifies_local_provider_and_model_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            request = SimpleNamespace(
                work_dir=str(root),
                settings={
                    "output_dir": str(root / "output"),
                    "remove_bg": True,
                    "remove_bg_provider": "local_rembg",
                    "local_rembg_profile": "quality",
                    "local_rembg_model": "isnet-general-use",
                },
                generated_prompts=[],
                selected_files=[str(root / "source.png")],
            )

            RunQueueSession(
                request,
                ProjectMode.PROCESSING,
                diagnostic_journal=journal,
            )

            started = next(
                event for event in journal.read_events()
                if event["event"] == "run_started"
            )
            self.assertEqual(
                started["details"]["provider_routes"],
                ["background_removal:local_rembg"],
            )
            self.assertEqual(
                started["details"]["model_routes"],
                ["background_removal:isnet-general-use"],
            )

    def test_generation_run_identifies_kie_models_and_operation_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            request = SimpleNamespace(
                mode="mode1_generate_only",
                work_dir=str(root),
                settings={
                    "text_generation_model": "gpt-image-2",
                    "reference_generation_model": "gpt-image-2-image-to-image",
                },
                generated_prompts=[{"prompt": "private", "references": []}],
                selected_files=[],
            )

            RunQueueSession(
                request,
                ProjectMode.CLIPART,
                diagnostic_journal=journal,
            )

            started = next(
                event for event in journal.read_events()
                if event["event"] == "run_started"
            )
            self.assertEqual(started["details"]["operation_type"], "mode1_generate_only")
            self.assertEqual(started["details"]["provider_routes"], ["generation:kie"])
            self.assertEqual(
                started["details"]["model_routes"],
                [
                    "text_generation:gpt-image-2",
                    "reference_generation:gpt-image-2-image-to-image",
                ],
            )

    def test_trim_print_run_records_configuration_stages_output_and_terminal_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output_dir = root / "output"
            source = root / "private-source.png"
            image = Image.new("RGB", (20, 20), "white")
            for x in range(4, 16):
                for y in range(5, 15):
                    image.putpixel((x, y), (20, 40, 60))
            image.save(source)
            journal = DiagnosticJournal(root, app_version="3.0")
            settings = {
                "output_dir": str(output_dir),
                "upscale": False,
                "upscale_after": False,
                "unsharp_enabled": False,
                "remove_bg": False,
                "edge_shrink_enabled": False,
                "trim_enabled": True,
                "trim_mode": "white",
                "export_300_dpi": True,
                "kie_api_key": "sk-secret-value",
            }
            request = SimpleNamespace(
                mode="mode2_process",
                work_dir=str(root),
                settings=settings,
                generated_prompts=[],
                selected_files=[str(source)],
            )
            session = RunQueueSession(
                request,
                ProjectMode.PROCESSING,
                diagnostic_journal=journal,
            )
            worker = main.WorkerThread(
                "mode2_process",
                str(root),
                settings,
                selected_files=[str(source)],
            )
            worker.progress.connect(session.handle_progress)
            worker.progress_value.connect(session.handle_progress_value)
            worker._mode2_process_files(emit_final=False)
            session.handle_finished()
            output = next(output_dir.glob("*.png"))

            events = list(reversed(journal.read_events()))
            started = next(event for event in events if event["event"] == "run_started")
            succeeded = next(event for event in events if event["event"] == "item_succeeded")
            finished = next(event for event in events if event["event"] == "run_finished")
            stages = [
                event["details"]
                for event in events
                if event["event"] == "stage_updated"
            ]

            self.assertEqual(
                started["details"]["enabled_stages"],
                ["trim", "export_300_dpi", "export"],
            )
            self.assertEqual(started["details"]["trim_mode"], "white")
            self.assertIn(
                {"mode": "processing", "item_index": 1, "stage": "export_300_dpi", "status": "complete"},
                stages,
            )
            self.assertEqual(succeeded["details"]["filename"], output.name)
            self.assertEqual(succeeded["details"]["output_bytes"], output.stat().st_size)
            self.assertEqual(finished["details"]["counts"]["succeeded"], 1)
            self.assertIn("elapsed_ms", finished["details"])
            raw = journal.session_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), raw)
            self.assertNotIn("sk-secret-value", raw)

    def test_explicit_results_exit_records_what_screen_changed_and_why(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            view = V3ApplicationView(
                draft_path=root / "project_state.json",
                diagnostic_journal=journal,
            )
            view._handle_mode_selected(ProjectMode.PROCESSING.value)
            view.shell.state.set_step(StepId.RESULTS)
            view.shell.refresh()

            view.shell.finish_requested.emit(ProjectMode.PROCESSING.value)

            events = journal.read_events()
            finished = next(event for event in events if event["event"] == "workflow_finished")
            screen = next(
                event
                for event in events
                if event["event"] == "screen_changed"
                and event.get("screen") == "mode_selection"
                and event.get("details", {}).get("status") == "workflow_finished"
            )
            self.assertEqual(finished["screen"], "results")
            self.assertEqual(finished["details"]["mode"], "processing")
            self.assertEqual(finished["details"]["status"], "explicit_user_action")
            self.assertEqual(screen["screen"], "mode_selection")
            view.close()

    def test_mode_switch_screen_transitions_are_recorded_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            view = V3ApplicationView(diagnostic_journal=journal)
            view._handle_mode_selected(ProjectMode.PROCESSING.value)
            view.show_mode_switcher()
            view.cancel_mode_switch()

            transitions = [
                event
                for event in reversed(journal.read_events())
                if event["event"] == "screen_changed"
            ]
            self.assertEqual(
                [event["details"]["status"] for event in transitions[-3:]],
                ["project_opened", "mode_switch_requested", "mode_switch_cancelled"],
            )
            self.assertEqual(
                [event["screen"] for event in transitions[-3:]],
                ["wizard", "mode_selection", "wizard"],
            )
            view.close()

    def test_local_processing_failure_keeps_safe_technical_reason(self) -> None:
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
            session.handle_progress("[1/1] Обработка файла: private-source.png")
            session.handle_progress(
                "Ошибка: Local rembg is not available: No module named 'onnxruntime'"
            )

            payload = next(
                event for event in journal.read_events()
                if event["event"] == "item_failed"
            )
            self.assertEqual(payload["event"], "item_failed")
            self.assertEqual(payload["details"]["reason"], "processing_error")
            self.assertEqual(
                payload["details"]["error_message"],
                "Local rembg is not available: No module named 'onnxruntime'",
            )
            self.assertNotIn(str(root), journal.session_path.read_text(encoding="utf-8"))

    def test_item_failure_keeps_safe_provider_task_and_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            request = SimpleNamespace(
                work_dir=str(root),
                settings={"output_dir": str(root / "output")},
                generated_prompts=[],
                selected_files=[str(root / "source.png")],
            )
            session = RunQueueSession(
                request,
                ProjectMode.PROCESSING,
                diagnostic_journal=journal,
            )
            session.handle_progress("[1/1] Обработка файла: source.png")
            session.handle_progress(
                "Ошибка: KIE task failed [taskId=task_safe_123; errorCode=500; "
                "message=provider failed; api_key=sk-secret-value]"
            )

            failed = next(
                event for event in journal.read_events()
                if event["event"] == "item_failed"
            )
            self.assertEqual(failed["details"]["task"], "task_safe_123")
            self.assertEqual(failed["details"]["error_code"], "500")
            self.assertEqual(failed["details"]["error_message"], "provider failed")
            self.assertNotIn("sk-secret-value", journal.session_path.read_text(encoding="utf-8"))

    def test_fatal_local_processing_failure_keeps_safe_technical_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            journal = DiagnosticJournal(root, app_version="3.0")
            request = SimpleNamespace(
                work_dir=str(root),
                settings={"output_dir": str(root / "output")},
                generated_prompts=[],
                selected_files=[str(root / "source.png")],
            )
            session = RunQueueSession(
                request,
                ProjectMode.PROCESSING,
                diagnostic_journal=journal,
            )
            session.handle_progress("[1/1] Обработка файла: source.png")
            session.handle_fatal_error(
                "Local rembg is not available: DLL load failed; api_key=sk-secret-value"
            )

            failed = next(
                event for event in journal.read_events()
                if event["event"] == "item_failed"
            )
            run_failed = next(
                event for event in journal.read_events()
                if event["event"] == "run_failed"
            )
            self.assertEqual(
                failed["details"]["error_message"],
                "Local rembg is not available: DLL load failed; api_key=[hidden]",
            )
            self.assertEqual(run_failed["details"]["counts"]["failed"], 1)
            self.assertIn("elapsed_ms", run_failed["details"])
            self.assertNotIn("sk-secret-value", journal.session_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
