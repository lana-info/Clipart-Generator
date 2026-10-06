from __future__ import annotations

from io import BytesIO
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor, CancelledError
from threading import Event
import math
from collections import Counter
import cv2
import numpy as np
import hashlib
import json
import os
import errno
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, UnidentifiedImageError
from PyQt6.QtCore import QEvent, QEventLoop, QPoint, QPointF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
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


from studio_contour import BezierNode, BezierPath, ContourDocument, extract_contours, rasterize_path, MAX_NODES_PER_PATH, MAX_AUTO_CONTOUR_SIDE, MAX_IMAGE_PIXELS as MAX_CONTOUR_IMAGE_PIXELS, changed_path_roi, _auto_handles

from studio_contour_local import simplify_selected, smooth_selected, local_changed_path_rois

_CONTOUR_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vibix-contour")

BRUSH_DIAMETERS = (2, 6, 10, 16, 32, 64)
_EDGE_SHARPEN_LUT = tuple(round(max(0, min(255, 2 * value - 127.5))) for value in range(256))

MAX_EDITOR_IMAGE_PIXELS = 40_000_000


class EditorImageTooLargeError(ValueError):
    pass


def _validate_editor_image_size(size: tuple[int, int]) -> None:
    width, height = size
    if width > 0 and height > 0 and width * height > MAX_EDITOR_IMAGE_PIXELS:
        megapixels = width * height / 1_000_000
        raise EditorImageTooLargeError(
            "Изображение слишком большое для редактора прозрачности "
            f"({megapixels:.1f} Мп). Максимум — 40 Мп. "
            "Уменьшите изображение и повторите проверку."
        )


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
        self.mask_revision = 0

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
        self.mask_revision += 1
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
        self.mask_revision += 1
        self._redo.append(entry)

    def redo(self) -> None:
        if not self._redo:
            return
        entry = self._redo.pop()
        bounds, _, after = entry
        self.mask.paste(after, bounds[:2])
        self.mask_revision += 1
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
        self.mask_revision += 1

    def apply_mask_proposal(self, mask: Image.Image) -> None:
        """Commit an explicitly accepted alpha-only proposal as one undo step."""
        if mask.mode != 'L' or mask.size != self.mask.size:
            raise ValueError('Предложение маски не соответствует изображению')
        if self._stroke_before is not None:
            raise ValueError('Сначала завершите штрих')
        bounds = ImageChops.difference(self.mask, mask).getbbox()
        if bounds is None:
            return
        if (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) * 2 > self.HISTORY_MEMORY_LIMIT:
            raise ValueError('Не хватает памяти истории для отмены этого шага. Маска не изменена.')
        before, after = self.mask.crop(bounds), mask.crop(bounds)
        self._undo.append((bounds, before, after))
        self._redo.clear()
        self._trim_history()
        self.mask.paste(after, bounds[:2])
        self.mask_revision += 1

    def corrected_image(self) -> Image.Image:
        return apply_mask_to_image(self.image, self.mask)

    def corrected_region(self, bounds: tuple[int, int, int, int]) -> Image.Image:
        region = self.image.crop(bounds)
        region.putalpha(self.mask.crop(bounds))
        return region

    def save(self, output_path: str | Path, mask_path: str | Path, *, copy_source: Path | None = None) -> None:
        destination = Path(output_path)
        mask_destination = Path(mask_path)
        if destination.suffix.casefold() != ".png":
            raise ValueError("Исправленный результат нужно сохранять в PNG")
        destination.parent.mkdir(parents=True, exist_ok=True)
        mask_destination.parent.mkdir(parents=True, exist_ok=True)
        from chroma_generation_record import (
            capture_generation_record, generation_transaction_lock, record_path,
            stage_rebound_generation_record,
        )
        with generation_transaction_lock(destination):
            self._recover_pair_unlocked(destination, mask_destination)
            try:
                generation_record = (
                    capture_generation_record(copy_source or destination)
                    if (copy_source or destination).exists() else None
                )
            except OSError as error:
                # A valid imported filename may leave no filesystem room for
                # optional provenance sidecars. Other I/O errors still surface.
                if copy_source is None or error.errno != errno.ENAMETOOLONG:
                    raise
                generation_record = None
            output_temporary = self._stage_png(
                self.corrected_image(),
                destination,
                self._save_info,
            )
            mask_temporary: Path | None = None
            sidecar_temporary: Path | None = None
            try:
                mask_temporary = self._stage_png(self.mask, mask_destination, {})
                if generation_record is not None:
                    sidecar_temporary = stage_rebound_generation_record(
                        output_temporary, generation_record, stage="final",
                        directory=destination.parent,
                    )
                self._replace_pair(
                    output_temporary,
                    destination,
                    mask_temporary,
                    mask_destination,
                    sidecar_temporary=sidecar_temporary,
                    sidecar_destination=(record_path(destination) if sidecar_temporary else None),
                )
            finally:
                output_temporary.unlink(missing_ok=True)
                if mask_temporary is not None:
                    mask_temporary.unlink(missing_ok=True)
                if sidecar_temporary is not None:
                    sidecar_temporary.unlink(missing_ok=True)
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
    def _pair_transaction_paths(
        output_destination: Path,
        mask_destination: Path,
    ) -> tuple[Path, tuple[Path, Path]]:
        identity = hashlib.sha256(
            (
                str(output_destination.resolve(strict=False))
                + "\0"
                + str(mask_destination.resolve(strict=False))
            ).encode("utf-8")
        ).hexdigest()[:16]
        marker = output_destination.parent / f".vibix-pair-{identity}.json"
        backups = (
            output_destination.with_name(
                f".{output_destination.name}.{identity}.backup"
            ),
            mask_destination.with_name(
                f".{mask_destination.name}.{identity}.backup"
            ),
        )
        return marker, backups

    @staticmethod
    def _write_pair_transaction(
        marker: Path,
        *,
        phase: str,
        existed: tuple[bool, ...],
        includes_sidecar: bool = False,
    ) -> None:
        payload = json.dumps(
            {
                "schema_version": 2 if includes_sidecar else 1,
                "phase": phase,
                "existed": list(existed),
                **({"includes_sidecar": True} if includes_sidecar else {}),
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{marker.name}.",
            suffix=".tmp",
            dir=marker.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, marker)
        finally:
            temporary.unlink(missing_ok=True)

    @classmethod
    def recover_pair(
        cls,
        output_destination: str | Path,
        mask_destination: str | Path,
    ) -> bool:
        """Recover an interrupted commit only while holding its advisory lock."""
        output = Path(output_destination)
        mask = Path(mask_destination)
        marker, _ = cls._pair_transaction_paths(output, mask)
        if not marker.is_file():
            return False
        from chroma_generation_record import generation_transaction_lock
        with generation_transaction_lock(output):
            return cls._recover_pair_unlocked(output, mask)

    @classmethod
    def _recover_pair_unlocked(
        cls,
        output_destination: str | Path,
        mask_destination: str | Path,
    ) -> bool:
        destinations = (Path(output_destination), Path(mask_destination))
        marker, backups = cls._pair_transaction_paths(*destinations)
        if not marker.is_file():
            return False
        try:
            payload = json.loads(marker.read_text(encoding="utf-8"))
            existed_raw = payload.get("existed")
            version = payload.get("schema_version")
            includes_sidecar = version == 2 and payload.get("includes_sidecar") is True
            expected_count = 3 if includes_sidecar else 2
            if (
                version not in {1, 2}
                or (version == 2 and not includes_sidecar)
                or payload.get("phase") not in {"prepared", "committed"}
                or not isinstance(existed_raw, list)
                or len(existed_raw) != expected_count
                or not all(isinstance(value, bool) for value in existed_raw)
            ):
                raise ValueError("Повреждён журнал сохранения PNG/mask")
            existed = tuple(existed_raw)
            committed = payload["phase"] == "committed"
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            raise OSError("Не удалось восстановить прерванное сохранение PNG/mask")

        if includes_sidecar:
            from chroma_generation_record import record_path
            sidecar = record_path(destinations[0])
            identity = marker.stem.rsplit("-", 1)[-1]
            destinations = (*destinations, sidecar)
            backups = (*backups, sidecar.with_name(f".{sidecar.name}.{identity}.backup"))

        if committed and all(destination.is_file() for destination in destinations):
            for backup in backups:
                backup.unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            return True

        for destination, backup, previously_existed in zip(
            destinations,
            backups,
            existed,
        ):
            if previously_existed:
                if backup.exists():
                    destination.unlink(missing_ok=True)
                    os.replace(backup, destination)
            else:
                destination.unlink(missing_ok=True)
                backup.unlink(missing_ok=True)
        for backup in backups:
            backup.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        return True

    @classmethod
    def _replace_pair(
        cls,
        output_temporary: Path,
        output_destination: Path,
        mask_temporary: Path,
        mask_destination: Path,
        *,
        sidecar_temporary: Path | None = None,
        sidecar_destination: Path | None = None,
    ) -> None:
        if (sidecar_temporary is None) != (sidecar_destination is None):
            raise ValueError("Sidecar transaction is incomplete")
        destinations = (output_destination, mask_destination)
        temporaries = (output_temporary, mask_temporary)
        marker, backups = cls._pair_transaction_paths(*destinations)
        includes_sidecar = sidecar_temporary is not None
        if includes_sidecar:
            identity = marker.stem.rsplit("-", 1)[-1]
            destinations = (*destinations, sidecar_destination)
            temporaries = (*temporaries, sidecar_temporary)
            backups = (*backups, sidecar_destination.with_name(
                f".{sidecar_destination.name}.{identity}.backup"
            ))
        existed = tuple(destination.exists() for destination in destinations)
        cls._write_pair_transaction(
            marker, phase="prepared", existed=existed,
            includes_sidecar=includes_sidecar,
        )
        try:
            for destination, backup, previously_existed in zip(
                destinations,
                backups,
                existed,
            ):
                backup.unlink(missing_ok=True)
                if previously_existed:
                    os.replace(destination, backup)
            for temporary, destination in zip(temporaries, destinations):
                os.replace(temporary, destination)
            cls._write_pair_transaction(
                marker,
                phase="committed",
                existed=existed,
                includes_sidecar=includes_sidecar,
            )
        except BaseException:
            cls._recover_pair_unlocked(output_destination, mask_destination)
            raise
        for backup in backups:
            backup.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)


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
    rgba = image.convert("RGBA")
    data = rgba.tobytes()
    qimage = QImage(data, rgba.width, rgba.height, rgba.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def _local_alpha_support(previous, replacement, bounds):
    """Pixel permission follows changed curves, never the allocation rectangle.

    Exact common cubics protect their raw alpha edge, even if a long changed
    C-shaped run encloses that edge in its bounding box.
    """
    def segments(path):
        return [(node.point, _auto_handles(path.nodes, i)[1],
                 _auto_handles(path.nodes, (i+1) % len(path.nodes))[0],
                 path.nodes[(i+1) % len(path.nodes)].point)
                for i, node in enumerate(path.nodes)]
    old, new = Counter(segments(previous)), Counter(segments(replacement))
    left, top, right, bottom = bounds
    support = np.zeros((bottom-top, right-left), dtype=np.uint8)
    protected = support.copy()
    def stroke(target, segment, width):
        a, b, c, d = np.asarray(segment, dtype=float)
        # Match the editor rasterizer's twelve intervals, including the endpoint.
        t = (np.arange(13, dtype=float) / 12)[:, None]
        points = (1-t)**3*a + 3*(1-t)**2*t*b + 3*(1-t)*t*t*c + t**3*d
        points = np.rint(points).astype(np.int32) - (left, top)
        cv2.polylines(target, [points.astype(np.int32)], False, 255, width, cv2.LINE_8)
    for segment in (old-new).keys() | (new-old).keys():
        stroke(support, segment, 9)
    for segment in (old & new):
        stroke(protected, segment, 5)
    coverage_changed = rasterize_path(previous, bounds) != rasterize_path(replacement, bounds)
    return ((support > 0) | coverage_changed) & (protected == 0)


def _calculate_contour(kind, alpha, originals, paths, cancelled):
    """Worker owns only immutable geometry and a mask snapshot, never Qt state."""
    if cancelled.is_set():
        raise CancelledError()
    if max(alpha.shape) > MAX_AUTO_CONTOUR_SIDE or alpha.size > MAX_CONTOUR_IMAGE_PIXELS:
        raise ValueError("Контуры поддерживают изображения до 32 мегапикселей и 32768 px по стороне.")
    if kind == "extract":
        if not np.any(alpha == 0) or not np.any(alpha > 0):
            raise ValueError("Автоконтур требует изображения с прозрачным фоном.")
        result = extract_contours(alpha, tolerance=1.0, cancelled=cancelled.is_set)
    elif kind in ('manual-remove', 'manual-keep'):
        h, w = alpha.shape
        coverage = rasterize_path(paths[0], (0, 0, w, h))
        result_alpha = alpha.copy()
        result_alpha[coverage > 0 if kind == 'manual-remove' else coverage == 0] = 0
        diff = result_alpha != alpha
        rows = np.flatnonzero(np.any(diff, axis=1))
        columns = np.flatnonzero(np.any(diff, axis=0))
        bounds = (int(columns[0]), int(rows[0]), int(columns[-1])+1, int(rows[-1])+1) if rows.size else None
        result = result_alpha, bounds
    elif kind in ('local-apply', 'local-preview'):
        result_alpha = alpha.copy()
        for index, path in enumerate(paths):
            for bounds in local_changed_path_rois(originals[index], path):
                if cancelled.is_set():
                    raise CancelledError()
                core = ContourDocument(alpha, list(originals))
                candidate = core.apply_path(index, path, bounds, cancelled=cancelled.is_set)
                left, top, right, bottom = bounds
                support = _local_alpha_support(originals[index], path, bounds)
                support &= candidate[top:bottom, left:right] != alpha[top:bottom, left:right]
                patch = result_alpha[top:bottom, left:right]
                patch[support] = candidate[top:bottom, left:right][support]
        diff = result_alpha != alpha
        rows = np.flatnonzero(np.any(diff, axis=1))
        columns = np.flatnonzero(np.any(diff, axis=0))
        bounds = (int(columns[0]), int(rows[0]), int(columns[-1])+1, int(rows[-1])+1) if rows.size else None
        result = result_alpha, bounds
    else:
        core = ContourDocument(alpha, list(originals))
        for index, path in enumerate(paths):
            if cancelled.is_set():
                raise CancelledError()
            if path != originals[index]:
                core.paths = list(originals)
                core.apply_path(index, path, changed_path_roi(originals[index], path), cancelled=cancelled.is_set)
        diff = core.alpha != alpha
        rows = np.flatnonzero(np.any(diff, axis=1))
        columns = np.flatnonzero(np.any(diff, axis=0))
        bounds = (int(columns[0]), int(rows[0]), int(columns[-1])+1, int(rows[-1])+1) if rows.size else None
        result = core.alpha, bounds
    if cancelled.is_set():
        raise CancelledError()
    return result


class InlineContour:
    """Pending vector edits on the existing mask; never owns a second canvas."""

    def __init__(self):
        self.original = []
        self.paths = []
        self._selected = None
        self.selection = set()
        self.local_before = None
        self.preview_after = True
        self._local_cache = None
        self.undo_stack = []
        self.redo_stack = []
        self.points = []
        self.manual = False

    @property
    def selected(self):
        self.sanitize_selection()
        return self._selected

    @selected.setter
    def selected(self, pair):
        self._selected = pair
        self.selection = {pair} if pair is not None else set()

    def sanitize_selection(self):
        self.selection = {(pi, ni) for pi, ni in self.selection
                          if 0 <= pi < len(self.paths) and 0 <= ni < len(self.paths[pi].nodes)}
        if self._selected not in self.selection:
            self._selected = min(self.selection) if self.selection else None

    def select(self, pairs, additive=False):
        self.selection = self.selection.union(pairs) if additive else set(pairs)
        self._selected = min(self.selection) if self.selection else None
        self.sanitize_selection()

    @property
    def local_active(self):
        return self.local_before is not None

    def local_steps(self):
        self.sanitize_selection()
        key = (tuple(self.paths), frozenset(self.selection))
        if self._local_cache is None or self._local_cache[0] != key:
            self._local_cache = (key, simplify_selected(*key), smooth_selected(*key))
        return self._local_cache[1:]

    def snapshot(self):
        return (list(self.paths), self._selected, frozenset(self.selection),
                list(self.points), self.manual, self.local_before, self.preview_after)

    @property
    def dirty(self):
        return bool(self.points) or self.paths != self.original

    def checkpoint(self):
        self.undo_stack.append(self.snapshot())
        del self.undo_stack[:-50]
        self.redo_stack.clear()

    def history(self, redo=False):
        source = self.redo_stack if redo else self.undo_stack
        target = self.undo_stack if redo else self.redo_stack
        if not source:
            return False
        target.append(self.snapshot())
        (self.paths, self._selected, selection, self.points, self.manual,
         self.local_before, self.preview_after) = source.pop()
        self.selection = set(selection)
        self.sanitize_selection()
        return True

    def add_point(self, point):
        if len(self.points) >= MAX_NODES_PER_PATH or (self.points and point == self.points[-1]):
            return
        self.checkpoint()
        self.manual = True
        self.points.append(point)

    def close_path(self, shape):
        if len(self.points) < 3:
            return False
        # Reject a line rather than applying a degenerate selection.
        a = self.points[0]
        if not any(abs((b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0])) > .01
                   for b, c in zip(self.points[1:], self.points[2:])):
            return False
        self.checkpoint()
        self.paths = [BezierPath(tuple(BezierNode(p) for p in self.points), 0, shape)]
        self.points = []
        self.selected = None
        return True

    def hit(self, point, tolerance):
        if self.selected:
            pi, ni = self.selected
            node = self.paths[pi].nodes[ni]
            for name in ('in_handle', 'out_handle'):
                handle = getattr(node, name)
                if handle and handle != node.point and math.dist(point, handle) <= tolerance:
                    return pi, ni, name
        for pi, path in enumerate(self.paths):
            for ni, node in enumerate(path.nodes):
                if math.dist(point, node.point) <= tolerance:
                    return pi, ni, 'point'
        return None

    def update_node(self, pi, ni, node):
        path = self.paths[pi]
        nodes = list(path.nodes)
        nodes[ni] = node
        self.paths[pi] = replace(path, nodes=tuple(nodes))

    def move(self, hit, point):
        pi, ni, part = hit
        node = self.paths[pi].nodes[ni]
        h, w = self.paths[pi].source_shape
        clamp = lambda p: (min(w-1, max(0, p[0])), min(h-1, max(0, p[1])))
        point = clamp(point)
        if part == 'point':
            dx, dy = point[0]-node.point[0], point[1]-node.point[1]
            shift = lambda p: clamp((p[0]+dx, p[1]+dy)) if p else None
            node = replace(node, point=point, in_handle=shift(node.in_handle), out_handle=shift(node.out_handle))
        else:
            changes = {part: point}
            if node.kind == 'smooth':
                other = 'out_handle' if part == 'in_handle' else 'in_handle'
                changes[other] = clamp((2*node.point[0]-point[0], 2*node.point[1]-point[1]))
            node = replace(node, **changes)
        self.update_node(pi, ni, node)

    def toggle(self):
        if self.selected is None:
            return
        self.checkpoint()
        pi, ni = self.selected
        path = self.paths[pi]
        node = path.nodes[ni]
        if node.kind == 'smooth':
            node = replace(node, kind='corner', in_handle=node.point, out_handle=node.point)
        else:
            prev, nxt = path.nodes[ni-1].point, path.nodes[(ni+1) % len(path.nodes)].point
            tangent = ((nxt[0]-prev[0])/6, (nxt[1]-prev[1])/6)
            h, w = path.source_shape
            handle = lambda sign: (min(w-1,max(0,node.point[0]+sign*tangent[0])), min(h-1,max(0,node.point[1]+sign*tangent[1])))
            node = replace(node, kind='smooth', in_handle=handle(-1), out_handle=handle(1))
        self.update_node(pi, ni, node)

    def delete(self):
        if self.points:
            self.checkpoint()
            self.points.pop()
            return
        if self.selected is None:
            return
        pi, ni = self.selected
        path = self.paths[pi]
        if len(path.nodes) <= 3:
            return
        self.checkpoint()
        self.paths[pi] = replace(path, nodes=path.nodes[:ni]+path.nodes[ni+1:])
        self.selection = {(p, i - (p == pi and i > ni)) for p, i in self.selection if (p, i) != (pi, ni)}
        self._selected = None
        self.sanitize_selection()

    def insert(self, point, tolerance):
        # De Casteljau splitting preserves the curve, including its handles.
        best = None
        for pi, path in enumerate(self.paths):
            for ni, node in enumerate(path.nodes):
                nxt = path.nodes[(ni+1) % len(path.nodes)]
                a, b = np.array(node.point), np.array(node.out_handle or node.point)
                c, d = np.array(nxt.in_handle or nxt.point), np.array(nxt.point)
                for t in np.linspace(.02, .98, 49):
                    q = (1-t)**3*a+3*(1-t)**2*t*b+3*(1-t)*t*t*c+t**3*d
                    distance = np.linalg.norm(q-point)
                    if distance <= tolerance and (best is None or distance < best[0]):
                        best = distance, pi, ni, t, a, b, c, d
        if best is None:
            return
        _, pi, ni, t, a, b, c, d = best
        ab, bc, cd = (1-t)*a+t*b, (1-t)*b+t*c, (1-t)*c+t*d
        abc, bcd = (1-t)*ab+t*bc, (1-t)*bc+t*cd
        q = (1-t)*abc+t*bcd
        path = self.paths[pi]
        if len(path.nodes) >= MAX_NODES_PER_PATH:
            return
        self.checkpoint()
        nodes = list(path.nodes)
        nodes[ni] = replace(nodes[ni], out_handle=tuple(ab))
        j = (ni+1) % len(nodes)
        nodes[j] = replace(nodes[j], in_handle=tuple(cd))
        nodes.insert(ni+1, BezierNode(tuple(q), 'smooth', tuple(abc), tuple(bcd)))
        self.paths[pi] = replace(path, nodes=tuple(nodes))
        self.selected = pi, ni+1


class TransparencyCanvas(QGraphicsView):
    """Large alpha-mask canvas with a brush and Space-to-pan behavior."""

    document_changed = pyqtSignal()
    tool_requested = pyqtSignal(str)
    diameter_requested = pyqtSignal(int)
    zoom_requested = pyqtSignal(int)
    history_requested = pyqtSignal(bool)
    preview_cancel_requested = pyqtSignal()
    status_changed = pyqtSignal(str)
    contour_finished = pyqtSignal(str, bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.space_pan_enabled = True
        self.document: MaskEditDocument | None = None
        self.tool = "brush"
        self.contour = InlineContour()
        self._contour_drag = None
        self.lasso_enabled = False
        self._lasso_points = []
        self._lasso_outline = []
        self._lasso_additive = False
        self._preview_alpha = None
        self._preview_paths = None
        self._preview_mask_revision = -1
        self.edge_preview_active = False
        self.edge_preview_mask: Image.Image | None = None
        self._contour_job = None
        self._contour_timer = QTimer(self)
        self._contour_timer.setInterval(20)
        self._contour_timer.timeout.connect(self._poll_contour)
        self._drag_checkpoint = False
        self.brush_action = "remove"
        self.brush_radius = 8
        self.brush_hardness = 85
        self._background_label = "Шахматный"
        self._zoom: int | None = None
        self._zoom_wheel_delta = 0
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
        self.cancel_contour()
        self.edge_preview_active = False
        self.edge_preview_mask = None
        self.document = document
        self.status_changed.emit("")
        self._lasso_points = []
        self._lasso_outline = []
        self._contour_drag = None
        self._preview_alpha = None
        self._preview_paths = None
        self.contour = getattr(document, "pending_contour", InlineContour())
        self.contour.sanitize_selection()
        if document is not None:
            document.pending_contour = self.contour
        self._brush_scene_point = None
        self.refresh_image()
        self.set_zoom(self._zoom)
        if document is not None and self.contour.local_active and not self.contour.manual and not self.contour_busy:
            self._start_contour('local-preview')

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
        rendered = document.corrected_image()
        if self.edge_preview_active and self.edge_preview_mask is not None:
            rendered.putalpha(self.edge_preview_mask)
        elif (self.contour.local_active and self.contour.preview_after
                and self._preview_alpha is not None and self._preview_paths == tuple(self.contour.paths)
                and self._preview_mask_revision == document.mask_revision):
            rendered.putalpha(Image.fromarray(self._preview_alpha))
        pixmap = _pixmap_for_pil(rendered)
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
        if self.contour_busy or self.edge_preview_active:
            event.accept()
            return
        if self.tool == "pen" and self.document is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self._show_after_for_edit()
                point = self._image_point(event.position().toPoint())
                hit = self.contour.hit(point, 7 / self.transform().m11()) if point and self.contour.paths else None
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if self.contour.paths and self.lasso_enabled and not (hit and event.modifiers() & Qt.KeyboardModifier.AltModifier):
                    self._lasso_points = [self.mapToScene(event.position().toPoint())]
                    self._lasso_additive = shift
                    self._lasso_outline = []
                elif point and not self.contour.paths:
                    if len(self.contour.points) >= 3 and math.dist(point, self.contour.points[0]) <= 7 / self.transform().m11():
                        self.close_manual_contour()
                    else:
                        self.contour.add_point(point)
                        self.document_changed.emit()
                elif point:
                    self.contour.select([hit[:2]] if hit else [], additive=shift)
                    self._lasso_outline = []
                    if hit and event.modifiers() & Qt.KeyboardModifier.AltModifier:
                        self.contour.toggle()
                        self.refresh_local_preview()
                    elif not shift:
                        self._contour_drag = hit
                        self._drag_checkpoint = False
                    self.document_changed.emit()
                self.viewport().update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self.document is not None:
            point = self._image_point(event.position().toPoint())
            if point is not None:
                self._preview_alpha = None
                self._preview_paths = None
                self.refresh_image()
                self._painting = True
                self._last_image_point = point
                self.document.begin_stroke()
                bounds = self.document.extend_stroke(
                    (point,),
                    radius=self.brush_radius,
                    action=self._effective_action(event.modifiers()),
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
        if self._lasso_points and event.buttons() & Qt.MouseButton.LeftButton:
            self._lasso_points.append(self.mapToScene(view_point))
            self.viewport().update()
            event.accept()
            return
        if self._contour_drag and event.buttons() & Qt.MouseButton.LeftButton:
            point = self._image_point(view_point)
            if point:
                if not self._drag_checkpoint:
                    self.contour.checkpoint()
                    self._drag_checkpoint = True
                self.contour.move(self._contour_drag, point)
                self.viewport().update()
                self.document_changed.emit()
            event.accept()
            return
        if self._painting and self.document is not None:
            self._stroke_action = self._effective_action(event.modifiers())
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
            action=getattr(self, "_stroke_action", self.brush_action),
            hardness=self.brush_hardness,
        )
        self._last_image_point = point
        self.refresh_region(bounds)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        dragged = self._contour_drag is not None and self._drag_checkpoint
        self._contour_drag = None
        if event.button() == Qt.MouseButton.LeftButton and self._lasso_points:
            self._lasso_points.append(self.mapToScene(event.position().toPoint()))
            polygon = QPainterPath(self._lasso_points[0])
            for point in self._lasso_points[1:]:
                polygon.lineTo(point)
            polygon.closeSubpath()
            pairs = {(pi, ni) for pi, path in enumerate(self.contour.paths)
                     for ni, node in enumerate(path.nodes) if polygon.contains(QPointF(*node.point))}
            if len(self._lasso_points) <= 2:
                point = self._image_point(event.position().toPoint())
                hit = self.contour.hit(point, 7 / self.transform().m11()) if point else None
                pairs = {hit[:2]} if hit else set()
            self.contour.select(pairs, self._lasso_additive)
            self._lasso_outline = self._lasso_points if len(self._lasso_points) > 2 else []
            self._lasso_points = []
            self.document_changed.emit()
            self.viewport().update()
            event.accept()
            return
        if dragged:
            self.refresh_local_preview()

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
            self.refresh_local_preview()
            self.document_changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _effective_action(self, modifiers):
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return "add" if self.brush_action == "remove" else "remove"
        return self.brush_action

    def mouseDoubleClickEvent(self, event):
        if self.contour_busy or self.edge_preview_active:
            event.accept()
            return
        if self.tool == "pen" and self.document is not None and event.button() == Qt.MouseButton.LeftButton:
            point = self._image_point(event.position().toPoint())
            if point:
                if self.contour.points:
                    if math.dist(point, self.contour.points[-1]) > 7 / self.transform().m11():
                        self.contour.add_point(point)
                    self.close_manual_contour()
                elif not (self.contour.manual and self.contour.hit(point, 7 / self.transform().m11())):
                    self._show_after_for_edit()
                    self.contour.insert(point, 8 / self.transform().m11())
                    self.refresh_local_preview()
                self.document_changed.emit()
                self.viewport().update()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def set_lasso_enabled(self, enabled):
        if self.contour_busy:
            return
        self.lasso_enabled = bool(enabled)
        self._lasso_points = []
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.setFocus()

    def _show_after_for_edit(self):
        if self.contour.local_active and not self.contour.preview_after:
            self.contour.preview_after = True
            self.refresh_image()
            self.document_changed.emit()

    def local_operation(self, operation):
        if self.contour_busy or self.document is None or self.contour.points:
            return
        result = self.contour.local_steps()[0 if operation == 'simplify' else 1]
        if not result.changed:
            return
        self.contour.checkpoint()
        if not self.contour.local_active:
            self.contour.local_before = (tuple(self.contour.paths), frozenset(self.contour.selection))
        self.contour.paths = list(result.paths)
        self.contour.select(result.selection)
        self.contour.preview_after = True
        self._lasso_outline = []
        self.refresh_local_preview()
        self.document_changed.emit()
        self.viewport().update()
        self.setFocus()

    def refresh_local_preview(self):
        self._preview_alpha = None
        self._preview_paths = None
        self.refresh_image()
        if self.contour.local_active and not self.contour.manual and not self.contour_busy:
            self._start_contour('local-preview')

    def show_local_preview(self, after):
        if self.contour_busy or not self.contour.local_active:
            return
        self.contour.preview_after = bool(after)
        self.refresh_image()
        self.document_changed.emit()
        self.viewport().update()

    def cancel_local_preview(self):
        if not self.contour.local_active:
            return
        self.cancel_contour()
        self.contour.checkpoint()
        paths, selection = self.contour.local_before
        self.contour.paths = list(paths)
        self.contour.select(selection)
        self.contour.local_before = None
        self.contour.preview_after = True
        self._preview_alpha = None
        self._preview_paths = None
        self._lasso_outline = []
        self.refresh_image()
        self.document_changed.emit()
        self.viewport().update()

    @property
    def contour_busy(self):
        return self._contour_job is not None

    def cancel_contour(self):
        if self._contour_job is not None:
            self._contour_job["cancelled"].set()
            self._contour_job["future"].cancel()
            self.status_changed.emit("Отмена…")

    def _start_contour(self, kind):
        if self.edge_preview_active:
            return
        if self.document is None or self.contour_busy or self._painting:
            return
        if (max(self.document.mask.size) > MAX_AUTO_CONTOUR_SIDE
                or self.document.mask.width * self.document.mask.height > MAX_CONTOUR_IMAGE_PIXELS):
            self.status_changed.emit("Контуры поддерживают изображения до 32 мегапикселей и 32768 px по стороне.")
            return
        cancelled = Event()
        paths = tuple(self.contour.paths)
        future = _CONTOUR_EXECUTOR.submit(
            _calculate_contour, kind, np.array(self.document.mask),
            tuple(self.contour.original), paths, cancelled,
        )
        self._contour_job = dict(future=future, cancelled=cancelled,
                                 document=self.document, mask_revision=self.document.mask_revision, contour=self.contour, kind=kind, paths=paths)
        self.status_changed.emit("Строим контур…" if kind == "extract" else "Применяем контур…")
        self.document_changed.emit()
        self._contour_timer.start()

    def _poll_contour(self):
        job = self._contour_job
        if job is None or not job["future"].done():
            return
        self._contour_timer.stop()
        self._contour_job = None
        success = False
        try:
            result = job["future"].result()
            if (job["cancelled"].is_set() or job["document"] is not self.document
                    or job["mask_revision"] != self.document.mask_revision):
                raise CancelledError()
            if job["kind"] == "extract":
                self.contour = InlineContour()
                self.document.pending_contour = self.contour
                self.contour.original = list(result)
                self.contour.paths = list(result)
                self.status_changed.emit("" if result else "Контур не найден.")
            elif job['kind'] == 'local-preview':
                if job['contour'] is not self.contour or job['paths'] != tuple(self.contour.paths) or not self.contour.local_active:
                    raise CancelledError()
                self._preview_alpha, _ = result
                self._preview_paths = job['paths']
                self._preview_mask_revision = self.document.mask_revision
                self.refresh_image()
                self.status_changed.emit('')
            else:
                self.document.begin_stroke()
                alpha, bounds = result
                self.document.mask = Image.fromarray(alpha)
                self.document.mask_revision += 1
                self.document.end_stroke()
                if job['kind'].startswith('manual-'):
                    self.contour = InlineContour()
                    self.document.pending_contour = self.contour
                else:
                    self.contour.original = list(job["paths"])
                    self.contour.undo_stack.clear()
                    self.contour.redo_stack.clear()
                    self.contour.local_before = None
                    self.contour.preview_after = True
                had_preview = self._preview_alpha is not None
                self._preview_alpha = None
                self._preview_paths = None
                if had_preview:
                    self.refresh_image()
                else:
                    # The worker supplies exact changed bounds. Rebuilding a
                    # 25 MP pixmap for a small edge edit stalls the UI needlessly.
                    self.refresh_region(bounds)
                self.status_changed.emit("")
            success = True
        except CancelledError:
            self.status_changed.emit("Расчёт отменён.")
        except Exception as error:
            # Worker failures must never escape a Qt timer or partially publish a mask.
            self.status_changed.emit(f"Контур не обработан: {error}")
        self.viewport().update()
        self.document_changed.emit()
        self.contour_finished.emit(job["kind"], success)

    def auto_contour(self):
        self.setFocus()
        if self.contour_busy:
            self.cancel_contour()
            return
        if self.contour.dirty:
            self.status_changed.emit("Примените текущий контур клавишей Enter перед повторным построением.")
            return
        self._start_contour("extract")

    def new_manual_contour(self):
        if self.document is None or self.contour_busy:
            return
        if self.contour.dirty:
            self.status_changed.emit('Примените текущий контур или нажмите Esc для отмены обводки.')
            return
        self.contour = InlineContour()
        self.document.pending_contour = self.contour
        self.setFocus()
        self.status_changed.emit('')
        self.document_changed.emit()
        self.viewport().update()

    def close_manual_contour(self):
        if self.document is None:
            return
        w, h = self.document.mask.size
        closed = self.contour.close_path((h, w))
        self.status_changed.emit(''
                                 if closed else 'Нужны минимум три точки, образующие область.')
        self.document_changed.emit()
        self.viewport().update()

    def apply_contour(self, keep_inside=False):
        self.setFocus()
        if self.contour_busy:
            self.cancel_contour()
            return
        if self.contour.points:
            self.status_changed.emit('Сначала замкните контур двойным кликом.')
            return
        if self.contour.dirty:
            kind = ('manual-keep' if keep_inside else 'manual-remove') if self.contour.manual else ('local-apply' if self.contour.local_active else 'apply')
            self._start_contour(kind)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._zoom_wheel_delta = 0
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta:
            if delta * self._zoom_wheel_delta < 0:
                self._zoom_wheel_delta = 0
            self._zoom_wheel_delta += delta
            while abs(self._zoom_wheel_delta) >= 120:
                step = 1 if self._zoom_wheel_delta > 0 else -1
                self._zoom_wheel_delta -= step * 120
                self.zoom_requested.emit(step)
        elif event.pixelDelta().y():
            self._zoom_wheel_delta = 0
            self.zoom_requested.emit(1 if event.pixelDelta().y() > 0 else -1)
        event.accept()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        key, mods = event.key(), event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if self.edge_preview_active and not (
                key == Qt.Key.Key_Space or ctrl and key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus)):
            if key == Qt.Key.Key_Escape or ctrl and key == Qt.Key.Key_Z:
                self.preview_cancel_requested.emit()
            event.accept()
            return
        if self.contour_busy and key == Qt.Key.Key_Escape:
            self.cancel_contour()
            event.accept()
            return
        if self.contour_busy and key not in (Qt.Key.Key_Space, Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
            event.accept()
            return
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
            step = -1 if key == Qt.Key.Key_Minus else 1
            if ctrl:
                self.zoom_requested.emit(step)
            elif self.tool == "brush":
                self.diameter_requested.emit(step)
            event.accept()
            return
        if not ctrl and event.text().lower() in ('b', 'и', 'p', 'з'):
            self.tool_requested.emit('brush' if event.text().lower() in ('b', 'и') else 'pen')
            event.accept()
            return
        if ctrl and key in (Qt.Key.Key_Z, Qt.Key.Key_Y):
            self.history_requested.emit(key == Qt.Key.Key_Y or bool(mods & Qt.KeyboardModifier.ShiftModifier))
            event.accept()
            return
        if self.tool == "pen":
            if key == Qt.Key.Key_Escape and self.contour.dirty:
                self.contour.checkpoint()
                self.contour.points = []
                self.contour.paths = list(self.contour.original)
                self.contour.selected = None
                self.contour.local_before = None
                self._preview_alpha = None
                self._preview_paths = None
                self.refresh_image()
                self.document_changed.emit()
                self.viewport().update()
                event.accept()
                return
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.apply_contour()
                event.accept()
                return
            if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self._show_after_for_edit()
                self.contour.delete()
                self.refresh_local_preview()
                self.document_changed.emit()
                self.viewport().update()
                event.accept()
                return
            offsets = {Qt.Key.Key_Left: (-1,0), Qt.Key.Key_Right: (1,0), Qt.Key.Key_Up: (0,-1), Qt.Key.Key_Down: (0,1)}
            if key in offsets and self.contour.selected:
                self._show_after_for_edit()
                pi, ni = self.contour.selected
                point = self.contour.paths[pi].nodes[ni].point
                dx, dy = offsets[key]
                step = 10 if mods & Qt.KeyboardModifier.ShiftModifier else 1
                self.contour.checkpoint()
                self.contour.move((pi,ni,'point'), (point[0]+dx*step, point[1]+dy*step))
                self.refresh_local_preview()
                self.document_changed.emit()
                self.viewport().update()
                event.accept()
                return
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

    def focusOutEvent(self, event):
        self.set_space_pan_active(False)
        self._panning = False
        self._contour_drag = None
        if self._painting:
            self._painting = False
            self._last_image_point = None
            if self.document is not None:
                self.document.end_stroke()
            self.refresh_local_preview()
            self.document_changed.emit()
        super().focusOutEvent(event)

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
        if self.tool == "pen":
            self.contour.sanitize_selection()
            primary_selected = self.contour._selected
            display_paths, display_selection = self.contour.paths, self.contour.selection
            if self.contour.local_active and not self.contour.preview_after:
                display_paths, display_selection = self.contour.local_before
            pen = QPen(QColor("#24d8c5"), 1.5)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r = 3.5 / self.transform().m11()
            if self.contour.points:
                curve = QPainterPath(QPointF(*self.contour.points[0]))
                for point in self.contour.points[1:]:
                    curve.lineTo(QPointF(*point))
                painter.drawPath(curve)
                for point in self.contour.points:
                    painter.drawEllipse(QPointF(*point), r, r)
            for pi, path in enumerate(display_paths):
                curve = QPainterPath(QPointF(*path.nodes[0].point))
                for ni, node in enumerate(path.nodes):
                    nxt = path.nodes[(ni+1) % len(path.nodes)]
                    curve.cubicTo(QPointF(*(node.out_handle or node.point)), QPointF(*(nxt.in_handle or nxt.point)), QPointF(*nxt.point))
                painter.drawPath(curve)
                for ni, node in enumerate(path.nodes):
                    selected = (pi,ni) in display_selection
                    node_pen = QPen(QColor('#fff2ff') if selected else QColor('#24d8c5'), 1.5)
                    node_pen.setCosmetic(True)
                    painter.setPen(node_pen)
                    painter.setBrush(QColor("#ff38bb") if selected else QColor("#10202e"))
                    painter.drawEllipse(QPointF(*node.point), r, r)
                    if selected and (pi,ni) == primary_selected:
                        for handle in (node.in_handle, node.out_handle):
                            if handle:
                                painter.drawLine(QPointF(*node.point), QPointF(*handle))
                                painter.drawEllipse(QPointF(*handle), r*.7, r*.7)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(pen)
            outline = self._lasso_points or self._lasso_outline
            if outline:
                lasso = QPainterPath(outline[0])
                for point in outline[1:]:
                    lasso.lineTo(point)
                lasso.closeSubpath()
                lasso_pen = QPen(QColor('#ff38bb'), 1.5, Qt.PenStyle.DashLine)
                lasso_pen.setCosmetic(True)
                painter.setPen(lasso_pen)
                painter.setBrush(QColor(255, 56, 187, 20))
                painter.drawPath(lasso)
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
    copy_saved = pyqtSignal(object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._paths: list[Path] = []
        self._rough_dir: Path | None = None
        self._save_dir: Path | None = None
        self._saved_copies: dict[Path, Path] = {}
        self._document: MaskEditDocument | None = None
        self._loaded_path: Path | None = None
        self._draft_masks: dict[Path, bytes] = {}
        self._draft_contours = {}
        self._save_after_contour = False
        self._focus_mode = False
        self._edge_preview: tuple[MaskEditDocument, int, Image.Image] | None = None
        self._edge_sharpen_check_key = None
        self._edge_sharpen_possible = False

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

        files_frame = self.files_frame = QFrame()
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
        tools_frame.setStyleSheet(
            "QPushButton {min-height: 28px; border: 1px solid #3b4b60; "
            "border-radius: 5px; background: #263548; color: #e4edf6;} "
            "QPushButton:checked {border-color: #28cbbb; background: #164741;} "
            "QPushButton:disabled {color: #74869a; background: #202b39;}"
        )
        tools_layout = QVBoxLayout(tools_frame)
        tools_layout.setContentsMargins(10, 8, 10, 8)
        tools_layout.setSpacing(6)

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
            button.setStyleSheet("font-size:11px;padding:4px 1px;")
            button.setToolTip("Масштаб изображения (Ctrl + / Ctrl −)")
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

        self.sharpen_edge_button = QPushButton('Сделать край чётче')
        self.sharpen_edge_button.clicked.connect(self.preview_sharper_edge)
        tools_layout.addWidget(self.sharpen_edge_button)
        self.edge_comparison = QWidget()
        edge_layout = QVBoxLayout(self.edge_comparison)
        edge_layout.setContentsMargins(0, 0, 0, 0)
        edge_layout.setSpacing(5)
        edge_views = QHBoxLayout()
        self.edge_before_button = QPushButton('До')
        self.edge_after_button = QPushButton('После')
        self.edge_comparison_group = QButtonGroup(self)
        for button, after in ((self.edge_before_button, False), (self.edge_after_button, True)):
            button.setCheckable(True)
            self.edge_comparison_group.addButton(button)
            button.clicked.connect(lambda checked=False, value=after: self.show_edge_preview(value))
            edge_views.addWidget(button)
        edge_layout.addLayout(edge_views)
        edge_actions = QHBoxLayout()
        self.cancel_edge_button = QPushButton('Отмена')
        self.apply_edge_button = QPushButton('Применить')
        self.apply_edge_button.setStyleSheet('QPushButton {border-color:#28cbbb;background:#164741;}')
        self.cancel_edge_button.clicked.connect(self.cancel_edge_preview)
        self.apply_edge_button.clicked.connect(self.apply_edge_preview)
        edge_actions.addWidget(self.cancel_edge_button)
        edge_actions.addWidget(self.apply_edge_button)
        edge_layout.addLayout(edge_actions)
        edge_note = QLabel('Проверьте тонкие детали перед применением')
        edge_note.setWordWrap(True)
        edge_note.setStyleSheet('font-size:11px;color:#93a4b8;')
        edge_layout.addWidget(edge_note)
        tools_layout.addWidget(self.edge_comparison)
        self.edge_comparison.hide()
        self.canvas.preview_cancel_requested.connect(self.cancel_edge_preview)

        tool_row = QHBoxLayout()
        self.tool_buttons = {}
        for key, label, shortcut in (("brush", "Кисть", "B / И"), ("pen", "Перо", "P / З")):
            button = QPushButton()
            button.setIcon(self._tool_icon(key))
            button.setIconSize(QSize(24, 24))
            button.setCheckable(True)
            button.setChecked(key == "brush")
            button.setAccessibleName(label)
            button.setToolTip(f"{label} ({shortcut})")
            button.clicked.connect(lambda checked=False, value=key: self._set_tool(value))
            self.tool_buttons[key] = button
            tool_row.addWidget(button)
        tools_layout.addLayout(tool_row)
        self.brush_controls = QWidget()
        brush_layout = QVBoxLayout(self.brush_controls)
        brush_layout.setContentsMargins(0, 0, 0, 0)
        brush_layout.setSpacing(6)
        action_row = QHBoxLayout()
        self.action_group = QButtonGroup(self)
        self.action_group.setExclusive(True)
        self.add_button = QPushButton("Вернуть")
        self.remove_button = QPushButton("Убрать")
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
        self.remove_button.setChecked(True)
        self.add_button.setToolTip("Вернуть область; Alt временно меняет действие кисти")
        self.remove_button.setToolTip("Убрать область; Alt временно возвращает область")
        brush_layout.addLayout(action_row)
        brush_layout.addWidget(self._small_label("Диаметр кисти, px"))
        diameter_row = QHBoxLayout()
        diameter_row.setSpacing(4)
        self.diameter_buttons = {}
        for diameter in BRUSH_DIAMETERS:
            button = QPushButton(str(diameter))
            button.setCheckable(True)
            button.setChecked(diameter == 16)
            button.setStyleSheet("padding: 4px 1px;")
            button.setToolTip(f"Диаметр {diameter} px (+ / −)")
            button.clicked.connect(lambda checked=False, value=diameter: self._set_diameter(value))
            diameter_row.addWidget(button)
            self.diameter_buttons[diameter] = button
        brush_layout.addLayout(diameter_row)
        self.hardness_slider, self.hardness_value = self._slider_row(
            brush_layout, "Жёсткость", 0, 100, 85, "%",
        )
        self.hardness_slider.valueChanged.connect(self._hardness_changed)
        tools_layout.addWidget(self.brush_controls)
        self.pen_controls = QWidget()
        pen_layout = QVBoxLayout(self.pen_controls)
        pen_layout.setContentsMargins(0, 0, 0, 0)
        self.new_contour_button = QPushButton('Обвести')
        self.new_contour_button.setToolTip('Начать ручную обводку с нуля. Текущую правку сначала примените или отмените клавишей Esc.')
        self.new_contour_button.clicked.connect(self.canvas.new_manual_contour)
        self.contour_button = QPushButton("Автоконтур")
        self.contour_button.setToolTip("Расставить точки по существующей прозрачности")
        self.contour_button.clicked.connect(self.canvas.auto_contour)
        contour_entry = QHBoxLayout()
        contour_entry.addWidget(self.new_contour_button)
        contour_entry.addWidget(self.contour_button)
        pen_layout.addLayout(contour_entry)

        self.local_contour_controls = QWidget()
        local_layout = QVBoxLayout(self.local_contour_controls)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(5)
        self.lasso_button = QPushButton('Лассо · Shift добавляет точки')
        self.lasso_button.setCheckable(True)
        self.lasso_button.setToolTip('Обведите точки произвольной линией. Shift добавляет точки к выделению; клик выбирает одну точку.')
        self.lasso_button.toggled.connect(self.canvas.set_lasso_enabled)
        local_layout.addWidget(self.lasso_button)
        self.local_selection_label = QLabel('Точки не выделены')
        self.local_selection_label.setWordWrap(True)
        self.local_selection_label.setStyleSheet('color:#93a4b8;font-size:12px;')
        local_layout.addWidget(self.local_selection_label)
        self.simplify_button = QPushButton('Упростить участок')
        self.smooth_button = QPushButton('Сгладить участок')
        self.simplify_button.clicked.connect(lambda: self.canvas.local_operation('simplify'))
        self.smooth_button.clicked.connect(lambda: self.canvas.local_operation('smooth'))
        local_layout.addWidget(self.simplify_button)
        local_layout.addWidget(self.smooth_button)
        self.local_comparison = QWidget()
        comparison_layout = QHBoxLayout(self.local_comparison)
        comparison_layout.setContentsMargins(0, 0, 0, 0)
        comparison_layout.setSpacing(5)
        self.before_button = QPushButton('До')
        self.after_button = QPushButton('После')
        self.local_comparison_group = QButtonGroup(self)
        for button, after in ((self.before_button, False), (self.after_button, True)):
            button.setCheckable(True)
            self.local_comparison_group.addButton(button)
            button.clicked.connect(lambda checked=False, value=after: self.canvas.show_local_preview(value))
            comparison_layout.addWidget(button)
        local_layout.addWidget(self.local_comparison)
        self.cancel_local_button = QPushButton('Отменить обработку участка')
        self.cancel_local_button.clicked.connect(self.canvas.cancel_local_preview)
        local_layout.addWidget(self.cancel_local_button)
        pen_layout.addWidget(self.local_contour_controls)
        self.apply_contour_button = QToolButton()
        self.apply_contour_button.setText("Применить контур")
        self.apply_contour_button.setToolTip("Применить контур (Enter)")
        self.apply_contour_button.clicked.connect(self.canvas.apply_contour)
        self.keep_contour_button = QToolButton()
        self.keep_contour_button.setText('Оставить внутри')
        self.keep_contour_button.clicked.connect(lambda: self.canvas.apply_contour(keep_inside=True))
        contour_actions = QHBoxLayout()
        for button, keep in ((self.apply_contour_button, False), (self.keep_contour_button, True)):
            button.setIcon(self._contour_action_icon(keep))
            button.setIconSize(QSize(38, 38))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setMinimumHeight(72)
            button.setAccessibleName('Оставить внутри контура' if keep else 'Удалить внутри контура')
            button.setToolTip('Оставить только область внутри обводки' if keep else 'Удалить область внутри обводки (Enter)')
            contour_actions.addWidget(button, 1)
        pen_layout.addLayout(contour_actions)
        tools_layout.addWidget(self.pen_controls)
        self.pen_controls.hide()
        self.contour_status = QLabel()
        self.contour_status.setWordWrap(True)
        self.contour_status.hide()
        tools_layout.addWidget(self.contour_status)
        self.canvas.status_changed.connect(self._show_contour_status)
        self.canvas.contour_finished.connect(self._contour_done)

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
            button.setStyleSheet(f"QPushButton {{background: {color}; border: 2px solid #526174;}} QPushButton:checked {{border: 3px solid #24d8c5;}}")
            if label == "Шахматный":
                tile = QPixmap(20,20)
                tile.fill(QColor("#eef1f4"))
                painter = QPainter(tile)
                painter.fillRect(0,0,10,10,QColor("#c8ced4"))
                painter.fillRect(10,10,10,10,QColor("#c8ced4"))
                painter.end()
                button.setIcon(QIcon(tile))
                button.setIconSize(QSize(20,20))
            button.clicked.connect(
                lambda checked=False, value=label: self._set_background(value)
            )
            self.background_group.addButton(button)
            self.background_buttons[label] = button
            background_row.addWidget(button)
        self.background_buttons["Шахматный"].setChecked(True)
        tools_layout.addLayout(background_row)

        tools_layout.addStretch()
        save_row = QHBoxLayout()
        self.save_button = V3Button("Сохранить PNG", ButtonVariant.PRIMARY)
        self.back_button = V3Button("К результатам", ButtonVariant.SECONDARY)
        for button in (self.save_button, self.back_button):
            button.setStyleSheet("padding-left: 8px; padding-right: 8px;")
        self.save_button.setStyleSheet("QPushButton {background:#26cbb9;color:#062c2a;font-weight:600;padding:4px 8px;} QPushButton:disabled {background:#202b39;color:#74869a;}")
        self.save_button.clicked.connect(self._save_clicked)
        self.back_button.clicked.connect(self._back_clicked)
        save_row.addWidget(self.save_button)
        save_row.addWidget(self.back_button)
        tools_layout.addLayout(save_row)
        self.tools_scroll = QScrollArea()
        self.tools_scroll.setWidgetResizable(True)
        self.tools_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tools_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tools_scroll.setWidget(tools_frame)
        right.addWidget(self.tools_scroll, 3)

        self.canvas.document_changed.connect(self._refresh_history_buttons)
        self.canvas.tool_requested.connect(self._set_tool)
        self.canvas.diameter_requested.connect(self._cycle_diameter)
        self.canvas.zoom_requested.connect(self._cycle_zoom)
        self.canvas.history_requested.connect(lambda redo: self.redo() if redo else self.undo())
        self.undo_button.setToolTip("Отменить (Ctrl+Z)")
        self.redo_button.setToolTip("Повторить (Ctrl+Shift+Z)")
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
        self._draft_contours[self._loaded_path] = self.canvas.contour
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
        save_dir: str | Path | None = None,
        saved_copies: dict[str, str] | None = None,
    ) -> None:
        self.cancel_edge_preview()
        self._stash_current_document()
        self._paths = [Path(path) for path in paths]
        self._rough_dir = Path(rough_dir) if rough_dir is not None else None
        self._save_dir = Path(save_dir) if save_dir is not None else None
        self.back_button.setText("К файлам" if self._save_dir is not None else "К результатам")
        self._saved_copies = {}
        invalid_copy = False
        if self._save_dir is not None:
            for source, destination in (saved_copies or {}).items():
                copy = Path(destination)
                if (Path(source) in self._paths and copy.suffix.lower() == ".png"
                        and not copy.is_symlink() and copy.is_file()
                        and copy.parent.resolve() == self._save_dir.resolve()):
                    try:
                        with Image.open(copy) as image:
                            _validate_editor_image_size(image.size)
                            if image.format != "PNG":
                                raise ValueError("Expected PNG copy")
                            image.verify()
                    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                        invalid_copy = True
                        continue
                    self._saved_copies[Path(source)] = copy
        allowed = set(self._paths)
        self._draft_contours = {p: c for p, c in self._draft_contours.items() if p in allowed}
        self._draft_masks = {
            path: data for path, data in self._draft_masks.items() if path in allowed
        }
        self._document = None
        self._loaded_path = None
        self.file_list.blockSignals(True)
        self.file_list.clear()
        for path in self._paths:
            self.file_list.addItem(QListWidgetItem(path.name))
        self.file_list.blockSignals(False)
        if self._paths:
            self.file_list.setCurrentRow(
                min(max(0, selected_index), len(self._paths) - 1)
            )
        else:
            self.canvas.set_document(None)
        self._refresh_history_buttons()
        if invalid_copy:
            self._show_contour_status("Сохранённая копия не читается. Открыт исходный PNG; копия сохранена на диске.")

    def refresh_from_state(self) -> None:
        """Keep the shared page-controller refresh contract."""
        self._refresh_history_buttons()

    def _select_file(self, row: int) -> None:
        self.cancel_edge_preview()
        self._stash_current_document()
        self._document = None
        self._loaded_path = None
        if not 0 <= row < len(self._paths):
            self.canvas.set_document(None)
            self._refresh_history_buttons()
            return
        path = self._paths[row]
        copy_failed = False
        try:
            rough_dir = self._rough_dir or path.parent.parent / "rough"
            mask_path = rough_dir / f"{path.stem}_alpha-mask.png"
            if self._save_dir is None:
                MaskEditDocument.recover_pair(path, mask_path)
            def load_document(candidate: Path) -> MaskEditDocument:
                with Image.open(candidate) as image:
                    _validate_editor_image_size(image.size)
                    return MaskEditDocument(image.copy())

            copy = self._saved_copies.get(path)
            if copy is not None:
                try:
                    document = load_document(copy)
                except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
                    self._saved_copies.pop(path, None)
                    document = load_document(path)
                    copy_failed = True
            else:
                document = load_document(path)
            draft = self._draft_masks.get(path)
            if draft is not None:
                with Image.open(BytesIO(draft)) as mask:
                    document.mask = mask.convert("L").copy()
        except EditorImageTooLargeError as error:
            self.canvas.set_document(None)
            QMessageBox.warning(
                self,
                "Изображение не открыто",
                str(error),
            )
            self._refresh_history_buttons()
            return
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            self.canvas.set_document(None)
            self._refresh_history_buttons()
            return
        self._document = document
        self._loaded_path = path
        item = self.file_list.item(row)
        if item is not None and item.icon().isNull():
            width, height = document.image.size
            scale = min(28 / width, 28 / height)
            thumbnail = document.image.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
            item.setIcon(QIcon(_pixmap_for_pil(thumbnail)))
        document.pending_contour = self._draft_contours.get(path, InlineContour())
        self.canvas.set_document(document)
        if copy_failed:
            self._show_contour_status("Сохранённая копия не читается. Открыт исходный PNG; копия сохранена на диске.")
        self.canvas.setFocus(Qt.FocusReason.OtherFocusReason)
        self._refresh_history_buttons()

    def _set_zoom(self, value: str | int) -> None:
        for key, button in self.zoom_buttons.items():
            button.setChecked(key == value)
        self.canvas.set_zoom(None if value == "fit" else int(value))

    def _set_action(self, action: str) -> None:
        self.canvas.brush_action = action
        self.canvas.setFocus()

    @staticmethod
    def _contour_action_icon(keep):
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        for y in range(4, 36, 4):
            for x in range(4, 36, 4):
                inside = 12 <= x < 28 and 12 <= y < 28
                color = '#20c9b7' if inside == keep else ('#d5dde4' if (x+y)//4 % 2 else '#738395')
                painter.fillRect(x, y, 4, 4, QColor(color))
        painter.setPen(QPen(QColor('#ffffff'), 1))
        painter.drawRect(12, 12, 16, 16)
        painter.end()
        return QIcon(pixmap)

    @staticmethod
    def _tool_icon(tool):
        pixmap = QPixmap(28,28)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#e4edf6"), 1.5))
        painter.setBrush(QColor("#e4edf6"))
        path = QPainterPath()
        if tool == "pen":
            path.moveTo(4,24); path.lineTo(8,9); path.lineTo(17,3)
            path.lineTo(25,11); path.lineTo(19,20); path.closeSubpath()
            painter.drawPath(path)
            painter.setPen(QPen(QColor("#152435"),1.5))
            painter.drawLine(4,24,14,14)
            painter.setBrush(QColor("#152435")); painter.drawEllipse(12,11,4,4)
        else:
            path.moveTo(11,17); path.lineTo(21,3); path.quadTo(25,1,25,6)
            path.lineTo(16,21); path.closeSubpath(); painter.drawPath(path)
            path = QPainterPath(); path.moveTo(10,17); path.cubicTo(3,18,9,23,3,25)
            path.cubicTo(15,28,19,21,10,17); painter.drawPath(path)
        painter.end()
        return QIcon(pixmap)

    def _show_contour_status(self, message):
        self.contour_status.setText(message)
        self.contour_status.setVisible(bool(message))

    def _set_tool(self, tool):
        if self.canvas._painting or self.canvas.contour_busy:
            return
        self.canvas.tool = tool
        self.canvas.setToolTip(
            "Новый контур: клики, двойной клик замыкает; добавить точку на линии: двойной клик; удалить: Delete; "
            "плавная/угловая: Alt+клик; сдвиг: стрелки, Shift ×10; применить: Enter"
            if tool == "pen" else "Кисть: + / −; временно вернуть/убрать: Alt; "
            "масштаб: Ctrl + / Ctrl −; перемещение: Пробел + мышь"
        )
        for key, button in self.tool_buttons.items():
            button.setChecked(key == tool)
        self.brush_controls.setVisible(tool == "brush")
        self.pen_controls.setVisible(tool == "pen")
        self.canvas.viewport().update()
        self.canvas.setFocus()
        self._refresh_history_buttons()

    def _set_diameter(self, diameter):
        self.canvas.brush_radius = diameter // 2
        for value, button in self.diameter_buttons.items():
            button.setChecked(value == diameter)
        self.canvas.viewport().update()
        self.canvas.setFocus()

    def _cycle_diameter(self, step):
        index = BRUSH_DIAMETERS.index(self.canvas.brush_radius * 2)
        self._set_diameter(BRUSH_DIAMETERS[max(0, min(len(BRUSH_DIAMETERS)-1, index+step))])

    def _cycle_zoom(self, step):
        current = self.canvas.transform().m11() * 100
        self._set_zoom(max(10, min(1600, round(current * (1.25 if step > 0 else .8)))))

    def _hardness_changed(self, value: int) -> None:
        self.hardness_value.setText(f"{value}%")
        self.canvas.brush_hardness = value

    def _set_background(self, label: str) -> None:
        self.canvas.set_background(label)

    def preview_sharper_edge(self) -> None:
        """Offer one deliberate contrast step; never alter RGB or auto-apply it."""
        canvas = self.canvas
        if (self._edge_preview is not None or canvas.contour_busy or canvas.contour.dirty or canvas.contour.local_active
                or canvas.contour.points or canvas._painting or canvas.document is None):
            return
        document = self.document
        proposal = document.mask.point(_EDGE_SHARPEN_LUT)
        if ImageChops.difference(document.mask, proposal).getbbox() is None:
            self._refresh_history_buttons()
            return
        self._edge_preview = (document, document.mask_revision, proposal)
        canvas.edge_preview_active = True
        self.show_edge_preview(True)
        self._refresh_history_buttons()

    def show_edge_preview(self, after: bool) -> None:
        if self._edge_preview is None:
            return
        self.canvas.edge_preview_mask = self._edge_preview[2] if after else None
        self.edge_before_button.setChecked(not after)
        self.edge_after_button.setChecked(after)
        self.canvas.refresh_image()

    def cancel_edge_preview(self) -> None:
        if self._edge_preview is None:
            return
        self._edge_preview = None
        self.canvas.edge_preview_active = False
        self.canvas.edge_preview_mask = None
        self.canvas.refresh_image()
        self._refresh_history_buttons()

    def apply_edge_preview(self) -> None:
        if self._edge_preview is None:
            return
        document, revision, proposal = self._edge_preview
        if (document is not self._document or document is not self.canvas.document
                or document.mask_revision != revision or self.canvas.contour_busy
                or self.canvas.contour.dirty or self.canvas._painting):
            self.cancel_edge_preview()
            self._show_contour_status('Изображение изменилось. Повторите предпросмотр края.')
            return
        try:
            document.apply_mask_proposal(proposal)
        except ValueError as error:
            self.cancel_edge_preview()
            self._show_contour_status(str(error))
            return
        self._edge_preview = None
        self.canvas.edge_preview_active = False
        self.canvas.edge_preview_mask = None
        document.pending_contour = InlineContour()
        self.canvas.set_document(document)
        if self.current_path is not None:
            self._draft_contours[self.current_path] = self.canvas.contour
        self._refresh_history_buttons()

    def undo(self) -> None:
        if self._edge_preview is not None:
            self.cancel_edge_preview()
            return
        if self.canvas.contour_busy:
            return
        if self.canvas.tool == "pen" and self.canvas.contour.history(redo=False):
            self.canvas.refresh_local_preview()
            self.canvas.viewport().update()
            self._refresh_history_buttons()
            return
        try:
            self.document.undo()
            if not self.canvas.contour.dirty:
                self.canvas.contour = InlineContour()
                self.document.pending_contour = self.canvas.contour
        except ValueError:
            return
        self.canvas.refresh_local_preview()
        if self.current_path is not None:
            self._draft_contours[self.current_path] = self.canvas.contour
        self._refresh_history_buttons()

    def redo(self) -> None:
        if self._edge_preview is not None:
            return
        if self.canvas.contour_busy:
            return
        if self.canvas.tool == "pen" and self.canvas.contour.history(redo=True):
            self.canvas.refresh_local_preview()
            self.canvas.viewport().update()
            self._refresh_history_buttons()
            return
        try:
            self.document.redo()
            if not self.canvas.contour.dirty:
                self.canvas.contour = InlineContour()
                self.document.pending_contour = self.canvas.contour
        except ValueError:
            return
        self.canvas.refresh_local_preview()
        if self.current_path is not None:
            self._draft_contours[self.current_path] = self.canvas.contour
        self._refresh_history_buttons()

    def reset(self) -> None:
        if self._edge_preview is not None:
            return
        if self.canvas.contour_busy:
            return
        try:
            self.document.reset()
            self.canvas.contour = InlineContour()
            self.document.pending_contour = self.canvas.contour
        except ValueError:
            return
        self.canvas.refresh_local_preview()
        if self.current_path is not None:
            self._draft_contours[self.current_path] = self.canvas.contour
        self._refresh_history_buttons()

    def _refresh_local_buttons(self):
        contour = self.canvas.contour
        count = len(contour.selection)
        active = contour.local_active
        busy = self.canvas.contour_busy
        valid = self.canvas.document is not None and bool(contour.paths) and not contour.points
        self.lasso_button.setEnabled(valid and not busy)
        self.local_comparison.setVisible(active)
        self.cancel_local_button.setVisible(active)
        self.cancel_local_button.setEnabled(active)
        self.before_button.setChecked(not contour.preview_after)
        self.after_button.setChecked(contour.preview_after)
        self.local_comparison.setEnabled(not busy)
        simplify, smooth = contour.local_steps()
        for button, result, text in ((self.simplify_button, simplify, 'Упростить участок'),
                                     (self.smooth_button, smooth, 'Сгладить участок')):
            button.setEnabled(valid and not busy and result.changed)
            button.setToolTip('Небольшой шаг. Повторите клик при необходимости.' if result.changed
                              else ('Точки не выделены' if not count else 'Достигнут предел для выделенного участка. Измените выделение или точки.'))
        if not count:
            label = 'Точки не выделены'
        elif active:
            label = f'Предпросмотр: {len(contour.local_before[1])} → {count} точек'
        else:
            label = f'Выделено точек: {count}'
        if count and not simplify.changed and not smooth.changed:
            label += ' · Достигнут предел'
        self.local_selection_label.setText(label)

    def _refresh_history_buttons(self) -> None:
        edge_active = self._edge_preview is not None
        document = self.canvas.document
        key = (document, document.mask_revision, document.mask) if document is not None else None
        if key != self._edge_sharpen_check_key:
            self._edge_sharpen_check_key = key
            self._edge_sharpen_possible = bool(document is not None and any(
                count and _EDGE_SHARPEN_LUT[value] != value
                for value, count in enumerate(document.mask.histogram())))
        self.sharpen_edge_button.setEnabled(
            self._edge_sharpen_possible and not edge_active and not self.canvas.contour_busy
            and not self.canvas.contour.dirty and not self.canvas.contour.local_active and not self.canvas.contour.points)
        self.sharpen_edge_button.setToolTip(
            'Предпросмотр одного шага без изменения цвета. Тонкие детали могут ослабнуть.'
            if self._edge_sharpen_possible else 'Следующий шаг не изменит край или изображение не выбрано')
        self.edge_comparison.setVisible(edge_active)
        self.pen_controls.setEnabled(not edge_active)
        self.canvas.contour.sanitize_selection()
        self._refresh_local_buttons()
        busy = self.canvas.contour_busy
        self.file_list.setEnabled(not busy)
        self.back_button.setEnabled(not busy)
        self.reset_button.setEnabled(not busy and self.canvas.document is not None)
        self.contour_button.setText("Автоконтур")
        self.apply_contour_button.setText("Применить контур")
        manual = self.canvas.contour.manual
        self.keep_contour_button.setVisible(manual)
        self.new_contour_button.setEnabled(not busy and self.canvas.document is not None)
        self.keep_contour_button.setEnabled(not busy and bool(self.canvas.contour.paths))
        if edge_active:
            for button in (self.undo_button, self.redo_button, self.reset_button, self.save_button,
                           self.contour_button, self.apply_contour_button, *self.tool_buttons.values()):
                button.setEnabled(False)
            self.brush_controls.setEnabled(False)
            return
        if manual:
            self.apply_contour_button.setText('Удалить внутри')
        self.apply_contour_button.setIcon(self._contour_action_icon(False) if manual else QIcon())
        self.apply_contour_button.setMinimumHeight(72 if manual else 30)
        if busy:
            for button in (self.undo_button, self.redo_button, self.save_button,
                           self.contour_button, self.apply_contour_button, *self.tool_buttons.values()):
                button.setEnabled(False)
            self.brush_controls.setEnabled(False)
            active = self.contour_button if self.canvas._contour_job["kind"] == "extract" else self.apply_contour_button
            active.setText("Отменить")
            active.setEnabled(True)
            active.setToolTip("Отменить расчёт (Esc)")
            return
        self.contour_button.setToolTip("Расставить точки по существующей прозрачности")
        self.apply_contour_button.setToolTip("Удалить область внутри обводки (Enter)" if manual else "Применить контур (Enter)")
        try:
            document = self.document
        except ValueError:
            self.undo_button.setEnabled(False)
            self.redo_button.setEnabled(False)
            self.save_button.setEnabled(False)
            self.contour_button.setEnabled(False)
            self.apply_contour_button.setEnabled(False)
            self.brush_controls.setEnabled(False)
            for button in self.tool_buttons.values():
                button.setEnabled(False)
            return
        contour = self.canvas.contour
        self.apply_contour_button.setEnabled(contour.dirty and not contour.points)
        self.undo_button.setEnabled(document.can_undo or bool(contour.undo_stack))
        self.redo_button.setEnabled(document.can_redo or bool(contour.redo_stack))
        self.save_button.setEnabled(not contour.local_active)
        self.contour_button.setEnabled(True)
        self.brush_controls.setEnabled(True)
        for button in self.tool_buttons.values():
            button.setEnabled(True)

    def _contour_done(self, kind, success):
        save = self._save_after_contour
        self._save_after_contour = False
        if save and success and (kind in ("apply", "local-apply") or kind.startswith('manual-')):
            self._save_clicked()

    def save_current(self) -> tuple[Path, Path]:
        if self._edge_preview is not None:
            raise ValueError('Сначала примените или отмените предпросмотр края')
        if self.canvas.contour_busy and self.canvas._contour_job['kind'] in ('apply', 'local-apply', 'manual-remove', 'manual-keep'):
            job = self.canvas._contour_job
            if job['future'].done():
                self.canvas._poll_contour()
            else:
                loop = QEventLoop(self)
                self.canvas.contour_finished.connect(loop.quit)
                try:
                    loop.exec()
                finally:
                    self.canvas.contour_finished.disconnect(loop.quit)
        if self.canvas.contour_busy or self.canvas.contour.dirty:
            raise ValueError("Дождитесь применения контура перед сохранением")
        output_path = self.current_path
        if output_path is None:
            raise ValueError("Нет изображения для сохранения")
        source_path = output_path
        if self._save_dir is not None:
            output_path, mask_path = self._save_new_copy(source_path)
            self._saved_copies[source_path] = output_path
            self._draft_masks.pop(source_path, None)
            self.copy_saved.emit(source_path, output_path)
            self.saved.emit(output_path.name)
            return output_path, mask_path
        rough_dir = self._rough_dir or output_path.parent.parent / "rough"
        mask_path = rough_dir / f"{output_path.stem}_alpha-mask.png"
        self.document.save(output_path, mask_path)
        self._draft_masks.pop(output_path, None)
        self.copy_saved.emit(output_path, output_path)
        self.saved.emit(output_path.name)
        return output_path, mask_path

    def _save_new_copy(self, source_path: Path) -> tuple[Path, Path]:
        from output_naming import _truncate_filename_stem
        from chroma_generation_record import record_path

        self._save_dir.mkdir(parents=True, exist_ok=True)
        rough = self._rough_dir or self._save_dir.parent / "rough"
        rough.mkdir(parents=True, exist_ok=True)
        for index in range(1, 10_001):
            suffix = "_edited.png" if index == 1 else f"_edited_{index}.png"
            # Leave room for alpha-mask names, generation sidecars and their
            # transaction backups on both Windows and UTF-8 filesystems.
            stem = _truncate_filename_stem(source_path.stem, 180, 180)
            destination = self._save_dir / f"{stem}{suffix}"
            mask = rough / f"{destination.stem}_alpha-mask.png"
            marker, backups = MaskEditDocument._pair_transaction_paths(destination, mask)
            if any(p.exists() or p.is_symlink() for p in (destination, mask, marker, *backups, record_path(destination))):
                continue
            reserved = []
            try:
                for path in (destination, mask):
                    with path.open("xb"):
                        pass
                    reserved.append(path)
            except FileExistsError:
                for path in reserved:
                    path.unlink(missing_ok=True)
                continue
            except OSError:
                for path in reserved:
                    path.unlink(missing_ok=True)
                raise
            try:
                self.document.save(destination, mask, copy_source=source_path)
            except Exception:
                for path in reserved:
                    path.unlink(missing_ok=True)
                raise
            return destination, mask
        raise ValueError("Не удалось выбрать свободное имя для копии PNG")

    def _save_clicked(self) -> None:
        if self._edge_preview is not None:
            self._show_contour_status('Сначала примените или отмените предпросмотр края.')
            return
        if self.canvas.contour_busy:
            return
        if self.canvas.contour.local_active:
            self._show_contour_status('Сначала примените контур или отмените обработку участка.')
            return
        if self.canvas.contour.manual and self.canvas.contour.dirty:
            self._show_contour_status('Сначала выберите «Удалить внутри» или «Оставить внутри».')
            return
        if self.canvas.contour.dirty:
            self._save_after_contour = True
            self.canvas.apply_contour()
            if not self.canvas.contour_busy:
                self._save_after_contour = False
            return
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
        return current_dirty or bool(self._draft_masks) or self.canvas.contour.dirty or any(c.dirty for c in self._draft_contours.values())

    def _back_clicked(self) -> None:
        self.cancel_edge_preview()
        if self.canvas.contour_busy:
            self.canvas.cancel_contour()
            return
        if self._has_unsaved_changes():
            answer = QMessageBox.warning(
                self,
                "Есть несохранённые изменения",
                ("Вернуться к файлам и отменить изменения маски?" if self._save_dir is not None
                 else "Вернуться к результатам и отменить изменения маски?"),
                QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Discard:
                return
            self._draft_masks.clear()
            self._draft_contours.clear()
            self._document = None
            self._loaded_path = None
        self.back_requested.emit()

    def hideEvent(self, event):
        self.cancel_edge_preview()
        self._save_after_contour = False
        self.canvas.cancel_contour()
        super().hideEvent(event)

    def closeEvent(self, event):
        self.cancel_edge_preview()
        self._save_after_contour = False
        self.canvas.cancel_contour()
        super().closeEvent(event)

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
        if self._edge_preview is not None and event.key() == Qt.Key.Key_Escape:
            self.cancel_edge_preview()
            event.accept()
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            key = event.key()
            if key in (Qt.Key.Key_Z, Qt.Key.Key_Y):
                if key == Qt.Key.Key_Y or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.redo()
                else:
                    self.undo()
                event.accept()
                return
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus):
                self._cycle_zoom(-1 if key == Qt.Key.Key_Minus else 1)
                event.accept()
                return
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
