import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from diagnostics import DiagnosticJournal
from update_client import UpdateRelease
from v3_updater import UpdateController


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
            events = [item["event"] for item in journal.read_events()]
            self.assertIn("update_accepted", events)
            self.assertIn("update_download_verified", events)
            self.assertIn("update_installer_launched", events)


if __name__ == "__main__":
    unittest.main()
