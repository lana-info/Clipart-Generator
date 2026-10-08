"""Approved nested recipes, semantic regressions and preserved saved identifiers."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from prompt_composer.catalog import apply_template, catalogue
from prompt_composer.directions import SCENARIOS
from prompt_composer.model import FIELD_TEXT_LIMIT, validate_draft

ARTIFACTS = Path(__file__).resolve().parents[1] / 'docs/ui/3.1/composer-directions-20261007'


def recipes(category, direction, mode):
    return [t for t in catalogue()['templates'] if t.get('direction') == direction
            and t['category'] == category and t['draft']['mode'] == mode]


def test_all_directions_have_five_distinct_bilingual_scenarios_in_both_modes():
    data = catalogue()
    assert len(data['directions']) == 25
    assert len({(d['category'], d['id']) for d in data['directions']}) == 25
    assert {d['category'] for d in data['directions']} == {c['id'] for c in data['categories']}
    for direction in data['directions']:
        per_mode = [recipes(direction['category'], direction['id'], mode) for mode in ('image', 'reels')]
        assert [len(group) for group in per_mode] == [5, 5]
        assert {t['scenario_id'] for t in per_mode[0]} == {t['scenario_id'] for t in per_mode[1]}
        for group in per_mode:
            assert len({t['label'] for t in group}) == 5
            assert len({t['draft']['fields']['action']['en'] for t in group}) == 5
            for template in group:
                draft = template['draft']
                validate_draft(draft)
                assert not draft['locks']
                assert not {'appearance', 'wardrobe', 'color', 'material'} & draft['fields'].keys()
                for key in ('subject', 'style', 'lighting', 'shot', 'angle', 'camera', 'location', 'action', 'exclusions'):
                    pair = draft['fields'][key]
                    assert set(pair) == {'ru', 'en'}
                    assert all(0 < len(text) <= FIELD_TEXT_LIMIT for text in pair.values())
                if draft['mode'] == 'image':
                    assert 'duration' not in draft['fields']
                    assert all(word not in draft['fields']['camera']['en'] for word in ('moves', 'pans', 'tracks', 'glides'))
                else:
                    assert draft['fields']['duration']['en'] == '8 seconds'
        for image, reels in zip(*per_mode):
            assert image['draft']['fields']['action'] != reels['draft']['fields']['action']


def test_direction_and_scenario_cards_match_the_approved_mockups():
    outline = json.loads((ARTIFACTS / 'nested-approved-outline.json').read_text())
    data = catalogue()
    for category, expected in outline['groups'].items():
        assert [(d['id'], d['label'], d['description']) for d in data['directions'] if d['category'] == category] == [tuple(x) for x in expected]
    for group in outline['scenarios']:
        actual = recipes(group['category'], group['direction'], group['mode'])
        assert [(t['label'], t['description']) for t in actual] == [tuple(x) for x in group['cards']]


def test_all_previous_69_recipes_keep_exact_payload_and_loadable_ids():
    hashes = json.loads((ARTIFACTS / 'legacy-recipe-sha256-before-nesting.json').read_text())
    previous = {t['id']: t for t in catalogue()['templates'] if not t.get('direction')}
    assert len(hashes) == len(previous) == 69
    for identifier, expected_hash in hashes.items():
        actual = hashlib.sha256(json.dumps(previous[identifier], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        assert actual == expected_hash, identifier
        assert apply_template(identifier) == previous[identifier]['draft']


def test_camera_actions_and_viewpoints_are_consistent_after_review():
    for category, direction, identifier in [
        ('nature', 'detail', 'nature_texture_detail'),
        ('nature', 'travel', 'travel_first_person_path'),
        ('food', 'cooking', 'cooking_finished_result'),
        ('animals', 'portrait', 'animal_portrait_surroundings'),
        ('products', 'composition', 'products_composition_01'),
    ]:
        template = next(t for t in recipes(category, direction, 'reels') if t['scenario_id'] == identifier)
        fields = template['draft']['fields']
        assert 'locked' not in fields['camera']['en']
        assert not fields['action']['en'].startswith('The camera')
        assert 'consistent with selected framing' in fields['angle']['en']
    nature = recipes('nature', 'travel', 'reels')
    assert all('facades' not in t['draft']['fields']['lighting']['en'] for t in nature)
    path = next(t for t in nature if t['scenario_id'] == 'travel_first_person_path')
    assert 'along one street' not in path['draft']['fields']['camera']['en']
    assert 'path' in path['draft']['fields']['camera']['en']


def test_animals_remain_generic_and_use_scenario_actually_uses_product():
    animal = next(t for t in recipes('animals', 'story', 'reels') if t['scenario_id'] == 'animal_toy_focus')
    assert 'paw' not in animal['draft']['fields']['action']['en']
    assert 'natural to it' in animal['draft']['fields']['action']['en']
    use = recipes('products', 'catalogue', 'reels')[3]
    assert use['label'] == 'Способ использования'
    assert 'as intended' in use['draft']['fields']['action']['en']
    rest = recipes('products', 'lifestyle', 'reels')[3]
    assert rest['draft']['fields']['action']['en'].startswith('a person')


def test_new_catalogue_metadata_does_not_leak_mutations():
    source = deepcopy(SCENARIOS)
    data = catalogue()
    data['directions'][0]['label'] = 'tampered'
    data['templates'][-1]['draft']['fields']['action']['en'] = 'tampered'
    assert catalogue()['directions'][0]['label'] != 'tampered'
    assert catalogue()['templates'][-1]['draft']['fields']['action']['en'] != 'tampered'
    assert SCENARIOS == source
