from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication, QMessageBox, QProgressDialog, QWidget

from update_client import UpdateClient, UpdateError, UpdateRelease
from app_identity import APP_NAME


class UpdateCheckWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, client: UpdateClient, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.client = client

    def run(self) -> None:
        try:
            self.client.cleanup_stale_downloads()
            self.completed.emit(self.client.check())
        except UpdateError as error:
            self.failed.emit(str(error))


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int, int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: UpdateClient,
        release: UpdateRelease,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.release = release
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()

    def run(self) -> None:
        try:
            path = self.client.download(
                self.release,
                cancelled=self._cancelled.is_set,
                progress=self.progress.emit,
            )
            self.completed.emit(str(path))
        except UpdateError as error:
            self.failed.emit(str(error))


def launch_windows_installer(path: Path) -> None:
    if os.name != "nt":
        raise UpdateError("Запуск установщика поддерживается только в Windows")
    if not path.is_file() or path.suffix.lower() != ".exe":
        raise UpdateError("Проверенный установщик обновления не найден")
    subprocess.Popen([str(path)], close_fds=True)


class UpdateController(QObject):
    def __init__(
        self,
        parent: QWidget,
        client: UpdateClient,
        journal=None,
        *,
        prompt: Callable[[UpdateRelease], bool] | None = None,
        check_worker_factory=UpdateCheckWorker,
        download_worker_factory=UpdateDownloadWorker,
        installer_launcher: Callable[[Path], None] = launch_windows_installer,
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.client = client
        self.journal = journal
        self.prompt = prompt or self._prompt_user
        self.check_worker_factory = check_worker_factory
        self.download_worker_factory = download_worker_factory
        self.installer_launcher = installer_launcher
        self.check_worker = None
        self.download_worker = None
        self.progress_dialog = None
        self._check_started = False

    def _record(self, event: str, summary: str, **fields) -> None:
        if self.journal is not None:
            self.journal.record(event, summary, **fields)

    def start_check(self) -> bool:
        if self._check_started:
            return False
        self._check_started = True
        self._record(
            "update_check_started",
            "Начата проверка обновлений.",
            details={"current_version": self.client.current_version},
        )
        worker = self.check_worker_factory(self.client, self)
        self.check_worker = worker
        worker.completed.connect(self._check_completed)
        worker.failed.connect(self._check_failed)
        worker.start()
        return True

    def _check_completed(self, release: UpdateRelease | None) -> None:
        if release is None:
            self._record(
                "update_current",
                "Установлена актуальная версия программы.",
                outcome="success",
                details={"current_version": self.client.current_version},
            )
            return
        self._record(
            "update_available",
            "Доступно обновление программы.",
            details={
                "current_version": self.client.current_version,
                "available_version": release.version,
                "correlation_id": release.correlation_id,
            },
        )
        if not self.prompt(release):
            self._record(
                "update_declined",
                "Пользователь выбрал «Не сейчас»; скачивание не начато.",
                outcome="cancelled",
                details={"available_version": release.version, "decision": "not_now"},
            )
            return
        self._record(
            "update_accepted",
            "Пользователь согласился скачать обновление.",
            details={"available_version": release.version, "decision": "update"},
        )
        self._start_download(release)

    def _prompt_user(self, release: UpdateRelease) -> bool:
        box = QMessageBox(self.parent_widget)
        box.setWindowTitle(f"Обновление {APP_NAME}")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Доступна версия {release.version}. Обновить программу сейчас?")
        box.setInformativeText(
            "Программа скачает обновление, закроется и запустит установщик."
        )
        update_button = box.addButton("Обновить", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Не сейчас", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is update_button

    def _start_download(self, release: UpdateRelease) -> None:
        dialog = QProgressDialog(
            "Скачивание обновления…",
            "Отмена",
            0,
            release.size,
            self.parent_widget,
        )
        dialog.setWindowTitle(f"Обновление {release.version}")
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        worker = self.download_worker_factory(self.client, release, self)
        self.progress_dialog = dialog
        self.download_worker = worker
        dialog.canceled.connect(worker.cancel)
        worker.progress.connect(self._download_progress)
        worker.completed.connect(self._download_completed)
        worker.failed.connect(self._download_failed)
        dialog.show()
        worker.start()

    def _download_progress(self, received: int, total: int) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.setMaximum(total)
            self.progress_dialog.setValue(received)
            self.progress_dialog.setLabelText(
                f"Скачано {received / (1024 * 1024):.1f} из {total / (1024 * 1024):.1f} МБ"
            )

    def _download_completed(self, path: str) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.close()
        installer = Path(path)
        self._record(
            "update_download_verified",
            "Обновление скачано и проверено.",
            outcome="success",
            details={"filename": installer.name, "status": "verified"},
        )
        try:
            self.installer_launcher(installer)
        except (OSError, UpdateError) as error:
            self._record(
                "update_installer_launch_failed",
                "Не удалось запустить установщик обновления.",
                severity="error",
                outcome="failed",
                details={"error_message": str(error)},
            )
            QMessageBox.warning(
                self.parent_widget,
                "Обновление",
                "Обновление скачано, но установщик не удалось запустить.",
            )
            return
        self._record(
            "update_installer_launched",
            "Установщик обновления запущен; приложение закрывается.",
            outcome="success",
            details={"filename": installer.name},
        )
        QApplication.instance().quit()

    def _download_failed(self, message: str) -> None:
        if self.progress_dialog is not None:
            self.progress_dialog.close()
        cancelled = "отмен" in message.casefold()
        self._record(
            "update_download_cancelled" if cancelled else "update_download_failed",
            "Скачивание обновления отменено." if cancelled else "Не удалось скачать обновление.",
            severity="warning" if cancelled else "error",
            outcome="cancelled" if cancelled else "failed",
            details={"error_message": message},
        )
        if not cancelled:
            QMessageBox.warning(
                self.parent_widget,
                "Обновление",
                "Не удалось скачать или проверить обновление. Текущая версия продолжит работать.",
            )

    def _check_failed(self, message: str) -> None:
        self._record(
            "update_check_failed",
            "Не удалось проверить обновления.",
            severity="warning",
            outcome="failed",
            details={"error_message": message},
        )
