from __future__ import annotations

from dataclasses import FrozenInstanceError
import unittest

from studio_catalog import CardAction, CatalogEntry, ModuleAvailability, card_action


class StudioCatalogTests(unittest.TestCase):
    def entry(self, **changes):
        values = {
            "module_id": "fictional-export", "title": "Fictional export",
            "description": "Exports fictional documents.", "artwork_key": "fictional-export",
            "released": True,
        }
        values.update(changes)
        return CatalogEntry(**values)

    def assert_action(self, expected, **availability):
        self.assertEqual(expected, card_action(self.entry(), ModuleAvailability(**availability)))

    def test_defaults_keep_unknown_rights_false_and_are_immutable(self):
        availability = ModuleAvailability()
        self.assertEqual(ModuleAvailability(False, False, True, False, False, False, False), availability)
        action = card_action(self.entry(), availability)
        self.assertEqual(CardAction("purchase", "Купить", False, "Покупка модуля сейчас недоступна."), action)
        with self.assertRaises(FrozenInstanceError):
            action.enabled = True

    def test_unreleased_wins_over_installed_or_any_right(self):
        action = card_action(
            self.entry(released=False),
            ModuleAvailability(True, True, True, True, True, True, True),
        )
        self.assertEqual(CardAction("soon", "Скоро выйдет", False, "Модуль ещё не выпущен."), action)

    def test_incompatible_wins_over_entitlement_and_purchase(self):
        self.assert_action(
            CardAction("unavailable", "Недоступно", False, "Модуль несовместим с этой версией Studio."),
            installed=True, entitled=True, compatible=False, open_supported=True,
        )

    def test_installed_entitled_opens_even_when_an_update_is_available(self):
        self.assert_action(
            CardAction("open", "Открыть", True, ""),
            installed=True, entitled=True, open_supported=True,
            update_available=True, download_supported=True,
        )

    def test_installed_entitled_uses_update_only_when_open_is_not_supported(self):
        self.assert_action(
            CardAction("update", "Обновить", True, ""),
            installed=True, entitled=True, update_available=True, download_supported=True,
        )
        self.assert_action(
            CardAction("open", "Открыть", False, "Открытие модуля сейчас недоступно."),
            installed=True, entitled=True, update_available=True, download_supported=False,
        )

    def test_entitled_but_not_installed_downloads_only_when_supported(self):
        self.assert_action(CardAction("download", "Скачать", True, ""), entitled=True, download_supported=True)
        self.assert_action(
            CardAction("download", "Скачать", False, "Скачивание модуля сейчас недоступно."),
            entitled=True,
        )

    def test_copied_installed_module_without_rights_cannot_open(self):
        self.assert_action(CardAction("purchase", "Купить", True, ""), installed=True, purchase_supported=True)
        self.assert_action(
            CardAction("purchase", "Купить", False, "Покупка модуля сейчас недоступна."),
            installed=True,
        )

    def test_catalogue_content_and_boolean_contract_are_validated(self):
        for field in ("module_id", "title", "description", "artwork_key"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.entry(**{field: "   "})
        with self.assertRaises(ValueError):
            self.entry(module_id="Invalid module")
        with self.assertRaises(TypeError):
            ModuleAvailability(entitled=1)
        with self.assertRaises(TypeError):
            card_action(object(), ModuleAvailability())


if __name__ == "__main__":
    unittest.main()
