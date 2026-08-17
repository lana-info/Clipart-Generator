from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from diagnostics import DiagnosticJournal
from v3_components import ButtonVariant, V3Button
from app_identity import APP_NAME


class DiagnosticJournalDialog(QDialog):
    def __init__(self, journal: DiagnosticJournal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.journal = journal
        self.events = journal.read_events()
        self.setWindowTitle("Журнал диагностики")
        self.setMinimumSize(820, 560)
        self.setAccessibleName(f"Журнал диагностики {APP_NAME}")

        layout = QVBoxLayout(self)
        heading = QLabel("Последние три запуска")
        heading.setProperty("v3Title", True)
        layout.addWidget(heading)
        note = QLabel(
            "Журнал не содержит лицензионные и API-ключи, промпты, изображения "
            "и полные личные пути."
        )
        note.setWordWrap(True)
        note.setProperty("v3Small", True)
        layout.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Vertical)
        self.event_list = QListWidget()
        self.event_list.setAccessibleName("Записи диагностики")
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setAccessibleName("Подробности записи диагностики")
        splitter.addWidget(self.event_list)
        splitter.addWidget(self.detail)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.copy_button = V3Button("Скопировать запись", ButtonVariant.SECONDARY)
        self.copy_button.clicked.connect(self.copy_selected)
        self.export_button = V3Button("Экспортировать диагностику", ButtonVariant.PRIMARY)
        self.export_button.clicked.connect(self.choose_export_path)
        close_button = V3Button("Закрыть", ButtonVariant.GHOST)
        close_button.clicked.connect(self.close)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.export_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

        self.event_list.currentRowChanged.connect(self._show_event)
        self._populate()

    @staticmethod
    def _local_time(value: object) -> str:
        try:
            return datetime.fromisoformat(str(value)).astimezone().strftime("%d.%m.%Y %H:%M:%S")
        except ValueError:
            return "—"

    def _populate(self) -> None:
        self.event_list.clear()
        for event in self.events:
            severity = {
                "error": "Ошибка",
                "warning": "Внимание",
                "info": "Информация",
                "debug": "Техническое",
            }.get(str(event.get("severity")), "Информация")
            label = (
                f"{self._local_time(event.get('timestamp'))} · {severity} · "
                f"{event.get('summary', 'Событие')}"
            )
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, event)
            self.event_list.addItem(item)
        has_events = bool(self.events)
        self.copy_button.setEnabled(has_events)
        if has_events:
            self.event_list.setCurrentRow(0)
        else:
            self.detail.setPlainText("Записей пока нет.")

    def _selected_event(self):
        item = self.event_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def _show_event(self, _row: int) -> None:
        event = self._selected_event()
        self.detail.setPlainText(
            self.journal.format_event(event) if isinstance(event, dict) else ""
        )

    def copy_selected(self) -> None:
        event = self._selected_event()
        if not isinstance(event, dict):
            return
        QApplication.clipboard().setText(self.journal.format_event(event))

    def choose_export_path(self) -> None:
        destination, _filter = QFileDialog.getSaveFileName(
            self,
            "Экспортировать диагностику",
            "VibixImages-diagnostics.zip",
            "ZIP (*.zip)",
        )
        if not destination:
            return
        if not destination.lower().endswith(".zip"):
            destination += ".zip"
        try:
            self.journal.export_zip(Path(destination))
            self.journal.record(
                "diagnostics_exported",
                "Пакет диагностики сохранён.",
                details={"filename": Path(destination).name, "status": "success"},
            )
        except OSError as error:
            self.journal.record(
                "diagnostics_export_failed",
                "Не удалось сохранить пакет диагностики.",
                severity="error",
                details={"error_message": str(error), "status": "failed"},
            )
            QMessageBox.warning(
                self,
                "Экспорт диагностики",
                "Не удалось сохранить пакет диагностики. Выберите другую папку.",
            )
