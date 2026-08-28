from __future__ import annotations

from io import BytesIO
import os
import tempfile
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from background_mask import (
    apply_mask_stroke,
    apply_mask_to_image,
    mask_for_image,
    save_mask_png,
)
from background_preview import PREVIEW_BACKGROUND_OPTIONS, composite_on_preview


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
        self.radius_spin.setRange(1, 500)
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
