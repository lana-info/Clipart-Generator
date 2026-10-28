from studio_workflow_host import WorkflowHost
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QEvent, QObject, QPointF, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication

from license_client import LicenseError
from v3_clipart_flow import ClipartRunRequest, install_clipart_flow
from v3_components import V3Button
from v3_processing_flow import install_processing_flow
from v3_project_state import (
    CommonProjectData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    StepId,
    route_for_mode,
)
from v3_run_queue import (
    RunItemStatus,
    RunQueueError,
    RunQueueSession,
    RunResultsPage,
    build_safe_run_report,
    export_safe_run_report,
    format_elapsed_duration,
    transparency_candidate_paths,
    _failure_reason,
)
from clipart_run_results import ClipartRunResultsExtension
from v3_wizard import AppShell


SECRET_PROMPT = "private prompt do not log"
SECRET_KEY = "secret-api-key-do-not-log"


def test_unclassified_failure_shows_its_reason_without_paths():
    """Owner 2026-10-27 (UP-14): the stub hid the real error; keep a short, path-free reason."""
    code, message = _failure_reason(
        r"[WinError 32] File is busy: 'C:\\Users\\owner\\Clipart\\output\\rose_ready.png'"
    )
    assert code == "processing_error"
    assert message.startswith("Не удалось завершить обработку файла: [WinError 32] File is busy")
    assert "Users" not in message and "rose_ready.png" in message
    assert _failure_reason("") == ("processing_error", "Не удалось завершить обработку файла.")


def test_failure_reason_explains_kie_credits_and_oversized_reference():
    assert _failure_reason(
        "KIE createTask rejected [errorCode=402; message=Insufficient Credits]"
    ) == (
        "insufficient_credits",
        "Недостаточно средств на балансе KIE. Пополните баланс KIE и повторите запуск.",
    )
    assert _failure_reason(
        "KIE task failed [errorCode=413; message=reference image exceeds 10MB]"
    ) == (
        "reference_too_large",
        "Референс превышает допустимый размер 10 МБ. Уменьшите файл и повторите запуск.",
    )


class FakeWorker(QObject):
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    diagnostic = pyqtSignal(object)

    def __init__(self, **kwargs):
        super().__init__()
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        self.stop_after_current = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        self.started = False

    def request_stop_after_current(self):
        self.stop_after_current = True

    def isRunning(self):
        return self.started


class WorkerFactory:
    def __init__(self):
        self.workers = []

    def __call__(self, **kwargs):
        worker = FakeWorker(**kwargs)
        self.workers.append(worker)
        return worker


class FakeMouseMoveEvent(QEvent):
    def __init__(self, position: QPointF):
        super().__init__(QEvent.Type.MouseMove)
        self._position = position

    def position(self) -> QPointF:
        return self._position


def generation_request(work_dir, count=3):
    return ClipartRunRequest(
        mode="mode1_generate_only",
        work_dir=str(work_dir),
        settings={"kie_api_key": SECRET_KEY},
        generated_prompts=[
            {
                "prompt": f"{SECRET_PROMPT} {index}",
                "references": [],
            }
            for index in range(1, count + 1)
        ],
    )


def processing_request(work_dir, sources):
    return ClipartRunRequest(
        mode="mode2_process",
        work_dir=str(work_dir),
        settings={},
        selected_files=[str(path) for path in sources],
    )


class V3RunQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        self.app.processEvents()

    def test_clipart_results_temporarily_hide_alpha_brush_editor(self):
        with tempfile.TemporaryDirectory(prefix="v3-results-alpha-hidden-") as temp:
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            page = RunResultsPage(state)
            session = RunQueueSession(generation_request(temp, count=1), ProjectMode.CLIPART)
            page.set_session(session)
            page._selection_changed(0)

            self.assertFalse(page.SHOW_TRANSPARENCY_EDITOR)
            self.assertTrue(page.transparency_preview.isHidden())
            self.assertTrue(page.save_corrected_button.isHidden())
            self.assertTrue(page.save_mask_button.isHidden())
            page.deleteLater()

    def test_clipart_results_open_the_dedicated_transparency_page_on_double_click(self):
        with tempfile.TemporaryDirectory(prefix="v3-results-alpha-page-") as temp:
            root = Path(temp)
            output = root / "output" / "flowers_ready.png"
            output.parent.mkdir(parents=True)
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(output)
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            page = RunResultsPage(state)
            session = RunQueueSession(
                generation_request(temp, count=1), ProjectMode.CLIPART
            )
            session.items[0].status = RunItemStatus.SUCCEEDED
            session.items[0].output_path = str(output)
            page.set_session(session)
            opened = []
            page.transparency_requested.connect(opened.append)

            page.queue.itemDoubleClicked.emit(page.queue.item(0))

            self.assertEqual(opened, [0])
            page.deleteLater()

    def test_terminal_clipart_results_offer_a_visible_transparency_button(self):
        with tempfile.TemporaryDirectory(prefix="v3-results-alpha-button-") as temp:
            root = Path(temp)
            output = root / "output" / "flowers_ready.png"
            output.parent.mkdir(parents=True)
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(output)
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            page = RunResultsPage(state)
            session = RunQueueSession(
                generation_request(temp, count=1), ProjectMode.CLIPART
            )
            session.items[0].status = RunItemStatus.SUCCEEDED
            session.items[0].output_path = str(output)
            session.handle_finished()
            page.set_session(session)
            page.queue.setCurrentRow(0)
            opened = []
            page.transparency_requested.connect(opened.append)

            self.assertEqual(
                page.check_transparency_button.text(),
                "Проверить прозрачность",
            )
            self.assertFalse(page.check_transparency_button.isHidden())
            page.check_transparency_button.click()

            self.assertEqual(opened, [0])
            page.deleteLater()

    def test_clipart_and_processing_routes_have_a_transparency_page_after_results(self):
        self.assertEqual(
            route_for_mode(ProjectMode.CLIPART)[-2:],
            (StepId.RESULTS, StepId.TRANSPARENCY),
        )
        self.assertEqual(
            route_for_mode(ProjectMode.PROCESSING)[-2:],
            (StepId.RESULTS, StepId.TRANSPARENCY),
        )
        self.assertNotIn(
            StepId.TRANSPARENCY,
            route_for_mode(ProjectMode.PINTEREST),
        )

    def test_clipart_controller_opens_editor_with_successful_outputs_and_returns(self):
        with tempfile.TemporaryDirectory(prefix="v3-alpha-controller-") as temp:
            root = Path(temp)
            output = root / "output" / "flowers_ready.png"
            output.parent.mkdir(parents=True)
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(output)
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            shell = AppShell(state)
            controller = install_clipart_flow(WorkflowHost(shell, "clipart"))
            session = RunQueueSession(
                generation_request(temp, count=1), ProjectMode.CLIPART
            )
            session.items[0].status = RunItemStatus.SUCCEEDED
            session.items[0].output_path = str(output)
            session.handle_finished()
            controller.run_queue.session = session
            controller.run_queue.page.set_session(session)

            controller.run_queue.page.transparency_requested.emit(0)

            editor = controller.pages[StepId.TRANSPARENCY]
            self.assertIs(shell.current_page, editor)
            self.assertEqual(editor.current_path, output)
            editor.focus_button.click()
            self.assertTrue(shell.sidebar.isHidden())
            editor.back_button.click()
            self.assertIs(shell.state.current_step, StepId.RESULTS)
            self.assertFalse(shell.sidebar.isHidden())
            shell.deleteLater()

    def test_clipart_failed_run_can_open_existing_ready_outputs_in_transparency_editor(self):
        with tempfile.TemporaryDirectory(prefix="v3-alpha-after-error-") as temp:
            root = Path(temp)
            existing_output = root / "output" / "previous_ready.png"
            existing_output.parent.mkdir(parents=True)
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(existing_output)
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            shell = AppShell(state)
            controller = install_clipart_flow(WorkflowHost(shell, "clipart"))
            session = RunQueueSession(
                generation_request(temp, count=1), ProjectMode.CLIPART
            )
            session.items[0].status = RunItemStatus.FAILED
            session.items[0].short_message = "Fal.ai HTTP 503"
            session.handle_finished()
            controller.run_queue.session = session
            controller.run_queue.page.set_session(session)

            self.assertFalse(
                controller.run_queue.page.check_transparency_button.isHidden()
            )
            controller.run_queue.page.check_transparency_button.click()

            editor = controller.pages[StepId.TRANSPARENCY]
            self.assertIs(shell.current_page, editor)
            self.assertTrue(os.path.samefile(editor.current_path, existing_output))
            shell.deleteLater()

    def test_transparency_candidates_reject_ready_symlink_outside_output(self):
        with tempfile.TemporaryDirectory(prefix="v3-alpha-output-boundary-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            external = root / "external.png"
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(external)
            escape = output / "escape_ready.png"
            try:
                escape.symlink_to(external)
            except OSError as error:
                self.skipTest(f"symlink is unavailable: {error}")
            session = RunQueueSession(
                generation_request(temp, count=1), ProjectMode.CLIPART
            )
            session.items[0].status = RunItemStatus.FAILED
            session.handle_finished()

            self.assertEqual(transparency_candidate_paths(session), [])

    def test_processing_controller_opens_the_same_transparency_editor(self):
        with tempfile.TemporaryDirectory(prefix="v3-processing-alpha-controller-") as temp:
            root = Path(temp)
            source = root / "source.png"
            output = root / "output" / "flowers_ready.png"
            output.parent.mkdir(parents=True)
            Image.new("RGB", (20, 20), (10, 20, 30)).save(source)
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(output)
            state = ProjectState(
                mode=ProjectMode.PROCESSING,
                common=CommonProjectData(work_dir=temp),
            )
            shell = AppShell(state)
            controller = install_processing_flow(WorkflowHost(shell, "processing"))
            session = RunQueueSession(
                processing_request(temp, [source]), ProjectMode.PROCESSING
            )
            session.items[0].status = RunItemStatus.SUCCEEDED
            session.items[0].output_path = str(output)
            session.handle_finished()
            controller.run_queue.session = session
            controller.run_queue.page.set_session(session)

            self.assertFalse(
                controller.run_queue.page.check_transparency_button.isHidden()
            )

            controller.run_queue.page.transparency_requested.emit(0)

            editor = controller.pages[StepId.TRANSPARENCY]
            self.assertIs(shell.current_page, editor)
            self.assertEqual(editor.current_path, output)
            editor.back_button.click()
            self.assertIs(shell.state.current_step, StepId.RESULTS)
            shell.deleteLater()

    def test_processing_failed_run_can_open_existing_ready_outputs_in_transparency_editor(self):
        with tempfile.TemporaryDirectory(prefix="v3-processing-alpha-after-error-") as temp:
            root = Path(temp)
            source = root / "source.png"
            existing_output = root / "output" / "previous_ready.png"
            existing_output.parent.mkdir(parents=True)
            Image.new("RGB", (20, 20), (10, 20, 30)).save(source)
            Image.new("RGBA", (20, 20), (10, 20, 30, 128)).save(existing_output)
            state = ProjectState(
                mode=ProjectMode.PROCESSING,
                common=CommonProjectData(work_dir=temp),
            )
            shell = AppShell(state)
            controller = install_processing_flow(WorkflowHost(shell, "processing"))
            session = RunQueueSession(
                processing_request(temp, [source]), ProjectMode.PROCESSING
            )
            session.items[0].status = RunItemStatus.FAILED
            session.items[0].short_message = "Не удалось декодировать входной файл"
            session.handle_finished()
            controller.run_queue.session = session
            controller.run_queue.page.set_session(session)

            self.assertFalse(
                controller.run_queue.page.check_transparency_button.isHidden()
            )
            controller.run_queue.page.check_transparency_button.click()

            editor = controller.pages[StepId.TRANSPARENCY]
            self.assertIs(shell.current_page, editor)
            self.assertTrue(os.path.samefile(editor.current_path, existing_output))
            shell.deleteLater()

    def test_elapsed_duration_is_human_readable(self):
        self.assertEqual(format_elapsed_duration(45), "45 секунд")
        self.assertEqual(format_elapsed_duration(93), "1 мин 33 сек")
        self.assertEqual(format_elapsed_duration(3848), "1 ч 4 мин 8 сек")

    def test_structured_diagnostic_is_correlated_and_ordered(self):
        with tempfile.TemporaryDirectory(prefix="v3-structured-diagnostic-") as temp:
            root = Path(temp)
            journal = Mock()
            session = RunQueueSession(
                generation_request(root, count=2),
                ProjectMode.CLIPART,
                diagnostic_journal=journal,
            )

            session.handle_diagnostic(
                {
                    "event": "provider_task_polled",
                    "provider": "kie",
                    "model": "gpt-image-2-text-to-image",
                    "task": "task-456",
                    "provider_state": "waiting",
                    "poll_attempt": 2,
                    "item_index": 2,
                    "item_total": 999,
                    "attempt": 999,
                    "prompt": SECRET_PROMPT,
                }
            )

            call = journal.record_structured.call_args
            event = call.args[0]
            self.assertEqual(call.kwargs["operation_id"], session.operation_id)
            self.assertEqual(event["item_index"], 2)
            self.assertEqual(event["item_total"], 2)
            self.assertEqual(event["attempt"], 1)
            self.assertIn("event=provider_task_polled", session.technical_log)
            self.assertIn("task=task-456", session.technical_log)
            self.assertNotIn(SECRET_PROMPT, session.technical_log)

    def test_worker_diagnostic_signal_reaches_only_active_session(self):
        with tempfile.TemporaryDirectory(prefix="v3-worker-diagnostic-") as temp:
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            state.clipart.prompts = [PromptEntry(SECRET_PROMPT)]
            state.clipart.operations.upscale_before = False
            state.clipart.operations.remove_background = False
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            factory = WorkerFactory()
            controller = install_clipart_flow(WorkflowHost(shell, 'clipart', runtime_settings_provider=lambda: {'kie_api_key': SECRET_KEY}, worker_factory=factory, authorization_provider=Mock(return_value=None)))
            shell.go_next()
            worker = factory.workers[0]

            worker.diagnostic.emit(
                {
                    "event": "provider_task_polled",
                    "provider": "kie",
                    "task": "active-task",
                    "provider_state": "waiting",
                    "item_index": 1,
                }
            )
            self.app.processEvents()

            self.assertIn("task=active-task", controller.run_queue.session.technical_log)
            shell.close()
            shell.deleteLater()

    def test_indexed_worker_progress_is_authoritative_over_legacy_text(self):
        with tempfile.TemporaryDirectory(prefix="v3-indexed-progress-") as temp:
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            state.clipart.prompts = [
                PromptEntry(f"{SECRET_PROMPT} one"),
                PromptEntry(f"{SECRET_PROMPT} two"),
            ]
            state.clipart.operations.upscale_before = False
            state.clipart.operations.remove_background = False
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            factory = WorkerFactory()
            controller = install_clipart_flow(WorkflowHost(shell, 'clipart', runtime_settings_provider=lambda: {'kie_api_key': SECRET_KEY}, worker_factory=factory, authorization_provider=Mock(return_value=None)))
            shell.go_next()
            worker = factory.workers[0]

            worker.item_progress.emit(
                {
                    "item_index": 2,
                    "total_items": 2,
                    "stage": "generation",
                    "status": "running",
                }
            )
            worker.progress.emit("[1/2] Генерация")
            worker.progress_value.emit(95)
            self.app.processEvents()

            session = controller.run_queue.session
            self.assertIs(session.items[0].status, RunItemStatus.PENDING)
            self.assertEqual(session.progress_percent, 0)
            self.assertIs(session.items[1].status, RunItemStatus.RUNNING)
            shell.close()
            shell.deleteLater()

    def test_structured_cancel_terminal_closes_all_parallel_rows(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-parallel-cancel-") as temp:
            session = RunQueueSession(
                generation_request(temp, count=4),
                ProjectMode.CLIPART,
            )
            for index in range(1, 4):
                session.handle_item_progress(
                    {
                        "item_index": index,
                        "total_items": 4,
                        "stage": "generation",
                        "status": "running",
                    }
                )
            native = Mock()
            self.assertTrue(
                session.request_stop_after_current(
                    immediate_stop=Mock(),
                    native_after_current=native,
                )
            )
            session.handle_diagnostic(
                {
                    "event": "run_finished",
                    "outcome": "cancelled",
                    "status": "cancelled",
                    "item_index": 1,
                }
            )

            native.assert_called_once_with()
            self.assertFalse(session.running)
            self.assertTrue(
                all(item.status is RunItemStatus.CANCELLED for item in session.items)
            )

    def test_retry_diagnostic_maps_local_index_to_original_item(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-retry-diagnostic-") as temp:
            journal = Mock()
            session = RunQueueSession(
                generation_request(temp, count=5),
                ProjectMode.CLIPART,
                diagnostic_journal=journal,
            )
            session.active_order = [2, 4]
            session.items[2].attempts = 2
            session.items[4].attempts = 3

            session.handle_diagnostic(
                {
                    "event": "provider_task_polled",
                    "provider": "kie",
                    "task": "retry-task",
                    "item_index": 1,
                }
            )

            event = journal.record_structured.call_args.args[0]
            self.assertEqual(event["item_index"], 3)
            self.assertEqual(event["attempt"], 2)

    def test_malformed_structured_diagnostic_never_breaks_run(self):
        with tempfile.TemporaryDirectory(prefix="v3-malformed-diagnostic-") as temp:
            session = RunQueueSession(
                processing_request(temp, [Path(temp) / "input.png"]),
                ProjectMode.PROCESSING,
                diagnostic_journal=Mock(record_structured=Mock(side_effect=OSError("disk"))),
            )

            session.handle_diagnostic({"event": "unknown", "raw_response": object()})

            self.assertTrue(session.running)
            self.assertIn("event=diagnostic_parse_failed", session.technical_log)

    def test_all_routes_include_the_shared_results_step(self):
        for mode in ProjectMode:
            with self.subTest(mode=mode):
                self.assertIn(StepId.RESULTS, route_for_mode(mode))
        self.assertEqual(
            route_for_mode(ProjectMode.PROCESSING)[-2:],
            (StepId.RESULTS, StepId.TRANSPARENCY),
        )
        self.assertIs(route_for_mode(ProjectMode.PINTEREST)[-1], StepId.RESULTS)

    def test_processing_item_start_is_not_reported_as_generation(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-processing-stage-") as temp:
            session = RunQueueSession(
                processing_request(temp, [Path(temp) / "input.png"]),
                ProjectMode.PROCESSING,
            )
            session.handle_progress("[1/1] Обработка файла: input.png")
            self.assertEqual(session.current_stage, "processing")
            self.assertNotIn("generation", session.items[0].stage_statuses)

    def test_generated_output_run_workspace_is_trusted(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-generated-path-") as temp:
            root = Path(temp)
            run_dir = root / ".run" / "current-run"
            run_dir.mkdir(parents=True)
            generated = run_dir / "gen_001.png"
            Image.new("RGB", (4, 4), "purple").save(generated)
            session = RunQueueSession(
                generation_request(root, count=1),
                ProjectMode.CLIPART,
            )
            session.handle_progress("[1/1] Генерация")
            session.handle_progress(f"Сгенерировано: {generated}")

            self.assertEqual(session.items[0].source_path, str(generated.resolve()))
            self.assertEqual(session.items[0].stage_statuses["generation"], "complete")

    def test_missing_processing_file_is_marked_failed(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-missing-file-") as temp:
            session = RunQueueSession(
                processing_request(temp, [Path(temp) / "README.jpg"]),
                ProjectMode.PROCESSING,
            )
            session.handle_progress("[1/1] Обработка файла: README.jpg")
            session.handle_progress(f"Файл не найден: {Path(temp) / 'README.jpg'}")
            self.assertEqual(session.items[0].status, RunItemStatus.FAILED)
            self.assertEqual(session.items[0].short_message, "Исходный файл недоступен.")

    def test_failure_does_not_hide_completed_items(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-partial-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            session = RunQueueSession(
                generation_request(root),
                ProjectMode.CLIPART,
            )

            session.handle_progress("[1/3] Генерация")
            session.handle_progress("  Удаление фона через model...")
            session.handle_progress("  Промежуточный без фона: internal")
            first = output / "first.png"
            Image.new("RGB", (8, 8), "red").save(first)
            session.handle_progress(f"  Итог сохранён: {first}")
            session.handle_progress("[2/3] Генерация")
            session.handle_progress("  Ошибка: provider request failed")
            session.handle_progress("[3/3] Генерация")
            third = output / "third.png"
            Image.new("RGB", (8, 8), "blue").save(third)
            session.handle_progress(f"  Итог сохранён: {third}")
            session.handle_finished()

            self.assertEqual(
                [item.status for item in session.items],
                [
                    RunItemStatus.SUCCEEDED,
                    RunItemStatus.FAILED,
                    RunItemStatus.SUCCEEDED,
                ],
            )
            self.assertTrue(first.is_file())
            self.assertTrue(third.is_file())
            self.assertEqual(session.counts()["succeeded"], 2)
            self.assertEqual(
                session.items[0].stage_statuses["background_removal"],
                "complete",
            )
            self.assertEqual(
                session.items[0].stage_statuses["export"],
                "complete",
            )
            self.assertEqual(
                session.items[1].stage_statuses["generation"],
                "failed",
            )

    def test_fatal_error_preserves_success_and_marks_only_remaining(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-fatal-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            session = RunQueueSession(
                generation_request(root),
                ProjectMode.CLIPART,
            )
            session.handle_progress("[1/3] Генерация")
            session.handle_progress("  Удаление фона через model...")
            session.handle_progress("  Промежуточный без фона: internal")
            first = output / "first.png"
            Image.new("RGB", (4, 4), "green").save(first)
            session.handle_progress(f"Итог сохранён: {first}")
            session.handle_progress("[2/3] Генерация")
            session.handle_fatal_error("HTTP provider failure")

            self.assertIs(
                session.items[0].status,
                RunItemStatus.SUCCEEDED,
            )
            self.assertTrue(
                all(
                    item.status is RunItemStatus.FAILED
                    for item in session.items[1:]
                )
            )
            self.assertTrue(first.is_file())
            self.assertEqual(
                session.items[1].stage_statuses["generation"],
                "failed",
            )

    def test_stop_marker_closes_active_stages_as_cancelled(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-cancel-stage-") as temp:
            session = RunQueueSession(
                generation_request(temp, count=2),
                ProjectMode.CLIPART,
            )
            session.handle_progress("[1/2] Генерация")
            session.handle_progress("Удаление фона через model...")
            session.handle_progress("Остановлено пользователем")

            self.assertIs(
                session.items[0].status,
                RunItemStatus.CANCELLED,
            )
            self.assertEqual(
                session.items[0].stage_statuses,
                {
                    "background_removal": "cancelled",
                    "generation": "cancelled",
                },
            )
            self.assertIs(
                session.items[1].status,
                RunItemStatus.CANCELLED,
            )
            self.assertIn("event=run_cancelled", session.technical_log)
            self.assertIn("counts=", session.technical_log)
            self.assertIn("elapsed_ms=", session.technical_log)

    def test_stop_after_current_uses_native_boundary_and_cancels_pending(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-stop-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            session = RunQueueSession(
                generation_request(root),
                ProjectMode.CLIPART,
            )
            calls = []
            session.handle_progress("[1/3] Генерация")
            self.assertTrue(
                session.request_stop_after_current(
                    immediate_stop=lambda: calls.append("immediate"),
                    native_after_current=lambda: calls.append("native"),
                )
            )
            self.assertEqual(calls, ["native"])

            first = output / "first.png"
            Image.new("RGB", (4, 4), "green").save(first)
            session.handle_progress(f"Итог сохранён: {first}")
            session.handle_progress("Остановлено после текущего файла")

            self.assertIs(
                session.items[0].status,
                RunItemStatus.SUCCEEDED,
            )
            self.assertTrue(
                all(
                    item.status is RunItemStatus.CANCELLED
                    for item in session.items[1:]
                )
            )
            self.assertFalse(session.running)

    def test_fallback_stop_waits_for_current_terminal_event(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-fallback-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            session = RunQueueSession(
                generation_request(root, count=2),
                ProjectMode.CLIPART,
            )
            calls = []
            session.handle_progress("[1/2] Генерация")
            session.request_stop_after_current(
                immediate_stop=lambda: calls.append("stop"),
            )
            self.assertEqual(calls, [])
            result = output / "first.png"
            Image.new("RGB", (4, 4), "green").save(result)
            session.handle_progress(f"Итог сохранён: {result}")

            self.assertEqual(calls, ["stop"])
            self.assertIs(
                session.items[0].status,
                RunItemStatus.SUCCEEDED,
            )
            self.assertIs(
                session.items[1].status,
                RunItemStatus.CANCELLED,
            )

    def test_immediate_stop_cancels_current_and_pending_items_without_waiting(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-immediate-stop-") as temp:
            session = RunQueueSession(
                generation_request(temp, count=3),
                ProjectMode.CLIPART,
            )
            calls = []
            session.handle_progress("[1/3] Генерация")

            self.assertTrue(
                session.request_immediate_stop(
                    immediate_stop=lambda: calls.append("stop"),
                )
            )

            self.assertEqual(calls, ["stop"])
            self.assertFalse(session.running)
            self.assertTrue(
                all(item.status is RunItemStatus.CANCELLED for item in session.items)
            )
            self.assertIn("прервана пользователем", session.items[0].short_message)

    def test_generated_object_id_survives_queue_and_retry(self):
        with tempfile.TemporaryDirectory(prefix='v3-object-id-') as temp:
            request = generation_request(temp)
            request.generated_prompts[1]['object_id'] = 'object-2'
            session = RunQueueSession(request, ProjectMode.CLIPART)
            self.assertEqual(session.items[1].payload['object_id'], 'object-2')
            session.items[1].status = RunItemStatus.FAILED
            session.running = False
            retry = session.prepare_retry()
            self.assertEqual(retry.generated_prompts[0]['object_id'], 'object-2')

    def test_regenerate_selected_builds_request_only_for_chosen_items(self):
        with tempfile.TemporaryDirectory(prefix="v3-regenerate-") as temp:
            request = generation_request(temp, 4)
            request.generated_prompts[2]["object_id"] = "object-3"
            session = RunQueueSession(request, ProjectMode.CLIPART)
            session.running = False
            for item in session.items:
                item.status = RunItemStatus.SUCCEEDED
                item.output_path = str(Path(temp) / f"{item.index}.png")
            session.items[3].status = RunItemStatus.RUNNING
            self.assertEqual(session.regenerable_indices([0, 2, 3, 9]), [0, 2])
            preview = session.preview_regenerate([2, 0])
            self.assertEqual([entry["prompt"] for entry in preview.generated_prompts],
                             [f"{SECRET_PROMPT} 1", f"{SECRET_PROMPT} 3"])
            self.assertEqual(preview.generated_prompts[1]["object_id"], "object-3")
            self.assertEqual(preview.settings["task_item_indices"], [1, 3])
            self.assertTrue(preview.settings["overwrite_existing"])
            self.assertEqual(session.items[0].status, RunItemStatus.SUCCEEDED)  # preview changes nothing
            prepared = session.prepare_regenerate([2, 0])
            self.assertEqual(prepared, preview)
            self.assertTrue(session.running)
            self.assertEqual(session.items[0].status, RunItemStatus.PENDING)
            self.assertEqual(session.items[1].status, RunItemStatus.SUCCEEDED)  # untouched
            self.assertEqual(session.items[0].attempts, 2)

    def test_regenerated_prompt_gets_the_flat_background_rule_once(self):
        from v3_project_state import with_background_rule
        green = with_background_rule("A duck.", "green")
        self.assertIn("#00FF00", green)
        self.assertIn("checkerboard", green)
        self.assertEqual(with_background_rule(green, "green"), green)  # added only once
        self.assertEqual(with_background_rule("A duck.", ""), "A duck.")  # no key colour, nothing to add

    def test_regenerate_is_not_offered_for_file_queues_or_running_sessions(self):
        with tempfile.TemporaryDirectory(prefix="v3-regenerate-off-") as temp:
            running = RunQueueSession(generation_request(temp, 2), ProjectMode.CLIPART)
            self.assertEqual(running.regenerable_indices([0, 1]), [])  # still running
            source = Path(temp) / "a.png"
            Image.new("RGB", (4, 4), "white").save(source)
            files = RunQueueSession(processing_request(temp, [source]), ProjectMode.PROCESSING)
            files.running = False
            files.items[0].status = RunItemStatus.SUCCEEDED
            self.assertEqual(files.regenerable_indices([0]), [])
            self.assertIsNone(files.preview_regenerate([0]))

    def test_retry_request_contains_only_failed_private_payloads(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-retry-") as temp:
            request = generation_request(temp)
            request.generated_prompts[1]["result_kind"] = "pattern"
            request.generated_prompts[0]["chroma_key_color"] = "red"
            session = RunQueueSession(
                request,
                ProjectMode.CLIPART,
            )
            for index in range(1, 4):
                session.handle_progress(f"[{index}/3] Генерация")
                if index == 2:
                    session.handle_progress("Удаление фона через model...")
                    session.handle_progress("Ошибка: timeout")
                else:
                    output = Path(temp) / "output"
                    output.mkdir(exist_ok=True)
                    path = output / f"{index}.png"
                    Image.new("RGB", (4, 4), "white").save(path)
                    session.handle_progress(f"Итог сохранён: {path}")
            session.handle_finished()

            retry = session.prepare_retry()

            self.assertIsNotNone(retry)
            self.assertEqual(len(retry.generated_prompts), 1)
            self.assertEqual(retry.generated_prompts[0]["result_kind"], "pattern")
            self.assertEqual(session.items[0].payload["chroma_key_color"], "red")
            self.assertEqual(
                retry.generated_prompts[0]["prompt"],
                f"{SECRET_PROMPT} 2",
            )
            self.assertEqual(session.active_order, [1])
            self.assertEqual(session.items[1].attempts, 2)
            self.assertEqual(session.items[1].stage_statuses, {})
            self.assertEqual(session.progress_percent, 0)

    def test_fatal_kie_error_keeps_safe_task_diagnostics(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-kie-error-") as temp:
            journal = Mock()
            session = RunQueueSession(
                processing_request(temp, [Path(temp) / "input.png"]),
                ProjectMode.PROCESSING,
                diagnostic_journal=journal,
            )
            session.handle_progress("[1/1] Обработка файла")
            session.handle_fatal_error(
                "KIE task failed [taskId=task_recraft_123; errorCode=501; "
                "message=provider could not process image]"
            )

            failed_call = next(
                call for call in journal.record.call_args_list
                if call.args and call.args[0] == "item_failed"
            )
            details = failed_call.kwargs["details"]
            self.assertEqual(details["task"], "task_recraft_123")
            self.assertEqual(details["error_code"], "501")
            self.assertEqual(
                details["error_message"],
                "provider could not process image",
            )
            self.assertIn(
                'error_message="provider could not process image"',
                session.technical_log,
            )

    def test_existing_alpha_skip_marker_reaches_structured_journal(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-alpha-skip-") as temp:
            journal = Mock()
            session = RunQueueSession(
                generation_request(temp, count=1),
                ProjectMode.CLIPART,
                diagnostic_journal=journal,
            )

            session.handle_diagnostic(
                {
                    "event": "stage_finished",
                    "item_index": 1,
                    "item_total": 1,
                    "stage": "background_removal",
                    "provider": "local_chroma_key",
                    "model": "chroma-key",
                    "outcome": "skipped",
                    "status": "already_alpha",
                }
            )

            persisted = journal.record_structured.call_args.args[0]
            self.assertEqual(persisted["outcome"], "skipped")
            self.assertEqual(persisted["status"], "already_alpha")

    def test_manual_chroma_skip_preserves_file_without_claiming_success(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-manual-chroma-") as temp:
            root = Path(temp)
            output = root / "output" / "flowers_ready.png"
            output.parent.mkdir(parents=True)
            Image.new("RGBA", (20, 20), (0, 0, 255, 255)).save(output)
            session = RunQueueSession(
                generation_request(root, count=1),
                ProjectMode.CLIPART,
            )
            session.handle_progress("[1/1] Генерация")
            session.handle_progress(
                "  Этап обработки: background_removal; status=running"
            )
            session.handle_item_progress(
                {
                    "item_index": 1,
                    "total_items": 1,
                    "stage": "background_removal",
                    "status": "stage_skipped",
                    "message": "Требуется ручная коррекция прозрачности.",
                }
            )

            session.handle_item_progress(
                {
                    "item_index": 1,
                    "total_items": 1,
                    "stage": "export",
                    "status": "succeeded",
                    "output_path": str(output),
                }
            )

            item = session.items[0]
            self.assertIs(item.status, RunItemStatus.FAILED)
            self.assertEqual(item.output_path, str(output.resolve()))
            self.assertIn("не готов к экспорту", item.short_message)
            self.assertIn(output.resolve(), transparency_candidate_paths(session))

    def test_incomplete_processing_survives_both_save_protocols_and_editor(self):
        for stage, status in (("background_removal", "stage_skipped"),
                              ("upscale_after", "stage_failed")):
            for indexed_save in (False, True):
                with self.subTest(stage=stage, indexed_save=indexed_save), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    session = RunQueueSession(generation_request(root, count=1), ProjectMode.CLIPART)
                    output = session.output_dir / "image_ready.png"
                    output.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (20, 20), "white").save(output)
                    session.handle_progress("[1/1] Генерация")
                    session.handle_item_progress(dict(item_index=1, total_items=1,
                                                      stage=stage, status=status))
                    if indexed_save:
                        session.handle_item_progress(dict(item_index=1, total_items=1,
                            stage="export", status="succeeded", output_path=str(output)))
                    else:
                        session.handle_progress(f"Итог сохранён: {output}")
                    session.handle_finished()
                    self.assertIs(session.items[0].status, RunItemStatus.FAILED)
                    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
                    page.set_session(session)
                    self.assertEqual(page._export_paths(), [])
                    self.assertIn(output.resolve(), transparency_candidate_paths(session))
                    edited = root / "corrected.png"
                    Image.new("RGBA", (20, 20), (20, 30, 40, 128)).save(edited)
                    page.use_edited_output(output, edited)
                    self.assertEqual(session.items[0].output_path, str(edited.resolve()))
                    self.assertIs(session.items[0].status, RunItemStatus.FAILED)
                    self.assertEqual(page._export_paths(), [])
                    self.assertIn(edited.resolve(), transparency_candidate_paths(session))
                    page.close()

    def test_indexed_chroma_skip_is_attributed_to_the_correct_parallel_item(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-chroma-batch-") as temp:
            session = RunQueueSession(
                generation_request(temp, count=2),
                ProjectMode.CLIPART,
            )
            for index in (1, 2):
                session.handle_item_progress(
                    {
                        "item_index": index,
                        "total_items": 2,
                        "stage": "background_removal",
                        "status": "running",
                    }
                )

            session.handle_item_progress(
                {
                    "item_index": 1,
                    "total_items": 2,
                    "stage": "background_removal",
                    "status": "stage_skipped",
                    "message": "Требуется ручная коррекция прозрачности.",
                }
            )

            self.assertEqual(
                session.items[0].stage_statuses["background_removal"],
                "skipped",
            )
            self.assertEqual(
                session.items[1].stage_statuses["background_removal"],
                "running",
            )

    def test_terminal_kie_failure_has_no_output_and_requires_explicit_retry(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-kie-terminal-") as temp:
            root = Path(temp)
            session = RunQueueSession(
                generation_request(root, count=1),
                ProjectMode.CLIPART,
            )
            session.handle_progress("[1/1] Генерация")
            session.handle_diagnostic(
                {
                    "schema_version": 2,
                    "event": "provider_task_failed",
                    "severity": "error",
                    "outcome": "failed",
                    "summary": "Внешний сервис завершил задачу с ошибкой.",
                    "task": "task-terminal-422",
                    "provider": "kie",
                    "model": "flux-2/flex-text-to-image",
                    "stage": "generation",
                    "error_code": "422",
                    "error_message": "Please try again, or change your input files or prompt.",
                    "item_index": 1,
                    "item_total": 1,
                }
            )
            session.handle_fatal_error(
                "KIE task failed [taskId=task-terminal-422; errorCode=422; "
                "message=Please try again, or change your input files or prompt.]"
            )

            self.assertFalse(session.running)
            self.assertEqual(session.failed_indices, [0])
            self.assertIs(session.items[0].status, RunItemStatus.FAILED)
            self.assertEqual(session.items[0].output_path, "")
            self.assertFalse((root / "output").exists())
            self.assertEqual(session.items[0].attempts, 1)

            retry = session.prepare_retry()

            self.assertIsNotNone(retry)
            self.assertEqual(len(retry.generated_prompts), 1)
            self.assertEqual(session.items[0].attempts, 2)

    def test_technical_error_keeps_the_cause_but_redacts_secrets_and_paths(self):
        with tempfile.TemporaryDirectory(prefix="v3-safe-error-") as temp:
            private_path = Path(temp) / "private" / "model.onnx"
            session = RunQueueSession(
                processing_request(temp, [Path(temp) / "input.png"]),
                ProjectMode.PROCESSING,
            )
            session.handle_progress("[1/1] Обработка файла: input.png")
            session.handle_fatal_error(
                f"Local rembg DLL load failed at {private_path}; api_key={SECRET_KEY}"
            )

            self.assertIn("Local rembg DLL load failed", session.technical_log)
            self.assertIn("<path>/model.onnx", session.technical_log)
            self.assertNotIn(str(private_path), session.technical_log)
            self.assertNotIn(SECRET_KEY, session.technical_log)


    def test_untrusted_output_path_is_rejected_not_succeeded(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-path-") as temp:
            root = Path(temp)
            outside = root.parent / "outside-result.png"
            session = RunQueueSession(
                generation_request(root, count=1),
                ProjectMode.CLIPART,
            )
            session.handle_progress("[1/1] Генерация")
            session.handle_progress(f"Итог сохранён: {outside}")

            self.assertIs(
                session.items[0].status,
                RunItemStatus.FAILED,
            )
            self.assertEqual(session.items[0].output_path, "")
            self.assertIn(
                "reason=output_path_rejected",
                session.technical_log,
            )
            self.assertNotIn(str(outside), session.technical_log)

    def test_missing_or_directory_output_is_not_success(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-missing-output-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            for candidate in (output / "missing.png", output):
                with self.subTest(candidate=candidate.name):
                    session = RunQueueSession(
                        generation_request(root, count=1),
                        ProjectMode.CLIPART,
                    )
                    session.handle_progress("[1/1] Генерация")
                    session.handle_progress(f"Итог сохранён: {candidate}")
                    self.assertIs(
                        session.items[0].status,
                        RunItemStatus.FAILED,
                    )
                    self.assertEqual(session.items[0].output_path, "")

    def test_truncated_image_output_is_not_success(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-truncated-output-") as temp:
            root = Path(temp)
            output = root / "output"
            output.mkdir()
            truncated = output / "truncated.png"
            Image.new("RGBA", (100, 100), "white").save(truncated)
            truncated.write_bytes(truncated.read_bytes()[:50])
            session = RunQueueSession(
                generation_request(root, count=1),
                ProjectMode.CLIPART,
            )

            session.handle_progress("[1/1] Генерация")
            session.handle_progress(f"Итог сохранён: {truncated}")

            self.assertIs(session.items[0].status, RunItemStatus.FAILED)
            self.assertEqual(session.items[0].output_path, "")

    def test_report_and_technical_log_are_atomic_and_private(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-report-") as temp:
            root = Path(temp)
            source_dir = root / "private" / "source"
            source_dir.mkdir(parents=True)
            source = source_dir / "input.png"
            Image.new("RGB", (4, 4), "white").save(source)
            output = root / "output"
            output.mkdir()
            result = output / "result.png"
            Image.new("RGB", (4, 4), "black").save(result)
            session = RunQueueSession(
                processing_request(root, [source]),
                ProjectMode.PROCESSING,
            )
            session.handle_progress("[1/1] Обработка файла: input.png")
            session.handle_progress(f"Итог сохранён: {result}")
            session.handle_finished()

            report = build_safe_run_report(session)
            encoded = json.dumps(report, ensure_ascii=False)
            self.assertNotIn(str(source_dir), encoded)
            self.assertNotIn(SECRET_KEY, encoded)
            self.assertNotIn(SECRET_PROMPT, encoded)
            self.assertIn('"stages"', encoded)
            self.assertNotIn(str(source_dir), session.technical_log)

            destination = root / "run-report.json"
            destination.write_text("old", encoding="utf-8")
            export_safe_run_report(session, destination)
            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                report,
            )
            self.assertEqual(list(root.glob("*.tmp")), [])
            with self.assertRaises(RunQueueError):
                export_safe_run_report(session, root / "report.txt")
            with self.assertRaises(RunQueueError):
                export_safe_run_report(
                    session,
                    root / "missing" / "run-report.json",
                )

    def test_safe_report_keeps_selected_fal_upscale_model_and_scale(self):
        request = processing_request(".", ["source.png"])
        request.settings.update(
            {
                "upscale": True,
                "upscale_provider": "fal",
                "fal_upscale_model": "topaz/upscale/image/precision",
                "fal_upscale_scale": 4,
            }
        )
        session = RunQueueSession(request, ProjectMode.PROCESSING)

        report = build_safe_run_report(session)

        self.assertEqual(
            report["settings"]["fal_upscale_model"],
            "topaz/upscale/image/precision",
        )
        self.assertEqual(report["settings"]["fal_upscale_scale"], "4")

    def test_safe_report_normalizes_bria_to_fixed_two_x(self):
        request = processing_request(".", ["source.png"])
        request.settings.update(
            {
                "upscale": True,
                "upscale_provider": "fal",
                "fal_upscale_model": "bria/upscale/creative",
                "fal_upscale_scale": 4,
            }
        )
        session = RunQueueSession(request, ProjectMode.PROCESSING)

        report = build_safe_run_report(session)

        self.assertEqual(report["settings"]["fal_upscale_scale"], "2")

    def test_safe_report_keeps_bria_increase_resolution_scale(self):
        request = processing_request(".", ["source.png"])
        request.settings.update(
            {
                "upscale": True,
                "upscale_provider": "fal",
                "fal_upscale_model": "bria/increase-resolution",
                "fal_upscale_scale": 4,
            }
        )
        session = RunQueueSession(request, ProjectMode.PROCESSING)

        report = build_safe_run_report(session)

        self.assertEqual(report["settings"]["fal_upscale_scale"], "4")

    def test_safe_report_normalizes_topaz_transparent_to_fixed_four_x(self):
        request = processing_request(".", ["source.png"])
        request.settings.update(
            {
                "upscale": True,
                "upscale_provider": "fal",
                "fal_upscale_model": "topaz/upscale/image/transparent",
                "fal_upscale_scale": 2,
            }
        )
        session = RunQueueSession(request, ProjectMode.PROCESSING)

        report = build_safe_run_report(session)

        self.assertEqual(report["settings"]["fal_upscale_scale"], "4")

    def test_safe_report_normalizes_recraft_to_fixed_four_x(self):
        request = processing_request(".", ["source.png"])
        request.settings.update(
            {
                "upscale": True,
                "upscale_provider": "fal",
                "fal_upscale_model": "fal-ai/recraft/upscale/crisp",
                "fal_upscale_scale": 2,
            }
        )
        session = RunQueueSession(request, ProjectMode.PROCESSING)

        report = build_safe_run_report(session)

        self.assertEqual(report["settings"]["fal_upscale_scale"], "4")

    def test_controller_opens_results_and_retries_only_error(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-controller-") as temp:
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            state.clipart.prompts = [PromptEntry(SECRET_PROMPT)]
            state.clipart.operations.upscale_before = False
            state.clipart.operations.remove_background = False
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            factory = WorkerFactory()
            authorization = Mock(return_value=None)
            controller = install_clipart_flow(WorkflowHost(shell, 'clipart', runtime_settings_provider=lambda: {'kie_api_key': SECRET_KEY}, worker_factory=factory, authorization_provider=authorization))

            shell.go_next()
            self.assertIs(state.current_step, StepId.RESULTS)
            self.assertIsInstance(
                controller.pages[StepId.RESULTS],
                RunResultsPage,
            )
            worker = factory.workers[0]
            worker.progress.emit("[1/1] Генерация")
            worker.progress.emit("Ошибка: provider failed")
            worker.started = False
            worker.finished.emit("Готово (0/1)")
            self.app.processEvents()
            with patch.object(
                type(controller.shell),
                "authorize_run",
                side_effect=AssertionError("RunQueue must not authorize separately"),
            ):
                controller.run_queue.page.retry_button.click()
                self.app.processEvents()
            self.assertEqual(authorization.call_count, 2)

            self.assertEqual(len(factory.workers), 2)
            self.assertEqual(
                len(factory.workers[1].kwargs["generated_prompts"]),
                1,
            )
            retry_worker = factory.workers[1]
            worker.progress.emit("[1/1] Генерация")
            worker.error.emit("late old error")
            worker.finished.emit("late old finish")
            self.app.processEvents()
            self.assertIs(
                controller.run_queue.session.items[0].status,
                RunItemStatus.PENDING,
            )
            self.assertTrue(controller.run_queue.session.running)
            retry_worker.progress.emit("[1/1] Генерация")
            self.app.processEvents()
            self.assertIs(
                controller.run_queue.session.items[0].status,
                RunItemStatus.RUNNING,
            )
            log = controller.run_queue.session.technical_log
            self.assertNotIn(SECRET_PROMPT, log)
            self.assertNotIn(SECRET_KEY, log)
            shell.close()
            shell.deleteLater()

    def test_results_offer_only_restart_in_the_same_mode_when_terminal(self):
        with tempfile.TemporaryDirectory(prefix="v3-results-finish-") as temp:
            state = ProjectState(
                mode=ProjectMode.PROCESSING,
                common=CommonProjectData(work_dir=temp),
            )
            state.set_step(StepId.RESULTS)
            shell = AppShell(state)
            page = RunResultsPage(state)
            shell.set_step_page(ProjectMode.PROCESSING, StepId.RESULTS, page)
            session = RunQueueSession(
                processing_request(temp, [Path(temp) / "input.png"]),
                ProjectMode.PROCESSING,
            )
            page.set_session(session)
            shell.next_button.setFocus()
            shell.refresh()

            self.assertTrue(shell.next_button.isHidden())
            self.assertTrue(page.finish_button.isHidden())
            unexpected_finish: list[str] = []
            shell.finish_requested.connect(unexpected_finish.append)
            shell.go_next()
            self.assertEqual(unexpected_finish, [])

            output = Path(temp) / "output" / "input.png"
            output.parent.mkdir()
            Image.new("RGB", (4, 4), "white").save(output)
            session.handle_progress("[1/1] Обработка файла: input.png")
            session.handle_progress(f"Итог сохранён: {output}")
            session.handle_finished()

            self.assertTrue(page.finish_button.isHidden())
            self.assertFalse(page.process_more_button.isHidden()) if page.state.mode is not ProjectMode.CLIPART else self.assertTrue(page.process_more_button.isHidden())
            self.assertEqual(
                page.process_more_button.text(),
                "Начать заново в этом режиме",
            )
            shell.close()
            shell.deleteLater()

    def test_hover_preview_disappears_when_pointer_leaves_or_app_deactivates(self):
        with tempfile.TemporaryDirectory(prefix="v3-hover-preview-") as temp:
            root = Path(temp)
            image = root / "preview.png"
            Image.new("RGB", (8, 8), "purple").save(image)
            session = RunQueueSession(
                processing_request(root, [image]),
                ProjectMode.PROCESSING,
            )
            page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING))
            page.set_session(session)
            page.show()
            self.app.processEvents()

            page._show_item_preview(page.queue.item(0))
            self.assertTrue(page.preview_popup.isVisible())
            page.eventFilter(
                page.queue.viewport(),
                FakeMouseMoveEvent(QPointF(page.queue.viewport().rect().bottomRight())),
            )
            self.assertFalse(page.preview_popup.isVisible())

            page._show_item_preview(page.queue.item(0))
            self.assertTrue(page.preview_popup.isVisible())
            QApplication.sendEvent(
                page.queue.viewport(),
                QEvent(QEvent.Type.Leave),
            )
            self.assertFalse(page.preview_popup.isVisible())

            page._show_item_preview(page.queue.item(0))
            self.assertTrue(page.preview_popup.isVisible())
            page.eventFilter(
                page.queue,
                QKeyEvent(
                    QEvent.Type.KeyPress,
                    Qt.Key.Key_Escape,
                    Qt.KeyboardModifier.NoModifier,
                ),
            )
            self.assertFalse(page.preview_popup.isVisible())

            page._show_item_preview(page.queue.item(0))
            self.assertTrue(page.preview_popup.isVisible())
            page._application_state_changed(
                Qt.ApplicationState.ApplicationInactive
            )
            self.assertFalse(page.preview_popup.isVisible())

            page._show_item_preview(page.queue.item(0))
            self.assertTrue(page.preview_popup.isVisible())
            page.hide()
            self.app.processEvents()
            self.assertFalse(page.preview_popup.isVisible())
            page.close()

    def test_completion_dialog_summarizes_terminal_run(self):
        with tempfile.TemporaryDirectory(prefix="v3-completion-dialog-") as temp:
            root = Path(temp)
            source = root / "input.png"
            output = root / "output" / "input.png"
            output.parent.mkdir()
            Image.new("RGB", (8, 8), "white").save(source)
            Image.new("RGB", (8, 8), "white").save(output)
            session = RunQueueSession(
                processing_request(root, [source]),
                ProjectMode.PROCESSING,
            )
            page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING))
            page.set_session(session)
            session.handle_progress("[1/1] Обработка файла: input.png")
            session.handle_progress(f"Итог сохранён: {output}")
            session.handle_finished()
            self.app.processEvents()

            dialog = page._completion_dialog
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.isVisible())
            self.assertIn("Обработано: 1", dialog.summary_label.text())
            self.assertIn("Пропущено: 0", dialog.summary_label.text())
            self.assertIn("Время:", dialog.summary_label.text())
            self.assertTrue(dialog.open_folder_button.isEnabled())
            dialog.close()
            page.close()

    def test_restart_closes_old_completion_dialog_before_opening_first_step(self):
        with tempfile.TemporaryDirectory(prefix="v3-restart-dialog-") as temp:
            root = Path(temp)
            state = ProjectState(
                mode=ProjectMode.PROCESSING,
                common=CommonProjectData(work_dir=temp),
            )
            state.processing.selected_files = [str(root / "input.png")]
            state.set_step(StepId.RESULTS)
            shell = AppShell(state)
            controller = install_processing_flow(WorkflowHost(shell, 'processing', worker_factory=WorkerFactory()))
            session = controller.run_queue.start_new(
                processing_request(root, [root / "input.png"])
            )
            session.handle_fatal_error("failed")
            self.app.processEvents()
            dialog = controller.run_queue.page._completion_dialog
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.isVisible())

            controller.run_queue.process_more()
            self.app.processEvents()

            self.assertFalse(dialog.isVisible())
            self.assertIsNone(controller.run_queue.page._completion_dialog)
            self.assertEqual(state.current_step, StepId.FILES)
            shell.close()

    def test_retry_closes_the_previous_completion_dialog(self):
        with tempfile.TemporaryDirectory(prefix="v3-retry-dialog-") as temp:
            root = Path(temp)
            session = RunQueueSession(
                processing_request(root, [root / "input.png"]),
                ProjectMode.PROCESSING,
            )
            page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING))
            page.set_session(session)
            session.handle_fatal_error("failed")
            self.app.processEvents()
            dialog = page._completion_dialog
            self.assertIsNotNone(dialog)
            self.assertTrue(dialog.isVisible())

            self.assertIsNotNone(session.prepare_retry())
            self.app.processEvents()

            self.assertFalse(dialog.isVisible())
            self.assertIsNone(page._completion_dialog)
            page.close()

    def test_retry_is_not_the_main_button_while_another_action_is_main(self):
        with tempfile.TemporaryDirectory(prefix="v3-one-main-") as temp:
            root = Path(temp)
            session = RunQueueSession(
                processing_request(root, [root / "input.png"]),
                ProjectMode.PROCESSING,
            )
            page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING))
            page.set_session(session)
            session.handle_fatal_error("failed")
            self.app.processEvents()
            page.refresh_from_state()
            self.assertEqual(page.retry_button.property("variant"), "primary")
            page.primary_elsewhere = lambda: True
            page.refresh_from_state()
            self.assertEqual(page.retry_button.property("variant"), "secondary")
            page.close()

    def test_results_finish_signal_is_ignored_until_the_queue_is_terminal(self):
        with tempfile.TemporaryDirectory(prefix="v3-terminal-guard-") as temp:
            state = ProjectState(
                mode=ProjectMode.PROCESSING,
                common=CommonProjectData(work_dir=temp),
            )
            shell = AppShell(state)
            controller = install_processing_flow(WorkflowHost(shell, 'processing', worker_factory=WorkerFactory()))
            session = controller.run_queue.start_new(
                processing_request(temp, [Path(temp) / "input.png"])
            )
            finish_events: list[str] = []
            shell.finish_requested.connect(finish_events.append)

            controller.run_queue.page.finish_requested.emit()
            self.assertEqual(finish_events, [])

            session.handle_fatal_error("local processing failed")
            controller.run_queue.page.finish_requested.emit()
            self.assertEqual(finish_events, [ProjectMode.PROCESSING.value])
            shell.close()
            shell.deleteLater()

    def test_technical_log_is_ordered_and_identifies_the_exact_local_stages(self):
        with tempfile.TemporaryDirectory(prefix="v3-technical-log-") as temp:
            root = Path(temp)
            output = root / "output" / "result.png"
            output.parent.mkdir()
            Image.new("RGB", (4, 4), "white").save(output)
            request = ClipartRunRequest(
                mode="mode2_process",
                work_dir=str(root),
                settings={
                    "output_dir": str(output.parent),
                    "trim_enabled": True,
                    "trim_mode": "software_background",
                    "export_300_dpi": True,
                    "kie_api_key": SECRET_KEY,
                },
                selected_files=[str(root / "private-source.png")],
            )
            session = RunQueueSession(request, ProjectMode.PROCESSING)
            session.handle_progress("[1/1] Обработка файла: private-source.png")
            session.handle_progress("Trim по программному фону: 20x20 → 12x12")
            session.handle_progress("Установлен DPI 300 для result.png")
            session.handle_progress(f"Итог сохранён: {output}")
            session.handle_finished()

            log = session.technical_log
            self.assertIn("seq=1", log)
            self.assertIn(f"operation_id={session.operation_id}", log)
            self.assertIn("enabled_stages=trim,export_300_dpi,export", log)
            self.assertIn(
                "event=stage_updated item=1 stage=export_300_dpi status=complete",
                log,
            )
            self.assertIn('event=item_succeeded item=1 filename="result.png"', log)
            self.assertIn("event=run_finished", log)
            self.assertIn("elapsed_ms=", log)
            self.assertNotIn(str(root), log)
            self.assertNotIn(SECRET_KEY, log)

    def test_output_file_does_not_hide_a_failed_selected_stage(self):
        with tempfile.TemporaryDirectory(prefix="v3-stage-failed-") as temp:
            root = Path(temp)
            output = root / "output" / "result.png"
            output.parent.mkdir()
            Image.new("RGB", (4, 4), "white").save(output)
            request = ClipartRunRequest(
                mode="mode2_process",
                work_dir=str(root),
                settings={
                    "output_dir": str(output.parent),
                    "export_300_dpi": True,
                },
                selected_files=[str(root / "source.png")],
            )
            session = RunQueueSession(request, ProjectMode.PROCESSING)

            session.handle_progress("[1/1] Обработка файла: source.png")
            session.handle_progress("Не удалось установить DPI для result.png: save failed")
            session.handle_progress(f"Итог сохранён: {output}")
            session.handle_finished()

            self.assertIs(session.items[0].status, RunItemStatus.FAILED)
            self.assertEqual(session.items[0].output_path, str(output.resolve()))
            self.assertEqual(
                session.items[0].stage_statuses["export_300_dpi"],
                "failed",
            )
            self.assertIn("reason=stage_failed", session.technical_log)

    def test_technical_log_keeps_safe_cyrillic_output_filename(self):
        with tempfile.TemporaryDirectory(prefix="v3-cyrillic-output-") as temp:
            root = Path(temp)
            output = root / "output" / "Мой результат 01.PNG"
            output.parent.mkdir()
            Image.new("RGB", (4, 4), "white").save(output)
            session = RunQueueSession(
                processing_request(root, [root / "source.png"]),
                ProjectMode.PROCESSING,
            )
            session.handle_progress("[1/1] Обработка файла: source.png")
            session.handle_progress(f"Итог сохранён: {output}")

            self.assertIn(
                'filename="Мой результат 01.PNG"',
                session.technical_log,
            )

    def test_technical_log_redacts_secret_like_output_filename(self):
        with tempfile.TemporaryDirectory(prefix="v3-secret-output-") as temp:
            root = Path(temp)
            output = root / "output" / "sk-live-secret123_result.png"
            output.parent.mkdir()
            Image.new("RGB", (4, 4), "white").save(output)
            session = RunQueueSession(
                processing_request(root, [root / "source.png"]),
                ProjectMode.PROCESSING,
            )

            session.handle_progress("[1/1] Обработка файла: source.png")
            session.handle_progress(f"Итог сохранён: {output}")

            self.assertNotIn("sk-live-secret123", session.technical_log)
            self.assertIn("[hidden]", session.technical_log)

    def test_retry_does_not_start_worker_when_online_authorization_fails(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-license-retry-") as temp:
            state = ProjectState(
                mode=ProjectMode.CLIPART,
                common=CommonProjectData(work_dir=temp),
            )
            state.clipart.prompts = [PromptEntry(SECRET_PROMPT)]
            state.clipart.operations.upscale_before = False
            state.clipart.operations.remove_background = False
            state.set_step(StepId.REVIEW_RUN)
            shell = AppShell(state)
            factory = WorkerFactory()
            authorization = Mock(
                side_effect=[None, LicenseError("Сервер лицензий недоступен")]
            )
            controller = install_clipart_flow(WorkflowHost(shell, 'clipart', runtime_settings_provider=lambda: {'kie_api_key': SECRET_KEY}, worker_factory=factory, authorization_provider=authorization))

            shell.go_next()
            worker = factory.workers[0]
            worker.progress.emit("[1/1] Генерация")
            worker.progress.emit("Ошибка: provider failed")
            worker.started = False
            worker.finished.emit("Готово (0/1)")
            self.app.processEvents()
            controller.run_queue.page.retry_button.click()
            self.app.processEvents()

            self.assertEqual(authorization.call_count, 2)
            self.assertEqual(len(factory.workers), 1)
            self.assertFalse(controller.run_queue.session.running)
            shell.close()
            shell.deleteLater()

    def test_results_page_smoke_at_minimum_window_size(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-ui-") as temp:
            state = ProjectState(mode=ProjectMode.PROCESSING)
            session = RunQueueSession(
                generation_request(temp, count=2),
                ProjectMode.PROCESSING,
            )
            page = RunResultsPage(state)
            page.set_session(session)
            page.resize(740, 560)
            page.show()
            self.app.processEvents()

            self.assertTrue(page.isVisible())
            self.assertLessEqual(page.width(), 740)
            self.assertIs(page.action_bar.parentWidget(), page)
            self.assertIs(page.scroll_area.widget(), page.card)
            self.assertEqual(page.progress_bar.value(), 0)
            self.assertEqual(page.queue.count(), 2)
            self.assertIn("Ожидает запуска", page.processing_label.text())
            self.assertEqual(
                page.processing_label.property("state"),
                "",
            )
            self.assertIn(
                "Проверка пикселей:",
                page.pixel_evidence_label.text(),
            )
            self.assertTrue(page.stop_button.isEnabled())
            page.close()
            page.deleteLater()

    def test_results_page_marks_failed_item_with_error_state_and_user_text(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-error-ui-") as temp:
            state = ProjectState(mode=ProjectMode.PROCESSING)
            session = RunQueueSession(
                generation_request(temp, count=1),
                ProjectMode.PROCESSING,
            )
            item = session.items[0]
            item.status = RunItemStatus.FAILED
            item.short_message = "Изображение повреждено или имеет неподдерживаемый формат."
            page = RunResultsPage(state)
            page.set_session(session)
            page.queue.setCurrentRow(0)
            page._selection_changed(0)

            self.assertIn("⚠ Файл не обработан", page.processing_label.text())
            self.assertIn("неподдерживаемый формат", page.processing_label.text())
            self.assertEqual(page.processing_label.property("state"), "error")
            page.close()
            page.deleteLater()

    def test_results_page_prioritizes_plain_language_summary_and_accessible_previews(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-summary-ui-") as temp:
            state = ProjectState(mode=ProjectMode.PROCESSING)
            session = RunQueueSession(
                generation_request(temp, count=2),
                ProjectMode.PROCESSING,
            )
            page = RunResultsPage(state)
            page.set_session(session)
            page.show()
            self.app.processEvents()

            self.assertIn("Обработка выполняется", page.summary_label.text())
            self.assertIn("Обработано: 0", page.summary_label.text())
            self.assertIn("Время:", page.summary_label.text())
            self.assertIn("идёт обработка", page._stage_label("processing"))
            self.assertIn("удаляется фон", page._stage_label("background_removal"))
            self.assertIn("очищается край", page._stage_label("edge_cleanup"))
            self.assertFalse(page.viewer.isVisible())
            result_button_texts = {
                button.text() for button in page.findChildren(V3Button)
            }
            self.assertNotIn("Диагностика", result_button_texts)
            self.assertEqual(page.queue.minimumHeight(), 360)
            self.assertEqual(page.open_folder_button.accessibleName(), "Открыть папку с результатами")
            page.close()
            page.deleteLater()

    def test_real_worker_stops_between_files_and_preserves_sources(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="v3-worker-stop-") as temp:
            root = Path(temp)
            first = root / "first.png"
            second = root / "second.png"
            Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(first)
            Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(second)
            before = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (first, second)
            }
            worker = WorkerThread(
                mode="mode2_process",
                work_dir=str(root),
                settings={
                    "upscale": False,
                    "upscale_after": False,
                    "remove_bg": False,
                    "unsharp_enabled": False,
                    "edge_shrink_enabled": False,
                    "trim_enabled": True,
                    "trim_mode": "alpha",
                },
                selected_files=[str(first), str(second)],
            )
            messages = []

            def capture(message):
                messages.append(message)
                if "Итог сохранён:" in message:
                    worker.request_stop_after_current()

            worker.progress.connect(capture)
            worker._mode2_process_files()

            outputs = list((root / "output").glob("*.png"))
            after = {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (first, second)
            }
            self.assertEqual(len(outputs), 1)
            self.assertEqual(before, after)
            self.assertTrue(
                any(
                    "Остановлено после текущего файла" in message
                    for message in messages
                )
            )

    def test_real_qthread_trim_and_dpi_finishes_in_results_state(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="v3-worker-qthread-") as temp:
            root = Path(temp)
            source = root / "source.png"
            image = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
            for x in range(3, 9):
                for y in range(2, 10):
                    image.putpixel((x, y), (230, 40, 30, 255))
            image.save(source)
            request = processing_request(root, [source])
            request.settings.update(
                {
                    "upscale": False,
                    "upscale_after": False,
                    "remove_bg": False,
                    "unsharp_enabled": False,
                    "edge_shrink_enabled": False,
                    "trim_enabled": True,
                    "trim_mode": "alpha",
                    "export_300_dpi": True,
                }
            )
            session = RunQueueSession(request, ProjectMode.PROCESSING)
            worker = WorkerThread(**request.worker_kwargs())
            worker.progress.connect(session.handle_progress)
            worker.progress_value.connect(session.handle_progress_value)
            worker.completed.connect(session.handle_finished)
            worker.error.connect(session.handle_fatal_error)

            worker.start()
            self.assertTrue(worker.wait(10_000))
            self.app.processEvents()

            self.assertFalse(session.running)
            self.assertIs(session.items[0].status, RunItemStatus.SUCCEEDED)
            output = Path(session.items[0].output_path)
            self.assertTrue(output.is_file())
            with Image.open(output) as result:
                self.assertEqual(result.size, (6, 8))
                self.assertAlmostEqual(result.info["dpi"][0], 300, delta=1)

    def test_real_worker_keeps_business_completion_separate_from_qthread_finished(self):
        from main import WorkerThread

        with tempfile.TemporaryDirectory(prefix="v3-worker-lifecycle-") as temp:
            worker = WorkerThread(
                mode="mode2_process",
                work_dir=temp,
                settings={
                    "upscale": False,
                    "remove_bg": False,
                    "trim_enabled": True,
                },
                selected_files=[],
            )
            completions = []
            thread_stops = []
            worker.completed.connect(completions.append)
            worker.finished.connect(lambda: thread_stops.append(True))

            worker.start()
            self.assertTrue(worker.wait(10_000))
            self.app.processEvents()

            self.assertEqual(len(completions), 1)
            self.assertEqual(thread_stops, [True])

    def test_open_folder_uses_only_the_session_output_directory(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-open-") as temp:
            root = Path(temp)
            (root / "output").mkdir()
            state = ProjectState(mode=ProjectMode.CLIPART)
            page = RunResultsPage(state)
            session = RunQueueSession(
                generation_request(root, count=1),
                ProjectMode.CLIPART,
            )
            page.set_session(session)
            with patch(
                "v3_run_queue.QDesktopServices.openUrl",
                return_value=True,
            ) as opener:
                page._open_folder()
            url = opener.call_args.args[0]
            self.assertTrue(url.isLocalFile())
            self.assertEqual(
                Path(url.toLocalFile()).resolve(),
                (root / "output").resolve(),
            )


def test_run_results_alpha_qc_checks_only_transparent_intent(tmp_path):
    app = QApplication.instance() or QApplication([])
    from v3_run_queue import RunItem
    clipart = tmp_path / 'clipart.png'
    surface = tmp_path / 'background.png'
    Image.new('RGBA', (20, 20), (10, 20, 30, 255)).save(clipart)
    Image.new('RGB', (20, 20), (10, 20, 30)).save(surface)
    state = ProjectState(mode=ProjectMode.CLIPART)
    page = RunResultsPage(
        state, results_extension=ClipartRunResultsExtension()
    )
    page.session = type('Session', (), {
        'items': [
            RunItem(1, 'clipart', status=RunItemStatus.SUCCEEDED, output_path=str(clipart),
                    payload={'result_kind': 'clipart', 'chroma_key_color': 'blue'}),
            RunItem(2, 'background', status=RunItemStatus.SUCCEEDED, output_path=str(surface),
                    payload={'result_kind': 'background'}),
        ]
    })()
    reports = page._alpha_qc_reports([clipart.resolve(), surface.resolve()])
    assert [Path(report.path) for report in reports] == [clipart.resolve()]
    assert reports[0].status == 'block'
    assert reports[0].issues[0].code == 'no_transparency'
    page.close()


def test_run_results_quality_fix_maps_output_path_back_to_item(tmp_path):
    app = QApplication.instance() or QApplication([])
    from v3_run_queue import RunItem
    output = tmp_path / 'clipart.png'
    Image.new('RGBA', (20, 20), (10, 20, 30, 128)).save(output)
    state = ProjectState(mode=ProjectMode.CLIPART)
    page = RunResultsPage(state)
    page.session = type('Session', (), {
        'items': [RunItem(1, 'clipart', status=RunItemStatus.SUCCEEDED,
                          output_path=str(output), payload={'result_kind': 'clipart'})]
    })()
    opened = []
    page.transparency_requested.connect(opened.append)
    page._request_quality_fix(str(output.resolve()))
    assert opened == [0]
    page.close()


def test_run_results_requests_interior_opening_qc_for_wreath_role_only(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from v3_run_queue import RunItem
    from studio_clipart_recipe import ClipartRecipe
    from studio_clipart_objects import fill_recipe
    from studio_alpha_qc import AlphaQcReport

    recipe = ClipartRecipe(theme='Holiday')
    recipe.total = 4
    recipe.counts = dict(hero=1, composition=0, wreath=1, border=2, decor=0)
    recipe.objects = fill_recipe([], recipe.counts)
    hero = next(item for item in recipe.objects if item['role'] == 'hero')
    wreath = next(item for item in recipe.objects if item['role'] == 'wreath')
    borders = [item for item in recipe.objects if item['role'] == 'border']
    borders[0]['name'] = 'Decorative frame'
    borders[1]['name'] = 'Floral border'
    cases = [('hero', hero), ('wreath', wreath), ('frame', borders[0]), ('border', borders[1])]
    paths = {}
    items = []
    for index, (label, obj) in enumerate(cases, 1):
        path = tmp_path / f'{label}.png'
        Image.new('RGBA', (20, 20), (0, 0, 0, 0)).save(path)
        paths[label] = path
        items.append(RunItem(index, label, status=RunItemStatus.SUCCEEDED, output_path=str(path),
                             payload={'result_kind': 'clipart', 'object_id': obj['id']}))
    state = ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.recipe = recipe.to_dict()
    page = RunResultsPage(
        state, results_extension=ClipartRunResultsExtension()
    )
    page.session = type('Session', (), {'items': items})()
    seen = {}
    def fake(path, **kwargs):
        seen[Path(path).name] = kwargs.get('expect_interior_opening')
        return AlphaQcReport(str(path), 'ok', ())
    monkeypatch.setattr('studio_alpha_qc.inspect_alpha_png', fake)

    page._alpha_qc_reports([path.resolve() for path in paths.values()])

    assert seen == {
        'hero.png': False, 'wreath.png': True, 'frame.png': True, 'border.png': False,
    }
    page.close()


def test_corrected_generated_image_finishes_locally_without_generation_or_upscale(tmp_path):
    import main
    app = QApplication.instance() or QApplication([])
    request = generation_request(tmp_path, count=1)
    request.settings.update(upscale=False, remove_bg=True, remove_bg_provider='local_chroma_key',
                            upscale_after=True, upscale_after_provider='kie',
                            unsharp_enabled=False, edge_shrink_enabled=False,
                            trim_enabled=False, export_300_dpi=False)
    session = RunQueueSession(request, ProjectMode.CLIPART)
    output = session.output_dir / 'image_ready.png'
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (64, 64), 'white').save(output)
    session.handle_diagnostic(dict(event='stage_finished', item_index=1, item_total=1,
                                  stage='upscale_after', outcome='succeeded'))
    session.handle_item_progress(dict(item_index=1, total_items=1,
                                      stage='alpha_validation', status='stage_failed'))
    session.handle_item_progress(dict(item_index=1, total_items=1, stage='export',
                                      status='succeeded', output_path=str(output)))
    session.handle_finished()
    page = RunResultsPage(ProjectState(mode=ProjectMode.CLIPART))
    page.set_session(session)
    edited = tmp_path / 'corrected.png'
    image = Image.new('RGBA', (64, 64))
    from PIL import ImageDraw
    ImageDraw.Draw(image).ellipse((8, 8, 55, 55), fill=(120, 60, 30, 255))
    image.save(edited)
    before = edited.read_bytes()
    page.use_edited_output(output, edited)
    retry = session.prepare_retry()
    assert retry.mode == 'mode2_process'
    assert retry.selected_files == [str(edited.resolve())]
    assert not retry.generated_prompts and not retry.settings['upscale_after']
    assert session.items[0].editor_output_path == str(edited.resolve())
    worker = main.WorkerThread(retry.mode, retry.work_dir, retry.settings,
                               selected_files=retry.selected_files)
    worker.progress.connect(session.handle_progress)
    messages = []
    worker.progress.connect(messages.append)
    worker.item_progress.connect(session.handle_item_progress)
    worker.diagnostic.connect(session.handle_diagnostic)
    with patch.object(worker, '_run_upscale_pass', side_effect=AssertionError('No upscale')), \
         patch.object(worker, '_run_local_rembg', side_effect=AssertionError('Existing alpha')):
        worker._mode2_process_files(emit_final=False)
    session.handle_finished()
    assert session.items[0].status is RunItemStatus.SUCCEEDED, messages
    assert session.items[0].editor_output_path == ""
    assert len(page._export_paths()) == 1
    assert edited.read_bytes() == before
    with Image.open(session.items[0].output_path) as saved:
        assert saved.convert('RGBA').tobytes() == image.tobytes()
    page.close()


def test_missing_saved_image_never_becomes_paid_generation_retry(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=1), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.FAILED
    session.items[0].output_path = str(session.output_dir / 'missing_ready.png')
    session.handle_finished()
    assert session.preview_retry() is None
    assert session.prepare_retry() is None


def test_explicit_cancelled_retry_selects_only_unfinished_rows_and_preserves_failed_counts(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=3), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    session.items[0].output_path = str(session.output_dir / 'kept_ready.png')
    session.items[1].status = RunItemStatus.CANCELLED
    session.items[1].attempts = 0
    session.items[2].status = RunItemStatus.FAILED
    session.handle_finished()
    assert session.failed_indices == [2]
    assert session.retry_indices == [1, 2]
    assert session.counts()['failed'] == 1 and session.counts()['cancelled'] == 1
    preview = session.preview_retry()
    assert len(preview.generated_prompts) == 2
    assert preview.settings['task_item_indices'] == [2, 3]
    assert session.items[1].status is RunItemStatus.CANCELLED
    retry = session.prepare_retry()
    assert retry == preview and session.active_order == [1, 2]
    assert session.items[0].status is RunItemStatus.SUCCEEDED
    assert session.items[0].output_path.endswith('kept_ready.png')
    assert session.items[1].attempts == 1


def test_cancelled_paid_missing_source_never_becomes_paid_generation_retry(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=2), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    item = session.items[1]
    item.status = RunItemStatus.CANCELLED
    item.source_path = str(session.transient_dir / 'missing_paid_raw.png')
    item.paid_completed_stages = ('upscale_after',)
    item.stage_statuses = {'generation': 'complete', 'upscale_after': 'complete'}
    item.attempts = 4
    session.handle_finished()
    assert session.failed_indices == [] and session.retry_indices == [1]
    assert session.preview_retry() is None and session.prepare_retry() is None
    assert item.status is RunItemStatus.CANCELLED and item.attempts == 4
    assert item.source_path.endswith('missing_paid_raw.png')
    assert item.paid_completed_stages == ('upscale_after',)
    assert item.stage_statuses == {'generation': 'complete', 'upscale_after': 'complete'}


def test_cancelled_saved_source_retries_local_processing_without_generation(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=2), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.SUCCEEDED
    raw = session.transient_dir / 'paid_raw.png'
    raw.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (32, 32), 'blue').save(raw)
    item = session.items[1]
    item.status = RunItemStatus.CANCELLED
    item.source_path = str(raw)
    item.stage_statuses = {'generation': 'complete'}
    session.handle_finished()
    preview = session.preview_retry()
    assert preview.mode == 'mode2_process' and not preview.generated_prompts
    assert preview.selected_files == [str(raw.resolve())]
    assert preview.settings['task_item_indices'] == [2]
    session.prepare_retry()
    assert session.active_order == [1]
    assert session.items[0].status is RunItemStatus.SUCCEEDED


def test_recovery_groups_pending_stages_and_does_not_repeat_generation_failures(tmp_path):
    app = QApplication.instance() or QApplication([])
    request = generation_request(tmp_path, count=3)
    request.settings.update(upscale=False, upscale_after=True, upscale_after_provider='kie')
    session = RunQueueSession(request, ProjectMode.CLIPART)
    session.output_dir.mkdir(parents=True, exist_ok=True)
    for index in (0, 1):
        path = session.output_dir / f'{index}_ready.png'
        Image.new('RGB', (64, 64), 'white').save(path)
        session.items[index].output_path = str(path)
    for item in session.items:
        item.status = RunItemStatus.FAILED
    session.items[0].stage_statuses = {'background_removal': 'skipped'}
    session.items[1].stage_statuses = {'upscale_after': 'complete', 'alpha_validation': 'failed'}
    session.handle_finished()
    retry = session.prepare_retry()
    assert session.active_order == [0]
    assert retry.settings['upscale_after'] is True
    assert not retry.generated_prompts
    assert session.items[1].status is RunItemStatus.FAILED
    assert session.items[2].status is RunItemStatus.FAILED
    session.handle_item_progress(dict(item_index=1, total_items=1, stage='export',
        status='succeeded', output_path=session.items[0].output_path))
    session.handle_finished()
    retry = session.prepare_retry()
    assert session.active_order == [1]
    assert retry.settings['upscale_after'] is False
    assert not retry.generated_prompts


def test_recovery_failure_does_not_claim_intermediate_work_in_old_output(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=1), ProjectMode.CLIPART)
    session.request.settings.update(upscale=False, upscale_after=True)
    saved = session.output_dir / 'old_ready.png'
    saved.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (64, 64), 'white').save(saved)
    item = session.items[0]
    item.status = RunItemStatus.FAILED
    item.output_path = str(saved)
    item.stage_statuses = {'background_removal': 'skipped'}
    session.handle_finished()
    session.prepare_retry()
    session.handle_diagnostic(dict(event='stage_finished', item_index=1, item_total=1,
                                  stage='upscale_after', outcome='succeeded'))
    session.handle_item_progress(dict(item_index=1, total_items=1, stage='export', status='failed'))
    session.handle_finished()
    assert item.output_path == str(saved)
    assert item.saved_stages() == {'background_removal': 'skipped'}
    assert session.preview_retry().settings['upscale_after'] is True


def test_raw_generated_source_does_not_inherit_intermediate_upscale(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=1), ProjectMode.CLIPART)
    session.request.settings.update(upscale=False, upscale_after=True)
    raw = session.transient_dir / 'raw.png'
    raw.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', (64, 64), 'white').save(raw)
    item = session.items[0]
    item.status = RunItemStatus.FAILED
    item.source_path = str(raw)
    item.stage_statuses = {'upscale_after': 'complete'}
    session.handle_finished()
    request = session.prepare_retry()
    assert request.settings['upscale_after'] is True
    assert request.selected_files == [str(raw.resolve())]
    assert not request.generated_prompts


def test_regeneration_cost_line_covers_only_requested_objects(monkeypatch):
    from types import SimpleNamespace
    import v3_image_generation_runtime as runtime
    from studio_auto_clipart_flow import AutoClipartFlowController

    seen = []
    monkeypatch.setattr(runtime, "estimate_image_generation_cost",
                        lambda data: seen.append([p.object_id for p in data.prompts])
                        or SimpleNamespace(summary="цена-подмножества"))
    prompts = [SimpleNamespace(object_id=f"o{i}") for i in range(1, 5)]
    fake = SimpleNamespace(shell=SimpleNamespace(state=SimpleNamespace(
        data=SimpleNamespace(prompts=prompts))))
    request = SimpleNamespace(generated_prompts=[{"object_id": "o2"}, {"object_id": "o4"}])
    assert AutoClipartFlowController._request_cost_line(fake, request) == "цена-подмножества"
    assert seen == [["o2", "o4"]]
    unknown = SimpleNamespace(generated_prompts=[{"prompt": "x"}])  # no object ids: honest fallback
    assert "не рассчитана" in AutoClipartFlowController._request_cost_line(fake, unknown)


class AutoRecoveredItemTests(unittest.TestCase):
    """Ported from 3.1.1 e99cade."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_auto_recovered_item_keeps_attempt_count_in_success_message(self):
        with tempfile.TemporaryDirectory(prefix="v3-auto-recovery-") as temp:
            session = RunQueueSession(
                processing_request(temp, ["source.png"]),
                ProjectMode.PROCESSING,
            )
            output = Path(temp) / "output" / "source_ready.png"
            output.parent.mkdir(parents=True)
            Image.new("RGBA", (8, 8), (20, 30, 40, 255)).save(output)

            session.handle_item_progress(
                {
                    "item_index": 1,
                    "total_items": 1,
                    "stage": "export",
                    "status": "auto_recovered",
                    "recovery_attempts": 3,
                }
            )
            session.handle_item_progress(
                {
                    "item_index": 1,
                    "total_items": 1,
                    "stage": "export",
                    "status": "succeeded",
                    "output_path": str(output),
                }
            )

            item = session.items[0]
            self.assertIs(item.status, RunItemStatus.SUCCEEDED)
            self.assertEqual(item.recovery_attempts, 3)
            self.assertIn("3-й попытки", item.short_message)


class ProblemFilesListTests(unittest.TestCase):
    """Approved mockup C (docs/ui/3.2/legacy-3.1-ports/): failed and stopped files, copy or save as text."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_button_counts_problem_files_and_report_has_no_paths(self):
        from v3_run_queue import ProblemFilesDialog, problem_file_rows
        with tempfile.TemporaryDirectory(prefix="v3-problem-files-") as temp:
            sources = []
            for name in ("a.png", "b.png", "c.png"):
                path = Path(temp) / name
                Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(path)
                sources.append(path)
            request = processing_request(temp, sources)
            request.settings["output_dir"] = temp
            session = RunQueueSession(request, ProjectMode.PROCESSING)
            output = Path(temp) / "a_ready.png"
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output)
            event = lambda index, status, **values: session.handle_item_progress(
                {"item_index": index, "total_items": 3, "stage": values.pop("stage", "export"), "status": status, **values})
            event(1, "succeeded", output_path=str(output))
            event(2, "stage_failed", stage="background_removal")
            event(2, "failed", stage="background_removal", message="Файл больше 8 МБ")
            event(3, "cancelled", message="Остановлено")
            session.handle_finished()
            state = ProjectState(mode=ProjectMode.PROCESSING, common=CommonProjectData(work_dir=temp))
            page = RunResultsPage(state)
            page.set_session(session)
            page.show()
            self.app.processEvents()
            self.assertTrue(page.problem_files_button.isVisible())
            self.assertEqual(page.problem_files_button.text(), "Проблемные файлы (2)")
            rows = problem_file_rows(session)
            self.assertEqual([(r[0], r[1], r[2]) for r in rows],
                             [("Ошибка", "b.png", "Удаление фона"), ("Остановлен", "c.png", "—")])
            dialog = ProblemFilesDialog(rows, 3, page)
            self.assertNotIn(temp, dialog.report)
            self.assertTrue(dialog.report.startswith("Проблемные файлы — 2 из 3"))
            dialog.copy_report()
            self.assertEqual(QApplication.clipboard().text(), dialog.report)
            saved = Path(temp) / "list.txt"
            self.assertTrue(dialog.save_report(str(saved)))
            self.assertEqual(saved.read_text(encoding="utf-8"), dialog.report)
            page.close()

    def test_button_hidden_when_everything_succeeded(self):
        with tempfile.TemporaryDirectory(prefix="v3-problem-files-ok-") as temp:
            source = Path(temp) / "a.png"
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(source)
            request = processing_request(temp, [source])
            request.settings["output_dir"] = temp
            session = RunQueueSession(request, ProjectMode.PROCESSING)
            output = Path(temp) / "a_ready.png"
            Image.new("RGBA", (8, 8), (1, 2, 3, 255)).save(output)
            session.handle_item_progress({"item_index": 1, "total_items": 1, "stage": "export",
                                          "status": "succeeded", "output_path": str(output)})
            session.handle_finished()
            page = RunResultsPage(ProjectState(mode=ProjectMode.PROCESSING, common=CommonProjectData(work_dir=temp)))
            page.set_session(session)
            page.show()
            self.app.processEvents()
            self.assertFalse(page.problem_files_button.isVisible())
            page.close()


def test_retry_restores_the_chroma_block_for_edited_prompts(tmp_path):
    session = RunQueueSession(generation_request(tmp_path, count=1), ProjectMode.CLIPART)
    session.items[0].status = RunItemStatus.FAILED
    session.items[0].payload = {**dict(session.items[0].payload), "prompt": "A duck.",
                                "chroma_key_color": "blue", "result_kind": "clipart"}
    session.handle_finished()
    preview = session.preview_retry()
    assert "chroma-key background" in preview.generated_prompts[0]["prompt"].lower()


def test_edited_prompt_without_the_chroma_block_gets_it_back():
    from v3_project_state import with_chroma_block
    plain = with_chroma_block("A duck.", "blue", "clipart")
    assert "chroma-key background" in plain and "fluffy edge" in plain
    assert with_chroma_block(plain, "blue", "clipart") == plain  # only once
    assert "fluffy edge" not in with_chroma_block("A duck.", "blue", "legacy")
    assert with_chroma_block("A duck.", "", "clipart") == "A duck."
