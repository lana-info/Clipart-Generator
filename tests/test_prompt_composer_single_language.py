"""Custom inputs are used verbatim without requiring a second language."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton

from prompt_composer.engine import generate_variants, preflight_ai
from prompt_composer.model import new_draft
from prompt_composer.ui import PromptComposerPage
from studio_prompt_composer_ai import validate_response
from studio_prompt_composer_host import PromptComposerHost


@pytest.mark.parametrize('mode', ['image', 'reels'])
@pytest.mark.parametrize('language', ['ru', 'en'])
def test_local_and_ai_accept_original_single_language_fields(mode, language):
    draft = new_draft()
    draft['mode'] = mode
    texts = {'subject': 'мой герой' if language == 'ru' else 'my own subject',
             'appearance': 'рыжие волосы' if language == 'ru' else 'red hair',
             'location': 'мой двор' if language == 'ru' else 'my yard',
             'action': 'медленно поворачивает голову' if language == 'ru' else 'slowly turns head',
             'exclusions': 'без букв' if language == 'ru' else 'no lettering'}
    draft['fields'] = {key: {'ru': value if language == 'ru' else '', 'en': value if language == 'en' else ''}
                       for key, value in texts.items()}
    before = deepcopy(draft)
    result = generate_variants(draft)
    assert len(result['variants']) == 7
    assert draft == before
    preflight_ai(draft)
    for variant in result['variants']:
        for output in ('en', 'ru'):
            assert all(text in variant[output] for text in texts.values())
    from tests.test_prompt_composer_ai import reply
    from tests.test_prompt_composer_auto_english import translated_reply
    if language == 'ru':
        with pytest.raises(ValueError):
            validate_response(reply(draft), draft)
    response = validate_response(translated_reply(draft), draft)
    assert len(response['variants']) == 7
    for variant in response['variants']:
        assert variant['draft']['fields']['subject'][language] == draft['fields']['subject'][language]
        assert variant['draft']['fields']['exclusions'][language] == draft['fields']['exclusions'][language]


@pytest.mark.parametrize('text,language', [('свой двор', 'ru'), ('my own yard', 'en')])
def test_ui_uses_one_custom_input_and_generates_without_translation(tmp_path, text, language):
    app = QApplication.instance() or QApplication([])
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    try:
        page.goto_step(2)
        def enter(dialog):
            inputs = dialog.findChildren(QLineEdit)
            assert len(inputs) == 1
            inputs[0].setText(text)
            assert not any('Перевести' in b.text() for b in dialog.findChildren(QPushButton))
            return QDialog.DialogCode.Accepted
        with patch.object(QDialog, 'exec', enter):
            page._edit_custom_pair('location')
        assert page.draft['fields']['location'][language] == text
        from tests.test_prompt_composer_auto_english import translated_reply
        requests = {}
        def quote(snapshot, done, error, **kwargs):
            requests['snapshot'] = snapshot
            done({'id': 'mock', 'configured': True})
            return 'quote-ticket'
        def submit(quote, done, error):
            done(validate_response(translated_reply(requests['snapshot']), requests['snapshot']))
            return 'request-ticket'
        with patch.object(page, '_show_message', side_effect=AssertionError('unexpected translation requirement')), \
             patch.object(page, '_ai_model', return_value={'provider': 'openrouter', 'model': 'test'}), \
             patch.object(host, 'quote_ai', side_effect=quote), patch.object(host, 'submit_ai', side_effect=submit):
            assert page.generate_local()
        if language == 'ru':
            assert page._proposal
            assert all('my own yard' in v['en'] and text in v['ru'] for v in page._active_variants())
            assert page.accept_proposal()
        else:
            assert all(text in variant['en'] and text in variant['ru'] for variant in page._variants)
        with patch.object(QDialog, 'exec', return_value=1):
            assert page.save_current()
        saved = host.load(page._saved_record['id'])
        assert saved['payload']['fields']['location'] == page._variants[0]['draft']['fields']['location']
    finally:
        host.close()
        page.deleteLater()
        app.processEvents()


def test_mixed_language_fields_and_locked_values_are_preserved():
    draft = new_draft()
    draft['mode'] = 'reels'
    values = {'subject': {'ru': 'рыжий кот', 'en': ''},
              'appearance': {'ru': '', 'en': 'one green eye'},
              'action': {'ru': 'медленно моргает', 'en': ''},
              'location': {'ru': '', 'en': 'on my windowsill'},
              'lighting': {'ru': '', 'en': 'gentle summer light'},
              'duration': {'ru': '6 секунд', 'en': ''},
              'exclusions': {'ru': '', 'en': 'no text overlays'}}
    draft['fields'] = deepcopy(values)
    draft['locks'] = ['lighting']
    for variant in generate_variants(draft)['variants']:
        for language in ('ru', 'en'):
            assert all((pair['ru'] or pair['en']) in variant[language] for pair in values.values())
        assert variant['draft']['fields']['lighting'] == values['lighting']
    from tests.test_prompt_composer_auto_english import translated_reply
    assert len(validate_response(translated_reply(draft), draft)['variants']) == 7


def test_existing_translations_and_english_inline_input_survive_noop_edit(tmp_path):
    from PyQt6.QtWidgets import QComboBox
    app = QApplication.instance() or QApplication([])
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    try:
        for pair in ({'ru': 'мой двор', 'en': 'my yard'}, {'ru': '', 'en': 'my yard'}):
            page._set_field('location', pair['ru'], pair['en'])
            page.goto_step(2)
            combo = page.scroll.widget().findChild(QComboBox, 'field_location')
            assert combo.currentText() == (pair['ru'] or pair['en'])
            before = deepcopy(page.draft)
            combo.lineEdit().editingFinished.emit()
            assert page.draft == before
        combo.lineEdit().setText('a new garden')
        combo.lineEdit().editingFinished.emit()
        assert page.draft['fields']['location'] == {'ru': '', 'en': 'a new garden'}
    finally:
        host.close()
        page.deleteLater()
        app.processEvents()


@pytest.mark.parametrize('language,text', [('ru', 'пушистый кот'), ('en', 'a fluffy cat')])
def test_ai_button_submits_untranslated_snapshot_once(tmp_path, language, text):
    app = QApplication.instance() or QApplication([])
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    page._set_field('subject', text if language == 'ru' else '', text if language == 'en' else '')
    snapshots = []
    def quote(snapshot, done, error, **kwargs):
        preflight_ai(snapshot)
        snapshots.append(deepcopy(snapshot))
        done({'id': 'mock', 'configured': True})
        return 'quote-ticket'
    try:
        with patch.object(page, '_ai_model', return_value={'provider': 'kie', 'model': 'test'}), \
             patch.object(host, 'quote_ai', side_effect=quote), \
             patch.object(host, 'submit_ai', return_value='request-ticket') as submit, \
             patch.object(page, '_show_message', side_effect=AssertionError('unexpected translation requirement')):
            assert page.request_ai_variants()
            assert submit.call_count == len(snapshots) == 1
            assert snapshots[0]['fields']['subject'] == page.draft['fields']['subject']
    finally:
        page.cancel_ai()
        host.close()
        page.deleteLater()
        app.processEvents()
