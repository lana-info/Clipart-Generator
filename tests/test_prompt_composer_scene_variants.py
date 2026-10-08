"""Semantic scene preservation, no paid generation and no implicit locks."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from prompt_composer.catalog import catalogue
from prompt_composer.engine import generate_variants

SCENES = [t for t in catalogue()['templates'] if t.get('reusable')]


@pytest.mark.parametrize('template', SCENES, ids=lambda t: t['id'])
def test_seven_variants_keep_scene_camera_style_action_and_subject(template):
    draft = deepcopy(template['draft'])
    original = deepcopy(draft)
    result = generate_variants(draft)
    assert result['status'] == 'complete'
    assert len({v['en'] for v in result['variants']}) == 7
    assert len({v['ru'] for v in result['variants']}) == 7
    for variant in result['variants']:
        fields = variant['draft']['fields']
        for key in ('style', 'camera', 'action', 'subject', 'location', 'exclusions'):
            assert fields[key] == original['fields'][key]
        for key in ('shot', 'lighting', 'angle'):
            for lang in ('ru', 'en'):
                assert fields[key][lang].startswith(original['fields'][key][lang])
        assert variant['draft']['locks'] == []
    assert draft == original


def test_scene_relative_variants_keep_custom_framing_and_user_locks():
    draft = deepcopy(SCENES[0]['draft'])
    draft['name'] = 'Моё название после сохранения'
    draft['fields']['shot'] = {'ru': 'только лицо целиком', 'en': 'whole face only'}
    draft['locks'] = ['lighting']
    result = generate_variants(draft)
    assert result['status'] == 'complete'
    for variant in result['variants']:
        assert variant['draft']['fields']['lighting'] == draft['fields']['lighting']
        assert variant['draft']['fields']['shot']['en'].startswith('whole face only')


def test_scene_cursor_and_saved_variant_remain_scene_relative():
    draft = deepcopy(SCENES[0]['draft'])
    first = generate_variants(draft)
    draft['selection_seed'] = first['next_seed']
    second = generate_variants(draft)
    assert len({v['en'] for v in first['variants'] + second['variants']}) == 14
    saved = deepcopy(second['variants'][1]['draft'])
    assert all(v['draft']['fields']['style'] == saved['fields']['style'] for v in generate_variants(saved)['variants'])


def test_ambiguous_scene_signature_uses_general_pools_not_arbitrary_recipe():
    draft = deepcopy(SCENES[0]['draft'])
    duplicate = deepcopy(SCENES[0])
    duplicate['id'] = 'duplicate'
    data = catalogue()
    data['templates'].append(duplicate)
    with patch('prompt_composer.engine.catalogue', return_value=data):
        result = generate_variants(draft)
    assert result['status'] == 'complete'
    assert any(v['draft']['fields']['style'] != draft['fields']['style'] for v in result['variants'])


@pytest.mark.parametrize('keys', [('shot',), ('shot', 'lighting', 'angle')])
def test_max_length_fields_produce_only_valid_savable_variants(keys):
    from prompt_composer.model import FIELD_TEXT_LIMIT, validate_draft
    draft = deepcopy(SCENES[0]['draft'])
    for key in keys:
        draft['fields'][key] = {'ru': 'я' * FIELD_TEXT_LIMIT, 'en': 'x' * FIELD_TEXT_LIMIT}
    result = generate_variants(draft)
    assert result['variants']
    for variant in result['variants']:
        validate_draft(variant['draft'])
        for key in keys:
            assert variant['draft']['fields'][key] == draft['fields'][key]
    if len(keys) == 3:
        assert result['status'] == 'insufficient'


def test_saved_relative_adjustments_are_replaced_not_accumulated():
    template = SCENES[0]
    first = generate_variants(template['draft'])
    saved = next(v['draft'] for v in first['variants'] if 'shift to the left' in v['draft']['fields']['angle']['en'])
    original = deepcopy(saved)
    second = generate_variants(saved)
    assert len(second['variants']) == 7
    for variant in second['variants']:
        for key in ('shot', 'angle', 'lighting'):
            for lang in ('ru', 'en'):
                text = variant['draft']['fields'][key][lang]
                assert sum(text.count(suffix[lang]) for suffix in template['variation_options'][key] if suffix[lang]) <= 1
    assert saved == original
    saved['locks'] = ['angle']
    assert all(v['draft']['fields']['angle'] == saved['fields']['angle'] for v in generate_variants(saved)['variants'])
