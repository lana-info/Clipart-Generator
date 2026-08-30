from __future__ import annotations

from io import BytesIO
import os
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, UnidentifiedImageError
from PyQt6.QtCore import QEvent, QPoint, QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QImage,
    QImageReader,
    QKeySequence,
    QPainter,
    QPen,
    QPixmap,
    QShortcut,
)
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from background_mask import (
    apply_mask_stroke,
    apply_mask_to_image,
    mask_for_image,
    paint_mask_path,
    save_mask_png,
)
from background_preview import PREVIEW_BACKGROUND_OPTIONS, composite_on_preview
from v3_components import ButtonVariant, V3Button


class MaskEditDocument:
    """One image, its editable alpha mask, and bounded undo/redo history."""

    HISTORY_LIMIT = 50
    HISTORY_MEMORY_LIMIT = 64 * 1024 * 1024

    def __init__(self, image: Image.Image) -> None:
        if not isinstance(image, Image.Image):
            raise TypeError("Ожидается изображение PIL")
        self._save_info = {
            key: image.info[key]
            for key in ("dpi", "icc_profile", "exif")
            if key in image.info and image.info[key] is not None
        }
        self.image = image.convert("RGBA")
        self._original_mask = mask_for_image(self.image)
        self.mask = self._original_mask.copy()
        self._saved_mask = self.mask.copy()
        self._undo: list[tuple[tuple[int, int, int, int], Image.Image, Image.Image]] = []
        self._redo: list[tuple[tuple[int, int, int, int], Image.Image, Image.Image]] = []
        self._stroke_before: Image.Image | None = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def history_bytes(self) -> int:
        return sum(
            before.width * before.height + after.width * after.height
            for _, before, after in (*self._undo, *self._redo)
        )

    @property
    def is_dirty(self) -> bool:
        return ImageChops.difference(self.mask, self._saved_mask).getbbox() is not None

    def _trim_history(self) -> None:
        del self._undo[:-self.HISTORY_LIMIT]
        while self._undo and self.history_bytes > self.HISTORY_MEMORY_LIMIT:
            self._undo.pop(0)

    def begin_stroke(self) -> None:
        if self._stroke_before is None:
            self._stroke_before = self.mask.copy()

    def extend_stroke(
        self,
        points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
        *,
        radius: int,
        action: str,
        hardness: int,
    ) -> tuple[int, int, int, int] | None:
        if self._stroke_before is None:
            raise RuntimeError("Сначала начните штрих")
        paint_mask_path(
            self.mask,
            points,
            radius=radius,
            action=action,
            hardness=hardness,
        )
        if not points:
            return None
        left = max(0, min(point[0] for point in points) - radius - 1)
        top = max(0, min(point[1] for point in points) - radius - 1)
        right = min(self.mask.width, max(point[0] for point in points) + radius + 2)
        bottom = min(self.mask.height, max(point[1] for point in points) + radius + 2)
        return (left, top, right, bottom)

    def end_stroke(self) -> None:
        before = self._stroke_before
        self._stroke_before = None
        if before is None:
            return
        bounds = ImageChops.difference(before, self.mask).getbbox()
        if bounds is None:
            return
        self._undo.append((bounds, before.crop(bounds), self.mask.crop(bounds)))
        self._redo.clear()
        self._trim_history()

    def undo(self) -> None:
        if not self._undo:
            return
        entry = self._undo.pop()
        bounds, before, _ = entry
        self.mask.paste(before, bounds[:2])
        self._redo.append(entry)

    def redo(self) -> None:
        if not self._redo:
            return
        entry = self._redo.pop()
        bounds, _, after = entry
        self.mask.paste(after, bounds[:2])
        self._undo.append(entry)

    def reset(self) -> None:
        if self.mask.tobytes() == self._original_mask.tobytes():
            return
        bounds = ImageChops.difference(self.mask, self._original_mask).getbbox()
        if bounds is None:
            return
        self._undo.append(
            (bounds, self.mask.crop(bounds), self._original_mask.crop(bounds))
        )
        self._redo.clear()
        self._trim_history()
        self.mask.paste(self._original_mask.crop(bounds), bounds[:2])

    def corrected_image(self) -> Image.Image:
        return apply_mask_to_image(self.image, self.mask)

    def corrected_region(self, bounds: tuple[int, int, int, int]) -> Image.Image:
        region = self.image.crop(bounds)
        region.putalpha(self.mask.crop(bounds))
        return region

    def save(self, output_path: str | Path, mask_path: str | Path) -> None:
        destination = Path(output_path)
        mask_destination = Path(mask_path)
        if destination.suffix.casefold() != ".png":
            raise ValueError("Исправленный результат нужно сохранять в PNG")
        destination.parent.mkdir(parents=True, exist_ok=True)
        mask_destination.parent.mkdir(parents=True, exist_ok=True)
        output_temporary = self._stage_png(
            self.corrected_image(),
            destination,
            self._save_info,
        )
        mask_temporary: Path | None = None
        try:
            mask_temporary = self._stage_png(self.mask, mask_destination, {})
            self._replace_pair(
                output_temporary,
                destination,
                mask_temporary,
                mask_destination,
            )
        finally:
            output_temporary.unlink(missing_ok=True)
            if mask_temporary is not None:
                mask_temporary.unlink(missing_ok=True)
        self._saved_mask = self.mask.copy()

    @staticmethod
    def _stage_png(
        image: Image.Image,
        destination: Path,
        save_info: dict[str, object],
    ) -> Path:
        fd, temporary = tempfile.mkstemp(
            prefix=f".{destination.stem}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        os.close(fd)
        temporary_path = Path(temporary)
        try:
            image.save(temporary_path, format="PNG", **save_info)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
        return temporary_path

    @staticmethod
    def _replace_pair(
        output_temporary: Path,
        output_destination: Path,
        mask_temporary: Path,
        mask_destination: Path,
    ) -> None:
        destinations = (output_destination, mask_destination)
        temporaries = (output_temporary, mask_temporary)
        backups: dict[Path, Path] = {}
        replaced: list[Path] = []
        try:
            for destination in destinations:
                if destination.exists():
                    fd, backup_name = tempfile.mkstemp(
                        prefix=f".{destination.stem}.",
                        suffix=".backup",
                        dir=destination.parent,
                    )
                    os.close(fd)
                    backup = Path(backup_name)
                    backup.unlink()
                    os.replace(destination, backup)
                    backups[destination] = backup
            for temporary, destination in zip(temporaries, destinations):
                os.replace(temporary, destination)
                replaced.append(destination)
        except Exception:
            for destination in replaced:
                destination.unlink(missing_ok=True)
            for destination, backup in backups.items():
                if backup.exists():
                    os.replace(backup, destination)
            raise
        finally:
            for backup in backups.values():
                backup.unlink(missing_ok=True)


class _MaskPreviewLabel(QLabel):
    def __init__(self, clicked, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._clicked = clicked

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self._clicked(event.position().toPoint())
        super().mousePressEvent(event)


class ClipartTransparencyPreview(QWidget):
    """Inspection-only preview for a Clipart image with transparency."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self._mask: Image.Image | None = None
        self.background_combo = QComboBox()
        for label, value in PREVIEW_BACKGROUND_OPTIONS:
            self.background_combo.addItem(label, value)
        self.background_combo.setAccessibleName("Фон предпросмотра прозрачности")
        self.background_combo.currentIndexChanged.connect(self.refresh_preview)

        self.action_combo = QComboBox()
        self.action_combo.addItem("Добавить область", "add")
        self.action_combo.addItem("Стереть область", "remove")
        self.action_combo.setAccessibleName("Действие кисти маски")
        self.radius_spin = QSpinBox()
        self.radius_spin.setRange(1, 200)
        self.radius_spin.setValue(24)
        self.radius_spin.setSuffix(" px")
        self.radius_spin.setAccessibleName("Радиус кисти маски")
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(25, 400)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix(" %")
        self.zoom_spin.setAccessibleName("Масштаб проверки краёв")
        self.reset_button = QPushButton("Сбросить маску")
        self.reset_button.clicked.connect(self.reset_mask)
        self.reset_button.setAccessibleName("Сбросить исправления маски")

        self.preview = _MaskPreviewLabel(
            self._apply_display_stroke,
            self,
        )
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(360, 260)
        self.preview.setWordWrap(True)
        self.preview.setAccessibleName("Предпросмотр прозрачного клипарта")

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setMinimumSize(380, 280)
        self.preview_scroll.setWidget(self.preview)

        form = QFormLayout()
        form.addRow("Фон проверки", self.background_combo)
        form.addRow("Кисть", self.action_combo)
        form.addRow("Радиус", self.radius_spin)
        form.addRow("Масштаб краёв", self.zoom_spin)
        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.addWidget(self.reset_button)
        controls_layout.addStretch()
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(controls)
        layout.addWidget(self.preview_scroll, 1)
        self.setAccessibleName("Проверка прозрачности клипарта")
        self.zoom_spin.valueChanged.connect(self.refresh_preview)

    def set_image(self, image: Image.Image | None) -> None:
        self._image = image.convert("RGBA") if image is not None else None
        self._mask = mask_for_image(self._image) if self._image is not None else None
        self.refresh_preview()

    def reset_mask(self) -> None:
        if self._image is None:
            return
        self._mask = mask_for_image(self._image)
        self.refresh_preview()

    def corrected_image(self) -> Image.Image | None:
        if self._image is None or self._mask is None:
            return None
        return apply_mask_to_image(self._image, self._mask)

    def save_corrected_png(self, path: str | Path) -> None:
        image = self.corrected_image()
        if image is None:
            raise ValueError("Нет изображения для сохранения")
        destination = Path(path)
        if destination.suffix.casefold() != ".png":
            raise ValueError("Исправленный результат нужно сохранять в PNG")
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{destination.stem}.", suffix=".tmp", dir=destination.parent
        )
        os.close(fd)
        temporary_path = Path(temporary)
        try:
            image.save(temporary_path, format="PNG")
            os.replace(temporary_path, destination)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise

    def save_mask(self, path: str | Path) -> None:
        if self._mask is None:
            raise ValueError("Нет маски для сохранения")
        save_mask_png(self._mask, path)

    def apply_stroke(self, center: tuple[int, int]) -> None:
        if self._mask is None:
            return
        self._mask = apply_mask_stroke(
            self._mask,
            center,
            radius=self.radius_spin.value(),
            action=str(self.action_combo.currentData()),
        )
        self.refresh_preview()

    def _apply_display_stroke(self, point) -> None:  # type: ignore[no-untyped-def]
        if self._mask is None or self.preview.pixmap().isNull():
            return
        pixmap = self.preview.pixmap()
        offset_x = max(0, (self.preview.width() - pixmap.width()) // 2)
        offset_y = max(0, (self.preview.height() - pixmap.height()) // 2)
        x = point.x() - offset_x
        y = point.y() - offset_y
        if not (0 <= x < pixmap.width() and 0 <= y < pixmap.height()):
            return
        source_x = round(x * self._mask.width / pixmap.width())
        source_y = round(y * self._mask.height / pixmap.height())
        self.apply_stroke((source_x, source_y))

    def set_path(self, path: str) -> None:
        if not path:
            self.set_image(None)
            return
        try:
            with Image.open(Path(path)) as image:
                self.set_image(image.copy())
        except (OSError, UnidentifiedImageError):
            self.set_image(None)
            self.preview.setText("Предпросмотр недоступен")

    def refresh_preview(self) -> None:
        if self._image is None:
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Выберите результат для проверки прозрачности")
            self.preview.adjustSize()
            return
        image = self._image.copy()
        if self._mask is not None:
            image.putalpha(self._mask)
        rendered = composite_on_preview(
            image,
            str(self.background_combo.currentText()),
        )
        buffer = BytesIO()
        rendered.save(buffer, format="PNG")
        image = QImage.fromData(buffer.getvalue(), "PNG")
        pixmap = QPixmap.fromImage(image)
        zoom = self.zoom_spin.value() / 100
        target = pixmap.size()
        target.setWidth(max(1, round(target.width() * zoom)))
        target.setHeight(max(1, round(target.height() * zoom)))
        self.preview.setFixedSize(
            max(360, target.width()),
            max(260, target.height()),
        )
        self.preview.setPixmap(pixmap.scaled(
            target,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        ))
        self.preview.setText("")


def _pixmap_for_pil(image: Image.Image) -> QPixmap:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return QPixmap.fromImage(QImage.fromData(buffer.getvalue(), "PNG"))


class TransparencyCanvas(QGraphicsView):
    """Large alpha-mask canvas with a brush and Space-to-pan behavior."""

    document_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.space_pan_enabled = True
        self.document: MaskEditDocument | None = None
        self.brush_action = "add"
        self.brush_radius = 24
        self.brush_hardness = 70
        self._background_label = "Шахматный"
        self._zoom: int | None = None
        self._painting = False
        self._space_pressed = False
        self.space_pan_indicator_visible = False
        self._panning = False
        self._last_image_point: tuple[int, int] | None = None
        self._last_view_point = QPoint()
        self._brush_scene_point: QPointF | None = None
        self._scene = QGraphicsScene(self)
        self._item = QGraphicsPixmapItem()
        self._scene.addItem(self._item)
        self.setScene(self._scene)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setBackgroundBrush(QColor("#08111e"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAccessibleName("Холст проверки прозрачности")
        self._apply_background_brush()

    @property
    def zoom_percent(self) -> int | None:
        return self._zoom

    def set_document(self, document: MaskEditDocument | None) -> None:
        self.document = document
        self._brush_scene_point = None
        self.refresh_image()
        self.set_zoom(self._zoom)

    def set_background(self, label: str) -> None:
        self._background_label = label
        self._apply_background_brush()

    def _apply_background_brush(self) -> None:
        colors = {
            "Белый": "#ffffff",
            "Чёрный": "#080b10",
            "Ярко-розовый": "#ff1493",
            "Зелёный": "#00a651",
            "Голубой": "#55c7f7",
        }
        if self._background_label != "Шахматный":
            self.setBackgroundBrush(QColor(colors[self._background_label]))
            self.viewport().update()
            return
        tile = QPixmap(20, 20)
        tile.fill(QColor("#eef1f4"))
        painter = QPainter(tile)
        painter.fillRect(0, 0, 10, 10, QColor("#c8ced4"))
        painter.fillRect(10, 10, 10, 10, QColor("#c8ced4"))
        painter.end()
        self.setBackgroundBrush(QBrush(tile))
        self.viewport().update()

    def set_zoom(self, percent: int | None) -> None:
        self._zoom = percent
        self.resetTransform()
        if self.document is None or self._item.pixmap().isNull():
            return
        if percent is None:
            self.fitInView(
                self._item.boundingRect(),
                Qt.AspectRatioMode.KeepAspectRatio,
            )
        else:
            factor = max(1, int(percent)) / 100
            self.scale(factor, factor)

    def refresh_image(self) -> None:
        document = self.document
        if document is None:
            self._item.setPixmap(QPixmap())
            self._scene.setSceneRect(0, 0, 1, 1)
            return
        pixmap = _pixmap_for_pil(document.corrected_image())
        self._item.setPixmap(pixmap)
        self._scene.setSceneRect(self._item.boundingRect())
        self.viewport().update()

    def refresh_region(self, bounds: tuple[int, int, int, int] | None) -> None:
        if bounds is None or self.document is None:
            return
        left, top, right, bottom = bounds
        if right <= left or bottom <= top:
            return
        patch = _pixmap_for_pil(self.document.corrected_region(bounds))
        pixmap = self._item.pixmap()
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.drawPixmap(left, top, patch)
        painter.end()
        self._item.setPixmap(pixmap)
        self.viewport().update()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self._zoom is None and self.document is not None:
            self.set_zoom(None)

    def _image_point(self, viewport_point: QPoint) -> tuple[int, int] | None:
        document = self.document
        if document is None:
            return None
        scene_point = self.mapToScene(viewport_point)
        self._brush_scene_point = scene_point
        local = self._item.mapFromScene(scene_point)
        width, height = document.image.size
        if not (0 <= local.x() < width and 0 <= local.y() < height):
            return None
        return (
            min(width - 1, max(0, round(local.x()))),
            min(height - 1, max(0, round(local.y()))),
        )

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.LeftButton and self._space_pressed:
            self._panning = True
            self._last_view_point = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.document is not None:
            point = self._image_point(event.position().toPoint())
            if point is not None:
                self._painting = True
                self._last_image_point = point
                self.document.begin_stroke()
                bounds = self.document.extend_stroke(
                    (point,),
                    radius=self.brush_radius,
                    action=self.brush_action,
                    hardness=self.brush_hardness,
                )
                self.refresh_region(bounds)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        view_point = event.position().toPoint()
        self._image_point(view_point)
        if self._panning:
            delta = view_point - self._last_view_point
            self._last_view_point = view_point
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
            event.accept()
            return
        if self._painting and self.document is not None:
            point = self._image_point(view_point)
            self._extend_active_stroke(point)
            event.accept()
            return
        self.viewport().update()
        super().mouseMoveEvent(event)

    def _extend_active_stroke(self, point: tuple[int, int] | None) -> None:
        if self.document is None:
            return
        if point is None:
            self._last_image_point = None
            return
        points = (
            (point,)
            if self._last_image_point is None
            else (self._last_image_point, point)
        )
        bounds = self.document.extend_stroke(
            points,
            radius=self.brush_radius,
            action=self.brush_action,
            hardness=self.brush_hardness,
        )
        self._last_image_point = point
        self.refresh_region(bounds)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton and self._panning:
            self._panning = False
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if self._space_pressed
                else Qt.CursorShape.ArrowCursor
            )
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._painting:
            self._painting = False
            self._last_image_point = None
            if self.document is not None:
                self.document.end_stroke()
            self.document_changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.set_space_pan_active(True)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.set_space_pan_active(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def set_space_pan_active(self, active: bool) -> None:
        """Temporarily switch the canvas from brush to hand-pan mode."""

        active = bool(active and self.space_pan_enabled)
        if self._space_pressed == active:
            return
        self._space_pressed = active
        self.space_pan_indicator_visible = active
        if not self._panning:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor
                if active
                else Qt.CursorShape.ArrowCursor
            )
        self.viewport().update()

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._brush_scene_point = None
        self.viewport().update()
        super().leaveEvent(event)

    def drawForeground(self, painter: QPainter, rect) -> None:  # type: ignore[no-untyped-def]
        super().drawForeground(painter, rect)
        if self._space_pressed:
            painter.save()
            painter.resetTransform()
            painter.setPen(QPen(QColor("#dce7f4"), 2))
            painter.setBrush(QColor("#16283f"))
            painter.drawRoundedRect(10, 10, 34, 34, 8, 8)
            painter.setBrush(QColor("#dce7f4"))
            painter.drawEllipse(18, 25, 16, 12)
            painter.drawLine(21, 26, 21, 18)
            painter.drawLine(25, 25, 25, 16)
            painter.drawLine(29, 26, 29, 18)
            painter.drawLine(33, 28, 33, 21)
            painter.restore()
            return
        if self.document is None or self._brush_scene_point is None:
            return
        pen = QPen(QColor("#ffffff"), 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        radius = self.brush_radius
        painter.drawEllipse(self._brush_scene_point, radius, radius)


class ClipartTransparencyEditorPage(QWidget):
    """Dedicated Clipart page for checking and correcting alpha masks."""

    back_requested = pyqtSignal()
    focus_mode_changed = pyqtSignal(bool)
    saved = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._rough_dir: Path | None = None
        self._document: MaskEditDocument | None = None
        self._loaded_path: Path | None = None
        self._draft_masks: dict[Path, bytes] = {}
        self._focus_mode = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        self.title_label = QLabel("Проверка и корректировка прозрачности")
        self.title_label.setProperty("v3Title", True)
        root.addWidget(self.title_label)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        root.addLayout(body, 1)

        canvas_frame = QFrame()
        canvas_frame.setProperty("v3Card", True)
        canvas_layout = QGridLayout(canvas_frame)
        canvas_layout.setContentsMargins(1, 1, 1, 1)
        self.canvas = TransparencyCanvas()
        canvas_layout.addWidget(self.canvas, 0, 0)
        self.focus_button = QToolButton()
        self.focus_button.setText("⛶")
        self.focus_button.setToolTip("Развернуть изображение")
        self.focus_button.setAccessibleName("Развернуть изображение")
        self.focus_button.setFixedSize(36, 36)
        self.focus_button.clicked.connect(self.toggle_focus_mode)
        canvas_layout.addWidget(
            self.focus_button,
            0,
            0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )
        body.addWidget(canvas_frame, 1)

        self.right_panel = QWidget()
        self.right_panel.setFixedWidth(276)
        right = QVBoxLayout(self.right_panel)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(10)
        body.addWidget(self.right_panel)

        files_frame = QFrame()
        files_frame.setProperty("v3Card", True)
        files_layout = QVBoxLayout(files_frame)
        files_layout.setContentsMargins(10, 8, 10, 8)
        files_layout.setSpacing(6)
        files_title = QLabel("Файлы")
        files_title.setProperty("v3Status", True)
        files_layout.addWidget(files_title)
        self.file_list = QListWidget()
        self.file_list.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.file_list.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.file_list.currentRowChanged.connect(self._select_file)
        self.file_list.setAccessibleName("Файлы для проверки прозрачности")
        files_layout.addWidget(self.file_list, 1)
        right.addWidget(files_frame, 2)

        tools_frame = QFrame()
        tools_frame.setProperty("v3Card", True)
        tools_layout = QVBoxLayout(tools_frame)
        tools_layout.setContentsMargins(10, 8, 10, 8)
        tools_layout.setSpacing(6)
        tools_title = QLabel("Инструменты")
        tools_title.setProperty("v3Status", True)
        tools_layout.addWidget(tools_title)

        tools_layout.addWidget(self._small_label("Масштаб"))
        zoom_grid = QGridLayout()
        zoom_grid.setSpacing(4)
        self.zoom_buttons: dict[str | int, QPushButton] = {}
        for index, (key, text) in enumerate(
            (
                ("fit", "Fit"),
                (50, "50%"),
                (100, "100%"),
                (150, "150%"),
                (200, "200%"),
                (300, "300%"),
            )
        ):
            button = QPushButton(text)
            button.setCheckable(True)
            button.setFixedHeight(30)
            button.setAccessibleName(
                "Вписать изображение" if key == "fit" else f"Масштаб {key}%"
            )
            button.clicked.connect(
                lambda checked=False, value=key: self._set_zoom(value)
            )
            self.zoom_buttons[key] = button
            zoom_grid.addWidget(button, index // 6, index % 6)
        self.zoom_buttons["fit"].setChecked(True)
        tools_layout.addLayout(zoom_grid)

        tools_layout.addWidget(self._small_label("Кисть"))
        action_row = QHBoxLayout()
        self.action_group = QButtonGroup(self)
        self.action_group.setExclusive(True)
        self.add_button = QPushButton("Добавить")
        self.remove_button = QPushButton("Стереть")
        for button, value in (
            (self.add_button, "add"),
            (self.remove_button, "remove"),
        ):
            button.setCheckable(True)
            button.clicked.connect(
                lambda checked=False, action=value: self._set_action(action)
            )
            self.action_group.addButton(button)
            action_row.addWidget(button)
        self.add_button.setChecked(True)
        tools_layout.addLayout(action_row)

        self.radius_slider, self.radius_value = self._slider_row(
            tools_layout,
            "Радиус",
            1,
            200,
            24,
            " px",
        )
        self.radius_slider.valueChanged.connect(self._radius_changed)
        self.hardness_slider, self.hardness_value = self._slider_row(
            tools_layout,
            "Жёсткость",
            0,
            100,
            70,
            "%",
        )
        self.hardness_slider.valueChanged.connect(self._hardness_changed)

        history = QHBoxLayout()
        self.undo_button = QPushButton("↶")
        self.redo_button = QPushButton("↷")
        self.reset_button = QPushButton("Сброс")
        self.undo_button.setAccessibleName("Отменить действие")
        self.redo_button.setAccessibleName("Повторить действие")
        self.reset_button.setAccessibleName("Вернуть исходную маску")
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.reset_button.clicked.connect(self.reset)
        history.addWidget(self.undo_button)
        history.addWidget(self.redo_button)
        history.addWidget(self.reset_button)
        tools_layout.addLayout(history)

        tools_layout.addWidget(self._small_label("Фон проверки"))
        background_row = QHBoxLayout()
        background_row.setSpacing(5)
        self.background_group = QButtonGroup(self)
        self.background_group.setExclusive(True)
        background_styles = (
            ("Шахматный", "#d7dde2"),
            ("Белый", "#ffffff"),
            ("Чёрный", "#080b10"),
            ("Ярко-розовый", "#ff1493"),
            ("Зелёный", "#00a651"),
            ("Голубой", "#55c7f7"),
        )
        self.background_buttons: dict[str, QPushButton] = {}
        for label, color in background_styles:
            button = QPushButton("")
            button.setCheckable(True)
            button.setFixedSize(28, 28)
            button.setAccessibleName(f"Фон проверки: {label}")
            button.setToolTip(label)
            button.setStyleSheet(f"background: {color};")
            button.clicked.connect(
                lambda checked=False, value=label: self._set_background(value)
            )
            self.background_group.addButton(button)
            self.background_buttons[label] = button
            background_row.addWidget(button)
        self.background_buttons["Шахматный"].setChecked(True)
        tools_layout.addLayout(background_row)

        save_row = QHBoxLayout()
        self.save_button = V3Button("Сохранить PNG", ButtonVariant.PRIMARY)
        self.back_button = V3Button("К результатам", ButtonVariant.SECONDARY)
        for button in (self.save_button, self.back_button):
            button.setStyleSheet("padding-left: 8px; padding-right: 8px;")
        self.save_button.clicked.connect(self._save_clicked)
        self.back_button.clicked.connect(self._back_clicked)
        save_row.addWidget(self.save_button)
        save_row.addWidget(self.back_button)
        tools_layout.addLayout(save_row)
        right.addWidget(tools_frame, 3)

        self.canvas.document_changed.connect(self._refresh_history_buttons)
        QShortcut(QKeySequence.StandardKey.Undo, self, activated=self.undo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, activated=self.redo)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        self._refresh_history_buttons()
        self.setAccessibleName("Проверка и корректировка прозрачности")

    @staticmethod
    def _small_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("v3Small", True)
        return label

    @staticmethod
    def _slider_row(
        layout: QVBoxLayout,
        label_text: str,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str,
    ) -> tuple[QSlider, QLabel]:
        row = QHBoxLayout()
        label = ClipartTransparencyEditorPage._small_label(label_text)
        label.setFixedWidth(60)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        value_label = QLabel(f"{value}{suffix}")
        value_label.setFixedWidth(48)
        row.addWidget(label)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        layout.addLayout(row)
        return slider, value_label

    @property
    def current_path(self) -> Path | None:
        row = self.file_list.currentRow()
        return self._paths[row] if 0 <= row < len(self._paths) else None

    @property
    def document(self) -> MaskEditDocument:
        path = self.current_path
        if path is None or path != self._loaded_path or self._document is None:
            raise ValueError("Нет изображения для проверки")
        return self._document

    def _stash_current_document(self) -> None:
        if self._loaded_path is None or self._document is None:
            return
        if not self._document.is_dirty:
            self._draft_masks.pop(self._loaded_path, None)
            return
        buffer = BytesIO()
        self._document.mask.save(buffer, format="PNG", optimize=True)
        self._draft_masks[self._loaded_path] = buffer.getvalue()

    def set_files(
        self,
        paths: tuple[str | Path, ...] | list[str | Path],
        *,
        selected_index: int = 0,
        rough_dir: str | Path | None = None,
    ) -> None:
        self._stash_current_document()
        self._paths = [Path(path) for path in paths]
        self._rough_dir = Path(rough_dir) if rough_dir is not None else None
        allowed = set(self._paths)
        self._draft_masks = {
            path: data for path, data in self._draft_masks.items() if path in allowed
        }
        self._document = None
        self._loaded_path = None
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for path in self._paths:
            item = QListWidgetItem(path.name)
            reader = QImageReader(str(path))
            source_size = reader.size()
            if source_size.isValid():
                source_size.scale(
                    QSize(28, 28),
                    Qt.AspectRatioMode.KeepAspectRatio,
                )
                reader.setScaledSize(source_size)
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                item.setIcon(QIcon(pixmap))
            self.file_list.addItem(item)
        self.file_list.blockSignals(False)
        if self._paths:
            self.file_list.setCurrentRow(
                min(max(0, selected_index), len(self._paths) - 1)
            )
        else:
            self.canvas.set_document(None)
        self._refresh_history_buttons()

    def refresh_from_state(self) -> None:
        """Keep the shared page-controller refresh contract."""
        self._refresh_history_buttons()

    def _select_file(self, row: int) -> None:
        self._stash_current_document()
        self._document = None
        self._loaded_path = None
        if not 0 <= row < len(self._paths):
            self.canvas.set_document(None)
            self._refresh_history_buttons()
            return
        path = self._paths[row]
        try:
            with Image.open(path) as image:
                document = MaskEditDocument(image.copy())
            draft = self._draft_masks.get(path)
            if draft is not None:
                with Image.open(BytesIO(draft)) as mask:
                    document.mask = mask.convert("L").copy()
        except (OSError, UnidentifiedImageError):
            self.canvas.set_document(None)
            self._refresh_history_buttons()
            return
        self._document = document
        self._loaded_path = path
        self.canvas.set_document(document)
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        self._refresh_history_buttons()

    def _set_zoom(self, value: str | int) -> None:
        for key, button in self.zoom_buttons.items():
            button.setChecked(key == value)
        self.canvas.set_zoom(None if value == "fit" else int(value))

    def _set_action(self, action: str) -> None:
        self.canvas.brush_action = action

    def _radius_changed(self, value: int) -> None:
        self.radius_value.setText(f"{value} px")
        self.canvas.brush_radius = value
        self.canvas.viewport().update()

    def _hardness_changed(self, value: int) -> None:
        self.hardness_value.setText(f"{value}%")
        self.canvas.brush_hardness = value

    def _set_background(self, label: str) -> None:
        self.canvas.set_background(label)

    def undo(self) -> None:
        try:
            self.document.undo()
        except ValueError:
            return
        self.canvas.refresh_image()
        self._refresh_history_buttons()

    def redo(self) -> None:
        try:
            self.document.redo()
        except ValueError:
            return
        self.canvas.refresh_image()
        self._refresh_history_buttons()

    def reset(self) -> None:
        try:
            self.document.reset()
        except ValueError:
            return
        self.canvas.refresh_image()
        self._refresh_history_buttons()

    def _refresh_history_buttons(self) -> None:
        try:
            document = self.document
        except ValueError:
            self.undo_button.setEnabled(False)
            self.redo_button.setEnabled(False)
            self.save_button.setEnabled(False)
            return
        self.undo_button.setEnabled(document.can_undo)
        self.redo_button.setEnabled(document.can_redo)
        self.save_button.setEnabled(True)

    def save_current(self) -> tuple[Path, Path]:
        output_path = self.current_path
        if output_path is None:
            raise ValueError("Нет изображения для сохранения")
        rough_dir = self._rough_dir or output_path.parent.parent / "rough"
        mask_path = rough_dir / f"{output_path.stem}_alpha-mask.png"
        self.document.save(output_path, mask_path)
        self._draft_masks.pop(output_path, None)
        self.saved.emit(output_path.name)
        return output_path, mask_path

    def _save_clicked(self) -> None:
        try:
            self.save_current()
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                self,
                "Не удалось сохранить PNG",
                f"Проверьте доступ к папке и свободное место.\n\n{error}",
            )

    def _has_unsaved_changes(self) -> bool:
        current_dirty = self._document is not None and self._document.is_dirty
        return current_dirty or bool(self._draft_masks)

    def _back_clicked(self) -> None:
        if self._has_unsaved_changes():
            answer = QMessageBox.warning(
                self,
                "Есть несохранённые изменения",
                "Вернуться к результатам и отменить изменения маски?",
                QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                return
            self._draft_masks.clear()
            self._document = None
            self._loaded_path = None
        self.back_requested.emit()

    def toggle_focus_mode(self) -> None:
        self._focus_mode = not self._focus_mode
        self.right_panel.setVisible(not self._focus_mode)
        self.title_label.setVisible(not self._focus_mode)
        self.focus_button.setText("⛶" if not self._focus_mode else "×")
        self.focus_button.setToolTip(
            "Развернуть изображение" if not self._focus_mode else "Вернуть обычный вид"
        )
        self.focus_mode_changed.emit(self._focus_mode)
        if self.canvas._zoom is None:
            self.canvas.set_zoom(None)

    def leave_focus_mode(self) -> None:
        if self._focus_mode:
            self.toggle_focus_mode()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.canvas.set_space_pan_active(True)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._focus_mode:
            self.leave_focus_mode()
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.canvas.set_space_pan_active(False)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if event.type() in {QEvent.Type.KeyPress, QEvent.Type.KeyRelease}:
            if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
                self.canvas.set_space_pan_active(
                    event.type() == QEvent.Type.KeyPress
                )
                event.accept()
                return True
        return super().eventFilter(watched, event)
