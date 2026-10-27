"""Automatic Clipart set summary with optional manual membership editing."""
import hashlib
import os
from collections import OrderedDict
from pathlib import Path
from threading import Event
from uuid import uuid4

from PyQt6.QtCore import QEvent, QPoint, QPointF, QRectF, QSize, QSizeF, QThread, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QFontMetrics, QIcon, QImage, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame,
    QHeaderView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QComboBox, QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QWidgetAction,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from background_preview import PREVIEW_BACKGROUND_OPTIONS
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


_THUMB_CACHE = OrderedDict()
_THUMB_CACHE_LIMIT = 600
PRIME_BOUND = 120


def _file_stamp(path):
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return (str(path), stat.st_size, stat.st_mtime_ns)


def _read_scaled_image(path, bound):
    """Thread-safe: decode a PNG scaled to ``bound``; an empty image when it is unusable."""
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > 100_000_000:
        return QImage()
    reader.setScaledSize(size.scaled(QSize(bound, bound), Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


THUMB_CACHE_DIRNAME = ".thumb-cache"
THUMB_CACHE_MAX_FILES = 3000
THUMB_CACHE_MAX_BYTES = 150 * 1024 * 1024


def thumb_cache_dir(workspace):
    """Disk cache of thumbnails inside the project's own work folder (gone with it); None without a workspace."""
    return Path(workspace) / THUMB_CACHE_DIRNAME if workspace else None


def _thumb_cache_file(cache_dir, path, bound):
    """The key is path + size + modification time + bound, so a regenerated or edited picture never shows an old one."""
    stamp = _file_stamp(path)
    if stamp is None:
        return None
    key = hashlib.sha1(f"{stamp[0]}|{stamp[1]}|{stamp[2]}|{bound}".encode("utf-8")).hexdigest()
    return Path(cache_dir) / f"{key}.png"


def read_thumbnail(path, bound, cache_dir=None):
    """Thread-safe: the thumbnail from the disk cache when it is there, else decoded and stored for next time."""
    cached = _thumb_cache_file(cache_dir, path, bound) if cache_dir is not None else None
    if cached is not None and cached.is_file():
        image = QImage(str(cached))
        if not image.isNull():
            try:
                os.utime(cached)  # recently used: pruned last
            except OSError:
                pass
            return image
    image = _read_scaled_image(path, bound)
    if cached is not None and not image.isNull():
        try:
            cached.parent.mkdir(parents=True, exist_ok=True)
            temp = cached.with_name(f"{cached.stem}.{uuid4().hex}.tmp.png")
            if image.save(str(temp), "PNG"):
                os.replace(temp, cached)
            else:
                temp.unlink(missing_ok=True)
        except OSError:
            pass  # a cache that cannot be written only means a slower next start
    return image


def prune_thumb_cache(cache_dir, max_files=THUMB_CACHE_MAX_FILES, max_bytes=THUMB_CACHE_MAX_BYTES):
    """Keep the cache bounded: drop the least recently used thumbnails first."""
    try:
        files = [(entry.stat().st_mtime, entry.stat().st_size, entry) for entry in Path(cache_dir).iterdir()
                 if entry.is_file() and entry.suffix == ".png" and not entry.is_symlink()]
    except OSError:
        return
    files.sort(key=lambda item: item[0])
    total = sum(size for _, size, _ in files)
    while files and (len(files) > max_files or total > max_bytes):
        _, size, entry = files.pop(0)
        try:
            entry.unlink()
            total -= size
        except OSError:
            pass


class _PngCheckWorker(QThread):
    """Loads thumbnails and the transparency check one PNG at a time, off the UI thread."""
    item_ready = pyqtSignal(str, QImage, object)  # path, thumbnail, report or None

    def __init__(self, paths, loader, parent=None, cache_dir=None):
        super().__init__(parent)
        self.paths, self.loader = list(paths), loader
        self.cache_dir = cache_dir
        self._stop = Event()

    def stop(self):
        self._stop.set()

    def run(self):
        for path in self.paths:
            if self._stop.is_set():
                return
            image = read_thumbnail(path, PRIME_BOUND, self.cache_dir)
            try:
                report = self.loader(path)
            except Exception:
                report = None
            if self._stop.is_set():
                return
            self.item_ready.emit(str(path), image, report)
        if self.cache_dir is not None:
            prune_thumb_cache(self.cache_dir)


class _CheckerPreview(QLabel):
    """The picture on a checkerboard, as large as the free space allows.

    Ctrl+wheel zooms (to the cursor), space+drag or the middle button pans, a double click fits it again."""

    ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 1.0, 16.0, 1.25

    def __init__(self, parent=None):
        super().__init__(parent)
        self._path = ''
        self._background = 'checkerboard'
        self._zoom = 1.0
        self._offset = QPointF(0.0, 0.0)  # of the zoomed picture's centre from the widget centre
        self._space = False
        self._drag = None
        self._base = QPixmap()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.setMinimumSize(160, 160)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_path(self, path):
        self._path = str(path or '')
        self.fit()

    def set_background(self, background):
        self._background = background
        self._refit()

    def fit(self):
        self._zoom, self._offset = 1.0, QPointF(0.0, 0.0)
        self._refit()

    def _refit(self):
        if not self._path:
            self._base = QPixmap()
            self.setPixmap(QPixmap())
            return
        bound = max(min(self.width(), self.height()) - 4, 64)
        # A zoomed picture is rendered from a larger source so that it stays sharp.
        self._base = SetExportDialog._checker_pixmap(self._path, int(bound * min(self._zoom, 4.0)), self._background)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._path:
            self._refit()

    def _fitted_size(self):
        """Size on screen: the base pixmap is rendered at up to 4x the fit, beyond that it is scaled."""
        if self._base.isNull():
            return QSizeF(0, 0)
        extra = self._zoom / min(self._zoom, 4.0)
        return QSizeF(self._base.width() * extra, self._base.height() * extra)

    def _clamp_offset(self):
        size = self._fitted_size()
        limit_x = max((size.width() - self.width()) / 2 + 40, 0.0)
        limit_y = max((size.height() - self.height()) / 2 + 40, 0.0)
        self._offset = QPointF(min(max(self._offset.x(), -limit_x), limit_x), min(max(self._offset.y(), -limit_y), limit_y))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._base.isNull():
            painter.end()
            super().paintEvent(event)
            return
        size = self._fitted_size()
        self._clamp_offset()
        target = QRectF(
            (self.width() - size.width()) / 2 + self._offset.x(),
            (self.height() - size.height()) / 2 + self._offset.y(),
            size.width(), size.height())
        painter.drawPixmap(target, self._base, QRectF(self._base.rect()))
        painter.end()

    def wheelEvent(self, event):
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier) or self._base.isNull():
            super().wheelEvent(event)
            return
        old = self._zoom
        factor = self.ZOOM_STEP if event.angleDelta().y() > 0 else 1 / self.ZOOM_STEP
        self._zoom = min(max(old * factor, self.ZOOM_MIN), self.ZOOM_MAX)
        if self._zoom != old:
            anchor = event.position() - QPointF(self.width() / 2, self.height() / 2)
            ratio = self._zoom / old
            self._offset = anchor - (anchor - self._offset) * ratio  # the point under the cursor stays put
            if self._zoom == self.ZOOM_MIN:
                self._offset = QPointF(0.0, 0.0)
            self._refit()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.fit()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and self._space):
            self._drag = (event.position(), QPointF(self._offset))
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            start, offset = self._drag
            self._offset = offset + (event.position() - start)
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            if self._space:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class SetExportDialog(QDialog):
    busy_changed = pyqtSignal()
    membership_saved = pyqtSignal(object)
    fix_requested = pyqtSignal(str)
    mark_requested = pyqtSignal(str, str)  # (png path, review mark) — same marks as on the results step
    prompt_requested = pyqtSignal(str)  # «Изменить промпт» for a picture marked as a generation defect
    regenerate_requested = pyqtSignal(str)  # «Перегенерировать» for the same picture (paid, confirmed by the module)
    review_requested = pyqtSignal()
    QUALITY_THUMB = 120
    export_availability_changed = pyqtSignal(bool)

    @staticmethod
    def _prime_pixmap(path, image):
        """Store a thumbnail decoded by the worker thread (call from the UI thread only)."""
        stamp = _file_stamp(path)
        if stamp is not None and not image.isNull():
            _THUMB_CACHE[(stamp, PRIME_BOUND)] = QPixmap.fromImage(image)
            while len(_THUMB_CACHE) > _THUMB_CACHE_LIMIT:
                _THUMB_CACHE.popitem(last=False)

    @staticmethod
    def _primed_pixmap(path, bound):
        """A cached thumbnail scaled down, or an empty pixmap; never touches the file's pixels."""
        stamp = _file_stamp(path)
        primed = _THUMB_CACHE.get((stamp, PRIME_BOUND)) if stamp is not None else None
        if primed is None:
            return QPixmap()
        return primed.scaled(QSize(bound, bound), Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)

    @staticmethod
    def _scaled_pixmap(path, bound):
        stamp = _file_stamp(path)
        key = (stamp, bound)
        if stamp is not None and key in _THUMB_CACHE:
            return _THUMB_CACHE[key]
        primed = _THUMB_CACHE.get((stamp, PRIME_BOUND)) if stamp is not None else None
        if primed is not None and bound <= PRIME_BOUND:
            picture = primed.scaled(
                QSize(bound, bound), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        else:
            picture = QPixmap.fromImage(_read_scaled_image(path, bound))
        if stamp is not None and not picture.isNull():
            _THUMB_CACHE[key] = picture
            while len(_THUMB_CACHE) > _THUMB_CACHE_LIMIT:
                _THUMB_CACHE.popitem(last=False)
        return picture

    def __init__(self, paths, parent=None, *, membership=None, review_issues=None, quality_reports=None,
                 workspace=None, embedded=False, project_name='', name_translator=None,
                 quality_loader=None):
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
        self._quality_background = 'checkerboard'
        self._quality_loader = quality_loader
        self._check_worker = None
        self._qc_pending = 0
        self._qc_total = 0
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
        if self.embedded:
            self.quality_back_button.hide()  # «К наборам» lives in the window footer next to «Назад» (owner 2026-10-27)
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
        if quality_loader is not None and self.paths:
            self._qc_total = self._qc_pending = len(self.paths)
        self._refresh_summary()
        self._start_png_check()

    def _start_png_check(self):
        if not self._qc_pending:
            return
        self._check_worker = _PngCheckWorker(self.paths, self._quality_loader, self, thumb_cache_dir(self.workspace))
        self._check_worker.item_ready.connect(self._png_checked)
        self._check_worker.finished.connect(self._png_check_finished)
        self._check_worker.start()

    def _png_checked(self, path, image, report):
        """One PNG finished: its thumbnail and verdict appear at once, the rest keep loading."""
        self._qc_pending = max(0, self._qc_pending - 1)
        self._prime_pixmap(path, image)
        if report is not None and str(getattr(report, 'status', '')) in {'ok', 'review', 'block'}:
            self.quality_reports[str(Path(path).resolve())] = report
        done = self._qc_total - self._qc_pending
        if not self._qc_pending or done <= 1 or done % 5 == 0:
            self._refresh_summary(rebuild=not self._qc_pending)
            if self.stack.currentWidget() is self.quality_page:
                self._refresh_quality_page()

    def _png_check_finished(self):
        if self._qc_pending:  # the worker stopped early (closed or crashed): never leave export blocked silently
            self._qc_pending = 0
            self._refresh_summary()

    def _stop_png_check(self):
        worker = self._check_worker
        if worker is not None and worker.isRunning():
            worker.stop()
            worker.wait(5000)

    def _set_quality_background(self, value='checkerboard'):
        self._quality_background = value
        self.quality_picture.set_background(self._quality_background)
        self._refresh_quality_page()

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
        self.review_now_button = QPushButton('Разобрать неготовые')
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
        self.review_quality_button = QPushButton('Открыть проверку PNG')
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
        # Owner 2026-10-27: no title, counter, filter buttons or captions on this screen. The widgets stay (hidden)
        # because other code reads them; the filter is always «all» and problems are marked on the pictures.
        self._quality_only_problems = False
        self.quality_page_summary_label = QLabel('')
        self.quality_filter_problems = QPushButton('')
        self.quality_filter_all = QPushButton('')
        for hidden in (self.quality_page_summary_label, self.quality_filter_problems, self.quality_filter_all):
            hidden.hide()
        self.quality_background_buttons = {}
        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(5)
        swatch_group = QButtonGroup(self)
        swatch_group.setExclusive(True)
        for label, value in PREVIEW_BACKGROUND_OPTIONS:
            button = QPushButton('')
            button.setCheckable(True)
            button.setFixedSize(28, 28)
            button.setAccessibleName(f'Фон: {label}')
            button.setToolTip(label)
            colour = '#d7dde2' if value == 'checkerboard' else value
            button.setStyleSheet(
                f'QPushButton {{background: {colour}; border: 2px solid #526174;}} '
                'QPushButton:checked {border: 3px solid #24d8c5;}')
            if value == 'checkerboard':
                tile = QPixmap(20, 20)
                tile.fill(QColor('#eef1f4'))
                tile_painter = QPainter(tile)
                tile_painter.fillRect(0, 0, 10, 10, QColor('#c8ced4'))
                tile_painter.fillRect(10, 10, 10, 10, QColor('#c8ced4'))
                tile_painter.end()
                button.setIcon(QIcon(tile))
                button.setIconSize(QSize(20, 20))
            button.setChecked(value == 'checkerboard')
            button.clicked.connect(lambda _=False, v=value: self._set_quality_background(v))
            swatch_group.addButton(button)
            self.quality_background_buttons[value] = button
            swatch_row.addWidget(button)
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
            bold = QFont(button.font())
            bold.setBold(True)
            # The chosen chip is drawn bold; room for that keeps its label whole.
            button.setMinimumWidth(QFontMetrics(bold).horizontalAdvance(label) + 40)
            self.quality_mark_buttons[key] = button
            marks_layout.addWidget(button)
        self.quality_marks_row.hide()
        # Two rows under the picture so that they fit 1120 px: marks with «Исключить из наборов»,
        # then the actions on this picture (prompt, regenerate) with the edit button on the right.
        detail_actions = QHBoxLayout()
        detail_actions.addWidget(self.quality_marks_row)
        self.quality_fix_button = QPushButton('Редактировать прозрачность')
        self.quality_fix_button.setProperty('v3Button', True)
        self.quality_fix_button.setProperty('variant', 'primary')
        self.quality_fix_button.clicked.connect(self._request_quality_fix)
        self.quality_exclude_button = QPushButton('Исключить из наборов')
        self.quality_exclude_button.setProperty('v3Button', True)
        self.quality_exclude_button.setProperty('variant', 'secondary')
        self.quality_exclude_button.clicked.connect(self._exclude_quality_selected)
        detail_actions.addStretch(1)
        detail_actions.addWidget(self.quality_exclude_button)
        detail_layout.addLayout(detail_actions)
        action_row = QHBoxLayout()
        self.quality_prompt_button = QPushButton('Изменить промпт')
        self.quality_prompt_button.setProperty('v3Button', True)
        self.quality_prompt_button.setProperty('variant', 'secondary')
        self.quality_prompt_button.clicked.connect(lambda: self.prompt_requested.emit(self._current_quality_key()))
        self.quality_prompt_button.hide()  # shown only for «Брак генерации»
        action_row.addWidget(self.quality_prompt_button)
        self.quality_regenerate_button = QPushButton('Перегенерировать')
        self.quality_regenerate_button.setProperty('v3Button', True)
        self.quality_regenerate_button.setProperty('variant', 'secondary')
        self.quality_regenerate_button.setToolTip('Новая платная генерация этой картинки; цена и модель — в подтверждении')
        self.quality_regenerate_button.clicked.connect(
            lambda: self.regenerate_requested.emit(self._current_quality_key()))
        self.quality_regenerate_button.hide()  # next to «Изменить промпт»: only for «Брак генерации»
        action_row.addWidget(self.quality_regenerate_button)
        action_row.addStretch(1)
        action_row.addWidget(self.quality_fix_button)
        detail_layout.addLayout(action_row)
        # The issue texts stay out of sight (owner 2026-10-27): problems are shown only as a mark on the picture.
        for hidden in (self.quality_issue_title, self.quality_issue_text, self.quality_action_text):
            hidden.hide()
        body.addWidget(detail, 3)
        layout.addLayout(body, 1)

        footer = QHBoxLayout()
        self.quality_back_button = QPushButton('← К наборам')
        self.quality_back_button.setProperty('v3Button', True)
        self.quality_back_button.setProperty('variant', 'secondary')
        self.quality_back_button.clicked.connect(self._show_summary)
        footer.addWidget(self.quality_back_button)
        footer.addStretch(1)
        footer.addWidget(QLabel('Фон'))
        footer.addLayout(swatch_row)
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
                # Background mode: never decode a PNG here; icons appear once the worker primed them.
                pixmap = (self._scaled_pixmap(path, 44) if self._quality_loader is None or not self._qc_pending
                          else self._primed_pixmap(path, 44))
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
            if report is None and self._qc_pending and not only_problems:
                # Not checked yet: the square and the name are there at once, the picture follows.
                row = QListWidgetItem(path.name)
                row.setData(Qt.ItemDataRole.UserRole, '')
                row.setFlags(Qt.ItemFlag.ItemIsEnabled)
                row.setToolTip(f'{path.name} — проверяется…')
                row.setIcon(self._placeholder_icon())
                self.quality_list.addItem(row)
                continue
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
            if key in getattr(self, '_edited', ()):
                status += ' · промпт исправлен'
            row = QListWidgetItem(path.name)  # status is a mark on the picture and a tooltip, not a caption
            row.setData(Qt.ItemDataRole.UserRole, key)
            row.setToolTip(f'{path.name} — {status}')
            row.setIcon(self._quality_icon(key, report, active, key in self._viewed_quality))
            self.quality_list.addItem(row)
            if key == selected_path:
                selected_row = self.quality_list.count() - 1
        self.quality_list.blockSignals(False)
        if selected_row < 0:
            selected_row = next((row for row in range(self.quality_list.count())
                                 if self.quality_list.item(row).data(Qt.ItemDataRole.UserRole)), -1)
        if selected_row >= 0:
            self.quality_list.setCurrentRow(selected_row)
        else:
            self._quality_selected(-1)

    def _placeholder_icon(self):
        icon = getattr(self, '_placeholder', None)
        if icon is None:
            size = self.QUALITY_THUMB
            pixmap = QPixmap(size, size)
            pixmap.fill(QColor('#223045'))
            painter = QPainter(pixmap)
            painter.setPen(QPen(QColor('#34465d'), 2))
            painter.drawRect(1, 1, size - 2, size - 2)
            painter.end()
            icon = self._placeholder = QIcon(pixmap)
        return icon

    def _set_quality_filter(self, only_problems):
        self._quality_only_problems = only_problems
        self._refresh_quality_page()

    def _quality_icon(self, key, report, active, viewed):
        """Thumbnail on the checkerboard with a status badge (⚠/✕) and a «viewed» tick; excluded files are dimmed."""
        size = self.QUALITY_THUMB
        picture = self._checker_pixmap(key, size, self._quality_background)
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

        mark = self._marks.get(key, '')
        if not active:
            painter.setPen(QPen(QColor('#8ea3b8'), 2))
            painter.setBrush(QColor('#2b3340'))
            painter.drawEllipse(size - 24, 4, 18, 18)
            painter.drawLine(size - 21, 19, size - 9, 7)
        elif mark == 'ok':
            badge(size - 25, 3, '#34d399', '', '#06201c')
        elif mark == 'bad_generation':
            badge(size - 25, 3, '#f59e0b', '', '#1f1300')
        elif mark == 'bad_cutout':
            badge(size - 25, 3, '#a78bfa', '', '#140a2e')
        elif self._needs_attention(key):
            badge(size - 25, 3, '#f59e0b', '!', '#1f1300')
        if key in getattr(self, '_edited', ()):  # a corrected prompt: pencil badge, opposite the mark
            badge(3, size - 25, '#1b2636', '✎', '#e4edf6')
        painter.end()
        icon = QIcon()
        for mode in (QIcon.Mode.Normal, QIcon.Mode.Active, QIcon.Mode.Selected):
            icon.addPixmap(canvas, mode)  # no highlight tint over the picture itself: the selection is drawn on the cell
        return icon

    @staticmethod
    def _checker_pixmap(path, bound=220, background='checkerboard'):
        picture = SetExportDialog._scaled_pixmap(path, bound)
        if picture.isNull():
            return picture
        canvas = QPixmap(picture.size())
        painter = QPainter(canvas)
        if background == 'checkerboard':
            for y in range(0, canvas.height(), 14):
                for x in range(0, canvas.width(), 14):
                    painter.fillRect(x, y, 14, 14, QColor('#d6dce4' if (x // 14 + y // 14) % 2 else '#ffffff'))
        else:
            painter.fillRect(canvas.rect(), QColor(background))
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
            self.quality_picture.setToolTip('')
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
        # No visible captions (owner 2026-10-27); the explanation stays one hover away.
        self.quality_picture.setToolTip('\n'.join(part for part in (title, messages, actions) if part))
        self.quality_fix_button.setEnabled(active and self.worker is None)
        self.quality_exclude_button.setEnabled(active and self.worker is None)

    def enable_marks(self, marks, edited=()):
        """Show the quick marks; ``marks`` maps a PNG path to its current mark."""
        self._marks = {str(Path(path).resolve()): mark for path, mark in dict(marks).items()}
        self._edited = {str(Path(path).resolve()) for path in edited}
        self._marks_enabled = True
        self._sync_mark_buttons(self._current_quality_key())
        self._refresh_quality_page()

    def _current_quality_key(self):
        item = self.quality_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or '') if item is not None else ''

    def _sync_mark_buttons(self, key):
        known = self._marks_enabled and key in self._marks
        self.quality_marks_row.setVisible(known)
        self.quality_prompt_button.setVisible(known and self._marks.get(key) == 'bad_generation')
        self.quality_regenerate_button.setVisible(known and self._marks.get(key) == 'bad_generation')
        for mark, button in self.quality_mark_buttons.items():
            button.setChecked(known and self._marks.get(key) == mark)
            button.setEnabled(known and self.worker is None)

    def _quality_mark_clicked(self, mark):
        key = self._current_quality_key()
        if not key or key not in self._marks:
            return
        self._marks[key] = mark
        # Show the new mark before the (slow) save runs, so two buttons are never lit while it works.
        self._sync_mark_buttons(key)
        self.quality_marks_row.repaint()
        self.mark_requested.emit(key, mark)
        self._refresh_quality_page()

    def _needs_attention(self, key):
        """A PNG the owner still has to look at: the check flags it and no mark says she has seen it."""
        report = self.quality_reports.get(key)
        if report is None or report.status == 'ok' or not self._path_is_active(key):
            return False
        if self._marks_enabled:
            return self._marks.get(key, '') not in ('ok', 'bad_generation', 'bad_cutout')
        return key not in self._viewed_quality  # a flow without marks: opening the picture counts

    def _mark_quality_viewed(self, key, item, report, active):
        if key in self._viewed_quality:
            return
        self._viewed_quality.add(key)
        item.setIcon(self._quality_icon(key, report, active, True))

    def _is_checked(self, key):
        """The owner has dealt with this PNG: she marked it («Ок» or a defect) or, without marks, opened it."""
        if self._marks_enabled:
            return self._marks.get(key, '') in ('ok', 'bad_generation', 'bad_cutout')
        return key in self._viewed_quality

    def _viewed_counts(self):
        keys = [str(path) for path in self.paths if str(path) in self.quality_reports and self._path_is_active(path)]
        return sum(self._is_checked(key) for key in keys), len(keys)

    def _set_quality_page_text(self, base):
        self._quality_page_base_text = base  # kept for callers; the screen shows no counter any more

    def _confirm_unviewed(self, viewed, total):
        """True = create the sets anyway; False = go back and look at the rest."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle('Не все изображения проверены')
        box.setText(f'Не все изображения проверены: {viewed} из {total}. Всё равно создать наборы?')
        review = box.addButton('Проверить остальные', QMessageBox.ButtonRole.AcceptRole)
        create = box.addButton('Создать', QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(review)
        box.exec()
        return box.clickedButton() is create

    def _show_first_unviewed(self):
        self._show_quality_review()
        for row in range(self.quality_list.count()):
            if not self._is_checked(str(self.quality_list.item(row).data(Qt.ItemDataRole.UserRole) or '')):
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
        self.quality_panel.setVisible(quality_issue_count > 0 or self._qc_pending > 0)
        self.review_quality_button.setVisible(not self._qc_pending)
        if self._qc_pending:
            done = self._qc_total - self._qc_pending
            self.quality_summary_label.setText(f'Автопроверка PNG идёт: {done} из {self._qc_total}…')
            self.quality_panel.setProperty('state', '')
            self.quality_panel.style().unpolish(self.quality_panel)
            self.quality_panel.style().polish(self.quality_panel)
        elif quality_issue_count:
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
        export_enabled = (bool(groups) and not self._blocking_review_issues() and not block_count
                          and not self._qc_pending and self.worker is None)
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
        self._stop_png_check()
        self._hide_preview()
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self.reject()
            event.ignore()
        else:
            self._stop_png_check()
            self._hide_preview()
            super().closeEvent(event)
