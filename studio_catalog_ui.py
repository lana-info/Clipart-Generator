"""Catalog cards emit intent only; no module code or paid operation runs here."""
from pathlib import Path
import sys

from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QBuffer, QIODevice
from PyQt6.QtGui import QImageReader, QPixmap

from studio_catalog import CatalogEntry, ModuleAvailability, card_action
from v3_components import ModeCard, DEFAULT_TOKENS, ButtonVariant


def style_module_action(button, attention: bool, *, tokens=DEFAULT_TOKENS) -> None:
    """Keep ordinary actions dark; outline only actionable delivery intent."""
    button.set_variant(ButtonVariant.SECONDARY)
    button.setProperty("moduleActionRequired", attention)
    button.setStyleSheet(
        f"QPushButton {{color:{tokens.accent};background:{tokens.surface};"
        f"border:1px solid {tokens.accent};}}"
        f"QPushButton:hover {{background:{tokens.accent_soft};}}"
        f"QPushButton:focus {{border:{tokens.focus_width}px solid {tokens.focus};}}"
        f"QPushButton:disabled {{color:{tokens.disabled};background:{tokens.disabled_soft};"
        f"border:1px solid {tokens.border};}}"
        if attention else ""
    )


BUILTIN_CATALOG = (
    CatalogEntry("clipart", "Генерация изображений", "Изображения и серии по промптам", "generation", released=True),
    CatalogEntry("auto-clipart", "Clipart", "Автоматические наборы клипартов", "clipart", released=True),
    CatalogEntry("processing", "Обработка изображений", "Фон, качество и прозрачность", "processing", released=True),
    CatalogEntry("pinterest", "Pinterest", "Пины по промптам, без публикации", "pinterest", released=True),
    CatalogEntry("prompt-composer", "Конструктор промптов", "7 вариантов: изображения и Reels", "prompt-composer", released=True),
)


def catalog_artwork(key: str) -> Path:
    # Keys, not arbitrary file paths/URLs, cross the catalog presentation boundary.
    filenames = {
        "clipart": "mode-clipart.png",
        "patterns": "studio-patterns-cover.png",
        "mockups": "studio-mockups-cover.png",
        "pinterest": "mode-pinterest.png",
        "processing": "mode-processing.png",
        "generation": "studio-generation-cover.png",
        "prompt-composer": "studio-prompt-composer-cover.png",
    }
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / "assets" / filenames.get(key, "vibix-images.svg")


class StudioCatalogCard(ModeCard):
    action_requested = pyqtSignal(str, str)

    def __init__(self, entry: CatalogEntry, availability: ModuleAvailability,
                 *, tokens=DEFAULT_TOKENS, preview_png=None):
        illustration = None
        if preview_png is not None:
            from studio_upcoming import preview_bytes
            raw = preview_bytes(preview_png)
            buffer = QBuffer()
            buffer.setData(QByteArray(raw))
            buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            reader = QImageReader(buffer, b'png')
            size = reader.size()
            if not (1 <= size.width() <= 512 and 1 <= size.height() <= 512):
                raise ValueError('Invalid preview dimensions')
            image = reader.read()
            if image.isNull():
                raise ValueError('Invalid preview image')
            illustration = QPixmap.fromImage(image)
        super().__init__(entry.module_id, entry.title, entry.description, "",
                         tokens=tokens, illustration_path=None if illustration is not None else catalog_artwork(entry.artwork_key),
                         illustration_image=illustration,
                         compact=True)
        self.entry = entry
        self.tokens = tokens
        self.availability = availability
        self.title_label.setTextFormat(Qt.TextFormat.PlainText)
        self.description_label.setTextFormat(Qt.TextFormat.PlainText)
        self.selected.connect(self._request_action)
        self.set_availability(availability)

    def set_availability(self, availability: ModuleAvailability) -> None:
        self.availability = availability
        action = card_action(self.entry, availability)
        self.start_button.setText(action.label)
        self.start_button.setEnabled(action.enabled)
        style_module_action(self.start_button,
                            action.enabled and action.action in {"download", "update"},
                            tokens=self.tokens)
        self.start_button.setToolTip(action.reason)
        self.start_button.setAccessibleName(f"{action.label}: {self.entry.title}")
        self.setAccessibleDescription(f"{self.entry.description}. {action.reason}")

    def _request_action(self, _module_id: str) -> None:
        action = card_action(self.entry, self.availability)
        if action.enabled:
            self.action_requested.emit(self.entry.module_id, action.action)
