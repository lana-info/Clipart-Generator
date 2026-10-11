"""Real Core admission and Qt presentation for new image providers, offline."""
import os
from types import SimpleNamespace
import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication, QLabel
from studio_image_run_services import CoreImageRunGateway
from v3_flow_runtime import FlowRunRequest, safe_runtime_error
from v3_image_generation_runtime import estimate_image_generation_cost, generation_model_options
from v3_image_review_ui import ImageReviewRunPage
from v3_project_state import ProjectState, ProjectMode, PromptEntry

@pytest.mark.parametrize('provider,label', [('atlascloud','AtlasCloud'),('piapi','PiAPI')])
def test_gateway_uses_new_key_without_requiring_kie(provider, label):
    request = FlowRunRequest('mode1_generate', '/tmp/dummy-images',
        {'text_generation_model':f'{provider}/gpt-image-2.5-flare'},
        generated_prompts=[{'prompt':'A ceramic cup','references':[]}])
    runtime = {}
    gateway = CoreImageRunGateway(runtime_settings_provider=lambda:runtime,
        authorization_provider=lambda:None, run_preparer=lambda:None,
        worker_factory=lambda **kwargs:None)
    assert gateway.preflight(request) == (f'{label} API Key',)
    runtime[f'{provider}_api_key'] = 'dummy-private-value'
    assert gateway.preflight(request) == ()
    assert all('api_key' not in key for key in request.settings)
    for sanitizer in (CoreImageRunGateway._safe_message, safe_runtime_error):
        assert 'dummy-private-value' not in sanitizer('Error dummy-private-value',runtime)

@pytest.mark.parametrize('provider,label', [('atlascloud','AtlasCloud'),('piapi','PiAPI')])
def test_unknown_token_cost_never_displays_free_total(provider, label):
    app = QApplication.instance() or QApplication([])
    state = ProjectState(mode=ProjectMode.CLIPART)
    data = state.clipart
    data.prompts = [PromptEntry('A ceramic cup')]
    data.generation.model = f'{provider}/gpt-image-2.5-flare'
    data.operations.upscale_before = False
    data.operations.upscale_after = False
    data.operations.remove_background = False
    estimate = estimate_image_generation_cost(data)
    assert not estimate.complete and provider in estimate.incomplete_providers
    holder = SimpleNamespace(cost_breakdown_label=QLabel(), _fal_cost_amount=None, _fal_cost_error=None)
    ImageReviewRunPage._render_cost_breakdown(holder,estimate)
    text = holder.cost_breakdown_label.text()
    assert f'{label} — стоимость недоступна' in text
    assert 'Итого — не рассчитано полностью' in text
    assert 'Итого — 0.000 USD' not in text
    assert f'{provider}/gpt-image-2.5-flare' in {option.model_id for option in generation_model_options(references=False)}
    assert f'{provider}/gpt-image-2.5-flare' not in {option.model_id for option in generation_model_options(references=True)}

@pytest.mark.parametrize('provider', ['atlascloud','piapi'])
def test_sunburst_routes_independently(provider):
    from gpt25_provider import generation_payload
    model = f'{provider}/gpt-image-2.5-sunburst'
    payload = generation_payload(model,'A ceramic cup','1:1','1K')
    expected = 'openai/gpt-image-2.5-sunburst/text-to-image' if provider == 'atlascloud' else 'gpt-image-2.5-sunburst'
    assert payload['model'] == expected
    assert payload['size'] == '1024x1024'
    assert model in {option.model_id for option in generation_model_options(references=False)}


def test_budget_route_omits_ignored_controls_and_qt_explains_auto():
    from gpt25_provider import generation_payload, Gpt25ProviderError
    from v3_clipart_flow import ClipartGenerationPage
    app = QApplication.instance() or QApplication([])
    payload = generation_payload('piapi/gpt-image-2.5','A ceramic cup','auto','auto')
    assert payload == {'model':'gpt-image-2.5','prompt':'A ceramic cup',
                       'output_format':'png','n':1,'response_format':'url'}
    with pytest.raises(Gpt25ProviderError):
        generation_payload('piapi/gpt-image-2.5','A ceramic cup','1:1','1K')
    state = ProjectState(mode=ProjectMode.CLIPART)
    page = ClipartGenerationPage(state,lambda:None)
    page.model_combo.setCurrentIndex(page.model_combo.findData('piapi/gpt-image-2.5'))
    assert state.clipart.generation.model == 'piapi/gpt-image-2.5'
    assert state.clipart.generation.ratio == 'auto'
    assert state.clipart.generation.resolution == 'auto'
    assert page.ratio_preview.isHidden()
    assert not page.ratio_combo.isEnabled()
    assert not page.resolution_combo.isEnabled()
    assert 'выбирает модель' in page.ratio_combo.currentText()
    assert 'качество выбирает модель' in page.model_capability_label.text()
    page.model_combo.setCurrentIndex(page.model_combo.findData('piapi/gpt-image-2.5-sunburst'))
    assert not page.ratio_preview.isHidden()
    assert page.ratio_combo.isEnabled() and page.resolution_combo.isEnabled()
    assert state.clipart.generation.resolution == '1K'
    page.close()


def test_api_dialog_saves_both_masked_keys(monkeypatch):
    import v3_api_settings
    from PyQt6.QtWidgets import QLineEdit
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(v3_api_settings,'load_credentials',lambda:{})
    saved = []
    monkeypatch.setattr(v3_api_settings,'save_credentials',lambda values:saved.append(values))
    dialog = v3_api_settings.ApiSettingsDialog({})
    dialog.atlascloud_edit.setText('dummy-atlas')
    dialog.piapi_edit.setText('dummy-piapi')
    assert dialog.atlascloud_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.piapi_edit.echoMode() == QLineEdit.EchoMode.Password
    dialog._save()
    assert saved[0]['atlascloud_api_key'] == 'dummy-atlas'
    assert saved[0]['piapi_api_key'] == 'dummy-piapi'
