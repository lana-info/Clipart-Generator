from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from update_client import UpdateClient, UpdateError, UpdateRelease
from app_identity import APP_NAME
from v3_components import ButtonVariant, V3Button


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


def launch_update_artifact(path: Path) -> None:
    if not path.is_file():
        raise UpdateError("Проверенный файл обновления не найден")
    if os.name == "nt" and path.suffix.lower() == ".exe":
        subprocess.Popen([str(path)], close_fds=True)
        return
    if sys.platform == "darwin" and path.suffix.lower() == ".zip":
        subprocess.Popen(["open", "-R", str(path)], close_fds=True)
        return
    raise UpdateError("Формат обновления не поддерживается на этой платформе")


class UpdateAvailableDialog(QDialog):
    """Approved compact release-notes prompt for a signed update."""

    def __init__(
        self,
        release: UpdateRelease,
        platform_id: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Обновление {APP_NAME}")
        self.setMinimumWidth(560)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 24)
        layout.setSpacing(14)

        title = QLabel("Доступна новая версия")
        title.setProperty("v3Title", True)
        layout.addWidget(title)

        version = QLabel(f"{APP_NAME} {release.version}")
        version.setProperty("v3Selection", True)
        layout.addWidget(version)

        self.notes_section = QFrame()
        self.notes_section.setProperty("v3Card", True)
        notes_layout = QVBoxLayout(self.notes_section)
        notes_layout.setContentsMargins(18, 16, 18, 16)
        notes_layout.setSpacing(10)
        notes_title = QLabel("Что нового")
        notes_title.setStyleSheet("font-size: 15px; font-weight: 700;")
        notes_layout.addWidget(notes_title)

        self.notes_view = QPlainTextEdit()
        self.notes_view.setReadOnly(True)
        self.notes_view.setFrameShape(QFrame.Shape.NoFrame)
        self.notes_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.notes_view.setFixedHeight(92)
        self.notes_view.setStyleSheet(
            "background: transparent; border: none; padding: 0;"
        )
        self.notes_view.setPlainText(release.notes.strip())
        notes_layout.addWidget(self.notes_view)
        layout.addWidget(self.notes_section)
        if not release.notes.strip():
            self.notes_section.hide()

        information = QLabel(self._information_text(platform_id))
        information.setProperty("v3Description", True)
        information.setWordWrap(True)
        layout.addWidget(information)
        layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        later_button = V3Button("Не сейчас", ButtonVariant.SECONDARY)
        update_button = V3Button("Обновить", ButtonVariant.PRIMARY)
        later_button.clicked.connect(self.reject)
        update_button.clicked.connect(self.accept)
        buttons.addWidget(later_button)
        buttons.addWidget(update_button)
        layout.addLayout(buttons)

    @staticmethod
    def _information_text(platform_id: str) -> str:
        if platform_id.startswith("macos-"):
            return (
                "Программа скачает и проверит ZIP-архив, затем покажет его в Finder. "
                "Приложение закроется; распакуйте архив и перенесите новую версию "
                "в папку «Программы»."
            )
        return "Программа скачает и проверит обновление, затем закроется и запустит установщик."


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
        installer_launcher: Callable[[Path], None] = launch_update_artifact,
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
        self.download_release: UpdateRelease | None = None
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
        dialog = UpdateAvailableDialog(
            release,
            self.client.platform_id,
            self.parent_widget,
        )
        return dialog.exec() == QDialog.DialogCode.Accepted

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
        self.download_release = release
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
        release = self.download_release
        try:
            if release is None:
                raise UpdateError("Неизвестна версия скачанного обновления")
            self.client.verify_download(release, installer)
        except UpdateError as error:
            self._record(
                "update_prelaunch_verification_failed",
                "Повторная проверка обновления перед запуском не пройдена.",
                severity="error",
                outcome="failed",
                details={"error_message": str(error)},
            )
            QMessageBox.warning(
                self.parent_widget,
                "Обновление",
                "Скачанный файл изменился или повреждён и не будет запущен.",
            )
            return
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
                "Обновление скачано, но файл не удалось открыть.",
            )
            return
        self._record(
            "update_download_verified",
            "Обновление скачано и проверено.",
            outcome="success",
            details={"filename": installer.name, "status": "verified"},
        )
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
