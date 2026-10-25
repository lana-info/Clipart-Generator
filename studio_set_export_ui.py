"""Automatic Clipart set summary with optional manual membership editing."""
from collections import OrderedDict
from pathlib import Path
from threading import Event
from uuid import uuid4

from PyQt6.QtCore import QEvent, QPoint, QSize, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QIcon, QImageReader, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QFrame,
    QHeaderView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QWidgetAction,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from studio_set_export import export_clipart_sets, ExportCancelled
from v3_components import apply_v3_theme


class ExportWorker(QThread):
    progress = pyqtSignal(int, int, str)  # done, total (0 = unknown), text

    def __init__(self, groups, destination, parent=None, *, workspace=None,
                 delete_intermediates=False, delete_originals=False,
                 project_name='', translator=None):
        super().__init__(parent)
        self.groups, self.destination = groups, destination
        self.project_name, self.translator = project_name, translator
        self.translation_note = ''
        self.cancelled = Event()
        self.paths, self.error = [], ''
        self.workspace = workspace
        self.delete_intermediates = delete_intermediates
        self.delete_originals = delete_originals
        self.cleanup_message = ''

    def run(self):
        try:
            exported_hashes = {}
            names = {}
            if self.translator is not None:
                # ONE request for every name of the export; any failure falls back to transliteration.
                from studio_name_translation import collect_export_names, has_cyrillic
                wanted = [n for n in collect_export_names(self.project_name, self.groups) if has_cyrillic(n)]
                if wanted:
                    self.progress.emit(0, 0, 'Перевожу названия на английский…')
                    try:
                        names = self.translator(wanted, cancelled=self.cancelled.is_set)
                        self.translation_note = ' Названия переведены на английский.'
                    except Exception:
                        names = {}
                        self.translation_note = (' Перевод не удался — имена даны транслитом; '
                                                 'платный запрос мог быть отправлен.')
            self.paths = export_clipart_sets(
                self.groups, self.destination, cancelled=self.cancelled.is_set,
                exported_hashes=exported_hashes, project_name=self.project_name, names=names,
                progress=lambda done, total, text: self.progress.emit(done, total, text),
            )
        except ExportCancelled:
            self.error = 'Экспорт отменён. Наборы не опубликованы.'
        except Exception:
            self.error = (
                'Не удалось создать наборы. Проверьте PNG, свободное место и '
                'доступ к папке. Неполные наборы не опубликованы.'
            )
        if self.paths and not self.cancelled.is_set() and (self.delete_intermediates or self.delete_originals):
            from studio_working_files import cleanup_working_files
            try:
                deleted, skipped = cleanup_working_files(
                    self.workspace, exported_hashes,
                    intermediates=self.delete_intermediates, originals=self.delete_originals,
                )
                self.cleanup_message = f' Рабочих файлов удалено: {deleted}.'
                if skipped:
                    self.cleanup_message += f' Оставлено без изменений: {skipped}.'
            except (OSError, ValueError):
                self.cleanup_message = ' Архивы сохранены, но очистку рабочих файлов завершить не удалось.'


class _CheckerPreview(QLabel):
    """The picture on a checkerboard, always as large as the free space allows."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ''
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(160, 160)

    def set_path(self, path):
        self._path = str(path or '')
        self._refit()

    def _refit(self):
        if not self._path:
            self.setPixmap(QPixmap())
            return
        bound = max(min(self.width(), self.height()) - 4, 64)
        self.setPixmap(SetExportDialog._checker_pixmap(self._path, bound))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._path:
            self._refit()


class SetExportDialog(QDialog):
    busy_changed = pyqtSignal()
    membership_saved = pyqtSignal(object)
    fix_requested = pyqtSignal(str)
    mark_requested = pyqtSignal(str, str)  # (png path, review mark) — same marks as on the results step
    review_requested = pyqtSignal()
    QUALITY_THUMB = 120
    export_availability_changed = pyqtSignal(bool)

    @staticmethod
    def _scaled_pixmap(path, bound):
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        size = reader.size()
        if not size.isValid() or size.width() * size.height() > 100_000_000:
            return QPixmap()
        reader.setScaledSize(size.scaled(
            QSize(bound, bound), Qt.AspectRatioMode.KeepAspectRatio,
        ))
        return QPixmap.fromImage(reader.read())

    def __init__(self, paths, parent=None, *, membership=None, review_issues=None, quality_reports=None,
                 workspace=None, embedded=False, project_name='', name_translator=None):
        super().__init__(parent)
        self.project_name = str(project_name or '')
        self.name_translator = name_translator
        self.embedded = embedded
        self.workspace = workspace
        from studio_export_membership import validate_export_membership

        saved = validate_export_membership(membership or {})
        self.paths = list(dict.fromkeys(Path(path).resolve() for path in paths))
        for path in self.paths:
            key = str(path)
            if key not in saved:
                saved.update(validate_export_membership(
                    {key: {'title': 'Set 1', 'included': True}}
                ))
        self.saved_membership = saved
        self._review_issue_candidates = [dict(issue) for issue in (review_issues or ())]
        self.review_issues = list(self._review_issue_candidates)
        allowed_paths = {str(path) for path in self.paths}
        self.quality_reports = {}
        for report in quality_reports or ():
            raw_path = str(getattr(report, 'path', '') or '')
            status = str(getattr(report, 'status', '') or '')
            if not raw_path or status not in {'ok', 'review', 'block'}:
                raise ValueError('Повреждён результат проверки PNG')
            key = str(Path(raw_path).resolve())
            if key in allowed_paths:
                self.quality_reports[key] = report
        self.worker = None
        self._viewed_quality = set()
        self._marks = {}
        self._marks_enabled = False
        self._quality_page_base_text = ''
        self.exported = []
        self._set_columns = []
        self._editing_set_id = None

        self.setWindowTitle('Clipart · Экспорт наборов')
        self.resize(1040, 720)
        apply_v3_theme(self)
        root = QVBoxLayout(self)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        self.summary_page = self._build_summary_page()
        self.quality_page = self._build_quality_page()
        self.manual_page = self.summary_page
        self.create_page = self._build_create_page()
        self.stack.addWidget(self.summary_page)
        self.stack.addWidget(self.quality_page)
        self.stack.addWidget(self.create_page)
        self.stack.setCurrentWidget(self.summary_page)
        if embedded:
            self.export_button.hide()
            self.setWindowFlags(Qt.WindowType.Widget)

        # Rarely needed and destructive, so they live in a menu instead of taking room under the pictures.
        self.delete_intermediates = QCheckBox('Удалить рабочие файлы после экспорта')
        self.delete_originals = QCheckBox('Удалить исходные картинки генерации после экспорта')
        self.delete_intermediates.setToolTip('Файлы, нужные только для обработки, удаляются после создания ZIP.')
        self.delete_originals.setToolTip('Картинки, полученные от генерации до вырезания, удаляются после создания ZIP.')
        options_menu = QMenu(self)
        for checkbox in (self.delete_intermediates, self.delete_originals):
            checkbox.setEnabled(workspace is not None)
            action = QWidgetAction(options_menu)
            action.setDefaultWidget(checkbox)
            options_menu.addAction(action)
        self.export_options_button = QPushButton('Параметры экспорта')
        self.export_options_button.setProperty('v3Button', True)
        self.export_options_button.setProperty('variant', 'ghost')
        self.export_options_button.setMenu(options_menu)
        self.export_options_button.setEnabled(workspace is not None)
        self.status = QLabel('')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        bottom = QHBoxLayout()
        bottom.addWidget(self.export_options_button)
        bottom.addWidget(self.status, 1)
        root.addLayout(bottom)
        # Large, obvious progress for long exports (owner request 2026-10-19).
        self.export_progress = QProgressBar()
        self.export_progress.setMinimumHeight(24)
        self.export_progress.setAccessibleName('Ход экспорта')
        self.export_progress.hide()
        root.addWidget(self.export_progress)

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
        self._resolve_review_issues(self.saved_membership)
        self._refresh_summary()

    def _build_summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel('Экспорт наборов')
        title.setProperty('v3Title', True)
        layout.addWidget(title)
        heading = QHBoxLayout()
        self.summary_counts = QLabel('')
        heading.addWidget(self.summary_counts)
        heading.addStretch(1)
        self.new_set_button = QPushButton('+ Добавить набор')
        self.new_set_button.setProperty('v3Button', True)
        self.new_set_button.setProperty('variant', 'secondary')
        self.new_set_button.clicked.connect(self._show_create_page)
        heading.addWidget(self.new_set_button)
        layout.addLayout(heading)
        self._build_membership_table(layout)
        actions = QHBoxLayout()
        self.rename_set_button = QPushButton('Переименовать набор')
        self.rename_set_button.setProperty('v3Button', True)
        self.rename_set_button.setProperty('variant', 'secondary')
        self.rename_set_button.clicked.connect(self._rename_current_set)
        self.delete_set_button = QPushButton('Удалить набор')
        self.delete_set_button.setProperty('v3Button', True)
        self.delete_set_button.setProperty('variant', 'secondary')
        self.delete_set_button.clicked.connect(self._delete_current_set)
        actions.addWidget(self.rename_set_button)
        actions.addWidget(self.delete_set_button)
        actions.addStretch(1)
        layout.addLayout(actions)
        self.issue_panel = QFrame()
        self.issue_panel.setProperty('v3Card', True)
        self.issue_panel.setProperty('state', 'warning')
        issue_layout = QHBoxLayout(self.issue_panel)
        self.issue_text = QLabel('')
        self.issue_text.setWordWrap(True)
        issue_layout.addWidget(self.issue_text, 1)
        self.review_now_button = QPushButton('Проверить')
        self.review_now_button.setProperty('v3Button', True)
        self.review_now_button.setProperty('variant', 'secondary')
        self.review_now_button.clicked.connect(self._review_incomplete)
        issue_layout.addWidget(self.review_now_button)
        layout.addWidget(self.issue_panel)
        self.ready_only = QCheckBox('Экспортировать только готовые PNG')
        self.ready_only.toggled.connect(lambda: self._refresh_summary(rebuild=False))
        layout.addWidget(self.ready_only)
        self.quality_panel = QFrame()
        self.quality_panel.setProperty('v3Card', True)
        quality_layout = QHBoxLayout(self.quality_panel)
        self.quality_summary_label = QLabel('')
        self.quality_summary_label.setWordWrap(True)
        quality_layout.addWidget(self.quality_summary_label, 1)
        self.review_quality_button = QPushButton('Проверить PNG')
        self.review_quality_button.setProperty('v3Button', True)
        self.review_quality_button.setProperty('variant', 'secondary')
        self.review_quality_button.clicked.connect(self._show_quality_review)
        quality_layout.addWidget(self.review_quality_button)
        layout.addWidget(self.quality_panel)
        self.empty_hint = QLabel('Готовых PNG пока нет. Проект можно сохранить и продолжить позже.')
        self.empty_hint.setWordWrap(True)
        layout.addWidget(self.empty_hint)
        actions = QHBoxLayout()
        actions.addStretch(1)
        self.export_button = QPushButton('Создать ZIP-наборы')
        self.export_button.setProperty('v3Button', True)
        self.export_button.setProperty('variant', 'primary')
        self.export_button.clicked.connect(self._export)
        actions.addWidget(self.export_button)
        layout.addLayout(actions)
        return page

    def _review_incomplete(self):
        if self.embedded:
            self.review_requested.emit()
        else:
            self._show_manual_editor()

    def _blocking_review_issues(self):
        return [issue for issue in self.review_issues
                if issue.get('kind') != 'missing' or not self.ready_only.isChecked()]

    def _build_quality_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel('Проверка PNG перед экспортом')
        title.setProperty('v3Title', True)
        self.quality_page_summary_label = QLabel('')
        self.quality_page_summary_label.setProperty('v3Small', True)
        self._quality_only_problems = False  # the owner must see every PNG before publishing; problems are a filter
        filters = QHBoxLayout()
        filters.addWidget(title)
        filters.addWidget(self.quality_page_summary_label)
        filters.addSpacing(12)
        self.quality_filter_problems = QPushButton('')
        self.quality_filter_all = QPushButton('')
        for button, only_problems in ((self.quality_filter_problems, True), (self.quality_filter_all, False)):
            button.setProperty('v3Button', True)
            button.clicked.connect(lambda _=False, value=only_problems: self._set_quality_filter(value))
            filters.addWidget(button)
        filters.addStretch(1)
        layout.addLayout(filters)

        body = QHBoxLayout()
        self.quality_list = QListWidget()
        self.quality_list.setViewMode(QListView.ViewMode.IconMode)
        self.quality_list.setIconSize(QSize(self.QUALITY_THUMB, self.QUALITY_THUMB))
        self.quality_list.setGridSize(QSize(self.QUALITY_THUMB + 28, self.QUALITY_THUMB + 56))
        self.quality_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.quality_list.setMovement(QListView.Movement.Static)
        self.quality_list.setWordWrap(True)
        self.quality_list.setSpacing(6)
        self.quality_list.setUniformItemSizes(True)
        self.quality_list.setMinimumWidth(330)
        self.quality_list.currentRowChanged.connect(self._quality_selected)
        body.addWidget(self.quality_list, 2)
        detail = QFrame()
        detail.setProperty('v3Card', True)
        detail_layout = QVBoxLayout(detail)
        self.quality_issue_title = QLabel('Выберите PNG')
        self.quality_issue_title.setProperty('v3Title', True)
        self.quality_picture = _CheckerPreview()
        self.quality_issue_text = QLabel('')
        self.quality_issue_text.setWordWrap(True)
        self.quality_action_text = QLabel('')
        self.quality_action_text.setWordWrap(True)
        self.quality_action_text.setProperty('v3Description', True)
        detail_layout.addWidget(self.quality_picture, 1)
        # Quick marks (the same as on the results step); shown only when the owner flow can store them.
        self.quality_marks_row = QWidget()
        marks_layout = QHBoxLayout(self.quality_marks_row)
        marks_layout.setContentsMargins(0, 0, 0, 0)
        self.quality_mark_buttons = {}
        for key, label in (('ok', 'Ок'), ('bad_generation', 'Брак генерации'), ('bad_cutout', 'Брак вырезания')):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty('v3Chip', True)
            button.setAccessibleName(f'Метка: {label}')
            button.clicked.connect(lambda _=False, mark=key: self._quality_mark_clicked(mark))
            self.quality_mark_buttons[key] = button
            marks_layout.addWidget(button)
        marks_layout.addStretch(1)
        self.quality_marks_row.hide()
        detail_layout.addWidget(self.quality_marks_row)
        detail_layout.addWidget(self.quality_issue_title)
        detail_layout.addWidget(self.quality_issue_text)
        detail_layout.addWidget(self.quality_action_text)
        detail_actions = QHBoxLayout()
        self.quality_fix_button = QPushButton('Открыть в проверке прозрачности')
        self.quality_fix_button.setProperty('v3Button', True)
        self.quality_fix_button.setProperty('variant', 'primary')
        self.quality_fix_button.clicked.connect(self._request_quality_fix)
        self.quality_exclude_button = QPushButton('Исключить из наборов')
        self.quality_exclude_button.setProperty('v3Button', True)
        self.quality_exclude_button.setProperty('variant', 'secondary')
        self.quality_exclude_button.clicked.connect(self._exclude_quality_selected)
        detail_actions.addWidget(self.quality_fix_button)
        detail_actions.addWidget(self.quality_exclude_button)
        detail_layout.addLayout(detail_actions)
        body.addWidget(detail, 3)
        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        self.quality_back_button = QPushButton('← К наборам')
        self.quality_back_button.setProperty('v3Button', True)
        self.quality_back_button.setProperty('variant', 'secondary')
        self.quality_back_button.clicked.connect(self._show_summary)
        footer.addWidget(self.quality_back_button)
        footer.addStretch(1)
        self.quality_export_button = QPushButton('Создать ZIP-наборы')
        self.quality_export_button.setProperty('v3Button', True)
        self.quality_export_button.setProperty('variant', 'primary')
        self.quality_export_button.clicked.connect(self._export)
        self.quality_export_button.hide()  # the one «Создать ZIP-наборы» is in the window footer
        footer.addWidget(self.quality_export_button)
        layout.addLayout(footer)
        return page

    def _build_membership_table(self, layout):
        self.table = QTableWidget(0, 1)
        self.table.setMouseTracking(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setIconSize(QSize(44, 44))
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.itemEntered.connect(
            lambda item: self._show_preview(item, QCursor.pos())
        )
        self.table.viewport().installEventFilter(self)
        self.table.itemChanged.connect(self._manual_changed)
        layout.addWidget(self.table, 1)

        self.table.horizontalHeader().setSectionsClickable(True)
        self.table.horizontalHeader().sectionClicked.connect(self._choose_set_column)
        self.table.currentCellChanged.connect(lambda _row, column, *_: self._choose_set_column(column))

    def _choose_set_column(self, column):
        if self.worker is not None or not 1 <= column <= len(self._set_columns):
            return
        self._editing_set_id = self._set_columns[column - 1][0]
        self.rename_set_button.setEnabled(True)
        self.delete_set_button.setEnabled(True)

    def _build_create_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        title = QLabel('Новый набор')
        title.setProperty('v3Title', True)
        layout.addWidget(title)
        note = QLabel('Назовите набор и выберите готовые PNG. Генерация заново не запускается.')
        note.setProperty('v3Description', True)
        layout.addWidget(note)
        self.new_set_name = QLineEdit()
        self.new_set_name.setMaxLength(200)
        self.new_set_name.setPlaceholderText('Например: Winter Characters')
        layout.addWidget(QLabel('Название набора'))
        layout.addWidget(self.new_set_name)
        layout.addWidget(QLabel('Добавить изображения'))
        self.new_set_images = QListWidget()
        self.new_set_images.setMouseTracking(True)
        self.new_set_images.setIconSize(QSize(44, 44))
        self.new_set_images.itemEntered.connect(
            lambda item: self._show_preview_path(item.data(Qt.ItemDataRole.UserRole), QCursor.pos())
        )
        self.new_set_images.viewport().installEventFilter(self)
        layout.addWidget(self.new_set_images, 1)
        actions = QHBoxLayout()
        self.cancel_new_set_button = QPushButton('К наборам')
        self.cancel_new_set_button.clicked.connect(self._show_summary)
        self.create_set_button = QPushButton('Создать набор')
        self.create_set_button.setProperty('v3Button', True)
        self.create_set_button.setProperty('variant', 'primary')
        self.create_set_button.clicked.connect(self._create_set)
        actions.addWidget(self.cancel_new_set_button)
        actions.addStretch(1)
        actions.addWidget(self.create_set_button)
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
                name.setToolTip(path.name)
                pixmap = self._scaled_pixmap(path, 44)
                if not pixmap.isNull():
                    name.setIcon(QIcon(pixmap))
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
        self._persist_membership(value, 'Состав наборов сохранён. Экспорт не запускался.')


    def _resolve_review_issues(self, membership):
        unresolved = []
        # A resolved choice can become ambiguous again after another checkbox
        # change. Keep the original candidates and recompute current blockers.
        for issue in self._review_issue_candidates:
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

    def _path_is_active(self, path, membership=None):
        source = self.saved_membership if membership is None else membership
        item = source.get(str(Path(path).resolve()))
        return bool(item and any(link.get('included') for link in item.get('memberships', ())))

    def _active_quality_blockers(self, membership=None):
        return [
            report for path, report in self.quality_reports.items()
            if report.status == 'block' and self._path_is_active(path, membership)
        ]

    def _refresh_quality_page(self):
        if not hasattr(self, 'quality_list'):
            return
        selected_path = ''
        current = self.quality_list.currentItem()
        if current is not None:
            selected_path = str(current.data(Qt.ItemDataRole.UserRole) or '')
        self.quality_list.blockSignals(True)
        self.quality_list.clear()
        selected_row = -1
        status_labels = {'ok': 'Готово', 'review': 'Проверьте края', 'block': 'Не экспортировать'}
        total = sum(str(path) in self.quality_reports for path in self.paths)
        problems = sum(
            self.quality_reports[str(path)].status != 'ok'
            for path in self.paths if str(path) in self.quality_reports
        )
        self.quality_filter_problems.setText(f'Нужно посмотреть ({problems})')
        self.quality_filter_all.setText(f'Все ({total})')
        only_problems = self._quality_only_problems and problems > 0
        for button, active in ((self.quality_filter_problems, only_problems), (self.quality_filter_all, not only_problems)):
            button.setProperty('variant', 'primary' if active else 'secondary')
            button.style().unpolish(button)
            button.style().polish(button)
        for path in self.paths:
            key = str(path)
            report = self.quality_reports.get(key)
            if report is None or (only_problems and report.status == 'ok'):
                continue
            active = self._path_is_active(key)
            if not active:
                status = 'Исключено из наборов'
            else:
                status = status_labels[report.status]
            mark = {'bad_generation': 'Брак генерации', 'bad_cutout': 'Брак вырезания'}.get(self._marks.get(key, ''), '')
            if mark and active:
                status = mark if report.status == 'ok' else f'{status} · {mark}'
            row = QListWidgetItem(path.name if (active and report.status == 'ok' and not mark) else f'{path.name}\n{status}')
            row.setData(Qt.ItemDataRole.UserRole, key)
            row.setToolTip(f'{path.name} — {status}')
            row.setIcon(self._quality_icon(key, report, active, key in self._viewed_quality))
            self.quality_list.addItem(row)
            if key == selected_path:
                selected_row = self.quality_list.count() - 1
        self.quality_list.blockSignals(False)
        if self.quality_list.count():
            self.quality_list.setCurrentRow(selected_row if selected_row >= 0 else 0)
        else:
            self._quality_selected(-1)

    def _set_quality_filter(self, only_problems):
        self._quality_only_problems = only_problems
        self._refresh_quality_page()

    def _quality_icon(self, key, report, active, viewed):
        """Thumbnail on the checkerboard with a status badge (⚠/✕) and a «viewed» tick; excluded files are dimmed."""
        size = self.QUALITY_THUMB
        picture = self._checker_pixmap(key, size)
        canvas = QPixmap(size, size)
        canvas.fill(QColor('#1b2636'))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not picture.isNull():
            painter.setOpacity(1.0 if active else 0.35)
            painter.drawPixmap((size - picture.width()) // 2, (size - picture.height()) // 2, picture)
            painter.setOpacity(1.0)
        font = QFont(painter.font())
        font.setPixelSize(13)
        font.setBold(True)
        painter.setFont(font)

        def badge(x, y, fill, glyph, ink):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(fill))
            painter.drawEllipse(x, y, 22, 22)
            painter.setPen(QColor(ink))
            painter.drawText(x, y, 22, 22, int(Qt.AlignmentFlag.AlignCenter), glyph)

        if viewed:
            badge(size - 25, 3, '#2dd4bf', '✓', '#06201c')
        if active and report.status == 'review':
            badge(3, size - 25, '#f59e0b', '!', '#1f1300')
        elif active and report.status == 'block':
            badge(3, size - 25, '#f87171', '✕', '#2a0a0a')
        painter.end()
        icon = QIcon()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
            icon.addPixmap(canvas, mode)  # no highlight tint over the picture itself: the selection is drawn on the cell
        return icon

    @staticmethod
    def _checker_pixmap(path, bound=220):
        picture = SetExportDialog._scaled_pixmap(path, bound)
        if picture.isNull():
            return picture
        canvas = QPixmap(picture.size())
        painter = QPainter(canvas)
        for y in range(0, canvas.height(), 14):
            for x in range(0, canvas.width(), 14):
                painter.fillRect(x, y, 14, 14, QColor('#d6dce4' if (x // 14 + y // 14) % 2 else '#ffffff'))
        painter.drawPixmap(0, 0, picture)
        painter.end()
        return canvas

    def _quality_selected(self, row):
        item = self.quality_list.item(row) if 0 <= row < self.quality_list.count() else None
        key = str(item.data(Qt.ItemDataRole.UserRole) or '') if item is not None else ''
        report = self.quality_reports.get(key)
        active = bool(key and self._path_is_active(key))
        self.quality_picture.set_path(key if report is not None else '')
        if report is not None:
            self._mark_quality_viewed(key, item, report, active)
        self._sync_mark_buttons(key)
        if report is None:
            self.quality_issue_title.setText('Выберите PNG')
            self.quality_issue_title.show()
            self.quality_issue_text.clear()
            self.quality_action_text.clear()
            self.quality_issue_text.hide()
            self.quality_action_text.hide()
            self.quality_fix_button.setEnabled(False)
            self.quality_exclude_button.setEnabled(False)
            return
        title = {'ok': '', 'review': 'Проверьте края', 'block': 'Не экспортировать'}[report.status]
        if not active:
            title = 'Исключено из наборов'
        self.quality_issue_title.setText(title)
        messages = '\n'.join(f'• {issue.message}' for issue in report.issues)
        actions = '\n'.join(f'• {issue.action}' for issue in report.issues if issue.action)
        self.quality_issue_text.setText(messages)
        self.quality_action_text.setText(('Что сделать:\n' + actions) if actions else '')
        for label in (self.quality_issue_title, self.quality_issue_text, self.quality_action_text):
            label.setVisible(bool(label.text()))
        self.quality_fix_button.setEnabled(active and self.worker is None)
        self.quality_exclude_button.setEnabled(active and self.worker is None)

    def enable_marks(self, marks):
        """Show the quick marks; ``marks`` maps a PNG path to its current mark."""
        self._marks = {str(Path(path).resolve()): mark for path, mark in dict(marks).items()}
        self._marks_enabled = True
        self._sync_mark_buttons(self._current_quality_key())

    def _current_quality_key(self):
        item = self.quality_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or '') if item is not None else ''

    def _sync_mark_buttons(self, key):
        known = self._marks_enabled and key in self._marks
        self.quality_marks_row.setVisible(known)
        for mark, button in self.quality_mark_buttons.items():
            button.setChecked(known and self._marks.get(key) == mark)
            button.setEnabled(known and self.worker is None)

    def _quality_mark_clicked(self, mark):
        key = self._current_quality_key()
        if not key or key not in self._marks:
            return
        self._marks[key] = mark
        self.mark_requested.emit(key, mark)
        self._sync_mark_buttons(key)
        self._refresh_quality_page()

    def _mark_quality_viewed(self, key, item, report, active):
        if key in self._viewed_quality:
            return
        self._viewed_quality.add(key)
        item.setIcon(self._quality_icon(key, report, active, True))
        self._set_quality_page_text(self._quality_page_base_text)

    def _viewed_counts(self):
        keys = [str(path) for path in self.paths if str(path) in self.quality_reports and self._path_is_active(path)]
        return sum(key in self._viewed_quality for key in keys), len(keys)

    def _set_quality_page_text(self, base):
        self._quality_page_base_text = base
        viewed, total = self._viewed_counts()
        counter = f'Просмотрено {viewed} из {total}' if total else ''
        self.quality_page_summary_label.setText(' · '.join(part for part in (counter, base) if part))

    def _confirm_unviewed(self, viewed, total):
        """True = create the sets anyway; False = go back and look at the rest."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle('Не все PNG просмотрены')
        box.setText(f'Просмотрено {viewed} из {total}. Всё равно создать наборы?')
        review = box.addButton('Просмотреть оставшиеся', QMessageBox.ButtonRole.AcceptRole)
        create = box.addButton('Создать', QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(review)
        box.exec()
        return box.clickedButton() is create

    def _show_first_unviewed(self):
        self._show_quality_review()
        for row in range(self.quality_list.count()):
            if str(self.quality_list.item(row).data(Qt.ItemDataRole.UserRole) or '') not in self._viewed_quality:
                self.quality_list.setCurrentRow(row)
                break

    def _show_quality_review(self):
        self._refresh_quality_page()
        self.stack.setCurrentWidget(self.quality_page)
        self.status.clear()

    def _request_quality_fix(self):
        if self.worker is not None:
            return
        item = self.quality_list.currentItem()
        if item is None:
            return
        path = str(item.data(Qt.ItemDataRole.UserRole) or '')
        report = self.quality_reports.get(path)
        if not path or report is None or not self._path_is_active(path):
            return
        if not self.embedded:
            self.done(QDialog.DialogCode.Rejected)
        self.fix_requested.emit(path)

    def _exclude_quality_selected(self):
        if self.worker is not None:
            return
        item = self.quality_list.currentItem()
        if item is None:
            return
        path = str(item.data(Qt.ItemDataRole.UserRole) or '')
        report = self.quality_reports.get(path)
        if not path or report is None:
            return
        from studio_export_membership import validate_export_membership
        value = validate_export_membership(self.saved_membership)
        entry = value.get(path)
        if entry is None:
            return
        for link in entry['memberships']:
            link['included'] = False
        value = validate_export_membership(value)
        self.saved_membership = value
        self._resolve_review_issues(value)
        self.membership_saved.emit(value)
        self.status.setText('Дизайн исключён из наборов. Файл на диске не удалён.')
        self._refresh_summary()
        self._refresh_quality_page()

    def _manual_changed(self, *_):
        if self.worker is not None:
            return
        try:
            value = self._membership()
        except ValueError as error:
            self.status.setText(str(error))
            return
        self.saved_membership = value
        self._resolve_review_issues(value)
        self.membership_saved.emit(value)
        self.status.clear()
        self._refresh_summary(rebuild=False)


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

    def _refresh_summary(self, *, rebuild=True):
        catalog = self._set_catalog()
        if rebuild:
            self._rebuild_manual_table()
        try:
            groups = self.groups()
        except ValueError:
            groups = []
        count = len(self.paths)
        images_word = 'изображение' if count % 10 == 1 and count % 100 != 11 else (
            'изображения' if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14) else 'изображений')
        set_count = len(catalog)
        sets_word = 'набор' if set_count % 10 == 1 and set_count % 100 != 11 else (
            'набора' if set_count % 10 in (2, 3, 4) and set_count % 100 not in (12, 13, 14) else 'наборов')
        self.summary_counts.setText(f'{count} {images_word} · {set_count} {sets_word}')
        self.empty_hint.setVisible(not self.paths)
        self.new_set_button.setEnabled(bool(self.paths) and self.worker is None)
        if self._editing_set_id not in dict(catalog):
            self._editing_set_id = catalog[0][0] if len(catalog) == 1 else None
        for button in (self.rename_set_button, self.delete_set_button):
            button.setEnabled(self._editing_set_id is not None and self.worker is None)
        issue_count = len(self.review_issues)
        missing_count = sum(issue.get('kind') == 'missing' for issue in self.review_issues)
        self.issue_panel.setVisible(issue_count > 0)
        self.ready_only.setVisible(missing_count > 0)
        self.ready_only.setEnabled(missing_count > 0 and self.worker is None)
        if issue_count:
            parts = [f'Готово: {count} PNG']
            if missing_count:
                parts.append(f'Не завершено: {missing_count} изображений')
            if issue_count > missing_count:
                parts.append(f'Нужно выбрать вариант: {issue_count - missing_count}')
            self.issue_text.setText(' · '.join(parts))
        review_count = sum(
            report.status == 'review' and self._path_is_active(path)
            for path, report in self.quality_reports.items()
        )
        block_count = len(self._active_quality_blockers())
        quality_issue_count = review_count + block_count
        self.quality_panel.setVisible(quality_issue_count > 0)
        if quality_issue_count:
            parts = []
            if review_count:
                parts.append(f'{review_count} нужно проверить')
            if block_count:
                parts.append(f'{block_count} блокирует экспорт')
            quality_text = (
                'Автопроверка PNG: ' + ' · '.join(parts) + '. '
                'Файлы не изменялись.'
            )
            self.quality_summary_label.setText(quality_text)
            total = sum(str(path) in self.quality_reports for path in self.paths)
            page_text = f'Блокирует экспорт: {block_count}' if block_count else ''
            self._set_quality_page_text(page_text)
            self.quality_panel.setProperty('state', 'error' if block_count else 'warning')
            self.quality_panel.style().unpolish(self.quality_panel)
            self.quality_panel.style().polish(self.quality_panel)
        else:
            self.quality_summary_label.clear()
            self._set_quality_page_text('')
        export_enabled = bool(groups) and not self._blocking_review_issues() and not block_count and self.worker is None
        self.export_button.setEnabled(export_enabled)
        self.quality_export_button.setEnabled(export_enabled)
        self.export_availability_changed.emit(export_enabled)

    def _show_manual_editor(self, set_id=None):
        if not isinstance(set_id, str):
            set_id = None
        catalog = self._set_catalog()
        self._editing_set_id = set_id or (catalog[0][0] if len(catalog) == 1 else None)
        self._rebuild_manual_table()
        self.rename_set_button.setEnabled(self._editing_set_id is not None)
        self.delete_set_button.setEnabled(self._editing_set_id is not None)
        self.stack.setCurrentWidget(self.manual_page)
        self.status.clear()

    def _show_create_page(self):
        if self.worker is not None:
            return
        self.new_set_name.clear()
        self.new_set_images.clear()
        for index, path in enumerate(self.paths):
            item = QListWidgetItem(path.name)
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            pixmap = self._scaled_pixmap(path, 44)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap))
            item.setSizeHint(QSize(0, 60))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if index == 0 else Qt.CheckState.Unchecked)
            self.new_set_images.addItem(item)
        self.stack.setCurrentWidget(self.create_page)
        self.status.clear()

    def _persist_membership(self, value, message, *, show_summary=True):
        from studio_export_membership import validate_export_membership
        value = validate_export_membership(value)
        self.saved_membership = value
        self.membership_saved.emit(value)
        self._resolve_review_issues(value)
        self.status.setText(message)
        self._refresh_summary()
        self._refresh_quality_page()
        if show_summary:
            self.stack.setCurrentWidget(self.summary_page)

    def _create_set(self):
        title = self.new_set_name.text().strip()
        if not title:
            self.status.setText('Введите название набора.')
            return
        if any(existing.casefold() == title.casefold() for _, existing in self._set_catalog()):
            self.status.setText('Набор с таким названием уже существует.')
            return
        selected = {
            self.new_set_images.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.new_set_images.count())
            if self.new_set_images.item(row).checkState() == Qt.CheckState.Checked
        }
        if not selected:
            self.status.setText('Выберите хотя бы один PNG для нового набора.')
            return
        value = self._membership() if self.stack.currentWidget() is self.manual_page else self.saved_membership
        value = {key: dict(item, memberships=[dict(link) for link in item['memberships']])
                 for key, item in value.items()}
        set_id = str(uuid4())
        for path in self.paths:
            value[str(path)]['memberships'].append({
                'set_id': set_id, 'title': title, 'included': str(path) in selected,
            })
        try:
            self._persist_membership(value, f'Набор «{title}» создан. Экспорт не запускался.')
        except ValueError as error:
            self.status.setText(str(error))

    def _rename_current_set(self):
        set_id = self._editing_set_id
        if not set_id or self.worker is not None:
            return
        catalog = dict(self._set_catalog())
        previous = catalog.get(set_id)
        if previous is None:
            return
        title, accepted = QInputDialog.getText(self, 'Переименовать набор',
            'Новое название:', text=previous)
        if not accepted:
            return
        title = title.strip()
        if not title or len(title) > 200 or any(
            other_id != set_id and other_title.casefold() == title.casefold()
            for other_id, other_title in catalog.items()
        ):
            self.status.setText('Укажите другое название набора (до 200 символов).')
            return
        value = self._membership()
        for item in value.values():
            for link in item['memberships']:
                if link['set_id'] == set_id:
                    link['title'] = title
        self._persist_membership(value, f'Набор переименован в «{title}».')

    def _delete_current_set(self):
        self._delete_set(self._editing_set_id)

    def _delete_set(self, set_id):
        if not set_id or self.worker is not None:
            return
        title = dict(self._set_catalog()).get(set_id)
        if title is None:
            return
        answer = QMessageBox.question(
            self, 'Удалить набор',
            f'Удалить набор «{title}»? PNG останутся в проекте.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        value = self._membership() if self.stack.currentWidget() is self.manual_page else self.saved_membership
        value = {key: dict(item, memberships=[dict(link) for link in item['memberships']
                if link['set_id'] != set_id]) for key, item in value.items()}
        self._editing_set_id = None
        self._persist_membership(value, f'Набор «{title}» удалён. PNG остались в проекте.')

    def _show_summary(self):
        self._hide_preview()
        self._refresh_summary()
        self.stack.setCurrentWidget(self.summary_page)

    def _show_preview(self, item, global_pos=None):
        if item is None or item.column() != 0:
            self._hide_preview()
            return
        self._show_preview_path(item.data(Qt.ItemDataRole.UserRole), global_pos)

    def _show_preview_path(self, raw_path, global_pos=None):
        path = Path(str(raw_path or ''))
        if not path.is_file():
            self._hide_preview()
            return
        pixmap = self._scaled_pixmap(path, 220)
        if pixmap.isNull():
            self._hide_preview()
            return
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
        if watched in (self.table.viewport(), self.new_set_images.viewport()) \
                and event.type() == QEvent.Type.Leave:
            self._hide_preview()
        if isinstance(watched, QLabel) and watched.property('previewPath'):
            if event.type() == QEvent.Type.Enter:
                self._show_preview_path(watched.property('previewPath'), QCursor.pos())
            elif event.type() == QEvent.Type.Leave:
                self._hide_preview()
        return super().eventFilter(watched, event)

    def _export(self):
        if self.worker is not None:
            return
        try:
            groups = self.groups()
            if self._blocking_review_issues():
                raise ValueError('Сначала проверьте отмеченные изображения')
            if self._active_quality_blockers():
                raise ValueError('Исправьте или исключите PNG, которые блокируют экспорт')
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        viewed, total = self._viewed_counts()
        if self.quality_reports and viewed < total and not self._confirm_unviewed(viewed, total):
            self._show_first_unviewed()
            return
        self._translation_notice = ''
        translator = self._choose_translation(groups)
        if translator is False:
            return
        folder = QFileDialog.getExistingDirectory(self, 'Папка для наборов')
        if not folder:
            return
        self.worker = ExportWorker(
            groups, folder, self, workspace=self.workspace,
            delete_intermediates=self.delete_intermediates.isChecked(),
            delete_originals=self.delete_originals.isChecked(),
            project_name=self.project_name, translator=translator,
        )
        self.table.setEnabled(False)
        self.ready_only.setEnabled(False)
        self.delete_intermediates.setEnabled(False)
        self.delete_originals.setEnabled(False)
        self.worker.finished.connect(self._finished)
        self.worker.progress.connect(self._export_progress)
        self.export_progress.setRange(0, 0)  # moving bar until the first real step
        self.export_progress.show()
        self.export_button.setEnabled(False)
        self.quality_export_button.setEnabled(False)
        self.new_set_button.setEnabled(False)
        self.rename_set_button.setEnabled(False)
        self.delete_set_button.setEnabled(False)
        self.create_set_button.setEnabled(False)
        self.quality_back_button.setEnabled(False)
        self.quality_fix_button.setEnabled(False)
        self.quality_exclude_button.setEnabled(False)
        self.status.setText(
            f'Создаю наборы: {len(groups)}. Не закрывайте приложение до завершения. '
            + (self._translation_notice or '')
        )
        self.busy_changed.emit()
        self.worker.start()

    def _choose_translation(self, groups):
        """Ask once before the only paid step. Returns a translator, None (transliterate) or False (cancel)."""
        from studio_name_translation import collect_export_names, has_cyrillic
        if not any(has_cyrillic(name) for name in collect_export_names(self.project_name, groups)):
            return None
        if self.name_translator is None:
            self._translation_notice = ('Ключ текстовой модели не найден: имена даны транслитом. '
                                        'Добавьте ключ в настройках API, чтобы переводить на английский.')
            return None
        box = QMessageBox(self)
        box.setWindowTitle('Названия на английском')
        box.setText(
            'Названия проекта, наборов и изображений будут переведены на английский '
            f'одним коротким запросом к выбранной текстовой модели ({self.name_translator.label}). '
            'Обычно это доли цента; точная сумма зависит от тарифа сервиса.')
        translate = box.addButton('Перевести', QMessageBox.ButtonRole.AcceptRole)
        translit = box.addButton('Без перевода (транслит)', QMessageBox.ButtonRole.ActionRole)
        box.addButton('Отмена', QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is translate:
            return self.name_translator
        if box.clickedButton() is translit:
            return None
        return False

    def _export_progress(self, done, total, text):
        if total <= 0:
            self.export_progress.setRange(0, 0)
        else:
            self.export_progress.setRange(0, total)
            self.export_progress.setValue(done)
            self.export_progress.setFormat(f'{done} / {total}')
        self.status.setText(text + '. Не закрывайте приложение до завершения.')
        self.status.setStyleSheet('font-size:15px;font-weight:600;')

    def _finished(self):
        worker = self.worker
        self.export_progress.hide()
        self.status.setStyleSheet('')
        self.exported = worker.paths
        if worker.error:
            self.status.setText(worker.error)
        elif worker.paths:
            self.status.setText(
                f'Наборы созданы: {len(worker.paths)}. Папка: {worker.paths[0].parent}'
                + worker.translation_note + worker.cleanup_message
            )
        else:
            self.status.setText('Наборы не созданы.')
        self.worker = None
        self.table.setEnabled(True)
        worker.deleteLater()
        self.delete_intermediates.setChecked(False)
        self.delete_originals.setChecked(False)
        self.delete_intermediates.setEnabled(self.workspace is not None)
        self.delete_originals.setEnabled(self.workspace is not None)
        self.new_set_button.setEnabled(True)
        self.rename_set_button.setEnabled(self._editing_set_id is not None)
        self.delete_set_button.setEnabled(self._editing_set_id is not None)
        self.create_set_button.setEnabled(True)
        self.quality_back_button.setEnabled(True)
        self._refresh_summary()
        self._refresh_quality_page()
        self.busy_changed.emit()

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
