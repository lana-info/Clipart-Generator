import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from diagnostics import DiagnosticJournal


class DiagnosticJournalTests(unittest.TestCase):
    def test_equal_timestamps_keep_exact_recording_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            fixed = datetime(2030, 1, 1, tzinfo=timezone.utc)
            journal = DiagnosticJournal(
                Path(temp), app_version="3.0", now=lambda: fixed
            )
            for event in ("first", "second", "third"):
                journal.record(event, event)

            events = journal.read_events()

            self.assertEqual(
                [item["event"] for item in events],
                ["third", "second", "first"],
            )

    def test_keeps_three_launches_and_recovers_corrupt_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for index in range(4):
                journal = DiagnosticJournal(
                    root,
                    app_version="3.0",
                    now=lambda index=index: datetime(2030, 1, 1, 0, index, tzinfo=timezone.utc),
                    session_id=f"session-{index}",
                )
                journal.record("application_started", f"Запуск {index}")
                journal.close()
            files = sorted((root / "diagnostics").glob("*.jsonl"))
            self.assertEqual(len(files), 3)
            with files[-1].open("ab") as handle:
                handle.write(b'{"broken":')
            events = journal.read_events()
            self.assertTrue(any(item["event"] == "application_started" for item in events))

    def test_redacts_secrets_prompts_and_personal_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            journal.record(
                "provider_failed",
                "Ошибка в C:\\Users\\Anna\\Pictures\\secret.png key sk-live-secret",
                details={
                    "api_key": "sk-live-secret",
                    "license_key": "CG-ABCDEFGHIJKLMNOP",
                    "prompt": "private prompt",
                    "filename": "C:\\Users\\Anna\\Pictures\\secret.png",
                    "provider": "kie",
                },
            )
            raw = journal.session_path.read_text(encoding="utf-8")
            self.assertNotIn("sk-live-secret", raw)
            self.assertNotIn("CG-ABCDEFGHIJKLMNOP", raw)
            self.assertNotIn("private prompt", raw)
            self.assertNotIn("Users\\\\Anna", raw)
            event = journal.read_events()[0]
            self.assertEqual(event["details"]["api_key"], "[СКРЫТО]")
            self.assertNotIn("prompt", event["details"])

    def test_active_session_and_total_bytes_are_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(
                Path(temp),
                app_version="3.0",
                session_max_bytes=1400,
                total_max_bytes=2200,
                event_max_bytes=400,
            )
            for index in range(100):
                journal.record(
                    "item_finished",
                    "Файл обработан " + ("x" * 300),
                    details={"item_index": index, "status": "success"},
                )
            self.assertLessEqual(journal.session_path.stat().st_size, 1400)
            self.assertLessEqual(
                sum(path.stat().st_size for path in journal.directory.glob("*.jsonl")),
                2200,
            )
            for line in journal.session_path.read_text(encoding="utf-8").splitlines():
                self.assertIsInstance(json.loads(line), dict)
            self.assertEqual(
                sum(
                    json.loads(line).get("event") == "log_truncated"
                    for line in journal.session_path.read_text(encoding="utf-8").splitlines()
                ),
                1,
            )

    def test_event_count_limit_preserves_late_error_and_session_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(
                Path(temp),
                app_version="3.1",
                session_max_bytes=64 * 1024,
                total_max_bytes=64 * 1024,
                session_max_events=8,
                priority_event_reserve=3,
            )
            for attempt in range(30):
                journal.record(
                    "stage_updated",
                    "Изменилось состояние обработки.",
                    details={"poll_attempt": attempt, "status": "running"},
                )
            journal.record(
                "provider_task_failed",
                "Внешний сервис завершил задачу с ошибкой.",
                severity="error",
                outcome="failed",
                details={"provider": "kie", "error_code": "422"},
            )
            journal.close()

            events = journal.read_events()

            self.assertLessEqual(len(events), 8)
            self.assertTrue(any(item["event"] == "log_truncated" for item in events))
            self.assertTrue(any(item["event"] == "provider_task_failed" for item in events))
            self.assertTrue(any(item["event"] == "session_summary" for item in events))

    def test_repeated_polling_is_sampled_but_state_changes_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.1")
            for attempt in range(1, 13):
                journal.record_structured(
                    {
                        "event": "provider_task_polled",
                        "provider": "kie",
                        "task": "task-sampled",
                        "provider_state": "waiting",
                        "poll_attempt": attempt,
                    }
                )
            journal.record_structured(
                {
                    "event": "provider_task_polled",
                    "provider": "kie",
                    "task": "task-sampled",
                    "provider_state": "processing",
                    "poll_attempt": 13,
                }
            )

            attempts = [
                item["details"]["poll_attempt"]
                for item in journal.read_events()
                if item["event"] == "provider_task_polled"
            ]

            self.assertEqual(sorted(attempts), [1, 10, 13])

    def test_recovery_deferred_keeps_provider_task_and_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.1")
            journal.record_structured(
                {
                    "event": "provider_task_recovery_deferred",
                    "provider": "fal",
                    "model": "fal-ai/flux/schnell",
                    "task": "safe-task-id",
                    "outcome": "deferred",
                    "error_message": "temporary transport failure",
                }
            )

            event = journal.read_events()[0]

            self.assertEqual(event["event"], "provider_task_recovery_deferred")
            self.assertEqual(event["severity"], "warning")
            self.assertEqual(event["details"]["provider"], "fal")
            self.assertEqual(event["details"]["task"], "safe-task-id")

    def test_read_events_bounds_oversized_journal_from_older_version(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(
                Path(temp),
                app_version="3.1",
                session_max_events=8,
                priority_event_reserve=3,
            )
            journal.session_path.write_text(
                "".join(
                    json.dumps(
                        {
                            "schema_version": 2,
                            "timestamp": f"2030-01-01T00:00:{index:02d}+00:00",
                            "sequence": index,
                            "event": "legacy_poll",
                            "summary": "old",
                            "session_id": "old-session",
                        }
                    )
                    + "\n"
                    for index in range(30)
                ),
                encoding="utf-8",
            )

            events = journal.read_events()

            self.assertEqual(len(events), 8)
            self.assertEqual(events[0]["sequence"], 29)

    def test_unwritable_journal_falls_back_to_memory_without_blocking(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.object(
            Path, "mkdir", side_effect=PermissionError("denied")
        ):
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            journal.record("application_started", "Приложение запущено")
        self.assertIsNone(journal.session_path)
        self.assertEqual(journal.read_events()[0]["event"], "application_started")

    def test_copy_text_and_zip_export_are_readable_and_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            event = journal.record(
                "update_available",
                "Доступно обновление",
                details={"current_version": "3.0", "available_version": "3.1.0"},
            )
            copied = journal.format_event(event)
            self.assertIn("Доступно обновление", copied)
            destination = Path(temp) / "diagnostics.zip"
            journal.export_zip(destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertEqual(
                    set(archive.namelist()),
                    {"diagnostics.txt", "diagnostics.json", "system.json", "README.txt"},
                )
                exported = "\n".join(
                    archive.read(name).decode("utf-8") for name in archive.namelist()
                )
            self.assertIn("update_available", exported)
            self.assertNotIn(str(Path.home()), exported)

    def test_export_redacts_posix_and_unc_paths_with_spaces(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            journal = DiagnosticJournal(Path(temp), app_version="3.0.5")
            journal.record(
                "provider_failed",
                "failed at /home/Jane Doe/Customer A/input.png; "
                r"mirror \\server\private share\Customer A\input.png",
                details={"provider": "kie"},
            )
            destination = Path(temp) / "diagnostics.zip"
            journal.export_zip(destination)
            with zipfile.ZipFile(destination) as archive:
                exported = "\n".join(
                    archive.read(name).decode("utf-8")
                    for name in archive.namelist()
                )

            self.assertNotIn("Jane Doe", exported)
            self.assertNotIn("Customer A", exported)
            self.assertNotIn("private share", exported)
            self.assertNotIn("server", exported)


if __name__ == "__main__":
    unittest.main()
