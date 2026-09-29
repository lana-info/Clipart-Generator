import json
from copy import deepcopy
import pytest
from prompt_composer.model import new_draft, FIELD_KEYS
from prompt_composer.engine import generate_variants
from studio_prompt_composer_ai import request_body, validate_response, perform_request
from studio_text_errors import TextGenerationError

MODEL = 'openai/gpt-5-mini'


def reply(draft):
    result = generate_variants(draft)
    variants = []
    for v in result['variants']:
        fields = {k: v['draft']['fields'].get(k, {'en': '', 'ru': ''}) for k in FIELD_KEYS}
        variants.append(dict(label=v['label'][:160], en=v['en'], ru=v['ru'], fields=fields))
    return dict(status=result['status'], reason=result['reason'], variants=variants)


def test_full_partial_and_empty_contract():
    draft = new_draft()
    value = reply(draft)
    assert len(validate_response(value, draft)['variants']) == 7
    value['status'], value['reason'] = 'insufficient', 'Нет других сочетаний'
    value['variants'] = value['variants'][:3]
    assert len(validate_response(value, draft)['variants']) == 3
    value['variants'] = []
    assert validate_response(value, draft)['variants'] == []
    value['reason'] = ''
    with pytest.raises(ValueError):
        validate_response(value, draft)


def test_reject_duplicates_and_locked_changes():
    draft = new_draft()
    draft['locks'] = ['subject']
    value = reply(draft)
    value['variants'][1] = deepcopy(value['variants'][0])
    with pytest.raises(ValueError, match='повтор'):
        validate_response(value, draft)
    value = reply(draft)
    value['variants'][0]['fields']['subject'] = {'en': 'other', 'ru': 'другой'}
    with pytest.raises(ValueError, match='закреп'):
        validate_response(value, draft)


def test_request_has_no_assets_or_profile_data():
    draft = new_draft()
    draft['profile_id'] = 'PRIVATE_PROFILE'
    digest = 'a' * 64
    draft['references'] = [dict(schema_version=1, asset_id=digest, sha256=digest, size=123, filename='PRIVATE_REF.png', media_type='image/png')]
    body = request_body(draft, 'openrouter', MODEL)
    encoded = json.dumps(body)
    assert 'PRIVATE_' not in encoded and digest not in encoded
    assert body['provider']['allow_fallbacks'] is False
    assert body['response_format']['json_schema']['strict'] is True


def test_transport_one_call_and_sanitized_failure(monkeypatch):
    calls = []
    def fail(*args, **kwargs):
        calls.append(kwargs)
        import requests
        raise requests.ConnectionError('secret-key in request URL')
    monkeypatch.setattr('studio_prompt_composer_ai.requests.post', fail)
    with pytest.raises(TextGenerationError) as error:
        perform_request(new_draft(), provider='openrouter', model=MODEL, api_key='secret-key')
    assert 'secret-key' not in str(error.value)
    assert len(calls) == 1 and calls[0]['allow_redirects'] is False


def test_cancel_before_transport(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('unexpected HTTP')
    monkeypatch.setattr('studio_prompt_composer_ai.requests.post', forbidden)
    assert perform_request(new_draft(), provider='openrouter', model=MODEL, api_key='dummy', cancelled=lambda: True) is None


def test_translation_shape():
    assert validate_response({'text': 'hello', 'target': 'en'}, new_draft(), 'translation', 'en')['text'] == 'hello'
    with pytest.raises(ValueError):
        validate_response({'text': 'hello', 'target': 'ru'}, new_draft(), 'translation', 'en')


@pytest.mark.parametrize('field', ['action', 'location', 'camera', 'style', 'shot'])
def test_structured_reels_multi_scene_is_rejected(field):
    from prompt_composer.catalog import apply_template
    draft = apply_template('reels_cup_turn')
    value = reply(draft)
    value['variants'][0]['fields'][field] = {'en': 'montage of two scenes', 'ru': 'монтаж двух сцен'}
    with pytest.raises(ValueError, match='Reels'):
        validate_response(value, draft)


def test_freeform_scene_warning_in_russian_requires_human_review():
    from prompt_composer.catalog import apply_template
    draft = apply_template('reels_cup_turn')
    value = reply(draft)
    value['variants'][0]['ru'] = 'Чашка у окна. Затем переход ко второй сцене.'
    result = validate_response(value, draft)
    assert any('без монтажа' in warning for warning in result['variants'][0]['warnings'])
