from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QComboBox,
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

        filters = QHBoxLayout()
        filters.addWidget(QLabel("Показать:"))
        self.severity_filter = QComboBox()
        self.severity_filter.setAccessibleName("Фильтр по уровню диагностики")
        self.severity_filter.addItem("Все события", "all")
        self.severity_filter.addItem("Предупреждения и ошибки", "warning_error")
        self.severity_filter.addItem("Только ошибки", "error")
        filters.addWidget(self.severity_filter)
        self.source_filter = QComboBox()
        self.source_filter.setAccessibleName("Фильтр по провайдеру диагностики")
        filters.addWidget(self.source_filter)
        self.item_filter = QComboBox()
        self.item_filter.setAccessibleName("Фильтр по изображению диагностики")
        filters.addWidget(self.item_filter, 1)
        layout.addLayout(filters)

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
        self._populate_filter_options()
        self.severity_filter.currentIndexChanged.connect(self._populate)
        self.source_filter.currentIndexChanged.connect(self._populate)
        self.item_filter.currentIndexChanged.connect(self._populate)
        self._populate()

    @staticmethod
    def _local_time(value: object) -> str:
        try:
            return datetime.fromisoformat(str(value)).astimezone().strftime("%d.%m.%Y %H:%M:%S")
        except ValueError:
            return "—"

    @staticmethod
    def _details(event: dict) -> dict:
        details = event.get("details")
        return details if isinstance(details, dict) else {}

    @classmethod
    def _item_key(cls, event: dict) -> str:
        details = cls._details(event)
        item_index = details.get("item_index")
        if item_index in (None, ""):
            return ""
        return f"{event.get('operation_id', event.get('session_id', ''))}:{item_index}"

    def _populate_filter_options(self) -> None:
        source_labels = {
            "kie": "KIE",
            "fal": "Fal.ai",
            "photoroom": "PhotoRoom",
            "runpod": "RunPod",
            "local": "Локальная обработка",
            "local_rembg": "Local rembg",
            "local_ben2": "Local BEN2",
            "local_realesrgan": "Local Real-ESRGAN",
            "external": "Внешний источник",
        }
        providers = sorted(
            {
                str(self._details(event).get("provider") or "").strip()
                for event in self.events
                if str(self._details(event).get("provider") or "").strip()
            }
        )
        self.source_filter.addItem("Все источники", "all")
        for provider in providers:
            self.source_filter.addItem(source_labels.get(provider, provider), provider)

        self.item_filter.addItem("Все изображения", "all")
        seen: set[str] = set()
        for event in self.events:
            key = self._item_key(event)
            if not key or key in seen:
                continue
            seen.add(key)
            details = self._details(event)
            item_index = details.get("item_index")
            filename = str(details.get("filename") or "").strip()
            label = f"Изображение {item_index}"
            if filename:
                label += f" · {filename}"
            self.item_filter.addItem(label, key)

    def _filtered_events(self) -> list[dict]:
        severity = self.severity_filter.currentData() or "all"
        provider = self.source_filter.currentData() or "all"
        item_key = self.item_filter.currentData() or "all"
        result: list[dict] = []
        for event in self.events:
            event_severity = str(event.get("severity") or "info")
            if severity == "error" and event_severity != "error":
                continue
            if severity == "warning_error" and event_severity not in {"warning", "error"}:
                continue
            details = self._details(event)
            if provider != "all" and str(details.get("provider") or "") != provider:
                continue
            if item_key != "all" and self._item_key(event) != item_key:
                continue
            result.append(event)
        return result

    def _populate(self, *_args) -> None:
        self.event_list.clear()
        source_labels = {
            "kie": "KIE",
            "fal": "Fal.ai",
            "photoroom": "PhotoRoom",
            "runpod": "RunPod",
            "local": "Локально",
            "local_rembg": "Local rembg",
            "local_ben2": "Local BEN2",
            "local_realesrgan": "Local Real-ESRGAN",
            "external": "Внешний источник",
        }
        visible_events = self._filtered_events()
        for event in visible_events:
            severity = {
                "error": "Ошибка",
                "warning": "Внимание",
                "info": "Информация",
                "debug": "Техническое",
            }.get(str(event.get("severity")), "Информация")
            details = self._details(event)
            item = details.get("item_index")
            filename = str(details.get("filename") or "").strip()
            provider = str(details.get("provider") or "").strip()
            context = []
            if item not in (None, ""):
                context.append(f"Изображение {item}")
            if filename:
                context.append(filename)
            if provider:
                context.append(source_labels.get(provider, provider))
            label_parts = [self._local_time(event.get("timestamp")), severity, *context]
            label_parts.append(str(event.get("summary") or "Событие"))
            label = " · ".join(label_parts)
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, event)
            self.event_list.addItem(item)
        has_events = bool(visible_events)
        self.copy_button.setEnabled(has_events)
        if has_events:
            self.event_list.setCurrentRow(0)
        else:
            self.detail.setPlainText("По выбранным фильтрам записей нет.")

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
