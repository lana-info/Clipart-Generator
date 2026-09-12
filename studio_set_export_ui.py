"""Automatic Clipart set summary with optional manual membership editing."""
from collections import OrderedDict
from pathlib import Path
from threading import Event

from PyQt6.QtCore import QEvent, QPoint, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QCursor, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QDialog, QFileDialog, QFrame, QGridLayout,
    QHeaderView, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

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
            self.paths = export_clipart_sets(
                self.groups, self.destination, cancelled=self.cancelled.is_set
            )
        except ExportCancelled:
            self.error = 'Экспорт отменён. Наборы не опубликованы.'
        except Exception:
            self.error = (
                'Не удалось создать наборы. Проверьте PNG, свободное место и '
                'доступ к папке. Неполные наборы не опубликованы.'
            )


class SetExportDialog(QDialog):
    membership_saved = pyqtSignal(object)

    def __init__(self, paths, parent=None, *, membership=None, review_issues=None):
        super().__init__(parent)
        from studio_export_membership import validate_export_membership

        saved = validate_export_membership(membership or {})
        self.paths = list(dict.fromkeys(Path(path).resolve() for path in paths))
        for path in self.paths:
            key = str(path)
            if key not in saved:
                saved.update(validate_export_membership(
                    {key: {'title': 'Набор 1', 'included': True}}
                ))
        self.saved_membership = saved
        self.review_issues = [dict(issue) for issue in (review_issues or ())]
        self.worker = None
        self.exported = []
        self._set_columns = []

        self.setWindowTitle('Clipart · Экспорт наборов')
        self.resize(1040, 720)
        apply_v3_theme(self)
        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.summary_page = self._build_summary_page()
        self.manual_page = self._build_manual_page()
        self.stack.addWidget(self.summary_page)
        self.stack.addWidget(self.manual_page)
        self.stack.setCurrentWidget(self.summary_page)

        self.status = QLabel('')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        self.preview_popup = QLabel(None, Qt.WindowType.ToolTip)
        self.preview_popup.setObjectName('setExportPreviewPopup')
        self.preview_popup.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_popup.setMinimumSize(180, 180)
        self.preview_popup.setMaximumSize(240, 240)
        self.preview_popup.setStyleSheet(
            'QLabel { background:#15243a; border:1px solid #496689; '
            'padding:8px; border-radius:8px; }'
        )
        self.preview_popup.hide()
        self._refresh_summary()

    def _build_summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel('Экспорт наборов')
        title.setProperty('v3Title', True)
        layout.addWidget(title)
        note = QLabel(
            'Приложение уже распределило готовые изображения по наборам. '
            'Один PNG может входить в несколько наборов без повторной генерации.'
        )
        note.setProperty('v3Description', True)
        note.setWordWrap(True)
        layout.addWidget(note)

        metrics = QHBoxLayout()
        self.summary_unique_value = QLabel('0')
        self.summary_sets_value = QLabel('0')
        for value, caption in (
            (self.summary_unique_value, 'уникальных PNG'),
            (self.summary_sets_value, 'наборов'),
        ):
            box = QFrame()
            box.setProperty('v3Card', True)
            box.setMinimumWidth(300)
            box.setMaximumHeight(78)
            box_layout = QVBoxLayout(box)
            value.setStyleSheet('font-size:22px; font-weight:700;')
            label = QLabel(caption)
            label.setProperty('v3Small', True)
            box_layout.addWidget(value)
            box_layout.addWidget(label)
            metrics.addWidget(box)
        metrics.addStretch(1)
        layout.addLayout(metrics)

        heading = QHBoxLayout()
        section_title = QLabel('Предложенные наборы')
        section_title.setProperty('v3Title', True)
        heading.addWidget(section_title)
        heading.addStretch(1)
        self.edit_sets_button = QPushButton('Изменить состав наборов')
        self.edit_sets_button.setMinimumWidth(self.edit_sets_button.sizeHint().width() + 18)
        self.edit_sets_button.setProperty('v3Button', True)
        self.edit_sets_button.setProperty('variant', 'secondary')
        self.edit_sets_button.clicked.connect(self._show_manual_editor)
        heading.addWidget(self.edit_sets_button)
        layout.addLayout(heading)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.cards_scroll.setMinimumHeight(125)
        self.cards_scroll.setMaximumHeight(270)
        self.cards_host = QWidget()
        self.cards_layout = QGridLayout(self.cards_host)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_scroll.setWidget(self.cards_host)
        layout.addWidget(self.cards_scroll, 1)

        self.issue_panel = QFrame()
        self.issue_panel.setProperty('v3Card', True)
        self.issue_panel.setProperty('state', 'warning')
        issue_layout = QHBoxLayout(self.issue_panel)
        self.issue_text = QLabel('')
        self.issue_text.setWordWrap(True)
        issue_layout.addWidget(self.issue_text, 1)
        self.review_now_button = QPushButton('Проверить сейчас')
        self.review_now_button.setProperty('v3Button', True)
        self.review_now_button.setProperty('variant', 'secondary')
        self.review_now_button.clicked.connect(self._show_manual_editor)
        issue_layout.addWidget(self.review_now_button)
        layout.addWidget(self.issue_panel)

        self.delivery_note = QLabel(
            'Для каждого набора будет создан отдельный ZIP-архив. '
            'Внутри: PNG, лист с превью и список файлов.'
        )
        self.delivery_note.setProperty('v3Description', True)
        self.delivery_note.setWordWrap(True)
        layout.addWidget(self.delivery_note)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.export_button = QPushButton('Создать наборы')
        self.export_button.setProperty('v3Button', True)
        self.export_button.setProperty('variant', 'primary')
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)
        return page

    def _build_manual_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel('Изменить состав наборов')
        title.setProperty('v3Title', True)
        layout.addWidget(title)
        note = QLabel(
            'Поставьте галочки, в какие наборы должен входить каждый PNG. '
            'Изменения не запускают повторную генерацию или обработку.'
        )
        note.setProperty('v3Description', True)
        note.setWordWrap(True)
        layout.addWidget(note)

        self.table = QTableWidget(0, 1)
        self.table.setMouseTracking(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.itemEntered.connect(
            lambda item: self._show_preview(item, QCursor.pos())
        )
        self.table.viewport().installEventFilter(self)
        self.table.itemChanged.connect(self._manual_changed)
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.return_button = QPushButton('К наборам')
        self.return_button.setProperty('v3Button', True)
        self.return_button.setProperty('variant', 'secondary')
        self.return_button.setMinimumWidth(max(130, self.return_button.sizeHint().width() + 20))
        self.return_button.clicked.connect(self._show_summary)
        self.save_membership = QPushButton('Сохранить состав')
        self.save_membership.setProperty('v3Button', True)
        self.save_membership.setProperty('variant', 'primary')
        self.save_membership.clicked.connect(self._save_membership)
        actions.addWidget(self.return_button)
        actions.addStretch(1)
        actions.addWidget(self.save_membership)
        layout.addLayout(actions)
        return page

    def _set_catalog(self):
        catalog = OrderedDict()
        for path in self.paths:
            item = self.saved_membership[str(path)]
            for link in item['memberships']:
                catalog.setdefault(link['set_id'], link['title'])
        return list(catalog.items())

    def _rebuild_manual_table(self):
        self._set_columns = self._set_catalog()
        self.table.blockSignals(True)
        try:
            self.table.clear()
            self.table.setRowCount(len(self.paths))
            self.table.setColumnCount(1 + len(self._set_columns))
            self.table.setHorizontalHeaderLabels(
                ['PNG'] + [title for _, title in self._set_columns]
            )
            first_header = self.table.horizontalHeaderItem(0)
            if first_header:
                first_header.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )
            for column in range(1, self.table.columnCount()):
                header = self.table.horizontalHeaderItem(column)
                header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.horizontalHeader().setSectionResizeMode(
                0, QHeaderView.ResizeMode.Stretch
            )
            for column in range(1, self.table.columnCount()):
                self.table.horizontalHeader().setSectionResizeMode(
                    column, QHeaderView.ResizeMode.ResizeToContents
                )
            for row, path in enumerate(self.paths):
                name = QTableWidgetItem(path.name)
                name.setData(Qt.ItemDataRole.UserRole, str(path))
                name.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(row, 0, name)
                links = {
                    link['set_id']: link
                    for link in self.saved_membership[str(path)]['memberships']
                }
                for column, (set_id, _) in enumerate(self._set_columns, 1):
                    cell = QTableWidgetItem('')
                    cell.setData(Qt.ItemDataRole.UserRole, set_id)
                    cell.setFlags(
                        Qt.ItemFlag.ItemIsEnabled
                        | Qt.ItemFlag.ItemIsSelectable
                        | Qt.ItemFlag.ItemIsUserCheckable
                    )
                    cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    included = bool(links.get(set_id, {}).get('included', False))
                    cell.setCheckState(
                        Qt.CheckState.Checked if included else Qt.CheckState.Unchecked
                    )
                    self.table.setItem(row, column, cell)
        finally:
            self.table.blockSignals(False)

    def _membership(self):
        from studio_export_membership import validate_export_membership
        value = validate_export_membership(self.saved_membership)
        if not self._set_columns:
            return value
        for row, path in enumerate(self.paths):
            key = str(path)
            existing = {link['set_id']: link for link in value[key]['memberships']}
            memberships = []
            for column, (set_id, title) in enumerate(self._set_columns, 1):
                previous = existing.get(set_id, {})
                memberships.append({
                    'set_id': set_id,
                    'title': previous.get('title', title),
                    'included': self.table.item(row, column).checkState()
                    == Qt.CheckState.Checked,
                })
            value[key]['memberships'] = memberships
        return validate_export_membership(value)

    def _save_membership(self):
        try:
            value = self._membership()
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.membership_saved.emit(value)
        self.saved_membership = value
        self._resolve_review_issues(value)
        self.status.setText('Состав наборов сохранён. Экспорт не запускался.')
        self._refresh_summary()
        self._show_summary()


    def _resolve_review_issues(self, membership):
        unresolved = []
        for issue in self.review_issues:
            if issue.get('kind') != 'ambiguous':
                unresolved.append(issue)
                continue
            paths = issue.get('paths')
            if not isinstance(paths, (list, tuple)) or not paths:
                unresolved.append(issue)
                continue
            active = 0
            for raw_path in paths:
                item = membership.get(str(Path(raw_path).resolve()))
                if item and any(link.get('included') for link in item.get('memberships', ())):
                    active += 1
            if active != 1:
                unresolved.append(issue)
        self.review_issues = unresolved

    def _manual_changed(self, *_):
        self.status.clear()

    def groups(self, membership=None):
        groups = OrderedDict()
        if membership is None:
            from studio_export_membership import validate_export_membership
            membership = validate_export_membership(self.saved_membership)
        for path in self.paths:
            for link in membership[str(path)]['memberships']:
                if link['included']:
                    group = groups.setdefault(
                        link['set_id'], {'title': link['title'], 'images': []}
                    )
                    group['images'].append(path)
        if (
            not groups or len(groups) > 100
            or any(len(group['images']) > 1000 for group in groups.values())
        ):
            raise ValueError('Выберите от 1 до 100 наборов, не более 1000 PNG в каждом')
        return list(groups.values())

    @staticmethod
    def _set_description(title):
        lowered = title.casefold()
        if 'мини' in lowered:
            return 'Основные изображения и базовые элементы'
        if 'стандарт' in lowered:
            return 'Расширенный набор с дополнительными элементами'
        if 'макси' in lowered:
            return 'Большой набор с рамками, венками и декором'
        if 'полный' in lowered or 'bundle' in lowered or 'бандл' in lowered:
            return 'Вся готовая коллекция'
        if 'персонаж' in lowered:
            return 'Персонажи и их варианты'
        if 'декор' in lowered:
            return 'Декоративные элементы коллекции'
        return 'Готовые изображения этого набора'

    def _refresh_summary(self):
        try:
            groups = self.groups()
        except ValueError:
            groups = []
        self.summary_unique_value.setText(str(len(self.paths)))
        self.summary_sets_value.setText(str(len(groups)))
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for index, group in enumerate(groups):
            card = QFrame()
            card.setProperty('v3Card', True)
            card.setMinimumHeight(105)
            card.setMaximumHeight(118)
            layout = QVBoxLayout(card)
            heading = QHBoxLayout()
            title = QLabel(group['title'])
            title.setStyleSheet('font-size:16px; font-weight:700;')
            count = QLabel(f"{len(group['images'])} PNG")
            count.setProperty('v3Selection', True)
            heading.addWidget(title)
            heading.addStretch(1)
            heading.addWidget(count)
            layout.addLayout(heading)
            description = QLabel(self._set_description(group['title']))
            description.setProperty('v3Description', True)
            description.setWordWrap(True)
            layout.addWidget(description)
            self.cards_layout.addWidget(card, index // 3, index % 3)
        issue_count = len(self.review_issues)
        self.issue_panel.setVisible(issue_count > 0)
        if issue_count:
            self.issue_text.setText(
                f'Нужно проверить {issue_count} изображений. '
                'Приложение ничего не выбрало автоматически.'
            )
        self.export_button.setEnabled(bool(groups) and not issue_count and self.worker is None)

    def _show_manual_editor(self):
        self._rebuild_manual_table()
        self.stack.setCurrentWidget(self.manual_page)
        self.status.clear()

    def _show_summary(self):
        self._hide_preview()
        self._refresh_summary()
        self.stack.setCurrentWidget(self.summary_page)

    def _show_preview(self, item, global_pos=None):
        if item is None or item.column() != 0:
            self._hide_preview()
            return
        path = Path(str(item.data(Qt.ItemDataRole.UserRole) or ''))
        if not path.is_file():
            self._hide_preview()
            return
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._hide_preview()
            return
        pixmap = pixmap.scaled(
            220, 220, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_popup.setPixmap(pixmap)
        point = global_pos if isinstance(global_pos, QPoint) else QCursor.pos()
        position = point + QPoint(18, 18)
        screen = QApplication.screenAt(point)
        if screen is not None:
            area = screen.availableGeometry()
            width = max(180, pixmap.width() + 16)
            height = max(180, pixmap.height() + 16)
            position.setX(min(position.x(), area.right() - width))
            position.setY(min(position.y(), area.bottom() - height))
        self.preview_popup.move(position)
        self.preview_popup.show()

    def _hide_preview(self):
        self.preview_popup.hide()

    def eventFilter(self, watched, event):
        if watched is self.table.viewport() and event.type() == QEvent.Type.Leave:
            self._hide_preview()
        return super().eventFilter(watched, event)

    def _export(self):
        if self.worker is not None:
            return
        try:
            groups = self.groups()
            if self.review_issues:
                raise ValueError('Сначала проверьте отмеченные изображения')
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        folder = QFileDialog.getExistingDirectory(self, 'Папка для наборов')
        if not folder:
            return
        self.worker = ExportWorker(groups, folder, self)
        self.worker.finished.connect(self._finished)
        self.export_button.setEnabled(False)
        self.edit_sets_button.setEnabled(False)
        self.save_membership.setEnabled(False)
        self.return_button.setEnabled(False)
        self.status.setText(
            f'Создаю наборы: {len(groups)}. Не закрывайте приложение до завершения.'
        )
        self.worker.start()

    def _finished(self):
        worker = self.worker
        self.exported = worker.paths
        if worker.error:
            self.status.setText(worker.error)
        elif worker.paths:
            self.status.setText(
                f'Наборы созданы: {len(worker.paths)}. Папка: {worker.paths[0].parent}'
            )
        else:
            self.status.setText('Наборы не созданы.')
        self.worker = None
        worker.deleteLater()
        self.edit_sets_button.setEnabled(True)
        self.save_membership.setEnabled(True)
        self.return_button.setEnabled(True)
        self._refresh_summary()

    def reject(self):
        if self.worker is not None:
            self.worker.cancelled.set()
            self.status.setText(
                'Отменяю экспорт и удаляю временные файлы. Дождитесь завершения.'
            )
            return
        self._hide_preview()
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            self._hide_preview()
            super().closeEvent(event)
