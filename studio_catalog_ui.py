"""Catalog cards emit intent only; no module code or paid operation runs here."""
from pathlib import Path
import sys

from PyQt6.QtCore import Qt, pyqtSignal

from studio_catalog import CatalogEntry, ModuleAvailability, card_action
from v3_components import ModeCard, DEFAULT_TOKENS


BUILTIN_CATALOG = (
    CatalogEntry("clipart", "Clipart", "Автоматические наборы клипартов", "clipart"),
    CatalogEntry("patterns", "Patterns", "Паттерны, повторения и плитки", "patterns"),
    CatalogEntry("mockups", "Mockups", "Ваши иллюстрации на товарах", "mockups"),
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
    }
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / "assets" / filenames.get(key, "vibix-images.svg")


class StudioCatalogCard(ModeCard):
    action_requested = pyqtSignal(str, str)

    def __init__(self, entry: CatalogEntry, availability: ModuleAvailability,
                 *, tokens=DEFAULT_TOKENS):
        super().__init__(entry.module_id, entry.title, entry.description, "",
                         tokens=tokens, illustration_path=catalog_artwork(entry.artwork_key),
                         compact=True)
        self.entry = entry
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
        self.start_button.setToolTip(action.reason)
        self.start_button.setAccessibleName(f"{action.label}: {self.entry.title}")
        self.setAccessibleDescription(f"{self.entry.description}. {action.reason}")

    def _request_action(self, _module_id: str) -> None:
        action = card_action(self.entry, self.availability)
        if action.enabled:
            self.action_requested.emit(self.entry.module_id, action.action)
