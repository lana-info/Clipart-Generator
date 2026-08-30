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
    _failure_reason,
)
from v3_wizard import AppShell


SECRET_PROMPT = "private prompt do not log"
SECRET_KEY = "secret-api-key-do-not-log"


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
            controller = install_clipart_flow(shell)
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
            controller = install_processing_flow(shell)
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
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": SECRET_KEY},
                worker_factory=factory,
                authorization_provider=Mock(return_value=None),
            )
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
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": SECRET_KEY},
                worker_factory=factory,
                authorization_provider=Mock(return_value=None),
            )
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

    def test_retry_request_contains_only_failed_private_payloads(self):
        with tempfile.TemporaryDirectory(prefix="v3-queue-retry-") as temp:
            session = RunQueueSession(
                generation_request(temp),
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
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {
                    "kie_api_key": SECRET_KEY
                },
                worker_factory=factory,
                authorization_provider=authorization,
            )

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
            self.assertFalse(page.process_more_button.isHidden())
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
            controller = install_processing_flow(shell, worker_factory=WorkerFactory())
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

    def test_results_finish_signal_is_ignored_until_the_queue_is_terminal(self):
        with tempfile.TemporaryDirectory(prefix="v3-terminal-guard-") as temp:
            state = ProjectState(
                mode=ProjectMode.PROCESSING,
                common=CommonProjectData(work_dir=temp),
            )
            shell = AppShell(state)
            controller = install_processing_flow(shell, worker_factory=WorkerFactory())
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
            controller = install_clipart_flow(
                shell,
                runtime_settings_provider=lambda: {"kie_api_key": SECRET_KEY},
                worker_factory=factory,
                authorization_provider=authorization,
            )

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
            self.assertIn("✓ Обработано: 0", page.summary_label.text())
            self.assertIn("📁 Папка результата:", page.summary_label.text())
            self.assertIn("⏱ Время:", page.summary_label.text())
            self.assertIn("идёт обработка", page._stage_label("processing"))
            self.assertFalse(page.viewer.isVisible())
            self.assertEqual(page.log_button.text(), "Диагностика")
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
            worker.finished.connect(session.handle_finished)
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
