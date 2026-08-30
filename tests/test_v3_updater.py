import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QLabel, QPushButton, QWidget

from diagnostics import DiagnosticJournal
from update_client import UpdateError, UpdateRelease
import v3_updater
from v3_updater import UpdateController, launch_update_artifact


class ImmediateCheckWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client

    def start(self):
        self.completed.emit(self.client.release)


class ImmediateDownloadWorker(QObject):
    progress = pyqtSignal(int, int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    starts = 0

    def __init__(self, client, release, parent=None):
        super().__init__(parent)
        self.client = client
        self.release = release
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def start(self):
        type(self).starts += 1
        self.progress.emit(self.release.size, self.release.size)
        self.completed.emit(str(self.client.installer_path))


class FakeUpdateClient:
    current_version = "3.0"

    def __init__(self, release, installer_path):
        self.release = release
        self.installer_path = installer_path
        self.verifications = []

    def verify_download(self, release, path):
        self.verifications.append((release, path))


class V3UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        ImmediateDownloadWorker.starts = 0

    def release(self):
        return UpdateRelease(
            version="3.1.0",
            filename="VibixImages-Setup-3.1.exe",
            size=20,
            sha256="a" * 64,
            download_url="https://license.example/downloads/token",
            correlation_id="correlation-1",
        )

    def test_update_dialog_shows_release_notes_as_plain_text(self) -> None:
        release = UpdateRelease(
            version="3.1.1",
            filename="VibixImages-Setup-3.1.1.exe",
            size=20,
            sha256="a" * 64,
            download_url="https://license.example/downloads/token",
            notes="Улучшено удаление фона\nДобавлен редактор прозрачности",
        )

        dialog = v3_updater.UpdateAvailableDialog(release, "windows-x64")

        labels = [item.text() for item in dialog.findChildren(QLabel)]
        buttons = [item.text() for item in dialog.findChildren(QPushButton)]
        self.assertIn("Что нового", labels)
        self.assertIn(release.notes, dialog.notes_view.toPlainText())
        self.assertIn("Обновить", buttons)
        self.assertIn("Не сейчас", buttons)
        dialog.deleteLater()

    def test_update_dialog_hides_notes_section_when_server_sent_no_notes(self) -> None:
        dialog = v3_updater.UpdateAvailableDialog(self.release(), "windows-x64")

        self.assertTrue(dialog.notes_section.isHidden())
        dialog.deleteLater()

    def test_update_dialog_never_interprets_release_notes_as_markup(self) -> None:
        release = UpdateRelease(
            version="3.1.1",
            filename="VibixImages-Setup-3.1.1.exe",
            size=20,
            sha256="a" * 64,
            download_url="https://license.example/downloads/token",
            notes="<b>Только текст</b>",
        )

        dialog = v3_updater.UpdateAvailableDialog(release, "windows-x64")

        self.assertEqual(dialog.notes_view.toPlainText(), "<b>Только текст</b>")
        dialog.deleteLater()

    def test_update_dialog_keeps_long_notes_in_a_scrollable_compact_area(self) -> None:
        release = UpdateRelease(
            version="3.1.1",
            filename="VibixImages-Setup-3.1.1.exe",
            size=20,
            sha256="a" * 64,
            download_url="https://license.example/downloads/token",
            notes="\n".join(f"Изменение {index}" for index in range(30)),
        )
        dialog = v3_updater.UpdateAvailableDialog(release, "windows-x64")
        dialog.show()
        self.app.processEvents()

        self.assertGreater(dialog.notes_view.verticalScrollBar().maximum(), 0)
        self.assertLessEqual(dialog.notes_view.height(), 92)
        dialog.close()
        dialog.deleteLater()

    def test_not_now_never_starts_download_and_check_runs_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            installer = root / "VibixImages-Setup-3.1.exe"
            installer.write_bytes(b"x")
            journal = DiagnosticJournal(root, app_version="3.0")
            controller = UpdateController(
                QWidget(),
                FakeUpdateClient(self.release(), installer),
                journal,
                prompt=lambda _release: False,
                check_worker_factory=ImmediateCheckWorker,
                download_worker_factory=ImmediateDownloadWorker,
            )
            self.assertTrue(controller.start_check())
            self.assertFalse(controller.start_check())
            self.assertEqual(ImmediateDownloadWorker.starts, 0)
            events = [item["event"] for item in journal.read_events()]
            self.assertIn("update_declined", events)

    def test_accept_downloads_launches_and_records_verified_installer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            installer = root / "VibixImages-Setup-3.1.exe"
            installer.write_bytes(b"verified")
            journal = DiagnosticJournal(root, app_version="3.0")
            launched = []
            controller = UpdateController(
                QWidget(),
                FakeUpdateClient(self.release(), installer),
                journal,
                prompt=lambda _release: True,
                check_worker_factory=ImmediateCheckWorker,
                download_worker_factory=ImmediateDownloadWorker,
                installer_launcher=launched.append,
            )
            controller.start_check()
            self.assertEqual(ImmediateDownloadWorker.starts, 1)
            self.assertEqual(launched, [installer])
            self.assertEqual(controller.client.verifications, [(controller.client.release, installer)])
            events = [item["event"] for item in journal.read_events()]
            self.assertIn("update_accepted", events)
            self.assertIn("update_download_verified", events)
            self.assertIn("update_installer_launched", events)

    def test_failed_prelaunch_recheck_never_starts_installer(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            installer = root / "VibixImages-Setup-3.1.exe"
            installer.write_bytes(b"tampered")
            client = FakeUpdateClient(self.release(), installer)
            client.verify_download = lambda _release, _path: (_ for _ in ()).throw(
                UpdateError("Файл обновления не прошёл повторную проверку")
            )
            launched = []
            controller = UpdateController(
                QWidget(),
                client,
                prompt=lambda _release: True,
                check_worker_factory=ImmediateCheckWorker,
                download_worker_factory=ImmediateDownloadWorker,
                installer_launcher=launched.append,
            )

            with patch("v3_updater.QMessageBox.warning"):
                controller.start_check()

            self.assertEqual(launched, [])

    def test_macos_update_reveals_verified_zip_in_finder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / "VibixImages-macOS-3.1.0-arm64.zip"
            archive.write_bytes(b"PK\x03\x04archive")
            with patch.object(v3_updater.sys, "platform", "darwin"), patch.object(
                v3_updater.subprocess, "Popen"
            ) as popen:
                launch_update_artifact(archive)
        popen.assert_called_once_with(["open", "-R", str(archive)], close_fds=True)


if __name__ == "__main__":
    unittest.main()
