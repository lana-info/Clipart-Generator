import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from dataclasses import replace
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from studio_catalog import CatalogEntry, ModuleAvailability
from studio_catalog_ui import BUILTIN_CATALOG, StudioCatalogCard, catalog_artwork
from v3_mode_selection import ModeSelectionScreen


class CatalogUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_default_home_has_six_equal_module_cards_and_preserves_artwork_size(self):
        screen = ModeSelectionScreen()
        screen.resize(1120, 780)
        screen.show()
        self.app.processEvents()
        cards = list(screen.module_cards.values())
        self.assertEqual(len(cards), 6)
        self.assertEqual({card.height() for card in cards}, {248})
        self.assertLessEqual(max(card.width() for card in cards) - min(card.width() for card in cards), 1)
        self.assertEqual({card.illustration.height() for card in cards}, {112})
        self.assertTrue(all(card.start_button.text() == "Нет доступа" for card in cards))
        self.assertTrue(all(not card.start_button.isEnabled() for card in cards))
        self.assertTrue(screen.license_status_label.isHidden())
        self.assertTrue(screen.license_verification_label.isHidden())
        screen.resize(980, 700)
        self.app.processEvents()
        scroll = screen.catalog_scroll
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        self.app.processEvents()
        last = screen.module_cards["patterns"].start_button
        position = last.mapTo(scroll.viewport(), last.rect().bottomRight())
        self.assertLessEqual(position.y(), scroll.viewport().height())
        screen.close()
        screen.deleteLater()

    def test_card_emits_only_supported_intent_and_revocation_disables_it(self):
        entry = replace(BUILTIN_CATALOG[1], released=True)
        availability = ModuleAvailability(entitled=True, download_supported=True)
        card = StudioCatalogCard(entry, availability)
        received = []
        card.action_requested.connect(lambda *args: received.append(args))
        self.assertEqual(card.start_button.text(), "Скачать")
        card.start_button.click()
        self.assertEqual(received, [("auto-clipart", "download")])
        card.set_availability(ModuleAvailability())
        self.assertEqual(card.start_button.text(), "Нет доступа")
        card.start_button.click()
        self.assertEqual(len(received), 1)
        card.deleteLater()

    def test_catalog_replace_preserves_workflows_and_routes_by_module_id(self):
        screen = ModeSelectionScreen()
        replaced = list(screen.module_cards.values())
        received = []
        screen.module_action_requested.connect(lambda *args: received.append(args))
        entry = CatalogEntry("documents", "Документы", "Подготовка документов", "unknown", True)
        screen.set_module_catalog([entry], {"documents": ModuleAvailability(entitled=True, download_supported=True)})
        self.assertEqual(screen.mode_cards, {})
        self.assertTrue(all(card.isHidden() for card in replaced))
        screen.module_cards["documents"].start_button.click()
        self.assertEqual(received, [("documents", "download")])
        with self.assertRaises(ValueError):
            screen.set_module_catalog([entry, entry])
        self.assertEqual(list(screen.module_cards), ["documents"])
        with self.assertRaises(TypeError):
            screen.set_module_catalog([entry], {"documents": "invalid rights"})
        self.assertEqual(list(screen.module_cards), ["documents"])
        screen.deleteLater()

    def test_titles_are_plain_text_and_artwork_is_allowlisted(self):
        entry = CatalogEntry("safe", "<b>Название</b>", "<img src=x>", "../../private")
        card = StudioCatalogCard(entry, ModuleAvailability())
        self.assertEqual(card.title_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(card.description_label.textFormat(), Qt.TextFormat.PlainText)
        self.assertEqual(catalog_artwork(entry.artwork_key).name, "vibix-images.svg")
        for key in ("generation", "clipart", "processing", "pinterest", "patterns", "mockups", "prompt-composer"):
            self.assertTrue(catalog_artwork(key).is_file())
            build = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(encoding="utf-8-sig")
            self.assertIn(f'assets/{catalog_artwork(key).name};assets', build)
        card.deleteLater()


if __name__ == "__main__":
    unittest.main()
