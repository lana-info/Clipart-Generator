import copy
import json
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox
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
    dialog = ClipartBuilderDialog(ProjectState())
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
    assert panel.model.count() == 3
    panel.provider.setCurrentIndex(0)
    assert panel.model.count() == 1
    jobs = queued(panel)
    panel.start(False)
    assert not jobs
    assert 'тариф' in panel.status.text()
    panel.provider.setCurrentIndex(1)
    panel.model.setCurrentIndex(panel.model.findData('openai/gpt-5-mini'))
    builder._apply()
    assert builder.state.clipart.recipe['assistant']['model'] == 'openai/gpt-5-mini'
    assert 'dummy-key' not in json.dumps(builder.state.to_dict())


def test_declined_quote_never_generates(builder, monkeypatch):
    jobs = queued(builder.planning)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.No)
    builder.planning.start(False)
    jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
    assert len(jobs) == 1
    assert builder.planning.pending is None


def test_cancel_quote_discards_and_does_not_prompt(builder, monkeypatch):
    jobs = queued(builder.planning)
    question = MagicMock()
    monkeypatch.setattr(QMessageBox, 'question', question)
    builder.planning.start(False)
    builder.planning.cancel()
    jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
    question.assert_not_called()


def test_edit_during_quote_prevents_paid_request(builder, monkeypatch):
    jobs = queued(builder.planning)
    question = MagicMock()
    monkeypatch.setattr(QMessageBox, 'question', question)
    builder.planning.start(False)
    builder.theme.setText('Другая тема')
    jobs[0][1]({'prompt': .25, 'completion': 2, 'request': 0}, None)
    question.assert_not_called()
    assert len(jobs) == 1
    assert builder.planning.pending is None


def test_mocked_handoff_and_stale_result(builder, monkeypatch):
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.StandardButton.Yes)
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
