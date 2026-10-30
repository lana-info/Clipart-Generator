import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication

from studio_catalog import CatalogEntry, ModuleAvailability, card_action
from studio_text_pricing import fetch_text_model_info
from v3_api_settings import check_openrouter_balance
from studio_clipart_builder_ui import ClipartBuilderDialog
from v3_project_state import ProjectState


def response(payload):
    result = Mock(status_code=200)
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    result.iter_content.return_value = [json.dumps(payload).encode()]
    return result


def test_token_only_catalogue_omits_request_fee(monkeypatch):
    monkeypatch.setattr('requests.get', lambda *args, **kwargs: response({'data': [{
        'id': 'openai/gpt-5-mini', 'pricing': {'prompt': '0.00000025', 'completion': '0.000002'},
    }]}))
    assert fetch_text_model_info('openai/gpt-5-mini', 'fixture') == {
        'prompt': 0.25, 'completion': 2.0, 'request': 0.0, 'input_modalities': (),
    }


def test_unknown_rights_never_offer_purchase():
    entry = CatalogEntry('auto-clipart', 'Clipart', 'Collections', 'clipart', True)
    action = card_action(entry, ModuleAvailability(installed=True, entitlement_known=False))
    assert action.action == 'verify'
    assert action.label != 'Купить'


def test_openrouter_balance_has_bounded_no_redirect_request(monkeypatch):
    get = Mock(return_value=response({'data': {'total_credits': 20, 'total_usage': 3.25}}))
    monkeypatch.setattr('requests.get', get)
    assert check_openrouter_balance('fixture') == 'Баланс OpenRouter: 16.75 USD'
    assert get.call_args.kwargs['allow_redirects'] is False
    assert get.call_args.kwargs['stream'] is True


def test_openrouter_regular_key_limit_is_not_account_balance(monkeypatch):
    forbidden = response({})
    forbidden.status_code = 403
    get = Mock(side_effect=[forbidden, response({'data': {'limit_remaining': 4.75}})])
    monkeypatch.setattr('requests.get', get)
    assert check_openrouter_balance('fixture') == 'Остаток лимита ключа OpenRouter: 4.75 USD (не баланс аккаунта)'
    assert get.call_args.args[0].endswith('/key')


def test_palette_selection_and_modifier_limit():
    _app = QApplication.instance() or QApplication([])
    dialog = ClipartBuilderDialog(ProjectState().clipart)
    first, second = dialog.palette_cards[:2]
    first['button'].click()
    assert first['button'].isChecked()
    second['button'].click()
    assert second['button'].isChecked()
    assert not first['button'].isChecked()
    buttons = list(dialog.style_modifier_buttons.values())
    buttons[0].click()
    buttons[1].click()
    assert not buttons[2].isEnabled()
    buttons[0].click()
    assert buttons[2].isEnabled()
    dialog.close()


def test_legacy_custom_visual_values_survive_dropdown_migration():
    _app = QApplication.instance() or QApplication([])
    data = ProjectState().clipart
    from studio_clipart_recipe import ClipartRecipe
    recipe = ClipartRecipe(theme="Лесные животные")
    custom = dict(line='Custom fine ink', detail='Large expressive eyes')
    recipe.visual.update(custom, material='Satin opaque')
    data.recipe = recipe.to_dict()
    dialog = ClipartBuilderDialog(data)
    for name, value in custom.items():
        assert dialog.visual_fields[name].currentText() == value
        assert not dialog.visual_fields[name].isEditable()
    assert 'material' not in dialog.visual_fields
    dialog._apply()
    assert data.recipe['visual']['material'] == ''
    for name, value in custom.items():
        assert data.recipe['visual'][name] == value
    dialog.close()


def test_home_refreshes_rights_and_keeps_saved_project(tmp_path):
    from license_client import LicenseAuthorization, ModuleEntitlement
    from v3_mode_selection import V3ApplicationView
    _app = QApplication.instance() or QApplication([])
    now = datetime.now(timezone.utc)
    gate = Mock(status_text='active', verification_text='checked', current_authorization=None)
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from studio_module_delivery import StudioModuleDelivery
    from studio_module_packaging import prepare_official_workflow_release
    from pathlib import Path
    signing = Ed25519PrivateKey.generate()
    delivery = StudioModuleDelivery(root=tmp_path / 'modules', studio_version='3.2.9',
        platform='windows-x64', license_client=Mock(), license_gate=gate,
        trusted_keys={'fixture': signing.public_key().public_bytes_raw()})
    view = V3ApplicationView(license_gate=gate, draft_path=tmp_path / 'draft.json', module_delivery=delivery)
    try:
        card = view.mode_selection.module_cards['auto-clipart']
        assert card.start_button.text() == 'Проверить доступ'
        gate.current_authorization = LicenseAuthorization('fixture', 'clipart-generator', 'fixture',
            now, now + timedelta(hours=1), module_entitlements=(
                ModuleEntitlement('auto-clipart', now, now + timedelta(hours=1)),))
        gate.authorize_run.return_value = gate.current_authorization
        view.refresh_license_status()
        assert card.start_button.text() == 'Скачать'
        package = tmp_path / 'auto.zip'
        package.write_bytes(prepare_official_workflow_release(source_root=Path(__file__).resolve().parents[1],
            module_id='auto-clipart', version='1.5.0', studio_min='3.2.9', studio_max_exclusive='3.3.0',
            platforms=['windows-x64'], key_id='fixture', private_key=signing))
        delivery.store.install(package)
        delivery.activate('auto-clipart', '1.5.0')
        view.refresh_license_status()
        assert card.start_button.text() == 'Открыть'
        view._handle_module_action('auto-clipart', 'open')
        controller = view.shell.workflow_controller('auto-clipart')
        controller.save_timer.stop()
        controller.brief.project_name.setText('Saved acceptance')
        view.show_mode_switcher()
        assert card.start_button.text() == 'Открыть'
        from PyQt6.QtWidgets import QMenu
        resume = view.mode_selection.all_projects_button
        assert resume.text() == 'Продолжить работу' and resume.isEnabled()
        record = next(item for item in view._project_store.recent(limit=None)
                      if item.name == 'Saved acceptance')

        def choose_saved_project(menu, *args):
            actions = [action for action in menu.actions() if 'Saved acceptance' in action.text()]
            assert len(actions) == 1
            actions[0].trigger()

        with patch.object(QMenu, 'exec', choose_saved_project):
            resume.click()
        assert view._active_project_id == record.project_id
        reopened = view.shell.workflow_controller('auto-clipart')
        assert reopened.brief.project_name.text() == 'Saved acceptance'
        assert reopened.worker is None
    finally:
        view.close()
