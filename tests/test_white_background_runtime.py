"""White cutout dispatch, local cache, cancellation and publication contracts."""
import hashlib
import importlib.util
from io import BytesIO
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import numpy as np
from PIL import Image, ImageDraw
import pytest

import main
import white_background as white
from tests.test_local_processing_acceptance import worker_settings


def fixture_png(tmp_path):
    source = tmp_path / 'source.png'
    image = Image.new('RGB', (32, 28), 'white')
    ImageDraw.Draw(image).rectangle((8, 6, 22, 23), fill=(247, 243, 231))
    image.save(source, dpi=(240, 240), icc_profile=b'fixture-ICC')
    mask = Image.new('RGBA', image.size, (100, 20, 20, 0))
    ImageDraw.Draw(mask).rectangle((8, 6, 22, 23), fill=(100, 20, 20, 255))
    data = BytesIO(); mask.save(data, format='PNG')
    return source, data.getvalue()


def worker(tmp_path, **overrides):
    return main.WorkerThread('mode2_process', str(tmp_path), worker_settings(
        remove_bg=True, remove_bg_provider='local_white_background', **overrides))


@pytest.mark.parametrize('layout', ['flat', 'nested', 'modern', 'xdg'])
def test_cached_model_follows_rembg_legacy_and_current_layouts(tmp_path, monkeypatch, layout):
    monkeypatch.delenv('U2NET_HOME', raising=False)
    monkeypatch.delenv('REMBG_HOME', raising=False)
    monkeypatch.delenv('XDG_DATA_HOME', raising=False)
    if layout in ('flat', 'nested'):
        monkeypatch.setenv('U2NET_HOME', str(tmp_path))
        path = tmp_path / ('u2net.onnx' if layout == 'flat' else 'models/u2net/u2net.onnx')
    elif layout == 'modern':
        monkeypatch.setenv('REMBG_HOME', str(tmp_path))
        path = tmp_path / 'models/u2net/u2net.onnx'
    else:
        monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path))
        path = tmp_path / 'rembg/models/u2net/u2net.onnx'
    path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'cached-fixture')
    assert white.cached_u2net_model_path() == path


def test_availability_requires_model_and_dependencies_without_importing_them(monkeypatch, tmp_path):
    finder = Mock(side_effect=lambda name: object())
    monkeypatch.setattr(white.importlib.util, 'find_spec', finder)
    monkeypatch.setattr(white, 'cached_u2net_model_path', lambda: None)
    assert not white.white_background_available(); finder.assert_not_called()
    monkeypatch.setattr(white, 'cached_u2net_model_path', lambda: tmp_path / 'fixture.onnx')
    assert white.white_background_available()
    finder.side_effect = lambda name: None if name == 'onnxruntime' else object()
    assert not white.white_background_available()


def test_missing_and_corrupt_models_fail_before_rembg_import_or_download(monkeypatch, tmp_path):
    monkeypatch.setattr(white, 'cached_u2net_model_path', lambda: None)
    with pytest.raises(white.WhiteBackgroundAmbiguousError, match='не установлена'):
        white.load_cached_white_background_model()
    path = tmp_path / 'bad.onnx'; path.write_bytes(b'not-the-official-model')
    monkeypatch.setattr(white, 'cached_u2net_model_path', lambda: path)
    with pytest.raises(white.WhiteBackgroundAmbiguousError, match='повреждена'):
        white.load_cached_white_background_model()


def test_verified_session_bypasses_rembg_downloader_and_reuses_explicit_cache(monkeypatch, tmp_path):
    path = tmp_path / 'model.onnx'; path.write_bytes(b'fixture-model')
    monkeypatch.setattr(white, 'cached_u2net_model_path', lambda: path)
    monkeypatch.setattr(white, 'U2NET_MODEL_MD5', hashlib.md5(path.read_bytes()).hexdigest())
    fake_rembg = ModuleType('rembg'); fake_rembg.remove = Mock()
    fake_session_module = ModuleType('rembg.sessions.u2net')
    class Session:
        def __init__(self, name, options, **kwargs):
            assert name == 'u2net'
            assert kwargs == {'providers': ['CPUExecutionProvider']}
            assert self.download_models() == str(path)
            self.path = path
        @classmethod
        def download_models(cls, *args, **kwargs):
            raise AssertionError('Downloader must never be called')
    fake_session_module.U2netSession = Session
    fake_ort = ModuleType('onnxruntime'); fake_ort.SessionOptions = type('Options', (), {})
    monkeypatch.setitem(__import__('sys').modules, 'rembg', fake_rembg)
    monkeypatch.setitem(__import__('sys').modules, 'rembg.sessions.u2net', fake_session_module)
    monkeypatch.setitem(__import__('sys').modules, 'onnxruntime', fake_ort)
    session, remove = white.load_cached_white_background_model()
    assert session.path == path and remove is fake_rembg.remove


def test_actual_worker_pipeline_preserves_rgb_dpi_icc_and_reports_local_success(tmp_path, monkeypatch):
    source, segmented = fixture_png(tmp_path)
    original = source.read_bytes()
    remover = Mock(return_value=segmented)
    loader = Mock(return_value=(object(), remover))
    monkeypatch.setattr(white, 'load_cached_white_background_model', loader)
    w = worker(tmp_path); messages = []; w.progress.connect(messages.append)
    raw = tmp_path / 'rough'; raw.mkdir()
    output = tmp_path / 'ready.png'
    remote = Mock(side_effect=AssertionError('No remote processing'))
    monkeypatch.setattr(w, '_kie_run_model_task', remote)
    w._process_file_entry(1, 1, str(source), str(raw), str(output))
    with Image.open(source) as before, Image.open(output) as after:
        assert after.mode == 'RGBA'
        assert np.array_equal(np.asarray(before), np.asarray(after)[:, :, :3])
        assert after.getpixel((8, 6))[3] == 255 and after.getpixel((0, 0))[3] == 0
        assert after.info.get('icc_profile') == b'fixture-ICC'
        assert after.info.get('dpi')[0] == pytest.approx(240, abs=.02)
    assert source.read_bytes() == original
    assert any('background_removal; status=running' in m for m in messages)
    assert any('background_removal; status=complete' in m for m in messages)
    loader.assert_called_once(); remover.assert_called_once(); remote.assert_not_called()
    assert w._uses_local_remove_bg() and not w._uses_kie_remove_bg()


def test_cancel_during_inference_never_publishes_output(tmp_path, monkeypatch):
    source, segmented = fixture_png(tmp_path); original = source.read_bytes()
    w = worker(tmp_path)
    def cancelled(*args, **kwargs):
        w.stop(); return segmented
    monkeypatch.setattr(white, 'load_cached_white_background_model', lambda: (object(), cancelled))
    output = tmp_path / 'ready.png'
    with pytest.raises(main.ProcessingCancelled):
        w._run_local_white_background(str(source), str(output))
    assert not output.exists() and source.read_bytes() == original


def test_missing_model_emits_failed_stage_without_output_and_can_retry(tmp_path, monkeypatch):
    source, segmented = fixture_png(tmp_path)
    w = worker(tmp_path); messages=[]; w.progress.connect(messages.append)
    w.selected_files = [str(source)]
    loader = Mock(side_effect=white.WhiteBackgroundAmbiguousError('Локальная модель не установлена'))
    monkeypatch.setattr(white, 'load_cached_white_background_model', loader)
    w._mode2_process_files(emit_final=False)
    assert any('background_removal; status=failed' in m for m in messages)
    assert not list(tmp_path.glob('**/*ready*.png'))
    loader.side_effect = None; loader.return_value = (object(), Mock(return_value=segmented))
    output = tmp_path / 'retry.png'
    w._run_local_white_background(str(source), str(output))
    assert output.exists()


@pytest.mark.parametrize('settings,expected_dpi', [
    ({'export_300_dpi': True}, 300),
    ({'cleanup_preserve_dpi': False}, None),
])
def test_white_export_respects_explicit_dpi_policy(tmp_path, monkeypatch, settings, expected_dpi):
    source, segmented = fixture_png(tmp_path)
    monkeypatch.setattr(white, 'load_cached_white_background_model', lambda: (object(), Mock(return_value=segmented)))
    w = worker(tmp_path, **settings)
    raw = tmp_path / 'rough'; raw.mkdir()
    output = tmp_path / 'ready.png'
    w._process_file_entry(1, 1, str(source), str(raw), str(output))
    with Image.open(output) as image:
        if expected_dpi is None:
            assert 'dpi' not in image.info
        else:
            assert image.info['dpi'][0] == pytest.approx(expected_dpi, abs=.02)


def test_batch_local_error_does_not_block_next_file_and_session_is_reused(tmp_path, monkeypatch):
    good, segmented = fixture_png(tmp_path)
    bad = tmp_path / 'blue.png'; Image.new('RGB', (32, 28), 'blue').save(bad)
    w = worker(tmp_path); w.selected_files = [str(bad), str(good)]
    messages=[]; w.progress.connect(messages.append)
    loader=Mock(return_value=(object(), Mock(return_value=segmented)))
    monkeypatch.setattr(white, 'load_cached_white_background_model', loader)
    w._mode2_process_files(emit_final=False)
    outputs=list(tmp_path.rglob('*_ready*.png'))
    assert len(outputs) == 1 and outputs[0].name.startswith('source')
    assert any('background_removal; status=failed' in m for m in messages)
    assert any('background_removal; status=complete' in m for m in messages)
    w._run_local_white_background(str(good), str(tmp_path/'second.png'))
    loader.assert_called_once()
