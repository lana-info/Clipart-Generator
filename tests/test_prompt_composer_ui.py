"""UI contract checks with a local host; no transport or user data."""

import os
import unittest
from copy import deepcopy
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox, QTextEdit

from prompt_composer.ui import PromptComposerPage


def draft():
    return {"schema_version": 1, "catalog_version": 1, "revision": 1,
            "mode": "image", "subject_type": "product", "fields": {"subject": {"ru": "чашка", "en": "mug"}},
            "locks": ["subject"], "references": [], "profile_id": None,
            "base_en": "", "base_ru": "", "manual_en": None, "manual_ru": None,
            "translation_stale": False, "name": "", "selection_seed": 0}


class Ticket:
    def __init__(self):
        self.cancelled = False

    def cancel(self):
        self.cancelled = True


class FakeHost:
    def __init__(self):
        self.entries = {}
        self.saved_calls = []
        self.generated = []
        self.quote_done = None
        self.submit_done = None
        self.quote_ticket = Ticket()
        self.submit_ticket = Ticket()
        self.closed = False

    def catalogue(self):
        return {"subject_types": [{"id": "product", "label": "Товар"}, {"id": "person", "label": "Человек"}],
                "templates": [{"id": "mug", "label": "Чашка", "description": "Предметное фото", "draft": draft()}],
                "options": {"color": [{"id": "sage", "ru": "Шалфейный", "en": "sage green"}]}}

    def new_draft(self):
        return draft()

    def generate(self, value):
        self.generated.append(deepcopy(value))
        variants = []
        for index in range(7):
            resolved = deepcopy(value)
            resolved["fields"]["location"] = {"ru": f"место {index}", "en": f"place {index}"}
            variants.append({"label": f"Вариант {index}", "draft": resolved,
                             "en": f"Mug in place {index}", "ru": f"Чашка в месте {index}",
                             "source": "local", "warnings": []})
        return {"status": "complete", "variants": variants, "reason": "", "next_seed": value["selection_seed"] + 1}

    def list_entries(self, kind="prompt"):
        return [deepcopy(x) for x in self.entries.values() if x["kind"] == kind]

    def load(self, entry_id):
        return deepcopy(self.entries[entry_id])

    def save(self, value, metadata, entry_id=None, expected_revision=None):
        self.saved_calls.append((deepcopy(value), deepcopy(metadata), entry_id, expected_revision))
        entry_id = entry_id or f"entry-{len(self.entries) + 1}"
        revision = self.entries[entry_id]["revision"] + 1 if entry_id in self.entries else 1
        record = {"id": entry_id, "revision": revision, "payload": deepcopy(value),
                  "updated_at": "2026-09-29", **metadata}
        self.entries[entry_id] = record
        return deepcopy(record)

    def delete(self, entry_id, expected_revision):
        assert self.entries[entry_id]["revision"] == expected_revision
        del self.entries[entry_id]

    def import_reference(self, path):
        return {"handle": "managed-1"}

    def reference_available(self, handle):
        return True

    def ai_options(self):
        return [{"provider": "fake", "model": "small", "label": "Fake", "configured": True}]

    def quote_ai(self, value, on_done, on_error, **kwargs):
        self.quote_done = on_done
        return self.quote_ticket

    def submit_ai(self, quote, on_done, on_error):
        self.submit_done = on_done
        return self.submit_ticket

    def close(self):
        self.closed = True


class PromptComposerUITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.host = FakeHost()
        self.page = PromptComposerPage(self.host)

    def tearDown(self):
        self.page.deleteLater()

    def test_local_variant_uses_selected_resolved_draft_on_save(self):
        self.assertTrue(self.page.generate_local())
        self.assertEqual(len(self.page._variants), 7)
        self.page._variant_index = 4
        with patch("PyQt6.QtWidgets.QDialog.exec", return_value=1):
            self.assertTrue(self.page.save_current())
        saved = self.host.saved_calls[-1][0]
        self.assertEqual(saved["fields"]["location"]["en"], "place 4")
        self.assertEqual(saved["base_en"], "Mug in place 4")
        self.assertIsNone(self.host.saved_calls[-1][2])

    def test_open_is_copy_and_explicit_replace_uses_revision(self):
        record = self.host.save(draft(), {"name": "Original", "tags": [], "favorite": False, "kind": "prompt"})
        self.assertTrue(self.page.open_entry(record["id"]))
        self.assertEqual(self.page.draft["fields"]["subject"]["en"], "mug")
        self.page._set_field("color", "синий", "blue")
        self.assertEqual(self.host.entries[record["id"]]["payload"]["fields"].get("color"), None)
        with patch("PyQt6.QtWidgets.QDialog.exec", return_value=2), patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.assertTrue(self.page.save_current())
        self.assertEqual(self.host.saved_calls[-1][2:], (record["id"], record["revision"]))

    def test_close_cancel_preserves_draft_and_does_not_close_host(self):
        self.page._set_field("color", "синий", "blue")
        with patch.object(self.page, "_ask_save_discard", return_value="cancel"):
            self.assertFalse(self.page.confirm_close())
        self.assertFalse(self.host.closed)
        self.assertEqual(self.page.draft["fields"]["color"]["en"], "blue")

    def test_ai_submits_without_payment_dialog_and_stale_offer_opens_separate(self):
        self.page.generate_local()
        with patch.object(QMessageBox, "question", side_effect=AssertionError("unexpected payment dialog")):
            self.assertTrue(self.page.request_ai_variants())
            self.assertIsNone(self.host.submit_done)
            self.host.quote_done({"id": "quote-1", "provider": "fake", "model": "small", "price": None, "configured": True})
        self.assertIsNotNone(self.host.submit_done)
        self.page._set_field("color", "синий", "blue")
        response = self.host.generate(draft())
        self.host.submit_done(response)
        self.assertTrue(self.page._proposal["stale"])
        self.assertEqual(self.page.draft["fields"]["color"]["en"], "blue")
        with patch.object(self.page, "_ask_save_discard", return_value="discard"):
            self.assertTrue(self.page.open_stale_proposal())
        self.assertNotIn("color", self.page.draft["fields"])
        self.assertEqual(self.page.draft["base_en"], "Mug in place 0")
        with patch("PyQt6.QtWidgets.QDialog.exec", return_value=1):
            self.assertTrue(self.page.save_current())
        self.assertEqual(self.host.saved_calls[-1][1]["source"], "ai")

    def test_cancel_suppresses_late_ai_callback(self):
        self.page.generate_local()
        self.page.request_ai_variants()
        callback = self.host.quote_done
        self.page.cancel_ai()
        self.assertTrue(self.host.quote_ticket.cancelled)
        callback({"id": "late", "configured": True})
        self.assertIsNone(self.host.submit_done)

    def test_manual_edit_belongs_to_selected_variant(self):
        self.page.generate_local()

        def edit_dialog(dialog):
            dialog.findChild(QTextEdit, "manualPromptEditor").setPlainText("Manual variant zero")
            return 1

        with patch("PyQt6.QtWidgets.QDialog.exec", new=edit_dialog):
            self.page.edit_variant_text()
        self.assertEqual(self.page._variant_text(self.page._variants[0], "en"), "Manual variant zero")
        self.page._select_variant(1)
        self.assertEqual(self.page._variant_text(self.page._variants[1], "en"), "Mug in place 1")
        self.page._select_variant(0)
        self.assertEqual(self.page._variant_text(self.page._variants[0], "en"), "Manual variant zero")

    def test_missing_english_pair_does_not_block_generation(self):
        self.page.generate_local()
        self.page._set_field("color", "синий", "")
        with patch.object(self.page, "_show_message", side_effect=AssertionError("unexpected translation requirement")):
            self.assertTrue(self.page.generate_local())
        self.assertIsNotNone(self.host.quote_done)
        self.assertEqual(self.page.draft["fields"]["color"], {"ru": "синий", "en": ""})
        self.assertEqual(len(self.host.generated), 1)

    def test_unconfigured_ai_never_submits(self):
        self.page.generate_local()
        with patch.object(self.page, "_show_message"):
            self.page.request_ai_variants()
            self.host.quote_done({"id": "quote-1", "configured": False})
        self.assertIsNone(self.host.submit_done)

    def test_profile_application_keeps_scene_fields(self):
        current = draft()
        current["fields"]["location"] = {"ru": "у окна", "en": "by a window"}
        self.page.draft = current
        profile = draft()
        profile["fields"]["appearance"] = {"ru": "матовая", "en": "matte"}
        profile["fields"]["location"] = {"ru": "в студии", "en": "in studio"}
        self.host.save(profile, {"name": "Чашка", "tags": [], "favorite": False, "kind": "profile"})
        with patch("PyQt6.QtWidgets.QInputDialog.getItem", return_value=("Чашка", True)):
            self.assertTrue(self.page.choose_profile())
        self.assertEqual(self.page.draft["fields"]["appearance"]["en"], "matte")
        self.assertEqual(self.page.draft["fields"]["location"]["en"], "by a window")

    def test_saved_manual_edit_does_not_leak_and_other_edits_survive(self):
        self.page.generate_local()
        self.page._variant_edits = {0: {"manual_en": "ONLY ZERO", "translation_stale": True}, 1: {"manual_en": "ONLY ONE"}}
        with patch("PyQt6.QtWidgets.QDialog.exec", return_value=1):
            self.assertTrue(self.page.save_current())
        self.page._select_variant(1)
        self.assertEqual(self.page._selected_draft()["manual_en"], "ONLY ONE")
        self.page._select_variant(2)
        self.assertIsNone(self.page._selected_draft()["manual_en"])
        self.assertEqual(self.page._variant_text(self.page._active_variant(), "en"), "Mug in place 2")
        self.page._select_variant(0)
        self.assertEqual(self.page._variant_text(self.page._active_variant(), "en"), "ONLY ZERO")

    def test_ai_proposal_becomes_stale_after_response(self):
        with patch.object(QMessageBox, "question", side_effect=AssertionError("unexpected payment dialog")):
            self.page.request_ai_variants()
            self.host.quote_done({"id": "quote", "configured": True})
        self.host.submit_done(self.host.generate(draft()))
        self.page._set_field("color", "синий", "blue")
        self.assertFalse(self.page.accept_proposal())
        self.assertTrue(self.page._proposal["stale"])
        self.assertEqual(self.page.draft["fields"]["color"]["en"], "blue")

    def test_manual_edit_survives_cancelled_ai(self):
        self.page.generate_local()
        self.page._variant_edits[0] = {"manual_en": "Keep me"}
        self.page.request_ai_variants()
        self.page.cancel_ai()
        self.host.quote_done({"id": "quote", "configured": True})
        self.assertIsNone(self.host.submit_done)
        self.assertEqual(self.page._selected_draft()["manual_en"], "Keep me")

    def test_translation_never_moves_to_other_variant(self):
        self.page.generate_local()
        with patch.object(QMessageBox, "question", side_effect=AssertionError("unexpected payment dialog")):
            self.page.translate_active_text()
            self.host.quote_done({"id": "quote", "configured": True})
        self.page._select_variant(1)
        with patch("PyQt6.QtWidgets.QDialog.exec", return_value=1):
            self.host.submit_done({"target": "ru", "text": "Перевод нулевого"})
        self.assertNotIn(1, self.page._variant_edits)

    def test_back_to_settings_uses_resolved_variant(self):
        self.page.generate_local()
        self.page._select_variant(4)
        self.page.goto_step(2)
        self.assertEqual(self.page.draft["fields"]["location"]["en"], "place 4")

    def test_new_draft_invalidates_pending_request(self):
        self.page.request_ai_variants()
        callback = self.host.quote_done
        self.page.new_draft()
        callback({"id": "late", "configured": True})
        self.assertIsNone(self.host.submit_done)

    def test_manual_parameter_change_and_ai_accept_can_be_cancelled(self):
        self.page.generate_local()
        self.page.draft["manual_en"] = "A handwritten lake scene"
        before = deepcopy(self.page.draft)
        with patch.object(self.page, "_guard_manual_rebuild", return_value=False) as guard:
            self.page._set_field("location", "студия", "studio")
            self.assertEqual(self.page.draft, before)
            self.assertTrue(guard.called)
            self.page._proposal = {"variants": deepcopy(self.page._variants), "snapshot": before, "stale": False}
            self.assertFalse(self.page.accept_proposal())
            self.assertEqual(self.page.draft, before)

    def test_save_manual_copies_covers_unselected_variants(self):
        self.page.generate_local()
        self.page._variant_edits = {0: {"manual_en": "Edited zero"}, 2: {"manual_en": "Edited two"}}
        self.page._variant_index = 1
        def choose_save(box):
            button = next(button for button in box.buttons() if button.text() == "Сохранить копии правок")
            button.click()
            return 0
        with patch.object(QMessageBox, "exec", new=choose_save):
            self.assertTrue(self.page.generate_local())
        self.assertEqual({call[0]["manual_en"] for call in self.host.saved_calls}, {"Edited zero", "Edited two"})
        self.assertFalse(self.page._variant_edits)

    def test_saving_one_variant_leaves_other_manual_edit_dirty(self):
        self.page.generate_local()
        self.page._variant_edits = {0: {"manual_en": "Zero"}, 2: {"manual_en": "Two"}}
        with patch("PyQt6.QtWidgets.QDialog.exec", return_value=1):
            self.assertTrue(self.page.save_current())
        self.assertTrue(self.page._dirty)
        self.assertEqual(self.page._variant_edits[2]["manual_en"], "Two")

    def test_rename_uses_revision_from_visible_row(self):
        row = self.host.save(draft(), {"name": "Old", "tags": [], "favorite": False, "kind": "prompt"})
        self.host.entries[row["id"]]["revision"] = 2
        with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Rename", True)):
            self.page.rename_entry(row)
        self.assertEqual(self.host.saved_calls[-1][3], 1)

    def test_leaving_saves_all_edited_variants(self):
        for action in ("new_draft", "confirm_close"):
            with self.subTest(action=action):
                self.setUp()
                self.page.generate_local()
                self.page._variant_edits = {0: {"manual_en": "Edited A"}, 2: {"manual_en": "Edited B"}}
                self.page._dirty = True
                with patch.object(self.page, "_ask_save_discard", return_value="save"), patch("PyQt6.QtWidgets.QDialog.exec", return_value=1):
                    self.assertTrue(getattr(self.page, action)())
                self.assertEqual({call[0]["manual_en"] for call in self.host.saved_calls}, {"Edited A", "Edited B"})
                self.tearDown()

    def test_changed_draft_before_quote_never_submits(self):
        self.page.generate_local()
        self.page.request_ai_variants()
        self.page._set_field("color", "синий", "blue")
        with patch.object(self.page, "_show_message"):
            self.host.quote_done({"id": "quote-1", "configured": True})
        self.assertIsNone(self.host.submit_done)
        self.assertIsNone(self.page._ai_ticket)


if __name__ == "__main__":
    unittest.main()
