"""Automatic Clipart set summary with optional manual membership editing."""
import hashlib
import os
from collections import OrderedDict, deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from uuid import uuid4

from PyQt6.QtCore import (
    QEvent, QItemSelection, QItemSelectionModel, QPoint, QPointF, QRect, QRectF, QSize, QSizeF, QThread,
    Qt, pyqtSignal,
)
from PyQt6.QtGui import QBrush, QColor, QCursor, QFont, QFontMetrics, QIcon, QImage, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QDialog, QFileDialog, QFrame,
    QHeaderView, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QWidgetAction,
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
# Big previews (the picture on the right, zoom, resizing the window) are scaled from one decoded copy per file
# instead of reading the PNG again for every size; a few copies are enough (owner 2026-10-28: previews were slow).
_FULL_CACHE = OrderedDict()
_FULL_CACHE_LIMIT = 4
FULL_BOUND = 2048
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
    """Loads thumbnails and the transparency check off the UI thread (owner 2026-10-30).

    The pictures are decoded by a few threads at once and reported in order: a single sequence left
    the grid filling one picture at a time, and one large PNG held every later picture back
    (measured: 334 ms per 4096-pixel picture, 47 of them in a row). Decoding at most a couple of
    pictures per thread ahead keeps a stop quick.
    """
    item_ready = pyqtSignal(str, QImage, object)  # path, thumbnail, report or None

    DECODE_THREADS = max(2, min(4, (os.cpu_count() or 2) - 1))

    def __init__(self, paths, loader, parent=None, cache_dir=None):
        super().__init__(parent)
        self.paths, self.loader = list(paths), loader
        self.cache_dir = cache_dir
        self._stop = Event()

    def stop(self):
        self._stop.set()

    def _report(self, path, future):
        """Emit one picture: its thumbnail comes from the pool, its check runs here, in order."""
        try:
            image = future.result()
        except Exception:
            image = QImage()
        try:
            report = self.loader(path)
        except Exception:
            report = None
        if self._stop.is_set():
            return False
        self.item_ready.emit(str(path), image, report)
        return True

    def run(self):
        pool = ThreadPoolExecutor(max_workers=self.DECODE_THREADS,
                                  thread_name_prefix="png-thumb")
        try:
            pending = deque()
            window = self.DECODE_THREADS * 2  # a stop should not wait for the whole run
            for path in self.paths:
                if self._stop.is_set():
                    return
                pending.append((path, pool.submit(read_thumbnail, path, PRIME_BOUND, self.cache_dir)))
                while len(pending) > window:
                    queued_path, future = pending.popleft()
                    if not self._report(queued_path, future):
                        return
            while pending:
                queued_path, future = pending.popleft()
                if not self._report(queued_path, future):
                    return
        finally:
            pool.shutdown(wait=True, cancel_futures=True)
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


class _SetsHeader(QHeaderView):
    """Set columns: «✓» marks the whole column, «✎» renames or deletes, «⇅» sorts (owner 2026-10-30).

    The title is a label only: owner 2026-10-30 asked to stop marking on it — a stray click used to tick
    every picture at once. Each action has its own small glyph on the right, and the tick shows the state.
    """

    marks_clicked = pyqtSignal(int)
    pencil_clicked = pyqtSignal(int)
    sort_clicked = pyqtSignal(int)

    GLYPH = 16
    GAP = 4
    EDGE = 10  # space between the last glyph and the column border
    ACCENT = '#24cabb'

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        self.setSectionsMovable(False)
        # The glyphs live in a strip of their own at the right edge of every section; the padding makes
        # «ResizeToContents» reserve it and keeps the centred title away from it (owner 2026-10-31: the glyphs
        # were lost on narrow columns). Only the right padding is overridden, the rest comes from the theme.
        self.setStyleSheet(f'QHeaderView::section {{ padding-right: {self.glyph_strip()}px; }}')
        self.setToolTip("✓ — отметить или снять весь столбец; ✎ — переименовать или удалить набор; "
                        "⇅ — сортировка по отметкам")
        self.marked_state = None  # callable(column) -> bool, set by the dialog
        self.chosen_state = None  # callable(column) -> bool: the column the buttons below act on

    @classmethod
    def glyph_strip(cls):
        """Width kept free at the right of a section: three glyphs, gaps, edge and a gap before the title."""
        return cls.EDGE + 3 * cls.GLYPH + 2 * cls.GAP + 6

    def _glyph_rects(self, index):
        right = self.sectionViewportPosition(index) + self.sectionSize(index)
        height = max(self.GLYPH, self.height() - 10)
        sort_rect = QRect(right - self.EDGE - self.GLYPH, 5, self.GLYPH, height)
        pencil_rect = QRect(sort_rect.left() - self.GAP - self.GLYPH, 5, self.GLYPH, height)
        marks_rect = QRect(pencil_rect.left() - self.GAP - self.GLYPH, 5, self.GLYPH, height)
        return marks_rect, pencil_rect, sort_rect

    def _column_marked(self, index):
        if not callable(self.marked_state):
            return False
        try:
            return bool(self.marked_state(index))
        except Exception:
            return False

    def _column_chosen(self, index):
        if not callable(self.chosen_state):
            return False
        try:
            return bool(self.chosen_state(index))
        except Exception:
            return False

    def paintSection(self, painter, rect, index):
        # `QHeaderView.paintSection` leaves an empty clip region on the painter: everything drawn after it was
        # cut away and the glyphs never appeared (owner 2026-10-31). The state is restored around the call.
        painter.save()
        try:
            super().paintSection(painter, rect, index)
        finally:
            painter.restore()
        if index <= 0:
            return
        if self._column_chosen(index):
            tint = QColor(self.ACCENT)
            tint.setAlpha(55)
            painter.fillRect(rect, tint)
            painter.fillRect(QRect(rect.left(), rect.bottom() - 2, rect.width(), 3), QColor(self.ACCENT))
        marks_rect, pencil_rect, sort_rect = self._glyph_rects(index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont(painter.font())
        font.setPixelSize(14)
        painter.setFont(font)
        painter.setPen(QColor(self.ACCENT) if self._column_marked(index) else QColor('#8ea3b8'))
        painter.drawText(marks_rect, int(Qt.AlignmentFlag.AlignCenter), '✓')
        painter.setPen(QColor(self.ACCENT))
        painter.drawText(pencil_rect, int(Qt.AlignmentFlag.AlignCenter), '✎')
        painter.drawText(sort_rect, int(Qt.AlignmentFlag.AlignCenter), '⇅')
        painter.restore()

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        index = self.logicalIndexAt(point)
        if index > 0:
            marks_rect, pencil_rect, sort_rect = self._glyph_rects(index)
            if marks_rect.contains(point):
                self.marks_clicked.emit(index)
                return
            if pencil_rect.contains(point):
                self.pencil_clicked.emit(index)
                return
            if sort_rect.contains(point):
                self.sort_clicked.emit(index)
                return
        super().mousePressEvent(event)


class SetExportDialog(QDialog):
    busy_changed = pyqtSignal()
    membership_saved = pyqtSignal(object)
    fix_requested = pyqtSignal(str)
    mark_requested = pyqtSignal(str, str)  # (png path, review mark) — same marks as on the results step
    prompt_requested = pyqtSignal(str)  # «Изменить промпт» for a picture marked as a generation defect
    cutout_requested = pyqtSignal(str)  # «Убрать фон»: free local re-cutout of the same picture (module runs it)
    regenerate_requested = pyqtSignal(str)  # «Перегенерировать» for the same picture (paid, confirmed by the module)
    files_dropped = pyqtSignal(list, object)  # PNG from the file manager: ([paths], target review path or None)
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
        elif bound <= 256:
            picture = QPixmap.fromImage(_read_scaled_image(path, bound))
        else:
            full = _FULL_CACHE.get(stamp) if stamp is not None else None
            if full is None:
                full = QPixmap.fromImage(_read_scaled_image(path, max(bound, FULL_BOUND)))
                if stamp is not None and not full.isNull():
                    _FULL_CACHE[stamp] = full
                    while len(_FULL_CACHE) > _FULL_CACHE_LIMIT:
                        _FULL_CACHE.popitem(last=False)
            elif stamp is not None:
                _FULL_CACHE.move_to_end(stamp)
            picture = full if full.isNull() or max(full.width(), full.height()) <= bound else full.scaled(
                QSize(bound, bound), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            return picture  # large previews are not kept per size; the decoded copy above is
        if stamp is not None and not picture.isNull():
            _THUMB_CACHE[key] = picture
            while len(_THUMB_CACHE) > _THUMB_CACHE_LIMIT:
                _THUMB_CACHE.popitem(last=False)
        return picture

    def __init__(self, paths, parent=None, *, membership=None, review_issues=None, quality_reports=None,
                 workspace=None, embedded=False, project_name='', name_translator=None,
                 quality_loader=None, review_paths=None):
        super().__init__(parent)
        self.project_name = str(project_name or '')
        self.name_translator = name_translator
        self.embedded = embedded
        self.workspace = workspace
        from studio_export_membership import validate_export_membership

        saved = validate_export_membership(membership or {})
        self.paths = list(dict.fromkeys(Path(path).resolve() for path in paths))
        # The PNG check reviews every ready picture: a regeneration clears its «Ок» mark, and an
        # unconfirmed or defect-marked picture must still be listed there (owner 2026-10-28).
        # The sets keep only confirmed members (SET-0).
        review_source = paths if review_paths is None else review_paths
        self.review_paths = list(dict.fromkeys(Path(path).resolve() for path in review_source))
        for path in self.paths:
            key = str(path)
            if key not in saved:
                saved.update(validate_export_membership(
                    {key: {'title': 'Set 1', 'included': True}}
                ))
        self.saved_membership = saved
        self._review_issue_candidates = [dict(issue) for issue in (review_issues or ())]
        self.review_issues = list(self._review_issue_candidates)
        allowed_paths = {str(path) for path in self.review_paths}
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
        self._notes = {}
        # Owner 2026-10-28: «отметки наверх» — the table can be ordered by one set's marks.
        self._sort_set_id = None
        self._sort_descending = False
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
        # Owner 2026-10-28: the progress line («Перегенерация: …») keeps an even gap from the
        # options menu instead of sitting right next to it, and the «Фон» block with
        # «Редактировать прозрачность» starts at the left edge of its part instead of being
        # pushed to the far right.
        bottom.setSpacing(16)
        bottom.addWidget(self.status, 1)
        bottom.addSpacing(16)
        bottom.addWidget(self.quality_bottom_row)
        bottom.addStretch(1)
        self.stack.currentChanged.connect(
            lambda _index: self.quality_bottom_row.setVisible(self.stack.currentWidget() is self.quality_page))
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
        if quality_loader is not None and self.review_paths:
            self._qc_total = self._qc_pending = len(self.review_paths)
        self._refresh_summary()
        self._start_png_check()

    def _start_png_check(self):
        if not self._qc_pending:
            return
        self._check_worker = _PngCheckWorker(self.review_paths, self._quality_loader, self,
                                             thumb_cache_dir(self.workspace))
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
        self.summary_drop_notice = QLabel('')
        self.summary_drop_notice.setWordWrap(True)
        self.summary_drop_notice.setStyleSheet('color: #e88b8b;')
        self.summary_drop_notice.hide()
        layout.addWidget(self.summary_drop_notice)
        self._build_membership_table(layout)
        # Owner 2026-10-30: one row of column actions above the table is gone — rename, delete and the
        # sort order now live in the column headers (✎ and ⇅). The widgets below stay hidden so the
        # long-standing code paths that drive them keep working untouched.
        self.rename_set_button = QPushButton('Переименовать набор')
        self.rename_set_button.setProperty('v3Button', True)
        self.rename_set_button.setProperty('variant', 'secondary')
        self.rename_set_button.clicked.connect(self._rename_current_set)
        self.delete_set_button = QPushButton('Удалить набор')
        self.delete_set_button.setProperty('v3Button', True)
        self.delete_set_button.setProperty('variant', 'secondary')
        self.delete_set_button.clicked.connect(self._delete_current_set)
        for retired in (self.rename_set_button, self.delete_set_button):
            retired.hide()
            layout.addWidget(retired)
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
        # Owner 2026-11-01: only pictures marked «Ок» are listed, so unfinished ones never block the export.
        return [issue for issue in self.review_issues if issue.get('kind') != 'missing']

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
        # Владелец 2026-10-31: CTRL выделяет по одной, SHIFT — группу между картинками;
        # существующие кнопки применяются ко всей выделенной группе (новых кнопок нет).
        self.quality_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.quality_list.currentRowChanged.connect(self._quality_selected)
        self.quality_list.itemDoubleClicked.connect(self._quality_double_clicked)
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
            # Owner 2026-10-29: the whole block — marks, «Исключить из наборов», «Редактировать
            # прозрачность» — has one rounding, the app's usual one, not the pill shape.
            button.setProperty('v3ChipControl', True)
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
        # then the actions on this picture (prompt, regenerate, edit); everything is left-aligned (owner 2026-10-27).
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
        detail_actions.addWidget(self.quality_exclude_button)
        detail_actions.addStretch(1)
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
        self.quality_regenerate_button.clicked.connect(self._regenerate_selected_quality)
        self.quality_regenerate_button.hide()  # next to «Изменить промпт»: only for «Брак генерации»
        action_row.addWidget(self.quality_regenerate_button)
        self.quality_cutout_button = QPushButton('Убрать фон')
        self.quality_cutout_button.setProperty('v3Button', True)
        self.quality_cutout_button.setProperty('variant', 'secondary')
        self.quality_cutout_button.setToolTip('Заново вырезать фон этой картинки на компьютере: бесплатно, прежняя картинка сохранится как версия')
        self.quality_cutout_button.clicked.connect(self._cutout_selected_quality)
        self.quality_cutout_button.hide()  # only for «Брак вырезания»
        action_row.addWidget(self.quality_cutout_button)
        action_row.addStretch(1)
        detail_layout.addLayout(action_row)
        # Owner 2026-10-28: «Редактировать прозрачность» and the background swatches sit in the bottom row of the
        # window (level with «Параметры экспорта»), under the picture column, the swatches to the right of the button.
        self.quality_bottom_row = QWidget()
        bottom_extras = QHBoxLayout(self.quality_bottom_row)
        bottom_extras.setContentsMargins(0, 0, 0, 0)
        bottom_extras.addWidget(self.quality_fix_button)
        bottom_extras.addSpacing(16)
        bottom_extras.addWidget(QLabel('Фон'))
        bottom_extras.addLayout(swatch_row)
        bottom_extras.addStretch(1)
        self.quality_bottom_row.hide()
        # The issue texts stay out of sight (owner 2026-10-27): problems are shown only as a mark on the picture.
        for hidden in (self.quality_issue_title, self.quality_issue_text, self.quality_action_text):
            hidden.hide()
        body.addWidget(detail, 3)
        layout.addLayout(body, 1)

        # Owner 2026-10-30 (approved mockup drag-drop-png-20261030): PNGs from the file
        # manager drop onto the check grid and attach to the position they land on.
        self.quality_drop_notice = QLabel('')
        self.quality_drop_notice.setWordWrap(True)
        self.quality_drop_notice.setProperty('v3Description', True)
        self.quality_drop_notice.setStyleSheet('color: #e88b8b;')
        self.quality_drop_notice.hide()
        layout.addWidget(self.quality_drop_notice)
        self.quality_list.setAcceptDrops(True)
        self.quality_list.viewport().setAcceptDrops(True)
        self.quality_list.dragEnterEvent = self._quality_drag_enter
        self.quality_list.dragMoveEvent = self._quality_drag_enter
        self.quality_list.dropEvent = self._quality_drop

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
        # Owner 2026-10-30: a double click on a picture opens its transparency editor.
        self.table.cellDoubleClicked.connect(self._table_row_double_clicked)
        layout.addWidget(self.table, 1)

        header = _SetsHeader(self.table)
        header.marks_clicked.connect(self._marks_glyph_clicked)
        header.pencil_clicked.connect(self._column_pencil_menu)
        header.sort_clicked.connect(self._sort_column_by_marks)
        header.marked_state = self._column_all_marked
        header.chosen_state = self._column_is_chosen
        self.table.setHorizontalHeader(header)
        header.setSectionsClickable(True)
        # A click on the title only remembers the column (owner 2026-10-30: the title must never mark).
        header.sectionClicked.connect(self._choose_set_column)
        self.table.currentCellChanged.connect(lambda _row, column, *_: self._choose_set_column(column))

    def _choose_set_column(self, column):
        if self.worker is not None or not 1 <= column <= len(self._set_columns):
            return
        self._editing_set_id = self._set_columns[column - 1][0]
        self.rename_set_button.setEnabled(True)
        self.delete_set_button.setEnabled(True)
        self._apply_column_highlight()

    def _column_is_chosen(self, column):
        return (self._editing_set_id is not None and 1 <= column <= len(self._set_columns)
                and self._set_columns[column - 1][0] == self._editing_set_id)

    def _apply_column_highlight(self):
        """Owner 2026-10-31: the column the buttons act on is tinted in the header and in every row."""
        tint = QColor(_SetsHeader.ACCENT)
        tint.setAlpha(40)
        self.table.blockSignals(True)  # a background change is not a membership change
        try:
            for column in range(1, self.table.columnCount()):
                brush = QBrush(tint) if self._column_is_chosen(column) else QBrush()
                for row in range(self.table.rowCount()):
                    item = self.table.item(row, column)
                    if item is not None:
                        item.setBackground(brush)
        finally:
            self.table.blockSignals(False)
        self.table.horizontalHeader().viewport().update()

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

    def _ordered_paths(self):
        """The table order: rows carrying the chosen set's mark first, the rest after them.

        The header arrows flip the direction (owner 2026-10-30): «отмеченные сверху» / «неотмеченные сверху».
        """
        if not self._sort_set_id:
            return list(self.paths)
        marked, rest = [], []
        for path in self.paths:
            links = {link['set_id']: link for link in self.saved_membership[str(path)]['memberships']}
            target = marked if links.get(self._sort_set_id, {}).get('included') else rest
            target.append(path)
        return (rest + marked) if self._sort_descending else (marked + rest)

    def _set_sort(self, set_id, *, descending=None):
        """Sort by one set's marks; without a set the original order comes back (owner 2026-10-30)."""
        if set_id is None:
            self._sort_set_id, self._sort_descending = None, False
        else:
            self._sort_descending = bool(descending)
            self._sort_set_id = set_id
        self._rebuild_manual_table()

    def _sort_column_by_marks(self, column):
        """⇅ in a column header: marked rows on top; the same arrows on the same column flip it."""
        if self.worker is not None or not 1 <= column <= len(self._set_columns):
            return
        set_id = self._set_columns[column - 1][0]
        descending = not self._sort_descending if set_id == self._sort_set_id else False
        self._set_sort(set_id, descending=descending)
        title = dict(self._set_columns).get(set_id, '')
        self.status.setText(f'Сортировка по набору «{title}»: '
                            + ('неотмеченные сверху.' if descending else 'отмеченные сверху.'))

    def _column_pencil_menu(self, column):
        """✎ in a column header: rename or delete this very column's set (owner 2026-10-30)."""
        if self.worker is not None or not 1 <= column <= len(self._set_columns):
            return
        self._choose_set_column(column)
        if self._editing_set_id is None:
            return
        menu = QMenu(self.table)
        rename = menu.addAction('Переименовать набор…')
        delete = menu.addAction('Удалить набор…')
        chosen = menu.exec(QCursor.pos())
        if chosen is rename:
            self._rename_current_set()
        elif chosen is delete:
            self._delete_current_set()

    def _marks_glyph_clicked(self, column):
        """«✓» in a column header marks or clears the whole column.

        Owner 2026-10-28 asked for mass marking; owner 2026-10-30 moved it off the title onto this glyph,
        so an accidental click on the name can no longer tick every picture.
        """
        self._choose_set_column(column)
        self._toggle_column_marks(column)

    def _column_all_marked(self, column):
        """Whether every selectable cell of this column is ticked: the state the ✓ glyph shows."""
        if not 1 <= column <= len(self._set_columns) or self.table.rowCount() == 0:
            return False
        states = [self.table.item(row, column).checkState()
                  for row in range(self.table.rowCount()) if self.table.item(row, column) is not None]
        return bool(states) and all(state == Qt.CheckState.Checked for state in states)

    def _toggle_column_marks(self, column):
        if self.worker is not None or not 1 <= column <= len(self._set_columns):
            return
        states = [self.table.item(row, column).checkState() for row in range(self.table.rowCount())]
        if not states:
            return
        target = (Qt.CheckState.Unchecked if all(state == Qt.CheckState.Checked for state in states)
                  else Qt.CheckState.Checked)
        self.table.blockSignals(True)
        try:
            for row in range(self.table.rowCount()):
                cell = self.table.item(row, column)
                if cell.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                    cell.setCheckState(target)
        finally:
            self.table.blockSignals(False)
        self._manual_changed()
        self.table.horizontalHeader().viewport().update()
        title = dict(self._set_columns).get(self._set_columns[column - 1][0], '')
        self.status.setText(f'Столбец «{title}»: '
                            + ('все отметки сняты.' if target == Qt.CheckState.Unchecked else 'отмечены все изображения.'))

    def _rebuild_manual_table(self):
        self.table.horizontalHeader().viewport().update()  # the ✓ glyph follows the column state
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
            for row, path in enumerate(self._ordered_paths()):
                name = QTableWidgetItem(path.name)
                # Owner 2026-10-30: the hint tells about the double click that opens the transparency editor.
                name.setToolTip(f'{path.name}\nДвойной клик — редактор прозрачности этой картинки')
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
        self._apply_column_highlight()

    def _membership(self):
        from studio_export_membership import validate_export_membership
        value = validate_export_membership(self.saved_membership)
        if not self._set_columns:
            return value
        for row in range(self.table.rowCount()):
            # The row's picture is taken from the row itself: the table may be sorted by a column.
            holder = self.table.item(row, 0)
            key = str(holder.data(Qt.ItemDataRole.UserRole) if holder is not None else '')
            if not key or key not in value:
                continue
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
        """In a set, or a ready picture awaiting the owner's «Ок» — the check lists both."""
        source = self.saved_membership if membership is None else membership
        item = source.get(str(Path(path).resolve()))
        if item is None:
            return Path(path).resolve() in self.review_paths
        return bool(item and any(link.get('included') for link in item.get('memberships', ())))

    def _path_has_sets(self, path):
        """The picture carries set records at all: only then can it be excluded or brought back."""
        item = self.saved_membership.get(str(Path(path).resolve()))
        return bool(item and item.get('memberships'))

    def _active_quality_blockers(self, membership=None):
        # Only a picture that is actually in a set can block that set's export.
        members = {str(path) for path in self.paths}
        return [
            report for path, report in self.quality_reports.items()
            if report.status == 'block' and str(Path(path).resolve()) in members
            and self._path_is_active(path, membership)
        ]

    def _refresh_quality_page(self):
        if not hasattr(self, 'quality_list'):
            return
        selected_path = getattr(self, '_select_path', '')
        focus = bool(selected_path)  # «open this picture»: it must be brought into view, not just selected
        current = self.quality_list.currentItem()
        if current is not None and not selected_path:
            selected_path = str(current.data(Qt.ItemDataRole.UserRole) or '')
        # Owner 2026-10-31: a rebuild keeps the whole CTRL/SHIFT selection, not only the
        # current picture — a mark on a group rebuilds the grid, the group must stay.
        selected_keys = self._selected_quality_keys()
        # Owner 2026-10-30: a rebuild (the check fills in, a picture is redone) used to drop the place —
        # the grid jumped to the first picture. Keep the position and the scroll, not the top of the list.
        previous_row = self.quality_list.currentRow()
        scroll = self.quality_list.verticalScrollBar().value()
        self.quality_list.blockSignals(True)
        self.quality_list.clear()
        self.quality_drop_notice.hide()  # перетаскивание начнёт новый итог после пересборки
        selected_row = -1
        status_labels = {'ok': 'Готово', 'review': 'Проверьте края', 'block': 'Не экспортировать'}
        total = sum(str(path) in self.quality_reports for path in self.review_paths)
        problems = sum(
            self.quality_reports[str(path)].status != 'ok'
            for path in self.review_paths if str(path) in self.quality_reports
        )
        self.quality_filter_problems.setText(f'Нужно посмотреть ({problems})')
        self.quality_filter_all.setText(f'Все ({total})')
        only_problems = self._quality_only_problems and problems > 0
        for button, active in ((self.quality_filter_problems, only_problems), (self.quality_filter_all, not only_problems)):
            button.setProperty('variant', 'primary' if active else 'secondary')
            button.style().unpolish(button)
            button.style().polish(button)
        for path in self.review_paths:
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
            if mark:
                # Owner 2026-10-30: an excluded picture keeps its mark in sight; the exclusion must not hide it.
                status = mark if (active and report.status == 'ok') else f'{status} · {mark}'
            if key in getattr(self, '_edited', ()):
                status += ' · промпт исправлен'
            note = self._notes.get(key)
            if note:
                status += f' · заметка: {note[:80]}'
            row = QListWidgetItem(path.name)  # status is a mark on the picture and a tooltip, not a caption
            row.setData(Qt.ItemDataRole.UserRole, key)
            row.setToolTip(f'{path.name} — {status}')
            row.setIcon(self._quality_icon(key, report, active, key in self._viewed_quality))
            self.quality_list.addItem(row)
            if key == selected_path:
                selected_row = self.quality_list.count() - 1
                self._select_path = ''
        self.quality_list.blockSignals(False)
        if selected_row < 0 and previous_row >= 0 and self.quality_list.count():
            # The picture she was looking at is momentarily gone (it is being redone): stay in place
            # instead of jumping to the first row and looking as if the grid had reset.
            selected_row = min(previous_row, self.quality_list.count() - 1)
        if selected_row < 0:
            selected_row = next((row for row in range(self.quality_list.count())
                                 if self.quality_list.item(row).data(Qt.ItemDataRole.UserRole)), -1)
        if selected_row >= 0:
            # Явный ClearAndSelect: одноаргументная форма после программного выделения
            # группы оставляет устаревшие выделенные строки (проверено офлайн).
            self.quality_list.setCurrentRow(selected_row, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            if focus:
                self.quality_list.scrollToItem(
                    self.quality_list.item(selected_row), QAbstractItemView.ScrollHint.PositionAtCenter)
        else:
            self._quality_selected(-1)
        if selected_keys:
            # Группа возвращается одним ClearAndSelect по выделению: построчный
            # setSelected(True) оставляет модель выделения «отравленной» — после него
            # одноаргументный setCurrentRow перестаёт снимать прежние строки.
            group = QItemSelection()
            for row in range(self.quality_list.count()):
                key = str(self.quality_list.item(row).data(Qt.ItemDataRole.UserRole) or '')
                if key and (key in selected_keys or row == self.quality_list.currentRow()):
                    index = self.quality_list.model().index(row, 0)
                    group.select(index, index)
            if not group.isEmpty():
                self.quality_list.selectionModel().select(
                    group, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.quality_list.verticalScrollBar().setValue(scroll)

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
        """Thumbnail on the checkerboard with the mark badge and a «viewed» tick; excluded files are dimmed."""
        size = self.QUALITY_THUMB
        picture = self._checker_pixmap(key, size, self._quality_background)
        canvas = QPixmap(size, size)
        canvas.fill(QColor('#1b2636'))
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not picture.isNull():
            # Owner 2026-10-30: an excluded picture keeps the mark readable, so the dimming is softer (0.35 → 0.55).
            painter.setOpacity(1.0 if active else 0.55)
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
        # Every state carries a glyph, not only a colour (owner 2026-10-29): «Г» — брак генерации,
        # «В» — брак вырезания, «✓» — принято, «✕» — удалено, «З» — у картинки есть заметка.
        state_badges = {
            'ok': ('#34d399', '✓', '#06201c'),
            'bad_generation': ('#f59e0b', 'Г', '#1f1300'),
            'bad_cutout': ('#a78bfa', 'В', '#140a2e'),
            'deleted': ('#8a97a8', '✕', '#101820'),
        }
        if mark in state_badges:
            fill, glyph, ink = state_badges[mark]
            badge(size - 25, 3, fill, glyph, ink)
        elif self._needs_attention(key):
            badge(size - 25, 3, '#f59e0b', '!', '#1f1300')
        if not active:
            # Owner 2026-10-30: the exclusion gets its own small sign in the free corner so that it
            # never hides the owner's mark («Ок»/«Брак…») — before, it replaced the mark badge.
            painter.setPen(QPen(QColor('#8ea3b8'), 2))
            painter.setBrush(QColor('#2b3340'))
            painter.drawEllipse(3, 3, 18, 18)
            painter.drawLine(6, 18, 18, 6)
        if key in getattr(self, '_edited', ()):  # a corrected prompt: pencil badge
            badge(3, size - 25, '#1b2636', '✎', '#e4edf6')
        if self._notes.get(key):  # a note is attached to the picture: its own badge
            badge(size - 25, size - 25, '#1d3a40', 'З', '#9fe8dc')
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
        self._sync_exclude_button(key, active)
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
        mark = {'bad_generation': 'Брак генерации', 'bad_cutout': 'Брак вырезания'}.get(self._marks.get(key, ''), '')
        if mark:
            # Owner 2026-10-30: the exclusion and the mark stand side by side instead of hiding each other.
            title = mark if (active and report.status == 'ok') else f'{title} · {mark}'
        self.quality_issue_title.setText(title)
        messages = '\n'.join(f'• {issue.message}' for issue in report.issues)
        actions = '\n'.join(f'• {issue.action}' for issue in report.issues if issue.action)
        self.quality_issue_text.setText(messages)
        self.quality_action_text.setText(('Что сделать:\n' + actions) if actions else '')
        # No visible captions (owner 2026-10-27); the explanation stays one hover away.
        self.quality_picture.setToolTip('\n'.join(part for part in (title, messages, actions) if part))
        # Owner 2026-10-30: fixing the picture does not depend on the sets — an excluded picture can be
        # repaired and then brought back with the same row's button. Only a running export locks it.
        self.quality_fix_button.setEnabled(self.worker is None)

    def _sync_exclude_button(self, key, active):
        """«Исключить из наборов» / «Вернуть в наборы» — one toggle button (owner 2026-10-30).

        Before, the button switched itself off as soon as the picture was excluded and there was no
        way back from this screen; the exclusion also hid every mark. Now the same button returns the
        picture to all of its sets, and the mark stays visible either way.
        """
        in_sets = self._path_has_sets(key)
        excluded = bool(key) and in_sets and not active
        self.quality_exclude_button.setText('Вернуть в наборы' if excluded else 'Исключить из наборов')
        if not in_sets:
            # Nothing to exclude yet: the picture joins the sets only after «Ок» (SET-0, 2026-10-28).
            self.quality_exclude_button.setToolTip('Картинка пока не в наборах: поставьте «Ок», и её можно будет исключить.')
        elif active:
            self.quality_exclude_button.setToolTip('Картинка не попадёт в ZIP-наборы. Файл на диске не удаляется.')
        else:
            self.quality_exclude_button.setToolTip('Вернуть картинку во все её наборы. Файл всё это время остаётся на диске.')
        self.quality_exclude_button.setEnabled(in_sets and self.worker is None)

    def enable_marks(self, marks, edited=(), notes=None):
        """Show the quick marks; ``marks`` maps a PNG path to its current mark.

        Owner 2026-10-29: the shortcuts in the gallery carry a readable badge for
        every state (ok / generation defect / cutout defect / deleted), a pencil for
        a corrected prompt and a separate badge when the picture has a note.
        ``edited`` and ``notes`` are iterables of resolved paths.
        """
        self._marks = {str(Path(path).resolve()): mark for path, mark in dict(marks).items()}
        self._edited = {str(Path(path).resolve()) for path in edited}
        self._notes = {str(Path(path).resolve()): str(text)
                       for path, text in dict(notes or {}).items() if str(text).strip()}
        self._marks_enabled = True
        self._sync_mark_buttons(self._current_quality_key())
        self._refresh_quality_page()

    def _current_quality_key(self):
        item = self.quality_list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole) or '') if item is not None else ''

    def _selected_quality_keys(self):
        """Все выделенные картинки сетки в порядке списка (CTRL/SHIFT, владелец 2026-10-31).

        Строки без ключа (квадрат «проверяется…») в действия не попадают.
        """
        keys = []
        for row in range(self.quality_list.count()):
            item = self.quality_list.item(row)
            if item is not None and item.isSelected():
                key = str(item.data(Qt.ItemDataRole.UserRole) or '')
                if key:
                    keys.append(key)
        return keys

    def _action_quality_keys(self):
        """Картинки, к которым применяется нажатая кнопка: выделенная группа, а если
        выделения нет — та, что сейчас открыта (как было при одиночном выборе)."""
        keys = self._selected_quality_keys()
        if keys:
            return keys
        current = self._current_quality_key()
        return [current] if current else []

    def _sync_mark_buttons(self, key):
        known = self._marks_enabled and key in self._marks
        self.quality_marks_row.setVisible(known)
        self.quality_prompt_button.setVisible(known and self._marks.get(key) == 'bad_generation')
        self.quality_regenerate_button.setVisible(known and self._marks.get(key) == 'bad_generation')
        self.quality_cutout_button.setVisible(known and self._marks.get(key) == 'bad_cutout')
        for mark, button in self.quality_mark_buttons.items():
            button.setChecked(known and self._marks.get(key) == mark)
            button.setEnabled(known and self.worker is None)

    def _quality_drop_png_candidates(self, urls):
        return [url.toLocalFile() for url in urls
                if url.isLocalFile() and url.toLocalFile().lower().endswith('.png')]

    def _quality_drag_enter(self, event):
        if self._quality_drop_png_candidates(event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _quality_drop(self, event):
        paths = self._quality_drop_png_candidates(event.mimeData().urls())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        # Бросок из папки добавляет позиции; заменить картинку можно только явно — Shift + бросок на неё.
        replace = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        item = self.quality_list.itemAt(event.position().toPoint()) if replace else None
        target = str(item.data(Qt.ItemDataRole.UserRole) or '') if item is not None else None
        self.files_dropped.emit(paths, target or None)

    def show_drop_notice(self, text):
        """Красная плашка отказов/итога перетаскивания (макет drag-drop-png-20261030)."""
        for label in (self.quality_drop_notice, self.summary_drop_notice):
            label.setText(text)
            label.setVisible(bool(text))

    def _quality_mark_clicked(self, mark):
        # Владелец 2026-10-31: метка ставится всем выделенным картинкам сразу.
        selected = self._action_quality_keys()
        keys = [key for key in selected if key in self._marks]
        if not keys:
            return
        # The same button again takes the mark off (owner 2026-10-28); with a group
        # that means: only when every highlighted picture already carries this mark.
        if all(self._marks.get(key) == mark for key in keys):
            mark = 'unchecked'
        for key in keys:
            self._marks[key] = mark
        current = self._current_quality_key()
        if current in keys:
            # Show the new mark before the (slow) save runs, so two buttons are never lit while it works.
            self._sync_mark_buttons(current)
            self.quality_marks_row.repaint()
        for key in keys:
            self.mark_requested.emit(key, mark)
        self._refresh_quality_page()
        skipped = len(selected) - len(keys)
        if skipped:
            self.show_drop_notice(
                f'Помечено картинок: {len(keys)}. Пропущено: {skipped} — у них нет быстрой пометки проекта.')

    def _needs_attention(self, key):
        """A PNG the owner still has to look at: the check flags it and no mark says she has seen it."""
        report = self.quality_reports.get(key)
        if report is None or not self._path_is_active(key):
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
                # Явный ClearAndSelect — как в _refresh_quality_page: одноаргументная
                # форма после выделения группы оставляет устаревшие выделенные строки.
                self.quality_list.setCurrentRow(row, QItemSelectionModel.SelectionFlag.ClearAndSelect)
                break

    def set_background_job(self, text):
        """Show that a regeneration or re-cutout started from this screen is running (empty text: it is over).
        The picture stays on screen; only the status line and a moving bar tell that work is going on."""
        if self.worker is not None:
            return  # an export owns the bar
        if text:
            self.export_progress.setRange(0, 0)
            self.export_progress.show()
            self.status.setText(text)
        elif self.export_progress.isVisible() or not self.export_progress.isHidden():
            self.export_progress.hide()
            self.status.clear()

    def focus_quality_path(self, path):
        """Open the PNG check on one picture (after its regeneration): fresh preview, no old «viewed» state."""
        key = str(Path(path).resolve())
        self._select_path = key
        self._viewed_quality.discard(key)
        self._show_quality_review()

    def _show_quality_review(self):
        self._refresh_quality_page()
        self.stack.setCurrentWidget(self.quality_page)
        self.status.clear()

    def _request_quality_fix(self):
        self._request_quality_fix_for(self.quality_list.currentItem())

    def _quality_double_clicked(self, item):
        """Double click on a picture of the PNG check opens its transparency editor (owner 2026-11-01)."""
        self._request_quality_fix_for(item)

    def _request_quality_fix_for(self, item):
        if self.worker is not None:
            self.show_drop_notice('Идёт обработка — редактор прозрачности откроется, когда она закончится.')
            return
        if item is None:
            return
        path = str(item.data(Qt.ItemDataRole.UserRole) or '')
        report = self.quality_reports.get(path)
        if not path or report is None:
            return
        if not self.embedded:
            self.done(QDialog.DialogCode.Rejected)
        self.fix_requested.emit(path)

    def _exclude_quality_selected(self):
        """Take the highlighted pictures out of every set, or bring them back (one button, owner 2026-10-30).

        Владелец 2026-10-31: кнопка действует на всю выделенную группу — исключает
        её целиком, а когда вся группа уже вне наборов, возвращает целиком. Картинки
        без записи о наборах пропускаются с пометкой в плашке, остальные работают.
        """
        if self.worker is not None:
            return
        selected = self._action_quality_keys()
        from studio_export_membership import validate_export_membership
        value = validate_export_membership(self.saved_membership)
        entries = {}
        for path in selected:
            if path and self.quality_reports.get(path) is not None:
                entry = value.get(path)
                if entry is not None:
                    entries[path] = entry
        if not entries:
            return
        excluded = all(not any(link.get('included') for link in entry['memberships'])
                       for entry in entries.values())
        for entry in entries.values():
            for link in entry['memberships']:
                link['included'] = excluded  # excluded → back into every set; in sets → out of every set
        value = validate_export_membership(value)
        self.saved_membership = value
        self._resolve_review_issues(value)
        self.membership_saved.emit(value)
        if len(entries) == 1:
            self.status.setText('Дизайн возвращён во все свои наборы. Файл всё это время оставался на диске.'
                                if excluded else
                                'Дизайн исключён из наборов. Файл на диске не удалён.')
        else:
            self.status.setText(f'Возвращены в наборы: {len(entries)}. Файлы всё это время оставались на диске.'
                                if excluded else
                                f'Исключены из наборов: {len(entries)}. Файлы на диске не удалены.')
        self._refresh_summary()
        self._refresh_quality_page()
        skipped = len(selected) - len(entries)
        if skipped:
            self.show_drop_notice(
                f'Обработано картинок: {len(entries)}. Пропущено: {skipped} — их нет в наборах проекта.')

    def _regenerate_selected_quality(self):
        """«Перегенерировать» for every highlighted picture (владелец 2026-10-31).

        Each picture goes through the same paid, confirmed re-creation as before:
        the module shows its own price confirmation and queues the rest one by one,
        so nothing starts without the owner's approval.
        """
        for key in self._action_quality_keys():
            self.regenerate_requested.emit(key)

    def _cutout_selected_quality(self):
        """«Убрать фон» for every highlighted picture: free, each with its own progress.

        The module starts the first one and waits the others out in its redo queue,
        so a group runs one by one exactly like a single picture.
        """
        for key in self._action_quality_keys():
            self.cutout_requested.emit(key)

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
        if count or not self.review_paths:
            self.summary_counts.setText(f'{count} {images_word} · {set_count} {sets_word}')
        else:
            # Owner 2026-10-30: a finished run whose pictures are not confirmed yet read as «no pictures at all».
            self.summary_counts.setText(
                f'Готово картинок: {len(self.review_paths)} · в наборах: 0 · наборов: {set_count}')
        if self.paths or not self.review_paths:
            self.empty_hint.setText('Готовых PNG пока нет. Проект можно сохранить и продолжить позже.')
        else:
            self.empty_hint.setText('В наборы попадут только картинки, подтверждённые «Ок».')
        self.empty_hint.setVisible(not self.paths)
        self.new_set_button.setEnabled(bool(self.paths) and self.worker is None)
        if self._editing_set_id not in dict(catalog):
            self._editing_set_id = catalog[0][0] if len(catalog) == 1 else None
        for button in (self.rename_set_button, self.delete_set_button):
            button.setEnabled(self._editing_set_id is not None and self.worker is None)
        issue_count = len(self.review_issues)
        missing_count = sum(issue.get('kind') == 'missing' for issue in self.review_issues)
        # Owner 2026-10-28: one message only (how many pictures are not marked «Ок»); no «Готово/Не завершено» panel
        # and no «только готовые» tick on this screen.
        self.issue_panel.setVisible(False)
        if issue_count:
            parts = [f'Готово: {count} PNG']
            if missing_count:
                parts.append(f'Не завершено: {missing_count} изображений')
            if issue_count > missing_count:
                parts.append(f'Нужно выбрать вариант: {issue_count - missing_count}')
            self.issue_text.setText(' · '.join(parts))
        _review_count = sum(
            report.status == 'review' and self._path_is_active(path)
            for path, report in self.quality_reports.items()
        )
        _block_count = len(self._active_quality_blockers())
        quality_issue_count = sum(self._needs_attention(str(path)) for path in self.review_paths)
        self.quality_panel.setVisible(quality_issue_count > 0 or self._qc_pending > 0)
        self.review_quality_button.setVisible(not self._qc_pending)
        if self._qc_pending:
            done = self._qc_total - self._qc_pending
            self.quality_summary_label.setText(f'Автопроверка PNG идёт: {done} из {self._qc_total}…')
            self.quality_panel.setProperty('state', '')
            self.quality_panel.style().unpolish(self.quality_panel)
            self.quality_panel.style().polish(self.quality_panel)
        elif quality_issue_count:
            quality_text = f'Не помечено «Ок»: {quality_issue_count}'
            self.quality_summary_label.setText(quality_text)
            self._set_quality_page_text('')
            self.quality_panel.setProperty('state', 'warning')
            self.quality_panel.style().unpolish(self.quality_panel)
            self.quality_panel.style().polish(self.quality_panel)
        else:
            self.quality_summary_label.clear()
            self._set_quality_page_text('')
        # Owner 2026-10-28: what the automatic check dislikes never blocks the export.
        export_enabled = (bool(groups) and not self._blocking_review_issues()
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

    def _table_row_double_clicked(self, row, _column):
        """Double click on a picture asks the module to open its transparency editor (owner 2026-10-30).

        The same request the «Редактировать прозрачность» button sends; the picture is taken from the row
        itself, so a sorted table cannot send the wrong one.
        """
        if self.worker is not None:
            self.status.setText('Идёт обработка — редактор прозрачности откроется, когда она закончится.')
            return
        holder = self.table.item(row, 0)
        key = str(holder.data(Qt.ItemDataRole.UserRole) if holder is not None else '')
        if key:
            self.fix_requested.emit(key)

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
