"""Composer regressions through real Qt widgets and the SQLite host."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QComboBox, QDialog, QInputDialog

from prompt_composer.ui import PromptComposerPage
from studio_prompt_composer_host import PromptComposerHost


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def composer(tmp_path, app):
    host = PromptComposerHost(tmp_path / "library", settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    yield page, host
    host.close()
    page.deleteLater()
    app.processEvents()


@pytest.mark.parametrize("selected", [0, 3, 6])
def test_save_selected_keeps_more_variants_cursor_and_combination_order(composer, selected):
    page, host = composer
    assert page.generate_local()
    previous = {v["en"] for v in page._variants}
    working = deepcopy(page.draft)
    expected = host.generate(working)
    page._select_variant(selected)
    chosen = deepcopy(page._selected_draft())
    with patch.object(QDialog, "exec", return_value=1):
        assert page.save_current()
    saved = host.load(page._saved_record["id"])
    assert saved["payload"] == chosen
    assert page.draft["selection_seed"] == working["selection_seed"]
    assert page.generate_local()
    assert [v["en"] for v in page._variants] == [v["en"] for v in expected["variants"]]
    assert previous.isdisjoint(v["en"] for v in page._variants)
    assert host.load(saved["id"]) == saved


def test_lock_changes_restart_the_reduced_combination_space(composer):
    page, host = composer
    assert page.generate_local()
    page.goto_step(2)
    for key in ("style", "lighting", "time", "camera", "shot", "angle"):
        page._toggle_lock(key)
    assert page.draft["selection_seed"] == 0
    before = deepcopy(page.draft)
    with patch.object(page, "_show_message"):
        assert page.generate_local()
    assert len(page._variants) == 1
    assert page._variants[0]["draft"]["fields"] == before["fields"]
    assert page._variants[0]["draft"]["locks"] == before["locks"]
    page.goto_step(2)
    page._toggle_lock("style")
    assert page.draft["selection_seed"] == 0
    expected = host.generate(page.draft)
    with patch.object(page, "_show_message"):
        assert page.generate_local()
    assert page._variants == expected["variants"]


def test_mode_change_restarts_cursor_even_when_aspect_is_locked(composer):
    page, _ = composer
    page._set_field("location", "студия", "studio")
    page._set_field("action", "вращается", "rotates")
    page._toggle_lock("aspect")
    assert page.generate_local()
    page.goto_step(3)
    page._set_mode("reels")
    assert page.draft["selection_seed"] == 0
    assert "aspect" in page.draft["locks"]
    assert page.generate_local()
    assert page._variants[0]["draft"]["selection_seed"] == 0


def test_subject_type_change_restarts_cursor(composer):
    page, _ = composer
    assert page.generate_local()
    page.goto_step(1)
    page._set_property("subject_type", "product")
    assert page.draft["selection_seed"] == 0


def test_randomized_parameters_restart_cursor_and_preserve_locks(composer):
    page, _ = composer
    page._toggle_lock("subject")
    assert page.generate_local()
    page.goto_step(2)
    previous = deepcopy(page.draft["fields"])
    page.randomize_unlocked()
    assert page.draft["fields"] != previous
    assert page.draft["fields"]["subject"] == previous["subject"]
    assert page.draft["locks"] == ["subject"]
    assert page.draft["selection_seed"] == 0
    assert page.generate_local()
    assert page._variants[0]["draft"]["selection_seed"] == 0


def test_profile_application_restarts_cursor_and_keeps_scene_locks(composer):
    page, host = composer
    profile = host.new_draft()
    profile["fields"]["subject"] = {"ru": "чашка", "en": "mug"}
    host.save(profile, {"name": "Чашка", "kind": "profile"})
    page._set_field("location", "у окна", "by a window")
    page._toggle_lock("location")
    assert page.generate_local()
    page.goto_step(1)
    with patch.object(QInputDialog, "getItem", return_value=("Чашка", True)):
        assert page.choose_profile()
    assert page.draft["selection_seed"] == 0
    assert page.draft["fields"]["location"]["en"] == "by a window"
    assert page.draft["locks"] == ["location"]


def test_same_name_profile_dialog_selects_the_clicked_record(composer, app):
    page, host = composer
    for ru, en in (("кот", "cat"), ("собака", "dog")):
        value = host.new_draft()
        value["fields"]["subject"] = {"ru": ru, "en": en}
        host.save(value, {"name": "Animal", "kind": "profile"})
    ordered = host.list_entries(kind="profile")
    selected_rows = []

    def select_second():
        for widget in app.topLevelWidgets():
            if isinstance(widget, QInputDialog):
                combo = widget.findChild(QComboBox)
                assert combo.count() == 2
                combo.setCurrentIndex(1)
                selected_rows.append(combo.currentIndex())
                widget.accept()

    QTimer.singleShot(0, select_second)
    assert page.choose_profile()
    assert selected_rows == [1]
    assert page.draft["profile_id"] == ordered[1]["id"]
    assert page.draft["fields"]["subject"] == ordered[1]["payload"]["fields"]["subject"]


def test_save_manual_variant_preserves_other_edits_and_saved_revision(composer):
    page, host = composer
    page._toggle_lock("subject")
    assert page.generate_local()
    page._variant_edits = {0: {"manual_en": "Manual zero", "translation_stale": True},
                           1: {"manual_en": "Manual one", "translation_stale": True}}
    with patch.object(QDialog, "exec", return_value=1):
        assert page.save_current()
    record = host.load(page._saved_record["id"])
    assert record["payload"]["manual_en"] == "Manual zero"
    assert record["payload"]["locks"] == ["subject"]
    assert page._variant_edits[1]["manual_en"] == "Manual one"
    assert len(page._manual_snapshots()) == 2
    page.goto_step(2)
    page._toggle_lock("style")
    assert page.draft["manual_en"] == "Manual zero"
    assert page._variant_edits[1]["manual_en"] == "Manual one"
    with patch.object(page, "_guard_manual_rebuild", return_value=False):
        assert not page.generate_local()
    assert host.load(record["id"]) == record


def _controlled_ai(page, host, monkeypatch):
    """Deliver a provider reply at a chosen GUI boundary, without network."""
    from types import SimpleNamespace
    replies = []
    monkeypatch.setattr(page, '_ai_model', lambda: {'provider': 'openrouter', 'model': 'openai/gpt-5-mini'})
    def quote(draft, done, error, **kwargs):
        done({'id': 'synthetic', 'configured': True})
        return SimpleNamespace(cancel=lambda: None)
    def submit(quote, done, error):
        replies.append(done)
        return SimpleNamespace(cancel=lambda: None)
    monkeypatch.setattr(host, 'quote_ai', quote)
    monkeypatch.setattr(host, 'submit_ai', submit)
    return replies


@pytest.mark.parametrize('literal', ['cat <lora:my_model:1>', '<b>cat</b> & <p>flower</p>', 'a < b, x > y & z'])
def test_manual_editor_keeps_literal_text_on_unchanged_save(composer, literal):
    from PyQt6.QtWidgets import QTextEdit
    page, _ = composer
    page.draft['fields']['subject'] = {'ru': 'кот', 'en': literal}
    assert page.generate_local()
    before = page._variant_text(page._active_variant(), 'en')
    def accept(dialog):
        editor = dialog.findChild(QTextEdit, 'manualPromptEditor')
        assert editor.toPlainText() == before
        return 1
    with patch.object(QDialog, 'exec', new=accept):
        page.edit_variant_text()
    assert page._variant_text(page._active_variant(), 'en') == before


@pytest.mark.parametrize('choice', [0, 1])
def test_save_dialog_keeps_translation_received_in_its_event_loop(composer, monkeypatch, app, choice):
    page, host = composer
    assert page.generate_local()
    replies = _controlled_ai(page, host, monkeypatch)
    assert page.translate_active_text()
    failures = []
    def reply_in_dialog():
        dialog = app.activeModalWidget()
        try:
            assert dialog.windowTitle() == 'Сохранить промпт'
            replies.pop()({'target': 'ru', 'text': 'Late translation'})
        except Exception as exc:
            failures.append(exc)
        finally:
            dialog.done(choice)
    QTimer.singleShot(0, reply_in_dialog)
    assert page.save_current() is bool(choice)
    assert not failures
    assert page._variant_text(page._active_variant(), 'ru') == 'Late translation'
    records = host.list_entries()
    if choice:
        assert records[0]['payload']['manual_ru'] == 'Late translation'
        assert not page._dirty
    else:
        assert not records
        assert page._dirty


def test_replace_confirmation_keeps_late_translation_and_other_card_edits(composer, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox
    page, host = composer
    assert page.generate_local()
    with patch.object(QDialog, 'exec', return_value=1):
        assert page.save_current()
    record_id = page._saved_record['id']
    page._variant_edits[1] = {'manual_en': 'Keep another card'}
    replies = _controlled_ai(page, host, monkeypatch)
    assert page.translate_active_text()
    def confirm(*args):
        replies.pop()({'target': 'ru', 'text': 'Late at replace confirmation'})
        return QMessageBox.StandardButton.Yes
    with patch.object(QDialog, 'exec', return_value=2), patch.object(QMessageBox, 'question', new=confirm):
        assert page.save_current()
    assert host.load(record_id)['payload']['manual_ru'] == 'Late at replace confirmation'
    assert page._variant_edits[1]['manual_en'] == 'Keep another card'
    assert page._dirty


def test_new_ai_proposal_during_save_keeps_proposal_and_aborts_stale_save(composer, monkeypatch):
    page, host = composer
    assert page.generate_local()
    response = {'status': 'complete', 'variants': deepcopy(page._variants)}
    replies = _controlled_ai(page, host, monkeypatch)
    assert page.request_ai_variants()
    messages = []
    monkeypatch.setattr(page, '_show_message', lambda message: messages.append(message))
    def accept(dialog):
        replies.pop()(response)
        return 1
    with patch.object(QDialog, 'exec', new=accept):
        assert not page.save_current()
    assert not host.list_entries()
    assert page._proposal['variants']
    assert messages


@pytest.mark.parametrize('change', ['unchanged', 'target', 'source', 'closed', 'deleted'])
def test_field_translation_never_overwrites_new_input_and_keeps_unapplied_reply(composer, monkeypatch, change):
    from PyQt6 import sip
    from PyQt6.QtWidgets import QLineEdit
    page, host = composer
    replies = _controlled_ai(page, host, monkeypatch)
    dialog = QDialog(page)
    dialog.composer_ru = QLineEdit('кот', dialog)
    dialog.composer_en = QLineEdit('original', dialog)
    dialog.show()
    assert page.request_translation('кот', 'en', 'subject', dialog)
    if change == 'target':
        dialog.composer_en.setText('My newer text')
    elif change == 'source':
        dialog.composer_ru.setText('собака')
    elif change == 'closed':
        dialog.close()
    elif change == 'deleted':
        sip.delete(dialog)
    unapplied = []
    monkeypatch.setattr(page, '_show_unapplied_translation', lambda text, message: unapplied.append(text))
    replies.pop()({'target': 'en', 'text': 'cat <lora:translated:1>'})
    if change == 'unchanged':
        assert dialog.composer_en.text() == 'cat <lora:translated:1>'
        assert not unapplied
    else:
        assert unapplied == ['cat <lora:translated:1>']
        if change != 'deleted':
            assert dialog.composer_en.text() == ('My newer text' if change == 'target' else 'original')
    if change != 'deleted':
        dialog.close()


def test_unapplied_translation_is_available_as_literal_readonly_text(composer):
    from PyQt6.QtWidgets import QTextEdit
    page, _ = composer
    translated = 'cat <lora:translated:1> & <b>literal</b>'
    def inspect(dialog):
        editor = dialog.findChild(QTextEdit)
        assert editor.isReadOnly()
        assert editor.toPlainText() == translated
        return 1
    with patch.object(QDialog, 'exec', new=inspect):
        page._show_unapplied_translation(translated, 'Keep the edited field')


def test_result_cards_have_two_lines_and_one_save_action(composer, app):
    from PyQt6.QtWidgets import QLabel, QListWidget, QPushButton
    page, host = composer
    assert page.generate_local()
    page.resize(1120, 780)
    page.show()
    page._variants[1]['label'] = 'Вариант 2: ' + 'длинное описание ' * 20
    page._select_variant(1)
    app.processEvents()
    listing = page.scroll.widget().findChild(QListWidget, 'variantList')
    assert listing.spacing() >= 6
    assert listing.item(1).text().count('\n') == 1
    assert len(listing.item(1).text().split('\n')[1]) <= 30
    assert page.scroll.widget().findChild(QLabel, 'variantHeading').text() == 'Вариант 2'
    assert page.scroll.widget().findChild(QPushButton, 'favoriteButton') is None
    assert page.scroll.widget().findChild(QPushButton, 'editParametersButton') is None
    assert page.scroll.widget().findChild(QPushButton, 'saveButton') is not None
    first = listing.visualItemRect(listing.item(0))
    second = listing.visualItemRect(listing.item(1))
    assert second.top() > first.bottom()


@pytest.mark.parametrize('outcome', ['success', 'error', 'cancel', 'unconfigured'])
def test_ai_wait_is_visible_survives_render_and_clears(composer, app, outcome):
    from PyQt6.QtWidgets import QPushButton, QProgressBar
    page, host = composer
    assert page.generate_local()
    page.show()
    callbacks = {}
    class Ticket:
        cancelled = False
        def cancel(self):
            self.cancelled = True
    ticket = Ticket()
    def quote(snapshot, done, error, **kwargs):
        callbacks['quote'] = done
        callbacks['error'] = error
        return ticket
    def submit(quote, done, error):
        callbacks['done'] = done
        return ticket
    with patch.object(page, '_ai_model', return_value={'provider': 'kie', 'model': 'test'}), \
         patch.object(host, 'quote_ai', side_effect=quote), \
         patch.object(host, 'submit_ai', side_effect=submit), \
         patch.object(page, '_show_message'):
        assert page.request_ai_variants()
        assert page.ai_activity.isVisible()
        progress = page.findChild(QProgressBar, 'aiProgress')
        assert progress.minimum() == progress.maximum() == 0
        page._change_language("ru")
        assert page.ai_activity.isVisible()
        active_ai = page.footer.itemAt(1).widget()
        assert not active_ai.isEnabled()
        assert active_ai.text() == 'AI готовит ответ…'
        assert not page.scroll.widget().findChild(QPushButton, 'translateButton').isEnabled()
        callbacks['quote']({'configured': outcome != 'unconfigured'})
        if outcome == 'success':
            callbacks['done']({'variants': deepcopy(page._variants), 'status': 'complete'})
            assert page._proposal
        elif outcome == 'error':
            callbacks['error']('Безопасная ошибка')
        elif outcome == 'cancel':
            page.cancel_ai()
            assert ticket.cancelled
            callbacks['done']({'variants': deepcopy(page._variants)})
            assert page._proposal is None
        assert not page.ai_activity.isVisible()
        assert page.footer.itemAt(1).widget().isEnabled()


@pytest.mark.parametrize('operation', ['variants', 'translation'])
@pytest.mark.parametrize('price', [None, 0.01])
def test_text_ai_submits_once_without_payment_dialog(composer, operation, price):
    from PyQt6.QtWidgets import QMessageBox
    page, host = composer
    page.generate_local()
    page.resize(1120, 780)
    page.show()
    def quote(snapshot, done, error, **kwargs):
        done({'id': 'test', 'configured': True, 'price': price})
        return 'quote-ticket'
    with patch.object(page, '_ai_model', return_value={'provider': 'kie', 'model': 'test'}), \
         patch.object(host, 'quote_ai', side_effect=quote), \
         patch.object(host, 'submit_ai', return_value='request-ticket') as submit, \
         patch.object(QMessageBox, 'question', side_effect=AssertionError('unexpected payment dialog')), \
         patch.object(page, '_show_message'):
        if operation == 'variants':
            assert page.request_ai_variants()
        else:
            assert page.request_translation('Исходный текст', target='en')
        assert submit.call_count == 1
        assert page.ai_activity.isVisible()
        page.layout().activate()
        assert page.ai_activity.y() >= page.footer.geometry().bottom()
        assert not page.request_ai_variants()
        assert submit.call_count == 1
