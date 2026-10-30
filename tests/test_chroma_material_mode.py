"""Regression coverage for profile delivery, old modules and actual source routing."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from PIL import Image
from PyQt6.QtWidgets import QApplication

from chroma_key import remove_chroma_key_automatic, measure_chroma_background
from chroma_provenance import write_receipt, load_receipt
from license_client import LicenseAuthorization, ModuleEntitlement
from studio_processing_api import ProcessingEngine
from studio_processing_engine import create_engine
from v3_clipart_flow import ClipartProcessingPage
from v3_image_worker_settings import build_image_run_settings
from v3_mode_selection import V3ApplicationView
from v3_processing_flow import ProcessingPipelinePage
from v3_project_state import ProjectState, ProjectMode, ProjectStateError

@pytest.fixture(scope='module', autouse=True)
def app():
    return QApplication.instance() or QApplication([])

@pytest.mark.parametrize('mode', [ProjectMode.PROCESSING, ProjectMode.CLIPART])
def test_ui_mode_survives_save_and_reaches_worker_snapshot(mode):
    state = ProjectState(mode=mode)
    data = state.processing if mode is ProjectMode.PROCESSING else state.clipart
    data.operations.remove_background = True
    data.operations.remove_background_provider = 'local_chroma_key'
    page = (ProcessingPipelinePage if mode is ProjectMode.PROCESSING else ClipartProcessingPage)(state, lambda: None)
    profile = page.operation_widgets['chroma_subject_profile']
    assert not profile.isHidden()
    profile.setCurrentIndex(profile.findData('legacy'))
    restored = ProjectState.from_dict(state.to_dict())
    data = restored.processing if mode is ProjectMode.PROCESSING else restored.clipart
    settings = build_image_run_settings(restored.runtime, restored.clipart.generation, data.operations, run_mode='process_only')
    assert settings['chroma_subject_profile'] == 'legacy'
    provider = page.operation_widgets['remove_background_provider']
    provider.setCurrentIndex(provider.findData('local_rembg'))
    assert profile.isHidden()
    assert page.chroma_subject_note.isHidden()
    provider.setCurrentIndex(provider.findData('local_chroma_key'))
    assert profile.currentData() == 'legacy'
    page.operation_widgets['remove_background'].setChecked(False)
    assert profile.isHidden()
    page.close()

def test_old_draft_keeps_opaque_and_invalid_mode_is_rejected():
    state = ProjectState()
    payload = state.to_dict()
    payload['clipart']['operations'].pop('chroma_subject_profile')
    payload['processing']['operations'].pop('chroma_subject_profile')
    restored = ProjectState.from_dict(payload)
    assert restored.clipart.operations.chroma_subject_profile == 'opaque_clipart'
    assert restored.processing.operations.chroma_subject_profile == 'opaque_clipart'
    payload['clipart']['operations']['chroma_subject_profile'] = 'guess'
    with pytest.raises(ProjectStateError):
        ProjectState.from_dict(payload)

def test_auto_collection_controls_update_state_without_starting_generation(tmp_path):
    now = datetime.now(timezone.utc)
    authorization = LicenseAuthorization('fixture', 'clipart-generator', 'fixture', now, now+timedelta(hours=1),
        module_entitlements=(ModuleEntitlement('auto-clipart', now, now+timedelta(hours=1)),))
    gate = Mock(current_authorization=authorization, status_text='Test', verification_text='Test')
    gate.authorize_run.return_value = authorization
    factory = Mock()
    view = V3ApplicationView(license_gate=gate, worker_factory=factory, draft_path=tmp_path/'draft.json')
    try:
        view._handle_module_action('auto-clipart', 'open')
        controller = view.shell.workflow_controller('auto-clipart')
        assert controller.background_color.currentData() == 'auto'
        controller.subject_profile.setCurrentIndex(controller.subject_profile.findData('legacy'))
        data = view.shell.state.clipart
        assert data.operations.chroma_subject_profile == 'legacy'
        controller._refresh_launch()
        assert controller.subject_profile.currentData() == 'legacy'
        restored = ProjectState.from_dict(view.shell.state.to_dict())
        settings = build_image_run_settings(restored.runtime, restored.clipart.generation,
                                            restored.clipart.operations, run_mode='both')
        assert settings['chroma_subject_profile'] == 'legacy'
        assert settings['chroma_key_color'] == 'auto'
        factory.assert_not_called()
    finally:
        view.close()

@pytest.mark.parametrize('profile', ['opaque_clipart', 'legacy'])
def test_real_worker_uses_selected_material_and_detects_actual_not_declared_background(tmp_path, profile):
    import main
    source = tmp_path/'source.png'
    image = Image.new('RGB', (48, 48), 'blue')
    image.paste((240,160,20), (12,12,36,36));image.save(source)
    seen = []
    def remove(image, color, *, subject_profile):
        seen.append((color,subject_profile))
        return remove_chroma_key_automatic(image,color,subject_profile=subject_profile)
    engine = ProcessingEngine('opaque-clipart-v16', remove, measure_chroma_background,
                              subject_profiles=('opaque_clipart','legacy'))
    raw=tmp_path/'raw';raw.mkdir()
    worker=main.WorkerThread('mode2_process',str(tmp_path),{
        'remove_bg':True,'remove_bg_provider':'local_chroma_key','chroma_key_color':'auto',
        'chroma_subject_profile':profile,'upscale':False,'upscale_after':False,
        'unsharp_enabled':False,'trim_enabled':False,'export_300_dpi':False},processing_engine=engine)
    result=worker._run_processing_pipeline(str(source),None,str(raw),1,'file',chroma_key_color='green')
    assert seen == [('blue',profile)]
    assert worker._item_context.chroma_receipt['subject_profile']==profile
    with Image.open(result) as output:
        assert output.getpixel((0,0))[3]==0
        assert output.getpixel((24,24))==(240,160,20,255)

@pytest.mark.parametrize('profile', ['opaque_clipart','legacy'])
def test_auto_preserves_existing_alpha_without_running_keyer(tmp_path,profile):
    import main
    source=tmp_path/'native.png';image=Image.new('RGBA',(48,48),(0,0,0,0))
    image.paste((240,160,20,128),(12,12,36,36));image.save(source)
    engine=create_engine()
    raw=tmp_path/'raw';raw.mkdir()
    worker=main.WorkerThread('mode2_process',str(tmp_path),{
        'remove_bg':True,'remove_bg_provider':'local_chroma_key','chroma_key_color':'auto',
        'chroma_subject_profile':profile,'upscale':False,'upscale_after':False,
        'unsharp_enabled':False,'trim_enabled':False,'export_300_dpi':False},processing_engine=engine)
    with patch('main.detect_chroma_key_color',side_effect=AssertionError('detector must be skipped')):
        result=worker._run_processing_pipeline(str(source),None,str(raw),1,'file')
    with Image.open(result) as output:
        assert output.convert('RGBA').tobytes()==image.tobytes()

def test_old_api1_component_is_usable_for_opaque_but_blocks_legacy_before_worker_start(tmp_path):
    import main
    remover=Mock(return_value=Image.new('RGBA',(4,4)))
    old=ProcessingEngine('opaque-clipart-v1',remover,lambda image:(0,0,255))
    old.remove(Image.new('RGB',(4,4)),'blue')
    assert remover.call_args.kwargs['subject_profile']=='opaque_clipart'
    with pytest.raises(ValueError,match='Обновите модуль'):
        main.WorkerThread('mode2_process',str(tmp_path),{'remove_bg':True,
            'remove_bg_provider':'local_chroma_key','chroma_subject_profile':'legacy'},processing_engine=old)

def test_legacy_receipt_records_material_mode_and_old_receipt_keeps_its_schema(tmp_path):
    for mode in ('opaque_clipart','legacy'):
        path=tmp_path/f'{mode}.png';Image.new('RGBA',(4,4)).save(path)
        write_receipt(path,source_sha256='a'*64,requested_background='#0000FF',
                      observed_background='#0000FF',subject_profile=mode)
        receipt=load_receipt(path)
        assert receipt.get('subject_profile','opaque_clipart')==mode
        assert ('subject_profile' in receipt)==(mode=='legacy')

def test_explicit_same_color_selection_is_saved_without_restore_or_material_changes_enabling_override():
    state=ProjectState(mode=ProjectMode.CLIPART)
    state.clipart.operations.remove_background_provider='local_chroma_key'
    page=ClipartProcessingPage(state,lambda:None)
    color=page.operation_widgets['chroma_key_color']
    profile=page.operation_widgets['chroma_subject_profile']
    try:
        page.refresh_from_state()
        profile.setCurrentIndex(profile.findData('legacy'))
        assert not state.clipart.operations.chroma_key_color_override
        color.activated.emit(color.currentIndex())
        assert state.clipart.operations.chroma_key_color_override
        restored=ProjectState.from_dict(state.to_dict())
        assert restored.clipart.operations.chroma_key_color_override
        color.setCurrentIndex(color.findData('auto'));color.activated.emit(color.currentIndex())
        assert not state.clipart.operations.chroma_key_color_override
    finally:
        page.close()

@pytest.mark.parametrize('override',[False,True])
def test_manual_selection_and_old_record_priority_are_both_preserved(tmp_path,override):
    import main
    from chroma_generation_record import write_generation_intent,bind_generation_record,record_path
    source=tmp_path/'generated.png'
    intent=write_generation_intent(source,color='green',prompt='fixture')
    image=Image.new('RGB',(48,48),'blue' if override else 'green')
    image.paste((240,160,20),(12,12,36,36));image.save(source)
    bind_generation_record(source,intent)
    record_before=record_path(source).read_bytes()
    seen=[]
    def remove(image,color,*,subject_profile):
        seen.append(color)
        return remove_chroma_key_automatic(image,color,subject_profile=subject_profile)
    engine=ProcessingEngine('opaque-clipart-v16',remove,measure_chroma_background,
                            subject_profiles=('opaque_clipart','legacy'))
    raw=tmp_path/'raw';raw.mkdir()
    worker=main.WorkerThread('mode2_process',str(tmp_path),{
        'remove_bg':True,'remove_bg_provider':'local_chroma_key','chroma_key_color':'blue',
        'chroma_key_color_override':override,'upscale':False,'upscale_after':False,
        'unsharp_enabled':False,'trim_enabled':False,'export_300_dpi':False},processing_engine=engine)
    worker._run_processing_pipeline(str(source),None,str(raw),1,'file',chroma_key_color='green')
    effective='blue' if override else 'green'
    assert seen==[effective]
    assert worker._item_context.chroma_receipt['requested_background']==('#0000FF' if override else '#00FF00')
    assert record_path(source).read_bytes()==record_before
    with pytest.raises(ValueError,match='не совпадает'):
        worker._run_processing_pipeline(str(source),None,str(raw),1,'file',chroma_key_color='red')

def test_default_modes_keep_old_request_fingerprint_and_changes_invalidate_reuse():
    from types import SimpleNamespace
    from studio_auto_clipart_flow import _run_settings_fingerprint
    state=ProjectState()
    ops=state.clipart.operations
    def settings():
        return build_image_run_settings(state.runtime,state.clipart.generation,ops,run_mode='both')
    original=settings()
    assert 'chroma_subject_profile' not in original
    assert 'chroma_key_color_override' not in original
    def fingerprint(value):
        return _run_settings_fingerprint(SimpleNamespace(work_dir='fixture',settings=value,generated_prompts=[]))
    unchanged=fingerprint(original)
    ops.chroma_subject_profile='legacy'
    assert fingerprint(settings())!=unchanged
    ops.chroma_subject_profile='opaque_clipart'
    ops.chroma_key_color_override=True
    assert fingerprint(settings())!=unchanged
    ops.chroma_key_color_override=False
    assert fingerprint(settings())==unchanged

def test_white_auto_source_requires_review_without_running_paid_or_local_fallback(tmp_path):
    import main
    source=tmp_path/'white.png';image=Image.new('RGB',(48,48),'white')
    image.paste((240,160,20),(12,12,36,36));image.save(source)
    raw=tmp_path/'raw';raw.mkdir()
    worker=main.WorkerThread('mode2_process',str(tmp_path),{
        'remove_bg':True,'remove_bg_provider':'local_chroma_key','chroma_key_color':'auto',
        'auto_clipart_sharp_fallback':True,'upscale':False,'upscale_after':False,
        'unsharp_enabled':False,'trim_enabled':False,'export_300_dpi':False},processing_engine=create_engine())
    with patch.object(worker,'_run_auto_clipart_sharp_fallback',side_effect=AssertionError('no unapproved white fallback')):
        result=worker._run_processing_pipeline(str(source),None,str(raw),1,'file')
    assert result==str(source)
    assert worker._item_context.manual_transparency_required
    assert worker._item_context.chroma_receipt is None
