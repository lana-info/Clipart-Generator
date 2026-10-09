"""One AI request prepares English prompts from untranslated user parameters."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QPushButton
from prompt_composer.model import new_draft
from prompt_composer.engine import _render
from prompt_composer.ui import PromptComposerPage
from studio_prompt_composer_ai import request_body, validate_response, perform_request
from studio_prompt_composer_host import PromptComposerHost
from tests.test_prompt_composer_ai import reply, MODEL


def russian_draft(mode='image'):
    draft = new_draft()
    draft['mode'] = mode
    draft['fields'].update(subject={'ru': 'рыжий кот', 'en': ''},
        lighting={'ru': 'мягкий дневной свет', 'en': ''},
        exclusions={'ru': 'без надписей', 'en': ''})
    draft['locks'] = ['lighting']
    if mode == 'reels':
        draft['fields'].update(action={'ru': 'медленно моргает', 'en': ''},
                               location={'ru': 'у окна', 'en': ''})
    return draft


def translated_reply(draft):
    value = reply(draft)
    translations = {'рыжий кот': 'a ginger cat', 'мягкий дневной свет': 'soft daylight',
                    'без надписей': 'no lettering', 'медленно моргает': 'slowly blinks', 'у окна': 'by a window',
                    'свой двор': 'my own yard', 'мой герой': 'my own subject', 'рыжие волосы': 'red hair',
                    'мой двор': 'my yard', 'медленно поворачивает голову': 'slowly turns head',
                    'без букв': 'no lettering', '6 секунд': '6 seconds'}
    for item in value['variants']:
        for pair in item['fields'].values():
            if pair['ru'] and not pair['en']:
                pair['en'] = translations[pair['ru']]
        snapshot = deepcopy(draft)
        snapshot['fields'] = item['fields']
        item['en'] = _render(snapshot, 'en')
        item['ru'] = _render(snapshot, 'ru')
    return value


@pytest.mark.parametrize('mode', ['image', 'reels'])
def test_translation_enriches_missing_english_without_changing_original_or_locks(mode):
    draft = russian_draft(mode)
    before = deepcopy(draft)
    result = validate_response(translated_reply(draft), draft)
    assert draft == before
    assert len(result['variants']) == 7
    for variant in result['variants']:
        assert 'a ginger cat' in variant['en'] and 'рыжий кот' not in variant['en']
        for key in ('subject', 'lighting', 'exclusions'):
            assert variant['draft']['fields'][key]['ru'] == draft['fields'][key]['ru']
            assert variant['draft']['fields'][key]['en']


@pytest.mark.parametrize('defect', ['original_changed', 'lock_changed', 'exclusion_changed', 'mixed_prompt', 'missing_english'])
def test_incomplete_translation_or_changed_original_is_rejected(defect):
    draft = russian_draft()
    value = translated_reply(draft)
    item = value['variants'][0]
    if defect == 'original_changed':
        item['fields']['subject']['ru'] = 'чёрная собака'
    elif defect == 'lock_changed':
        item['fields']['lighting']['ru'] = 'жёсткий свет'
    elif defect == 'exclusion_changed':
        item['fields']['exclusions']['ru'] = 'с надписями'
    elif defect == 'mixed_prompt':
        item['en'] += ' рыжий кот'
    else:
        item['fields']['subject']['en'] = ''
    with pytest.raises(ValueError):
        validate_response(value, draft)


@pytest.mark.parametrize('mode', ['image', 'reels'])
def test_get_variants_automatically_submits_one_request_and_keeps_draft_until_accept(tmp_path, mode):
    app = QApplication.instance() or QApplication([])
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    page.draft = russian_draft(mode)
    page.goto_step(3)
    before = deepcopy(page.draft)
    callbacks = {}
    def quote(snapshot, done, error, **kwargs):
        callbacks['snapshot'] = deepcopy(snapshot)
        done({'id': 'test', 'configured': True})
        return 'quote-ticket'
    def submit(quote, done, error):
        callbacks.update(done=done, error=error)
        return 'request-ticket'
    try:
        with patch.object(page, '_ai_model', return_value={'provider': 'openrouter', 'model': MODEL}), \
             patch.object(host, 'quote_ai', side_effect=quote) as quoted, \
             patch.object(host, 'submit_ai', side_effect=submit) as submitted, \
             patch.object(host, 'generate', side_effect=AssertionError('mixed-language local result')):
            assert page.generate_local()
            assert quoted.call_count == submitted.call_count == 1
            assert page.draft == before
            next_button = next(page.footer.itemAt(i).widget() for i in range(page.footer.count())
                if isinstance(page.footer.itemAt(i).widget(), QPushButton)
                and page.footer.itemAt(i).widget().objectName() == "nextButton")
            assert not next_button.isEnabled()
            result = validate_response(translated_reply(callbacks['snapshot']), callbacks['snapshot'])
            callbacks['done'](result)
            assert page.draft == before
            assert page._proposal and len(page._active_variants()) == 7
            assert 'a ginger cat' in page._active_variant()['en']
            assert page.accept_proposal()
            assert page.draft['fields']['subject'] == {'ru': 'рыжий кот', 'en': 'a ginger cat'}
            with patch('PyQt6.QtWidgets.QDialog.exec', return_value=1):
                assert page.save_current()
            saved = host.load(page._saved_record['id'])
            assert 'a ginger cat' in saved['payload']['base_en']
    finally:
        page.cancel_ai()
        host.close()
        page.deleteLater()
        app.processEvents()


def test_ai_instruction_requests_automatic_translation():
    body = request_body(russian_draft(), 'openrouter', MODEL)
    instruction = body['messages'][0]['content']
    assert 'Translate' in instruction and 'English' in instruction
    assert 'insert its available original value into the final prompt' not in instruction


def test_transport_translates_and_generates_seven_with_one_post(monkeypatch):
    import json
    draft = russian_draft('reels')
    raw = json.dumps({'choices': [{'finish_reason': 'stop', 'message': {
        'content': json.dumps(translated_reply(draft))}}]}).encode()
    class Response:
        status_code = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def iter_content(self, size):
            yield raw
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr('studio_prompt_composer_ai.requests.post', post)
    result = perform_request(draft, provider='openrouter', model=MODEL, api_key='test-only')
    assert len(calls) == 1 and len(result['variants']) == 7
    assert json.loads(calls[0]['json']['messages'][1]['content'])['fields'] == draft['fields']
    assert all('a ginger cat' in v['en'] and 'рыжий кот' not in v['en'] for v in result['variants'])


@pytest.mark.parametrize('outcome', ['error', 'cancel', 'unconfigured'])
def test_failed_auto_translation_preserves_parameters_and_previous_results(tmp_path, outcome):
    app = QApplication.instance() or QApplication([])
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    assert page.generate_local()
    previous = deepcopy(page._variants)
    page.draft = russian_draft()
    before = deepcopy(page.draft)
    callbacks = {}
    def quote(snapshot, done, error, **kwargs):
        done({'id': 'mock', 'configured': outcome != 'unconfigured'})
        return 'quote-ticket'
    def submit(quote, done, error):
        callbacks.update(done=done, error=error)
        return 'request-ticket'
    try:
        with patch.object(page, '_ai_model', return_value={'provider': 'openrouter', 'model': MODEL}), \
             patch.object(host, 'quote_ai', side_effect=quote), patch.object(host, 'submit_ai', side_effect=submit) as submitted, \
             patch.object(page, '_show_message'):
            assert page.generate_local()
            if outcome == 'error':
                callbacks['error']('AI temporarily unavailable')
            elif outcome == 'cancel':
                page.cancel_ai()
                callbacks['done'](validate_response(translated_reply(before), before))
            assert submitted.call_count == (0 if outcome == 'unconfigured' else 1)
        assert page.draft == before and page._variants == previous
        assert page._proposal is None and page._ai_ticket is None
    finally:
        host.close()
        page.deleteLater()
        app.processEvents()


def test_ready_english_parameters_do_not_start_ai(tmp_path):
    app = QApplication.instance() or QApplication([])
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    page._custom_field('subject', 'a ginger cat')
    try:
        with patch.object(host, 'quote_ai', side_effect=AssertionError('unexpected AI request')):
            assert page.generate_local()
        assert len(page._variants) == 7
        assert all('a ginger cat' in v['en'] for v in page._variants)
    finally:
        host.close()
        page.deleteLater()
        app.processEvents()
