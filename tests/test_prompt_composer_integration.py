from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication
from license_client import LicenseAuthorization, ModuleEntitlement, LicenseError
from v3_mode_selection import V3ApplicationView


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


class Gate:
    status_text = 'Лицензия активна'
    verification_text = 'Тестовое разрешение'
    def __init__(self):
        now = datetime.now(timezone.utc)
        self.current_authorization = LicenseAuthorization('test', 'studio', 'test', now - timedelta(seconds=1), now + timedelta(hours=1),
            module_entitlements=(ModuleEntitlement('prompt-composer', now - timedelta(seconds=1), now + timedelta(hours=1)),))
    def authorize_run(self):
        if self.current_authorization is None:
            raise LicenseError('Нет доступа')
        return self.current_authorization


def test_real_card_open_generate_save_reopen_and_denial(tmp_path, app):
    gate = Gate()
    view = V3ApplicationView(draft_path=tmp_path / 'draft.json', license_gate=gate)
    view.resize(1120, 780)
    view.show()
    app.processEvents()
    card = view.mode_selection.module_cards['prompt-composer']
    assert card.start_button.isEnabled()
    card.start_button.click()
    page = view._composer_page_handle.value
    assert view.stack.currentWidget() is page
    assert len(page.host.catalogue()['templates']) == 21
    assert page.generate_local()
    assert len(page._variants) == 7
    selected = page._selected_draft()
    saved = page.host.save(selected, {'name': 'Проверка', 'source': 'local', 'tags': ['тест']})
    page._dirty = False
    assert page.confirm_close()
    view._close_composer()
    view.mode_selection.module_cards['prompt-composer'].start_button.click()
    page = view._composer_page_handle.value
    assert page.open_entry(saved['id'])
    assert page.draft == selected
    page._set_field('color', 'красный', 'red')
    assert page.host.load(saved['id'])['payload'] == selected
    page._dirty = False
    assert page.confirm_close()
    view._close_composer()
    gate.current_authorization = None
    view.refresh_license_status()
    assert not view.mode_selection.module_cards['prompt-composer'].start_button.isEnabled()
    with patch('v3_mode_selection.QMessageBox.warning') as warning:
        view._open_composer('prompt-composer', 'open')
        assert warning.called
    assert view._composer_page_handle is None
    view.close()


def test_real_reference_import_through_ui(tmp_path, app):
    from PIL import Image
    from prompt_composer.ui import PromptComposerPage
    from studio_prompt_composer_host import PromptComposerHost
    image = tmp_path / 'sample.png'
    Image.new('RGB', (20, 20), 'blue').save(image)
    host = PromptComposerHost(tmp_path / 'library', settings_provider=lambda: {}, authorize=lambda: True)
    page = PromptComposerPage(host)
    with patch('prompt_composer.ui.QFileDialog.getOpenFileName', return_value=(str(image), '')):
        assert page.import_reference()
    saved = host.save(page.draft, {'name': 'С референсом'})
    image.unlink()
    assert host.reference_available(saved['payload']['references'][0])
    assert saved['payload']['references'][0]['filename'] == 'sample.png'
    page._dirty = False
    page.confirm_close()
    page.deleteLater()
