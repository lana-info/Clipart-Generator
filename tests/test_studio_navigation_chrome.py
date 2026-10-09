"""Shared Core navigation and compact project resume, without provider requests."""
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication, QMenu, QPushButton

from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode, ProjectState


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(app, tmp_path):
    page = V3ApplicationView(draft_path=tmp_path / 'draft.json')
    page.resize(1120, 780)
    page.show()
    yield page
    page.close()
    page.deleteLater()
    app.processEvents()


@pytest.mark.parametrize('mode', list(ProjectMode))
def test_shared_header_persists_in_workflows_and_focus_mode(view, app, mode):
    header = view.mode_selection.account_card
    assert header.parentWidget() is view.studio_header
    view._handle_mode_selected(mode.value)
    app.processEvents()
    assert view.stack.currentWidget() is view.shell
    assert view.studio_header.isVisible() and header.isVisible()
    assert view.shell.api_settings_button.isHidden()
    assert view.shell.diagnostics_button.isHidden()
    view.shell.set_canvas_focus_mode(True)
    assert not view.studio_header.isVisible()
    view.shell.set_canvas_focus_mode(False)
    assert view.studio_header.isVisible()
    view.show_new_project()
    assert view.stack.currentWidget() is view.mode_selection
    assert header.parentWidget() is view.studio_header


def test_shared_header_routes_all_four_actions(app, monkeypatch):
    calls = []
    for method in ('_show_license', '_show_module_updates', '_show_api_settings', '_show_diagnostics'):
        monkeypatch.setattr(V3ApplicationView, method, lambda self, action=method: calls.append(action))
    view = V3ApplicationView()
    view.show()
    try:
        buttons = [view.mode_selection.license_button, view.mode_selection.module_updates_button,
                   view.mode_selection.api_settings_button, view.mode_selection.diagnostics_button]
        view.mode_selection.module_updates_button.show()
        for button in buttons:
            button.click()
        assert calls == ['_show_license', '_show_module_updates', '_show_api_settings', '_show_diagnostics']
        assert [button.text() for button in buttons] == ['Лицензия', 'Обновления модулей', 'Настройки API', 'Диагностика']
    finally:
        view.close()
        view.deleteLater()


@pytest.mark.parametrize('module,expected', [('processing', 'Обработка изображений'),
    ('auto-clipart', 'Clipart'), ('clipart', 'Генерация изображений'), ('pinterest', 'Pinterest'),
    ('prompt-composer', 'Конструктор промптов'), ('future-module', 'future-module')])
@pytest.mark.parametrize('name', ['Без названия', '  ', 'Мой набор & лето'])
def test_project_menu_label_always_includes_module_and_local_date(view, module, expected, name):
    record = SimpleNamespace(module_id=module, name=name, updated_at='2026-10-08T12:06:00+00:00')
    label = view._project_menu_label(record)
    assert label.startswith(expected + ' · ')
    assert label.endswith(datetime.fromisoformat(record.updated_at).astimezone().strftime('%d.%m.%Y %H:%M'))
    assert 'Без названия' not in label
    if name.strip() and name != 'Без названия':
        assert name in label


def test_resume_menu_shows_every_project_and_routes_exact_id(view, app):
    for number in range(20):
        state = ProjectState(mode=ProjectMode.PROCESSING)
        view._project_store.create('processing', 'Без названия' if number % 2 else f'Набор {number}', state.to_dict())
    view._refresh_saved_projects()
    assert view.mode_selection.all_projects_button.text() == 'Продолжить работу'
    assert view.mode_selection.all_projects_button.isEnabled()
    assert not hasattr(view.mode_selection, 'saved_projects_card')
    records = view._project_store.recent(limit=None)
    chosen = []
    def choose(menu, *args):
        assert len(menu.actions()) == len(records) == 20
        assert all('Обработка изображений' in action.text() for action in menu.actions())
        for index in (0, 10, 19):
            menu.actions()[index].trigger()
    with patch.object(QMenu, 'exec', choose), patch.object(view, 'continue_saved_project', side_effect=chosen.append):
        view.mode_selection.all_projects_button.click()
    assert chosen == [records[index].project_id for index in (0, 10, 19)]


def test_signed_composer_uses_the_same_core_header(view, app, tmp_path):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from pathlib import Path
    from studio_module_packaging import prepare_module_release
    from studio_module_runtime import ModuleRuntimeHost
    from studio_modules import ModuleStore
    from studio_prompt_composer_package import composer_payload
    key = Ed25519PrivateKey.generate()
    package = prepare_module_release(module_id='prompt-composer', version='1.0.0',
        studio_min='3.2.12', studio_max_exclusive='3.3.0', platforms=['linux-x64'],
        entrypoint='entry.py', files=composer_payload(Path.cwd()), key_id='test', private_key=key)
    package_path = tmp_path / 'composer.zip'
    package_path.write_bytes(package)
    store = ModuleStore(tmp_path / 'modules', studio_version='3.2.12', platform='linux-x64',
        trusted_keys={'test': key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)})
    store.install(package_path)
    store.activate('prompt-composer', '1.0.0')
    runtime = ModuleRuntimeHost(store, lambda module, action: True)
    view._module_delivery = SimpleNamespace(host=runtime)
    view._license_gate = object()
    try:
        with patch('v3_mode_selection.authorize_module_run'), patch.object(view, '_composer_allowed', return_value=True), \
             patch('v3_mode_selection.QMessageBox.warning', side_effect=AssertionError('module launch failed')):
            view._open_composer()
        page = view._composer_page_handle.value
        app.processEvents()
        assert view.stack.currentWidget() is page
        assert view.studio_header.isVisible()
        assert page.findChild(QPushButton, 'settingsButton').isHidden()
        assert page.findChild(QPushButton, 'backButton').isVisible()
        page._set_field('subject', '', 'my test subject')
        assert page.generate_local() and len(page._variants) == 7
        assert all('my test subject' in v['en'] and 'my test subject' in v['ru'] for v in page._variants)
        from tests.test_prompt_composer_auto_english import translated_reply
        from studio_prompt_composer_ai import validate_response
        page.goto_step(1)
        page._set_field('subject', 'рыжий кот', '')
        snapshots = []
        def quote(snapshot, done, error, **kwargs):
            page.host._kernel.preflight_ai(snapshot)
            snapshots.append(snapshot)
            done({'id': 'mock', 'configured': True})
            return 'quote-ticket'
        def submit(quote, done, error):
            snapshot = snapshots[0]
            done(validate_response(translated_reply(snapshot), snapshot, kernel=page.host._kernel))
            return 'request-ticket'
        with patch.object(page, '_ai_model', return_value={'provider': 'openrouter', 'model': 'test'}), \
             patch.object(page.host, 'quote_ai', side_effect=quote), \
             patch.object(page.host, 'submit_ai', side_effect=submit) as submitted:
            assert page.generate_local()
            assert submitted.call_count == 1 and len(page._active_variants()) == 7
            assert all('a ginger cat' in v['en'] and 'рыжий кот' not in v['en'] for v in page._active_variants())
            assert page.accept_proposal()
        page._dirty = False
    finally:
        # Close handle without querying the synthetic delivery bridge's catalog.
        if view._composer_page_handle is not None:
            handle = view._composer_page_handle
            handle.value.host.close()
            view.stack.removeWidget(handle.value)
            handle.close()
            handle.value.deleteLater()
            view._composer_page_handle = None
        view._module_delivery = None
        view._license_gate = None
