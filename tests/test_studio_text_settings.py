from PyQt6.QtWidgets import QApplication, QLineEdit
import pytest

from api_credentials import SECRET_CONFIG_KEYS
from runtime_settings import build_runtime_settings
from studio_clipart_recipe import ClipartRecipe
from v3_api_settings import ApiSettingsDialog, save_credentials, load_credentials


def test_openrouter_is_secret_and_survives_store(tmp_path):
    assert 'openrouter_api_key' in SECRET_CONFIG_KEYS
    path = tmp_path / '.env'
    save_credentials({'kie_api_key': 'dummy-kie', 'openrouter_api_key': 'dummy-or'}, path)
    assert load_credentials(path) == {'kie_api_key': 'dummy-kie', 'openrouter_api_key': 'dummy-or'}
    assert build_runtime_settings({}, load_credentials(path))['openrouter_api_key'] == 'dummy-or'


def test_api_dialog_masks_and_saves_openrouter(monkeypatch):
    _app = QApplication.instance() or QApplication([])
    monkeypatch.setattr('v3_api_settings.load_credentials', lambda: {})
    saved = []
    monkeypatch.setattr('v3_api_settings.save_credentials', lambda values: saved.append(values))
    dialog = ApiSettingsDialog()
    assert dialog.openrouter_edit.echoMode() == QLineEdit.EchoMode.Password
    dialog.openrouter_edit.setText('dummy-or')
    dialog._save()
    assert saved[0]['openrouter_api_key'] == 'dummy-or'
    dialog.close()


def test_assistant_roundtrip_and_secrets_rejected():
    recipe = ClipartRecipe(assistant={'provider': 'openrouter', 'model': 'openai/gpt-5-mini'})
    assert ClipartRecipe.from_dict(recipe.to_dict()).assistant == recipe.assistant
    assert 'assistant' not in ClipartRecipe().to_dict()
    recipe.assistant['api_key'] = 'not-allowed'
    with pytest.raises(ValueError):
        recipe.to_dict()


def test_multiline_secret_rejected_without_overwrite(tmp_path):
    path = tmp_path / '.env'
    save_credentials({'openrouter_api_key': 'dummy-old'}, path)
    with pytest.raises(ValueError):
        save_credentials({'openrouter_api_key': 'dummy\nother_key=bad'}, path)
    assert load_credentials(path)['openrouter_api_key'] == 'dummy-old'
