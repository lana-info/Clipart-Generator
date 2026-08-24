import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from license_client import LicenseError
from v3_clipart_flow import ClipartRunRequest, install_clipart_flow
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
)
from v3_wizard import AppShell


SECRET_PROMPT = "private prompt do not log"
SECRET_KEY = "secret-api-key-do-not-log"


class FakeWorker(QObject):
    progress = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

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

    def test_elapsed_duration_is_human_readable(self):
        self.assertEqual(format_elapsed_duration(45), "45 секунд")
        self.assertEqual(format_elapsed_duration(93), "1 мин 33 сек")
        self.assertEqual(format_elapsed_duration(3848), "1 ч 4 мин 8 сек")

    def test_all_routes_end_in_the_shared_results_step(self):
        for mode in ProjectMode:
            with self.subTest(mode=mode):
                self.assertIs(route_for_mode(mode)[-1], StepId.RESULTS)

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
            run_dir = root / "output" / ".run"
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
