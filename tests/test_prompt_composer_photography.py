"""Concrete, subject-aware shooting briefs without extra provider calls."""
from copy import deepcopy
import json
import re

import pytest

from prompt_composer.catalog import apply_template, catalogue
from prompt_composer.engine import generate_variants
from prompt_composer.model import FIELD_TEXT_LIMIT, validate_draft
from studio_prompt_composer_ai import request_body, validate_response
from tests.test_prompt_composer_ai import MODEL, reply


def recipe(category, direction, scene, mode='image'):
    return apply_template(f'scene_{category}_v2_{direction}_{scene}_{mode}')


def test_all_current_scenarios_have_concrete_editable_bilingual_direction():
    current = [t for t in catalogue()['templates'] if t.get('direction')]
    assert len(current) == 250
    for template in current:
        draft = template['draft']
        assert validate_draft(draft) == draft
        fields = draft['fields']
        assert draft['locks'] == [] and 'time' not in fields
        text = json.dumps(fields, ensure_ascii=False)
        assert 'appropriate to the selected scene' not in text
        assert 'consistent with selected framing' not in text
        assert all(len(pair[lang]) <= FIELD_TEXT_LIMIT
                   for pair in fields.values() for lang in ('ru', 'en'))
        assert re.search(r'\d+(?:mm| мм)', fields['camera']['en'] + fields['camera']['ru'])
        assert not re.search('[А-Яа-яЁё]', ''.join(pair['en'] for pair in fields.values()))
        assert not any(k in fields for k in ('appearance', 'wardrobe', 'material', 'color'))


@pytest.mark.parametrize('category,direction,scene,lens,focus', [
    ('people', 'portrait', 'people_portrait_01', '85mm', 'eyes'),
    ('people', 'portrait', 'people_portrait_04', '50mm', 'depth of field'),
    ('products', 'catalogue', 'products_catalogue_02', '85mm', 'interaction area'),
    ('spaces', 'interior', 'interior_room_overview', '24mm', 'depth of field'),
    ('animals', 'portrait', 'animal_face_portrait', '85mm', 'animal eyes'),
    ('nature', 'detail', 'nature_leaf_detail', '100mm macro', 'action detail'),
    ('people', 'ugc', 'people_ugc_01', '26mm', 'eyes'),
])
def test_lens_focus_and_rendering_follow_subject_and_framing(category, direction, scene, lens, focus):
    draft = recipe(category, direction, scene)
    result = generate_variants(draft)
    assert result['status'] == 'complete'
    first = result['variants'][0]
    assert lens in first['en'] and focus in first['en']
    assert first['en'].count('\n\n') >= 4
    assert len({v['draft']['fields']['style']['en'] for v in result['variants']}) >= 2
    for v in result['variants']:
        assert len(v['en']) < 12000 and len(v['ru']) < 12000
        if category in ('products', 'spaces', 'nature'):
            assert 'skin' not in v['en'] and 'facial' not in v['en']
        if direction == 'ugc':
            assert 'phone' in v['en'] and 'studio styling' not in v['en'].replace('without studio styling', '')


def test_flatlay_evening_and_profile_do_not_receive_conflicting_defaults():
    flatlay = recipe('products', 'composition', 'products_composition_01')
    assert 'directly overhead' in flatlay['fields']['angle']['en']
    assert 'eye-level' not in flatlay['fields']['angle']['en']
    evening = recipe('spaces', 'atmosphere', 'atmosphere_evening_room', 'reels')
    assert 'warm light from existing interior sources' in evening['fields']['lighting']['en']
    assert 'time' not in evening['fields']
    assert 'pans' in evening['fields']['camera']['en']
    profile = recipe('people', 'portrait', 'people_portrait_05')
    assert 'side view' in profile['fields']['angle']['en']
    makeup = recipe('people', 'beauty', 'people_beauty_03')
    assert 'specified makeup detail' in makeup['fields']['shot']['en']
    assert 'focus on the eyes' not in makeup['fields']['shot']['en']


def test_user_camera_framing_locks_and_saved_treatments_survive_new_generation():
    draft = recipe('products', 'catalogue', 'products_catalogue_02')
    draft['fields']['subject'] = {'ru': 'моя синяя чашка', 'en': 'my blue cup'}
    draft['fields']['camera'] = {'ru': 'только объектив 50 мм', 'en': '50mm lens only'}
    draft['fields']['lighting'] = {'ru': 'только пасмурный свет', 'en': 'overcast light only'}
    draft['locks'] = ['camera', 'lighting', 'shot']
    before = deepcopy(draft)
    first = generate_variants(draft)
    assert first['status'] == 'complete'
    assert draft == before
    for v in first['variants']:
        for key in ('subject', 'camera', 'lighting', 'shot'):
            assert v['draft']['fields'][key] == before['fields'][key]
        assert '85mm' not in v['en'] and 'overcast light only' in v['en']
    saved = deepcopy(first['variants'][1]['draft'])
    saved['selection_seed'] = 0
    again = generate_variants(saved)
    base_style = draft['fields']['style']
    for v in again['variants']:
        for lang in ('ru', 'en'):
            assert v['draft']['fields']['style'][lang].startswith(base_style[lang])
            assert v['draft']['fields']['style'][lang].count(base_style[lang]) == 1
        assert v['draft']['fields']['camera'] == draft['fields']['camera']


def test_previous_catalogue_saved_style_and_adjustments_keep_their_scene():
    template = next(t for t in catalogue()['templates'] if t.get('scenario_id') == 'people_portrait_01'
                    and t['draft']['mode'] == 'image')
    saved = deepcopy(template['draft'])
    saved['fields']['style'] = deepcopy(template['style_aliases'][0])
    saved['fields']['camera'] = {'ru': 'моя сохранённая камера', 'en': 'my saved camera'}
    old_suffix = template['legacy_variation_options']['shot'][1]
    base_shot = {'ru': 'Мой сохранённый портрет', 'en': 'My saved portrait'}
    saved['fields']['shot'] = {lang: base_shot[lang] + old_suffix[lang] for lang in ('ru', 'en')}
    saved['selection_seed'] = 7
    before = deepcopy(saved)
    result = generate_variants(saved)
    assert saved == before and result['status'] == 'complete'
    assert len({v['en'] for v in result['variants']}) == 7
    for variant in result['variants']:
        for lang in ('ru', 'en'):
            assert variant['draft']['fields']['style'][lang].startswith(saved['fields']['style'][lang])
            assert variant['draft']['fields']['shot'][lang].startswith(base_shot[lang])
            assert variant['draft']['fields']['shot'][lang].count(old_suffix[lang]) <= 1
        assert variant['draft']['fields']['camera'] == saved['fields']['camera']


def test_video_shooting_keeps_the_original_single_motion_with_stable_focus():
    draft = recipe('products', 'composition', 'products_composition_01', 'reels')
    assert 'glides' in draft['fields']['camera']['en']
    assert 'stable exposure and focus' in draft['fields']['camera']['en']
    for variant in generate_variants(draft)['variants']:
        assert variant['draft']['fields']['camera'] == draft['fields']['camera']
        assert variant['draft']['fields']['action'] == draft['fields']['action']
        assert not variant['warnings']


@pytest.mark.parametrize('time', [None, {'ru': 'вечер', 'en': 'evening'}])
def test_custom_style_fallback_never_invents_or_changes_time(time):
    draft = recipe('spaces', 'atmosphere', 'atmosphere_evening_room')
    draft['fields']['style'] = {'ru': 'моя интерьерная подача', 'en': 'my interior treatment'}
    if time is not None:
        draft['fields']['time'] = deepcopy(time)
    result = generate_variants(draft)
    assert result['status'] == 'complete'
    for variant in result['variants']:
        assert variant['draft']['fields']['time'] == (time or {'ru': '', 'en': ''})
        assert 'morning' not in variant['en']


@pytest.mark.parametrize('key', ['appearance', 'wardrobe', 'material', 'color', 'location',
                                 'surface', 'action', 'duration', 'aspect', 'time'])
def test_ai_cannot_rewrite_existing_subject_or_scene_facts(key):
    draft = recipe('people', 'portrait', 'people_portrait_01')
    draft['fields'][key] = {'ru': 'моё точное значение', 'en': 'my exact specified value'}
    value = reply(draft)
    validate_response(value, draft)
    value['variants'][0]['fields'][key]['en'] = 'a newly invented value'
    with pytest.raises(ValueError, match='AI изменил'):
        validate_response(value, draft)


def test_ai_brief_requires_concrete_coherent_shooting_not_keyword_padding():
    draft = recipe('products', 'ugc', 'products_ugc_01', 'reels')
    body = request_body(draft, 'openrouter', MODEL)
    instruction = body['messages'][0]['content']
    for requirement in ('photographer and cinematographer', 'depth', 'light direction', 'material texture',
                        'distinct compatible photographic emphasis', 'without studio polish',
                        'one feasible', 'no extra actions', 'camera brands', 'invented facts',
                        'Keep unlocked shooting fields concise', 'never shorten protected source-language values'):
        assert requirement in instruction
    source = json.loads(body['messages'][1]['content'])
    assert source['fields'] == draft['fields']
    assert body['max_tokens'] == 12000


def test_variant_names_show_the_changed_treatment_instead_of_the_shared_prefix():
    draft = recipe('people', 'portrait', 'people_portrait_01')
    variants = generate_variants(draft)['variants']
    names = [v['label'].split(': ', 1)[1] for v in variants if ': ' in v['label']]
    assert any(name.startswith('эмоциональный акцент') for name in names)
    assert any(name.startswith('редакционный акцент') for name in names)
    assert all(not name.startswith('выразительная портретная фотография') for name in names)
    assert all(name.strip() and not name.startswith(',') for name in names)
