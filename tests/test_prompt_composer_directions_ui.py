"""Approved directions, hero preservation and actual Qt navigation, offline."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox, QPushButton

from prompt_composer.catalog import catalogue
from prompt_composer.model import new_draft, validate_draft
from prompt_composer.ui import PromptComposerPage
from studio_prompt_composer_host import PromptComposerHost
from studio_asset_api import AssetHandle


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(app, tmp_path):
    host = PromptComposerHost(tmp_path, settings_provider=lambda: {}, authorize=lambda: True)
    widget = PromptComposerPage(host)
    widget.resize(1120, 780)
    widget.show()
    app.processEvents()
    yield widget
    widget.hide()
    host.close()
    widget.deleteLater()
    app.processEvents()


def scene(category='products', mode='image'):
    return next(t for t in catalogue()['templates'] if t.get('reusable') and t['category'] == category and t['draft']['mode'] == mode)


def flush(app):
    app.processEvents()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def click(page, app, name):
    QTest.mouseClick(page.findChild(QPushButton, name), Qt.MouseButton.LeftButton)
    flush(app)


def select_first_scenario(page, app):
    if page.findChild(QPushButton, 'template0') is None:
        click(page, app, 'direction0')
    click(page, app, 'template0')


@pytest.mark.parametrize('mode', ['image', 'reels'])
def test_real_category_clicks_filter_cards_without_changing_draft(page, app, mode):
    page.draft['mode'] = mode
    page._render()
    before = deepcopy(page.draft)
    for category in catalogue()['categories']:
        QTest.mouseClick(page.findChild(QPushButton, 'category_' + category['id']), Qt.MouseButton.LeftButton)
        app.processEvents()
        assert page.draft == before
        assert sum(b.isChecked() for b in page.findChildren(QPushButton) if b.objectName().startswith('category_')) == 1
        cards = [b for b in page.findChildren(QPushButton) if b.objectName().startswith('direction')]
        expected = [t for t in catalogue()['directions'] if t['category'] == category['id']]
        assert {b.property('directionId') for b in cards} == {t['id'] for t in expected}
        for button in cards:
            assert button.accessibleName()
            assert button.mapTo(page, QPoint()).y() + button.height() < 720


def test_upper_tabs_centered_in_both_views(page, app):
    for tab in ['composer', 'library']:
        page._show_tab(tab)
        app.processEvents()
        left, right = page.composer_tab, page.library_tab
        center = (left.mapTo(page, QPoint()).x() + right.mapTo(page, QPoint()).x() + right.width()) / 2
        assert abs(center - page.width() / 2) < 2


@pytest.mark.parametrize('mode', ['image', 'reels'])
def test_all_directions_open_five_scenarios_and_return_without_changing_draft(page, app, mode):
    page._set_mode(mode)
    before = deepcopy(page.draft)
    for direction in catalogue()['directions']:
        page._select_template_category(direction['category'])
        flush(app)
        button = next(b for b in page.findChildren(QPushButton) if b.property('directionId') == direction['id'])
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        flush(app)
        assert page._step == 0 and page.draft == before
        cards = [b for b in page.findChildren(QPushButton) if b.property('templateId')]
        assert len(cards) == 5
        expected = {t['id'] for t in catalogue()['templates'] if t.get('direction') == direction['id'] and t['category'] == direction['category'] and t['draft']['mode'] == mode}
        assert {b.property('templateId') for b in cards} == expected
        click(page, app, 'template0')
        assert page._pending_template_id in expected and page.draft == before
        click(page, app, 'directionsBack')
        assert page._pending_template_id is None
        assert page._template_direction is None and page.draft == before


def test_mode_change_and_custom_path_reset_nested_navigation(page, app):
    select_first_scenario(page, app)
    click(page, app, 'mode_reels')
    assert page._template_direction is None and page._pending_template_id is None
    assert page.findChild(QPushButton, 'direction0') is not None
    select_first_scenario(page, app)
    click(page, app, 'start_custom')
    assert page._template_direction is None and page._pending_template_id is None
    click(page, app, 'start_template')
    assert page.findChild(QPushButton, 'direction0') is not None


def test_direction_without_scenario_allows_next_without_applying_defaults(page, app):
    page.draft['manual_en'] = 'My own prompt'
    before = deepcopy(page.draft)
    click(page, app, 'direction0')
    with patch.object(page, 'apply_template', side_effect=AssertionError('No scenario selected')):
        click(page, app, 'nextButton')
    assert page._step == 1 and page.draft == before


@pytest.mark.parametrize('mode', ['image', 'reels'])
def test_card_real_mouse_click_preserves_custom_object_and_protections(page, app, mode):
    page.draft['mode'] = mode
    page.draft['subject_type'] = 'product'
    fields = {
        'subject': {'ru': 'кожаная сумка', 'en': 'leather handbag'},
        'appearance': {'ru': 'два коротких ремешка', 'en': 'two short straps'},
        'material': {'ru': 'натуральная кожа', 'en': 'natural leather'},
        'color': {'ru': 'бордовый', 'en': 'burgundy'},
        'exclusions': {'ru': 'лишние застёжки', 'en': 'extra fasteners'},
        'location': {'ru': 'своя студия', 'en': 'own studio'},
    }
    page.draft['fields'] = deepcopy(fields)
    page.draft['locks'] = ['location']
    page.draft['profile_id'] = 'own-profile'
    page._select_template_category('products')
    before = deepcopy(page.draft)
    select_first_scenario(page, app)
    assert page._step == 0 and page.draft == before
    assert page._pending_template_id == page.findChild(QPushButton, 'template0').property('templateId')
    click(page, app, 'nextButton')
    assert page._step == 1
    for key, value in fields.items():
        assert page.draft['fields'][key] == value
    assert page.draft['profile_id'] == 'own-profile'
    assert page.draft['subject_type'] == 'product'
    assert page.draft['locks'] == ['location']
    validate_draft(page.draft)
    assert page.host.generate(page.draft)['status'] == 'complete'


def test_custom_path_discards_pending_selection_and_preserves_full_draft(page, app):
    page.draft['manual_ru'] = 'Мой ручной промпт'
    page.draft['profile_id'] = 'own-profile'
    page.draft['locks'] = ['color']
    before = deepcopy(page.draft)
    select_first_scenario(page, app)
    assert page._pending_template_id
    click(page, app, 'start_custom')
    assert page._pending_template_id is None
    assert page.draft == before
    assert page.findChild(QPushButton, 'template0') is None
    assert page.findChild(QPushButton, 'category_people') is None
    assert page.findChild(QPushButton, 'mode_image').isChecked()
    assert page.findChild(QPushButton, 'start_custom').isChecked()
    assert not page.findChild(QPushButton, 'start_template').isChecked()
    assert page.findChild(QPushButton, 'nextButton').text() == 'Далее'
    with patch.object(page, '_guard_manual_rebuild', side_effect=AssertionError('Navigation must not rebuild manual text')):
        click(page, app, 'nextButton')
    assert page._step == 1 and page.draft == before
    click(page, app, 'previousButton')
    assert page._step == 0 and page.draft == before
    assert page.findChild(QPushButton, 'start_custom').isChecked()


def test_pending_template_cancel_guard_keeps_selection_and_draft(page, app):
    page.draft['manual_en'] = 'My literal prompt'
    before = deepcopy(page.draft)
    with patch.object(page, '_guard_manual_rebuild', side_effect=AssertionError('Selecting a card must not rebuild')):
        select_first_scenario(page, app)
    pending = page._pending_template_id
    with patch.object(page, '_guard_manual_rebuild', return_value=False):
        assert page.goto_step(1) is False
    assert page._step == 0 and page.draft == before
    assert page._pending_template_id == pending


@pytest.mark.parametrize('control', ['category_products', 'mode_reels'])
def test_changing_filter_clears_pending_card(page, app, control):
    select_first_scenario(page, app)
    assert page._pending_template_id
    click(page, app, control)
    assert page._pending_template_id is None
    before = deepcopy(page.draft)
    click(page, app, 'nextButton')
    assert page._step == 1 and page.draft == before


def test_direct_step_navigation_applies_pending_once_and_keeps_later_edits(page, app):
    select_first_scenario(page, app)
    with patch.object(page, 'apply_template', wraps=page.apply_template) as apply:
        QTest.mouseClick(page.step_buttons[2], Qt.MouseButton.LeftButton)
        flush(app)
        assert page._step == 2 and apply.call_count == 1
        page._set_field('location', 'Моя студия', 'My studio')
        before = deepcopy(page.draft)
        page.goto_step(0)
        flush(app)
        click(page, app, 'nextButton')
        assert page._step == 1 and page.draft == before
        assert apply.call_count == 1


def test_start_path_and_mode_selections_are_independent(page, app):
    click(page, app, 'start_custom')
    click(page, app, 'mode_reels')
    assert page.findChild(QPushButton, 'start_custom').isChecked()
    assert page.findChild(QPushButton, 'mode_reels').isChecked()
    click(page, app, 'start_template')
    assert page.findChild(QPushButton, 'start_template').isChecked()
    assert page.findChild(QPushButton, 'mode_reels').isChecked()
    assert page.draft['mode'] == 'reels'


def test_custom_person_keeps_clothes_and_references(page):
    page.draft['subject_type'] = 'person'
    page.draft['fields'] = {'subject': {'ru': 'женщина с короткой стрижкой', 'en': 'woman with short hair'}, 'wardrobe': {'ru': 'синий костюм', 'en': 'blue suit'}}
    page.draft['references'] = [AssetHandle('a' * 64, 'a' * 64, 64, 'reference.png', 'image/png').to_dict()]
    references = deepcopy(page.draft['references'])
    assert page.apply_template(scene('people'))
    assert page.draft['fields']['wardrobe']['en'] == 'blue suit'
    assert page.draft['fields']['subject']['en'] == 'woman with short hair'
    assert page.draft['references'] == references
    validate_draft(page.draft)


def test_incompatible_scene_leaves_custom_hero_unchanged(page):
    page.draft['subject_type'] = 'product'
    page.draft['fields']['subject'] = {'ru': 'сумка', 'en': 'handbag'}
    before = deepcopy(page.draft)
    with patch.object(page, '_show_message') as message:
        assert not page.apply_template(scene('people'))
    assert page.draft == before
    assert message.call_count == 1


def test_fresh_placeholder_allows_scene_subject_type(page):
    page.draft = new_draft()
    assert page.apply_template(scene('people'))
    assert page.draft['subject_type'] == 'person'


def test_cancel_manual_text_guard_is_atomic(page, app):
    page.draft['manual_ru'] = 'Мой самостоятельный текст'
    before = deepcopy(page.draft)
    def cancel_dialog():
        dialog = QApplication.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        dialog.reject()
    QTimer.singleShot(0, cancel_dialog)
    assert not page.apply_template(scene('products'))
    app.processEvents()
    assert page.draft == before


def test_signed_catalogue_has_no_clipart_direction():
    assert len(catalogue()['categories']) == 6
    assert all('клипарт' not in c['label'].lower() for c in catalogue()['categories'])


def test_neutral_template_hero_can_switch_sections_until_user_edits(page):
    assert page.apply_template(scene('people'))
    assert page.apply_template(scene('products'))
    assert page.apply_template(scene('animals'))
    page._set_field('subject', 'полосатый кот', 'striped cat')
    before = deepcopy(page.draft)
    with patch.object(page, '_show_message'):
        assert not page.apply_template(scene('products'))
    assert page.draft == before


def test_reference_or_subject_lock_protects_even_neutral_placeholder(page):
    assert page.apply_template(scene('people'))
    page.draft['locks'] = ['subject']
    before = deepcopy(page.draft)
    with patch.object(page, '_show_message'):
        assert not page.apply_template(scene('products'))
    assert page.draft == before


@pytest.mark.parametrize('field', ['appearance', 'wardrobe', 'material', 'color'])
def test_editing_identity_makes_neutral_hero_user_defined(page, field):
    assert page.apply_template(scene('people'))
    page._set_field(field, 'своё описание', 'own description')
    before = deepcopy(page.draft)
    with patch.object(page, '_show_message'):
        assert not page.apply_template(scene('products'))
    assert page.draft == before


def test_applying_profile_makes_neutral_hero_user_defined(page):
    assert page.apply_template(scene('people'))
    payload = deepcopy(page.draft)
    payload['fields']['appearance'] = {'ru': 'голубые глаза и веснушки', 'en': 'blue eyes and freckles'}
    record = page.host.save(payload, {'name': 'Мой человек', 'tags': [], 'favorite': False, 'kind': 'profile'})
    with patch('prompt_composer.ui.QInputDialog.getItem', return_value=('Мой человек', True)):
        assert page.choose_profile()
    assert page.draft['profile_id'] == record['id']
    before = deepcopy(page.draft)
    with patch.object(page, '_show_message'):
        assert not page.apply_template(scene('products'))
    assert page.draft == before


def test_decorative_edit_does_not_lock_neutral_hero_to_section(page):
    assert page.apply_template(scene('people'))
    page._set_field('location', 'светлая студия', 'bright studio')
    assert page.apply_template(scene('products'))
