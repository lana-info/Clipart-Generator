import copy
import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QEventLoop, QTimer

from studio_clipart_builder_ui import ClipartBuilderDialog
from studio_clipart_objects import TEXT_FIELDS, fill_recipe
from studio_clipart_planner import planning_request
from studio_planning_ui import PlanningWorker
from studio_text_pricing import fetch_text_tariff
from studio_text_client import TextGenerationError
from v3_project_state import ProjectState


@pytest.fixture
def builder(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('v3_api_settings.load_credentials', lambda: {'openrouter_api_key': 'dummy-key'})
    dialog = ClipartBuilderDialog(ProjectState().clipart)
    dialog.theme.setText('Мишки и самолёты')
    dialog.object_editor.items = fill_recipe([], dialog.recipe.counts)
    dialog.object_editor.refresh()
    dialog.planning.provider.setCurrentIndex(1)
    dialog.planning.model.setCurrentIndex(dialog.planning.model.findData('openai/gpt-5-mini'))
    yield dialog
    dialog.reject()
    app.processEvents()


def queued(panel):
    jobs = []
    panel._run = lambda work, callback: jobs.append((work, callback))
    return jobs


def test_provider_filter_and_save_selection(builder):
    panel = builder.planning
    assert panel.model.count() == 10  # Nine routes and a disabled group heading.
    panel.provider.setCurrentIndex(0)
    assert panel.model.count() == 2
    jobs = queued(panel)
    panel.start(False)
    assert not jobs
    assert 'ключ kie' in panel.status.text().lower()
    panel.provider.setCurrentIndex(1)
    panel.model.setCurrentIndex(panel.model.findData('openai/gpt-5-mini'))
    builder._apply()
    assert builder.data.recipe['assistant']['model'] == 'openai/gpt-5-mini'
    assert 'dummy-key' not in json.dumps(builder.data.to_dict())


def test_declined_quote_never_generates(builder, monkeypatch):
    jobs = queued(builder.planning)
    displayed = []
    def decline(*args):
        displayed.append(args[1])
        return False
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', decline)
    builder.planning.start(False)
    jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
    assert len(jobs) == 1
    assert builder.planning.pending is None
    assert 'Ориентировочная стоимость запроса: $' in displayed[0]
    assert 'Тариф за 1 млн' not in displayed[0]
    assert 'OpenRouter · GPT-5 mini' in displayed[0]
    assert 'Запросов: 1.' in displayed[0]


def test_cancel_quote_discards_and_does_not_prompt(builder, monkeypatch):
    jobs = queued(builder.planning)
    question = MagicMock()
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', question)
    builder.planning.start(False)
    builder.planning.cancel()
    jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
    question.assert_not_called()


def test_edit_during_quote_prevents_paid_request(builder, monkeypatch):
    jobs = queued(builder.planning)
    question = MagicMock()
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', question)
    builder.planning.start(False)
    builder.theme.setText('Другая тема')
    jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
    question.assert_not_called()
    assert len(jobs) == 1
    assert builder.planning.pending is None


def test_mocked_handoff_and_stale_result(builder, monkeypatch):
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: True)
    for stale in (False, True):
        jobs = queued(builder.planning)
        before = copy.deepcopy(builder.object_editor.items)
        recipe, palette = builder._planning_snapshot()
        req = planning_request(recipe, palette)
        rows = [dict(id=item['id'], **dict.fromkeys(TEXT_FIELDS, 'Мишка')) for item in before]
        builder.planning.start(False)
        jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
        assert len(jobs) == 2
        if stale:
            builder.theme.setText('Новая тема')
        jobs[1][1](dict(request=req, suggestions=rows), None)
        if stale:
            assert builder.object_editor.items == before
            assert 'изменились' in builder.planning.status.text()
        else:
            assert builder.object_editor.items[0]['name'] == 'Мишка'


def test_pinned_single_has_no_network(builder):
    builder.object_editor.pinned.setChecked(True)
    jobs = queued(builder.planning)
    builder.planning.start(True)
    assert not jobs
    assert 'закреплённый' in builder.planning.status.text()


def test_worker_delivers_on_event_loop(builder):
    loop = QEventLoop()
    worker = PlanningWorker(lambda: 42)
    received = []
    worker.signals.completed.connect(lambda value, error: (received.append(value), loop.quit()))
    from PyQt6.QtCore import QThreadPool
    QThreadPool.globalInstance().start(worker)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    assert received == [42]


def test_tariff_read_and_invalid_price(monkeypatch):
    response = MagicMock()
    response.status_code = 200
    get = MagicMock()
    get.return_value.__enter__.return_value = response
    monkeypatch.setattr('studio_text_pricing.requests.get', get)
    for price in ('0.00000025', '-1', 'NaN'):
        response.iter_content.return_value = [json.dumps({'data': [dict(id='openai/gpt-5-mini',
            pricing=dict(prompt=price, completion='0.000002', request='0'))]}).encode()]
        if price == '0.00000025':
            assert fetch_text_tariff('openai/gpt-5-mini', 'dummy') == dict(prompt=.25, completion=2., request=0.)
        else:
            with pytest.raises(TextGenerationError):
                fetch_text_tariff('openai/gpt-5-mini', 'dummy')



def test_reference_image_capability_preflight_blocks_text_only_model(builder, monkeypatch, tmp_path):
    from PIL import Image
    ref = tmp_path / 'vision.png'
    Image.new('RGB', (20, 20), (20, 30, 40)).save(ref)
    builder.reference_editor.add_reference(ref)
    builder.reference_editor.send_image_radio.setChecked(True)
    jobs = queued(builder.planning)
    question = MagicMock()
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', question)
    builder.planning.start(False)
    assert len(jobs) == 1
    assert builder.reference_editor.selected_ai_image_paths() == (str(ref.resolve()),)
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text',)), None)
    question.assert_not_called()
    assert len(jobs) == 1
    assert builder.reference_editor.selected_ai_image_paths() == (str(ref.resolve()),)
    assert 'изображ' in builder.planning.status.text().casefold()


def test_reference_image_quote_names_files_and_is_one_shot(builder, monkeypatch, tmp_path):
    from PIL import Image
    ref = tmp_path / 'teddy-reference.png'
    Image.new('RGB', (20, 20), (20, 30, 40)).save(ref)
    builder.reference_editor.add_reference(ref)
    builder.reference_editor.send_image_radio.setChecked(True)
    jobs = queued(builder.planning)
    prompts = []
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: prompts.append(args[1]) or False)
    builder.planning.start(False)
    self_info = dict(prompt=.25, completion=2., request=0., input_modalities=('text','image'))
    assert builder.reference_editor.selected_ai_image_paths() == (str(ref.resolve()),)
    jobs[0][1](self_info, None)
    assert prompts and 'teddy-reference.png' in prompts[0]
    assert '1' in prompts[0]
    assert builder.reference_editor.selected_ai_image_paths() == ()



def test_reference_image_consent_clears_only_after_positive_confirmation(builder, monkeypatch, tmp_path):
    from PIL import Image
    ref = tmp_path / 'confirmed-reference.png'
    Image.new('RGB', (20, 20), (20, 30, 40)).save(ref)
    builder.reference_editor.add_reference(ref)
    builder.reference_editor.send_image_radio.setChecked(True)
    jobs = queued(builder.planning)
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: True)
    builder.planning.start(False)
    assert builder.reference_editor.selected_ai_image_paths() == (str(ref.resolve()),)
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text','image')), None)
    assert len(jobs) == 2
    assert builder.reference_editor.selected_ai_image_paths() == ()



def test_reference_image_change_after_confirmation_stops_before_network(builder, monkeypatch, tmp_path):
    from PIL import Image
    ref = tmp_path / 'changing-reference.png'
    Image.new('RGB', (20, 20), (20, 30, 40)).save(ref)
    builder.reference_editor.add_reference(ref)
    builder.reference_editor.send_image_radio.setChecked(True)
    jobs = queued(builder.planning)
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: True)
    post = MagicMock(side_effect=AssertionError('network must not run for changed reference'))
    monkeypatch.setattr('studio_text_client.requests.post', post)
    builder.planning.start(False)
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text','image')), None)
    assert len(jobs) == 2
    Image.new('RGB', (20, 20), (200, 30, 40)).save(ref)
    with pytest.raises(TextGenerationError, match='измен'):
        jobs[1][0]()
    post.assert_not_called()



def test_planning_panel_copy_says_images_are_opt_in(builder):
    text = builder.planning.status.text().casefold()
    assert 'по умолчанию' in text
    assert 'явн' in text
    assert 'изображ' in text


def test_model_info_exposes_live_input_modalities(monkeypatch):
    from studio_text_pricing import fetch_text_model_info
    response = MagicMock(); response.status_code = 200
    response.iter_content.return_value = [json.dumps({'data': [dict(
        id='openai/gpt-5-mini',
        pricing=dict(prompt='0.00000025', completion='0.000002', request='0'),
        architecture=dict(input_modalities=['text', 'image']),
    )]}).encode()]
    get = MagicMock(); get.return_value.__enter__.return_value = response
    monkeypatch.setattr('studio_text_pricing.requests.get', get)
    info = fetch_text_model_info('openai/gpt-5-mini', 'dummy')
    assert info['input_modalities'] == ('text', 'image')
    assert info['prompt'] == .25



def test_reference_image_total_size_blocks_before_quote(builder, monkeypatch):
    refs = []
    for n in range(3):
        path = f'/tmp/ref-{n}.png'
        builder.recipe.references.append(dict(path=path, roles=['style'], notes=''))
        refs.append(path)
    builder.planning.reference_images = lambda: tuple(refs)
    monkeypatch.setattr('studio_clipart_references.reference_image_upload_info',
                        lambda path: dict(mime_type='image/png', size=8 * 1024 * 1024,
                                          width=100, height=100, sha256='0' * 64))
    jobs = queued(builder.planning)
    builder.planning.start(False)
    assert not jobs
    assert '20' in builder.planning.status.text()


def _make_large_collection(builder, total):
    builder.recipe.select(total)
    builder.object_editor.items = fill_recipe([], builder.recipe.counts)
    builder.object_editor.refresh()


def _fake_batch_result(recipe, palette, replace_ids):
    req = planning_request(recipe, palette, list(replace_ids))
    rows = []
    for target in req['targets']:
        row = dict(id=target['id'], **dict.fromkeys(TEXT_FIELDS, ''))
        row['name'] = f"Идея {target['id'][:8]}"
        rows.append(row)
    return dict(request=req, suggestions=rows)


def test_large_planning_is_split_into_bounded_paid_batches(builder, monkeypatch):
    _make_large_collection(builder, 161)
    before_ids = [item['id'] for item in builder.object_editor.items]
    jobs = queued(builder.planning)
    quote_texts = []
    monkeypatch.setattr(
        'studio_planning_ui.confirm_paid_quote',
        lambda *args: quote_texts.append(args[1]) or True,
    )
    calls = []
    def fake_generate(recipe, *, palette='', replace_ids=None, **kwargs):
        calls.append(tuple(replace_ids or ()))
        return _fake_batch_result(recipe, palette, replace_ids)
    monkeypatch.setattr('studio_planning_ui.generate_plan', fake_generate)

    builder.planning.start(False)
    assert len(jobs) == 1
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text',)), None)

    assert quote_texts
    assert quote_texts[0].startswith('Ориентировочная стоимость подбора: $')
    assert 'Запросов: 3.' in quote_texts[0]
    assert 'OpenRouter · GPT-5 mini' in quote_texts[0]
    assert len(jobs) == 2
    for index in range(3):
        result = jobs[index + 1][0]()
        jobs[index + 1][1](result, None)
    assert [len(batch) for batch in calls] == [80, 80, 1]
    assert [item for batch in calls for item in batch] == before_ids
    assert all(item['name'].startswith('Идея ') for item in builder.object_editor.items)
    assert builder.planning.pending is None


def test_authorization_is_rechecked_before_each_paid_batch(builder, monkeypatch):
    _make_large_collection(builder, 81)
    jobs = queued(builder.planning)
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: True)
    generate = MagicMock(side_effect=lambda recipe, *, palette='', replace_ids=None, **kwargs:
                         _fake_batch_result(recipe, palette, replace_ids))
    monkeypatch.setattr('studio_planning_ui.generate_plan', generate)
    authorize = MagicMock(side_effect=[None, ValueError('Access revoked')])
    builder.planning.authorize = authorize
    builder.planning.start(False)
    before = copy.deepcopy(builder.object_editor.items)
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text',)), None)
    jobs[1][1](jobs[1][0](), None)
    with pytest.raises(ValueError, match='Access revoked'):
        jobs[2][0]()
    jobs[2][1](None, 'Access revoked')
    assert authorize.call_count == 2
    generate.assert_called_once()
    assert builder.object_editor.items == before
    assert builder.planning.pending is None


def test_large_planning_failure_keeps_editor_atomic(builder, monkeypatch):
    _make_large_collection(builder, 81)
    jobs = queued(builder.planning)
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: True)
    monkeypatch.setattr(
        'studio_planning_ui.generate_plan',
        lambda recipe, *, palette='', replace_ids=None, **kwargs:
            _fake_batch_result(recipe, palette, replace_ids),
    )

    builder.planning.start(False)
    before = copy.deepcopy(builder.object_editor.items)
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text',)), None)
    assert len(jobs) == 2
    first = jobs[1][0]()
    jobs[1][1](first, None)
    assert len(jobs) == 3
    jobs[2][1](None, 'Второй запрос не выполнен')

    assert builder.object_editor.items == before
    assert 'не измен' in builder.planning.status.text().casefold()
    assert builder.planning.pending is None


def test_large_planning_next_batch_sees_previous_batch_suggestions(builder, monkeypatch):
    _make_large_collection(builder, 81)
    jobs = queued(builder.planning)
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: True)
    seen_existing_names = []

    def fake_generate(recipe, *, palette='', replace_ids=None, **kwargs):
        seen_existing_names.append([item['name'] for item in recipe.objects[:80]])
        return _fake_batch_result(recipe, palette, replace_ids)

    monkeypatch.setattr('studio_planning_ui.generate_plan', fake_generate)
    builder.planning.start(False)
    jobs[0][1](dict(prompt=.25, completion=2., request=0., input_modalities=('text',)), None)
    first = jobs[1][0]()
    jobs[1][1](first, None)
    second = jobs[2][0]()
    jobs[2][1](second, None)

    assert all(not name for name in seen_existing_names[0])
    assert all(name.startswith('Идея ') for name in seen_existing_names[1])


def test_automatic_mode_keeps_saved_provider_and_model(builder):
    panel = builder.planning
    panel.provider.setCurrentIndex(panel.provider.findData('kie'))
    panel.model.setCurrentIndex(panel.model.findData('claude-sonnet-4-6'))
    panel.configure_automatic()
    assert panel.selection() == {'provider': 'kie', 'model': 'claude-sonnet-4-6'}
    assert panel.tabs.tabText(1) == 'Модель текста'
    assert not panel.provider.isHidden()
    assert not panel.model.isHidden()


def test_model_changes_never_launch_and_group_cannot_be_selected(builder):
    panel = builder.planning
    jobs = queued(panel)
    for model in ('deepseek/deepseek-v4.1-flash', 'openai/gpt-6-sol', 'x-ai/grok-4.7'):
        panel.model.setCurrentIndex(panel.model.findData(model))
        assert panel.selection()['model'] == model
        assert 'Понимает изображения' in panel.model_note.text()
    assert jobs == []
    group = panel.model.findText('Другие модели')
    assert not panel.model.model().item(group).isEnabled()


@pytest.mark.parametrize('model,label', [
    ('claude-sonnet-4-6', 'Claude Sonnet 4.6'),
    ('gemini-3-8-flash-openai', 'Gemini 3.8 Flash'),
])
def test_kie_quote_uses_kie_key_and_no_openrouter_price_cap(builder, monkeypatch, model, label):
    panel = builder.planning
    monkeypatch.setattr('v3_api_settings.load_credentials', lambda: {'kie_api_key': 'kie-only'})
    panel.provider.setCurrentIndex(panel.provider.findData('kie'))
    panel.model.setCurrentIndex(panel.model.findData(model))
    jobs = queued(panel)
    quotes = []
    monkeypatch.setattr('studio_planning_ui.confirm_paid_quote', lambda *args: quotes.append(args[1]) or True)
    monkeypatch.setattr('studio_planning_ui.fetch_kie_text_model_info', lambda model:
                        dict(prompt=.85, completion=4.275, request=0, input_modalities=('text',)))
    generate = MagicMock()
    monkeypatch.setattr('studio_planning_ui.generate_plan', generate)
    panel.start(False)
    tariff = jobs[0][0]()
    jobs[0][1](tariff, None)
    jobs[1][0]()
    assert f'KIE · {label}' in quotes[0]
    assert generate.call_args.kwargs['model'] == model
    assert 'Запросов: 1.' in quotes[0]
    assert generate.call_args.kwargs['api_key'] == 'kie-only'
    assert generate.call_args.kwargs['provider'] == 'kie'
    assert generate.call_args.kwargs['max_price'] is None
    panel.cancel()


def test_kie_references_are_blocked_before_quote(builder):
    panel = builder.planning
    panel.provider.setCurrentIndex(panel.provider.findData('kie'))
    panel.model.setCurrentIndex(panel.model.findData('claude-sonnet-4-6'))
    panel.reference_images = lambda: ('/tmp/unused-reference.png',)
    jobs = queued(panel)
    panel.start(False)
    assert jobs == []
    assert 'только текстовые признаки' in panel.status.text()


def test_kie_tariff_expires_and_never_uses_other_model_price(monkeypatch):
    from datetime import date
    from studio_text_pricing import fetch_kie_text_model_info
    class BeforeExpiry(date):
        @classmethod
        def today(cls): return cls(2026, 9, 29)
    monkeypatch.setattr('datetime.date', BeforeExpiry)
    assert fetch_kie_text_model_info('claude-sonnet-4-6')['completion'] == 4.275
    assert fetch_kie_text_model_info('gemini-3-8-flash-openai')['completion'] == 1.125
    with pytest.raises(TextGenerationError):
        fetch_kie_text_model_info('unknown')
    class AfterExpiry(date):
        @classmethod
        def today(cls): return cls(2026, 10, 30)
    monkeypatch.setattr('datetime.date', AfterExpiry)
    with pytest.raises(TextGenerationError):
        fetch_kie_text_model_info('claude-sonnet-4-6')
