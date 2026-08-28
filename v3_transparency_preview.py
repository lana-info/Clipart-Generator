from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from background_preview import PREVIEW_BACKGROUND_OPTIONS, composite_on_preview


class ClipartTransparencyPreview(QWidget):
    """Inspection-only preview for a Clipart image with transparency."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: Image.Image | None = None
        self.background_combo = QComboBox()
        for label, value in PREVIEW_BACKGROUND_OPTIONS:
            self.background_combo.addItem(label, value)
        self.background_combo.setAccessibleName("Фон предпросмотра прозрачности")
        self.background_combo.currentIndexChanged.connect(self.refresh_preview)

        self.preview = QLabel("Выберите результат для проверки прозрачности")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumSize(360, 260)
        self.preview.setWordWrap(True)
        self.preview.setAccessibleName("Предпросмотр прозрачного клипарта")

        form = QFormLayout()
        form.addRow("Фон проверки", self.background_combo)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.preview, 1)
        self.setAccessibleName("Проверка прозрачности клипарта")

    def set_image(self, image: Image.Image | None) -> None:
        self._image = image.convert("RGBA") if image is not None else None
        self.refresh_preview()

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
            return
        label = str(self.background_combo.currentText())
        rendered = composite_on_preview(self._image, label)
        buffer = BytesIO()
        rendered.save(buffer, format="PNG")
        image = QImage.fromData(buffer.getvalue(), "PNG")
        pixmap = QPixmap.fromImage(image)
        self.preview.setPixmap(
            pixmap.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview.setText("")
