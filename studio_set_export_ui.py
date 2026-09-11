"""Review explicit membership before exporting completed Clipart results."""
from collections import OrderedDict
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QLineEdit, QPushButton, QLabel, QCheckBox, QFileDialog,
    QAbstractItemView, QHeaderView)

from studio_set_export import export_clipart_sets, ExportCancelled
from v3_components import apply_v3_theme


class ExportWorker(QThread):
    def __init__(self, groups, destination, parent=None):
        super().__init__(parent)
        self.groups, self.destination = groups, destination
        self.cancelled = Event()
        self.paths, self.error = [], ''

    def run(self):
        try:
            self.paths = export_clipart_sets(self.groups, self.destination,
                                            cancelled=self.cancelled.is_set)
        except ExportCancelled:
            self.error = 'Экспорт отменён. Архивы не опубликованы.'
        except Exception:
            self.error = 'Не удалось экспортировать наборы. Проверьте PNG, свободное место и доступ к папке. Неполные архивы не опубликованы.'


class SetExportDialog(QDialog):
    membership_saved = pyqtSignal(object)

    def __init__(self, paths, parent=None, *, membership=None):
        super().__init__(parent)
        from studio_export_membership import validate_export_membership
        saved = validate_export_membership(membership or {})
        self.saved_membership = saved
        self.paths = [Path(path) for path in paths]
        self.worker = None
        self.exported = []
        self.setWindowTitle('Clipart · Экспорт наборов')
        self.resize(960, 680)
        apply_v3_theme(self)
        root = QVBoxLayout(self)
        note = QLabel('Выберите PNG и укажите набор для каждого файла. Каждый набор получит отдельный ZIP с обзорным PDF и перечнем файлов. Исходники не изменяются.')
        note.setWordWrap(True)
        root.addWidget(note)
        self.table = QTableWidget(len(self.paths), 2)
        self.table.setHorizontalHeaderLabels(['PNG · включить в экспорт', 'Набор'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for row, path in enumerate(self.paths):
            assignment = saved.get(str(path.resolve()), {'title': 'Набор 1', 'included': True})
            item = QTableWidgetItem(path.name)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if assignment['included'] else Qt.CheckState.Unchecked)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem(assignment['title']))
        root.addWidget(self.table, 1)
        assignment = QHBoxLayout()
        self.group = QLineEdit()
        self.group.setMaxLength(200)
        self.group.setPlaceholderText('Название набора для выделенных строк')
        self.assign = QPushButton('Назначить набор')
        self.assign.clicked.connect(self._assign)
        assignment.addWidget(self.group, 1)
        assignment.addWidget(self.assign)
        root.addLayout(assignment)
        self.reviewed = QCheckBox('Я проверил(а) выбранные изображения и их распределение по наборам')
        root.addWidget(self.reviewed)
        self.status = QLabel('Упаковка не заменяет проверку прозрачности и качества края.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        actions = QHBoxLayout()
        self.close_button = QPushButton('Закрыть')
        self.close_button.clicked.connect(self.reject)
        self.export_button = QPushButton('Создать ZIP наборов')
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.close_button)
        self.save_membership = QPushButton('Сохранить распределение')
        self.save_membership.clicked.connect(self._save_membership)
        actions.addWidget(self.save_membership)
        actions.addStretch()
        actions.addWidget(self.export_button)
        root.addLayout(actions)
        self.table.itemChanged.connect(self._invalidate_review)

    def _invalidate_review(self, *_):
        self.reviewed.setChecked(False)

    def _save_membership(self):
        from studio_export_membership import validate_export_membership
        try:
            value = validate_export_membership(self.saved_membership | {str(path.resolve()): dict(
                title=self.table.item(row, 1).text().strip(),
                included=self.table.item(row, 0).checkState() == Qt.CheckState.Checked)
                for row, path in enumerate(self.paths)})
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.membership_saved.emit(value)
        self.saved_membership = value
        self.status.setText('Распределение передано проекту для сохранения. Экспорт не запускался.')

    def _assign(self):
        title = self.group.text().strip()
        if not title:
            self.status.setText('Введите название набора')
            return
        for row in {index.row() for index in self.table.selectedIndexes()}:
            self.table.item(row, 1).setText(title)

    def groups(self):
        groups = OrderedDict()
        for row, path in enumerate(self.paths):
            if self.table.item(row, 0).checkState() != Qt.CheckState.Checked:
                continue
            title = self.table.item(row, 1).text().strip()
            if not title or len(title) > 200:
                raise ValueError('Укажите название набора до 200 символов для каждого выбранного PNG')
            groups.setdefault(title, []).append(path)
        if not groups or len(groups) > 100 or any(len(paths) > 1000 for paths in groups.values()):
            raise ValueError('Выберите от 1 до 100 наборов, не более 1000 PNG в каждом')
        return [dict(title=title, images=paths) for title, paths in groups.items()]

    def _export(self):
        if self.worker is not None:
            return
        try:
            groups = self.groups()
            if not self.reviewed.isChecked():
                raise ValueError('Сначала проверьте выбранные изображения и отметьте подтверждение')
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        folder = QFileDialog.getExistingDirectory(self, 'Папка для архивов наборов')
        if not folder:
            return
        self.worker = ExportWorker(groups, folder, self)
        self.worker.finished.connect(self._finished)
        for widget in (self.table, self.group, self.assign, self.reviewed, self.export_button, self.save_membership):
            widget.setEnabled(False)
        self.close_button.setText('Отменить экспорт')
        self.status.setText(f'Создаю архивы: {len(groups)}. Не закрывайте приложение до завершения.')
        self.worker.start()

    def _finished(self):
        worker = self.worker
        self.exported = worker.paths
        self.status.setText(worker.error or f'Создано ZIP: {len(worker.paths)}. Папка: {worker.paths[0].parent}')
        for widget in (self.table, self.group, self.assign, self.reviewed, self.export_button, self.save_membership):
            widget.setEnabled(True)
        self.close_button.setEnabled(True)
        self.close_button.setText('Закрыть')
        self.worker = None
        worker.deleteLater()

    def reject(self):
        if self.worker is not None:
            self.worker.cancelled.set()
            self.close_button.setEnabled(False)
            self.status.setText('Отменяю экспорт и удаляю временные файлы. Дождитесь завершения.')
            return
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
