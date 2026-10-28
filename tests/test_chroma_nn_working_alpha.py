"""Keep NN colour reconstruction independent of the approved weak-edge delivery mask."""
import numpy as np
import pytest
from PIL import Image

import main
from alpha_cleanup import DELIVERY_EDGE_GAIN, HARD_EDGE_MAX_WIDTH, clean_alpha
from studio_processing_api import ProcessingEngine


@pytest.fixture(autouse=True)
def without_edge_matting(monkeypatch):
    """These tests pin the engine-cutout contract that applies when edge matting does not."""
    monkeypatch.setattr(main, 'matte_edges', lambda _source, cutout, _key, **_kwargs: cutout)


def forbid_providers(worker):
    def reject(*_args, **_kwargs):
        raise AssertionError('Network/provider call forbidden in this offline test')
    worker._kie_upload_file = reject
    worker._download_file = reject
    worker._fal_source_url = reject
    worker._download_precleanup_result = reject


def masks(has_partial=True):
    working = Image.new('RGBA', (10, 8), (0, 0, 255, 0))
    working.paste((200, 150, 80, 255), (2, 2, 8, 6))
    working.paste((190, 140, 70, 64), (4, 1, 6, 2))
    if has_partial:
        working.paste((180, 130, 60, 192), (4, 6, 6, 7))
    delivery = working.copy()
    delivery.paste((190, 140, 70, 0), (4, 1, 6, 2))
    return working, delivery


@pytest.mark.parametrize('trim', [False, True])
@pytest.mark.parametrize('has_hint', [False, True])
@pytest.mark.parametrize('has_partial', [False, True])
def test_local_nn_uses_working_alpha_then_publishes_delivery_alpha(tmp_path, trim, has_hint, has_partial):
    working, delivery = masks(has_partial)
    source = tmp_path / 'source.png'
    Image.new('RGB', working.size, (0, 0, 255)).save(source)
    source_before = source.read_bytes()

    def remove(_source, _color, *, subject_profile):
        assert subject_profile == 'opaque_clipart'
        result = delivery.copy()
        if has_hint:
            result.info['vibix:precleanup_alpha'] = working.getchannel('A')
        return result

    engine = ProcessingEngine('opaque-clipart-v15' if has_hint else 'opaque-clipart-v14', remove,
                              lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False,
        'remove_bg': True, 'remove_bg_provider': 'local_chroma_key', 'chroma_key_color': 'blue',
        'upscale_after': True, 'upscale_after_provider': 'local_realesrgan',
        'local_realesrgan_after_scale': 2, 'trim_enabled': trim, 'trim_mode': 'alpha',
    }, processing_engine=engine)
    forbid_providers(worker)
    raw = tmp_path / 'raw'
    raw.mkdir()
    expected_input = working if has_hint else delivery
    box = expected_input.getchannel('A').getbbox() if trim else (0, 0, *working.size)
    expected_input = expected_input.crop(box)
    # With the matte hint the delivery alpha is published cleaned of haze (owner 2026-10-28); colours are untouched.
    published = clean_alpha(delivery, gain=DELIVERY_EDGE_GAIN) if has_hint else delivery
    expected_delivery = published.crop(box).getchannel('A')
    calls = []

    def upscale(input_path, output_path, scale):
        assert scale == 2
        with Image.open(input_path) as opened:
            actual_input = opened.convert('RGBA')
        assert actual_input.tobytes() == expected_input.tobytes()
        assert 'vibix:precleanup_alpha' not in actual_input.info
        np.testing.assert_array_equal(np.asarray(worker._prepare_upscale_rgb(actual_input)),
                                      np.asarray(worker._prepare_upscale_rgb(expected_input)))
        # Actual runner restores its working alpha after NN. The host replaces
        # it with delivery alpha only after colour reconstruction has finished.
        size = (actual_input.width*2, actual_input.height*2)
        Image.new('RGB', size, (101, 121, 141)).save(output_path)
        worker._restore_upscaled_alpha(output_path, actual_input.getchannel('A'))
        calls.append(input_path)

    worker._run_local_realesrgan = upscale
    result_path = worker._run_processing_pipeline(str(source), None, str(raw), 1, 'case',
                                                  chroma_key_color='blue', result_kind='clipart')
    assert len(calls) == 1
    with Image.open(result_path) as opened:
        result = opened.convert('RGBA')
        histogram = expected_delivery.histogram()
        resample = Image.Resampling.BILINEAR if any(histogram[1:255]) else Image.Resampling.NEAREST
        resized = expected_delivery.resize(result.size, resample)
        # The smooth edge is tightened again after the upscale (owner 2026-10-28).
        tightened = clean_alpha(Image.merge('RGBA', (*result.convert('RGB').split(), resized)),
                                hard_max_width=HARD_EDGE_MAX_WIDTH * 2)
        assert result.getchannel('A').tobytes() == tightened.getchannel('A').tobytes()
        np.testing.assert_array_equal(np.asarray(result)[..., :3],
                                      np.broadcast_to([101, 121, 141], (result.height, result.width, 3)))
        assert 'vibix:precleanup_alpha' not in result.info
    normal_cutout = next(raw.glob('*_chroma_key_nobg_*.png'))
    with Image.open(normal_cutout) as saved:
        assert saved.convert('RGBA').tobytes() == published.tobytes()
        assert 'vibix:precleanup_alpha' not in saved.info
    assert worker._item_context.chroma_receipt['profile'] == engine.profile
    assert not worker._item_context.manual_transparency_required
    assert source.read_bytes() == source_before


def test_chroma_hint_is_consumed_even_without_upscale(tmp_path):
    working, delivery = masks()
    returned = []
    def remove(_source, _color, *, subject_profile):
        result = delivery.copy()
        result.info['vibix:precleanup_alpha'] = working.getchannel('A')
        returned.append(result)
        return result
    engine = ProcessingEngine('opaque-clipart-v15', remove, lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False,
        'remove_bg': True, 'remove_bg_provider': 'local_chroma_key', 'chroma_key_color': 'blue',
    }, processing_engine=engine)
    forbid_providers(worker)
    source = tmp_path / 'source.png'
    Image.new('RGB', working.size, 'blue').save(source)
    result_path = worker._run_processing_pipeline(str(source), None, str(tmp_path), 1, 'native',
                                                  result_kind='clipart')
    with Image.open(result_path) as saved:
        # The final alpha clean-up is applied to the engine's delivery mask; colours are untouched.
        assert saved.convert('RGBA').tobytes() == clean_alpha(delivery, gain=DELIVERY_EDGE_GAIN).tobytes()
    assert 'vibix:precleanup_alpha' not in returned[0].info


@pytest.mark.parametrize('bad', ['type', 'mode', 'size', 'strong_crop', 'strong_cut', 'partial_change', 'empty'])
def test_invalid_working_alpha_is_rejected_before_upscale(tmp_path, bad):
    working, delivery = masks()
    hint = working.getchannel('A')
    if bad == 'type':
        hint = 'malformed'
    elif bad == 'mode':
        hint = hint.convert('RGB')
    elif bad == 'size':
        hint = hint.resize((1, 1))
    elif bad == 'strong_crop':
        hint.putpixel((2, 2), 0)  # Would let working bbox omit retained strong paint.
    elif bad == 'strong_cut':
        delivery.putpixel((2, 2), (200, 150, 80, 0))
    elif bad == 'partial_change':
        delivery.putpixel((4, 1), (190, 140, 70, 32))
    else:
        delivery.putalpha(Image.new('L', delivery.size, 0))
        hint = Image.new('L', working.size, 64)
    def remove(_source, _color, *, subject_profile):
        result = delivery.copy()
        result.info['vibix:precleanup_alpha'] = hint
        return result
    engine = ProcessingEngine('opaque-clipart-v15', remove, lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False, 'remove_bg': True, 'remove_bg_provider': 'local_chroma_key',
        'chroma_key_color': 'blue', 'upscale_after': True,
        'upscale_after_provider': 'local_realesrgan', 'trim_enabled': True,
    }, processing_engine=engine)
    forbid_providers(worker)
    def forbidden_nn(*_args, **_kwargs):
        raise AssertionError('Invalid hint must be rejected before NN')
    worker._run_local_realesrgan = forbidden_nn
    source = tmp_path / 'source.png'
    Image.new('RGB', working.size, 'blue').save(source)
    before = source.read_bytes()
    with pytest.raises(ValueError):
        worker._run_processing_pipeline(str(source), None, str(tmp_path), 1, 'invalid',
                                        result_kind='clipart')
    assert source.read_bytes() == before


@pytest.mark.parametrize('first_fails', [False, True])
def test_working_alpha_does_not_survive_into_next_item(tmp_path, first_fails):
    working, delivery = masks()
    removes = []
    def remove(_source, _color, *, subject_profile):
        result = delivery.copy()
        if not removes:
            result.info['vibix:precleanup_alpha'] = working.getchannel('A')
        removes.append(True)
        return result
    engine = ProcessingEngine('opaque-clipart-v15', remove, lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False, 'remove_bg': True, 'remove_bg_provider': 'local_chroma_key',
        'chroma_key_color': 'blue', 'upscale_after': True,
        'upscale_after_provider': 'local_realesrgan', 'local_realesrgan_after_scale': 2,
    }, processing_engine=engine)
    forbid_providers(worker)
    calls = []
    def upscale(input_path, output_path, scale):
        expected = working if not calls else delivery
        with Image.open(input_path) as opened:
            actual = opened.convert('RGBA')
        assert actual.tobytes() == expected.tobytes()
        calls.append(input_path)
        if first_fails and len(calls) == 1:
            raise RuntimeError('Simulated NN failure')
        Image.new('RGB', (actual.width*scale, actual.height*scale), (101, 121, 141)).save(output_path)
        worker._restore_upscaled_alpha(output_path, actual.getchannel('A'))
    worker._run_local_realesrgan = upscale
    source = tmp_path / 'source.png'
    Image.new('RGB', working.size, 'blue').save(source)
    if first_fails:
        with pytest.raises(RuntimeError, match='Simulated NN failure'):
            worker._run_processing_pipeline(str(source), None, str(tmp_path), 1, 'first', result_kind='clipart')
    else:
        worker._run_processing_pipeline(str(source), None, str(tmp_path), 1, 'first', result_kind='clipart')
    worker._run_processing_pipeline(str(source), None, str(tmp_path), 2, 'second', result_kind='clipart')
    assert len(calls) == 2


def test_empty_delivery_after_wrong_nn_size_is_rejected(tmp_path):
    working = Image.new('RGBA', (8, 8), (190, 140, 70, 64))
    working.putpixel((0, 0), (200, 150, 80, 255))
    delivery = working.copy()
    delivery.putalpha(Image.new('L', working.size, 0))
    delivery.putpixel((0, 0), (200, 150, 80, 255))
    def remove(_source, _color, *, subject_profile):
        result = delivery.copy()
        result.info['vibix:precleanup_alpha'] = working.getchannel('A')
        return result
    engine = ProcessingEngine('opaque-clipart-v15', remove, lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False, 'remove_bg': True, 'remove_bg_provider': 'local_chroma_key',
        'chroma_key_color': 'blue', 'upscale_after': True,
        'upscale_after_provider': 'local_realesrgan', 'local_realesrgan_after_scale': 2,
    }, processing_engine=engine)
    forbid_providers(worker)
    def upscale(_input_path, output_path, scale):
        # Working alpha passes existing validation, but binary delivery resized
        # to this invalid size loses the one retained corner. Never export blank.
        Image.new('RGBA', (1, 1), (101, 121, 141, 64)).save(output_path)
    worker._run_local_realesrgan = upscale
    source = tmp_path / 'source.png'
    Image.new('RGB', working.size, 'blue').save(source)
    with pytest.raises(ValueError, match='пустое изображение'):
        worker._run_processing_pipeline(str(source), None, str(tmp_path), 1, 'empty', result_kind='clipart')


def test_faint_haze_is_removed_from_the_delivery_alpha_with_local_upscale(tmp_path):
    """Owner 2026-10-28: «туман» around the cut-out. With the local upscale after the cut-out the delivery alpha
    skipped the final alpha clean-up, so faint alpha far from the subject survived into the final PNG."""
    size = (40, 24)
    working = Image.new('RGBA', size, (0, 0, 255, 0))
    working.paste((200, 150, 80, 255), (20, 6, 38, 20))
    working.paste((200, 150, 80, 8), (1, 1, 9, 9))  # haze: weak alpha far from the subject
    delivery = working.copy()
    source = tmp_path / 'source.png'
    Image.new('RGB', size, (0, 0, 255)).save(source)

    def remove(_source, _color, *, subject_profile):
        result = delivery.copy()
        result.info['vibix:precleanup_alpha'] = working.getchannel('A')
        return result

    engine = ProcessingEngine('opaque-clipart-v15', remove, lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False, 'remove_bg': True, 'remove_bg_provider': 'local_chroma_key', 'chroma_key_color': 'blue',
        'upscale_after': True, 'upscale_after_provider': 'local_realesrgan',
        'local_realesrgan_after_scale': 2, 'trim_enabled': False, 'trim_mode': 'alpha',
    }, processing_engine=engine)
    forbid_providers(worker)
    raw = tmp_path / 'raw'
    raw.mkdir()

    def upscale(input_path, output_path, scale):
        with Image.open(input_path) as opened:
            actual_input = opened.convert('RGBA')
        Image.new('RGB', (actual_input.width * scale, actual_input.height * scale), (101, 121, 141)).save(output_path)
        worker._restore_upscaled_alpha(output_path, actual_input.getchannel('A'))

    worker._run_local_realesrgan = upscale
    result_path = worker._run_processing_pipeline(str(source), None, str(raw), 1, 'case',
                                                  chroma_key_color='blue', result_kind='clipart')
    with Image.open(result_path) as opened:
        alpha = np.asarray(opened.convert('RGBA').getchannel('A'))
    assert alpha[2:16, 2:16].max() == 0  # the haze patch is gone (the picture is 2x here)
    assert alpha[24:36, 44:72].min() == 255  # the subject itself is untouched


def test_smooth_edge_is_tightened_again_after_the_local_upscale(tmp_path):
    """Owner 2026-10-28: the upscale stretches a smooth alpha edge by its factor; the edge clean-up runs again so
    the published edge is as narrow as it was before the enlargement."""
    size = (60, 24)
    working = Image.new('RGBA', size, (0, 0, 255, 0))
    working.paste((200, 150, 80, 255), (30, 4, 58, 20))
    ramp = [32, 80, 128, 176, 224]  # a smooth edge about 5 px wide on the left side of the subject
    for step, alpha in enumerate(ramp):
        working.paste((200, 150, 80, alpha), (25 + step, 4, 26 + step, 20))
    delivery = working.copy()
    source = tmp_path / 'source.png'
    Image.new('RGB', size, (0, 0, 255)).save(source)

    def remove(_source, _color, *, subject_profile):
        result = delivery.copy()
        result.info['vibix:precleanup_alpha'] = working.getchannel('A')
        return result

    engine = ProcessingEngine('opaque-clipart-v15', remove, lambda _source: (0, 0, 255))
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'upscale': False, 'remove_bg': True, 'remove_bg_provider': 'local_chroma_key', 'chroma_key_color': 'blue',
        'upscale_after': True, 'upscale_after_provider': 'local_realesrgan',
        'local_realesrgan_after_scale': 4, 'trim_enabled': False, 'trim_mode': 'alpha',
    }, processing_engine=engine)
    forbid_providers(worker)
    raw = tmp_path / 'raw'
    raw.mkdir()

    def upscale(input_path, output_path, scale):
        with Image.open(input_path) as opened:
            actual_input = opened.convert('RGBA')
        Image.new('RGB', (actual_input.width * scale, actual_input.height * scale), (101, 121, 141)).save(output_path)
        worker._restore_upscaled_alpha(output_path, actual_input.getchannel('A'))

    worker._run_local_realesrgan = upscale
    result_path = worker._run_processing_pipeline(str(source), None, str(raw), 1, 'case',
                                                  chroma_key_color='blue', result_kind='clipart')
    with Image.open(result_path) as opened:
        row = np.asarray(opened.convert('RGBA').getchannel('A'))[48]
    partial = int(((row > 0) & (row < 255)).sum())
    # The delivery cut keeps its soft transition now, so only the pass after the upscale narrows the edge.
    assert partial <= 14, f'the edge is {partial} px wide after a 4x upscale (20 without the second pass)'
