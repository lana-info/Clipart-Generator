"""Transparent padding is final canvas space, never alpha softening or upscale input."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
import pytest
from PIL import Image
import main
from v3_project_state import ImageOperationData


@pytest.mark.parametrize('size,pad', [((2000, 3000), 30), ((87, 101), 2), ((4, 3), 1)])
def test_final_padding_dimensions_pixels_dpi_and_repeat(tmp_path, size, pad):
    source = tmp_path / 'source.png'
    image = Image.new('RGBA', size, (220, 190, 100, 255))
    image.putpixel((0, 0), (199, 179, 99, 30))
    image.save(source)
    original = source.read_bytes()
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'trim_enabled': True, 'trim_mode': 'alpha', 'trim_padding_percent': 1,
        'export_300_dpi': True})
    output = tmp_path / 'ready.png'
    worker._save_final_output(None, str(source), str(output), str(tmp_path), 1, 'file')
    with Image.open(output) as final:
        assert final.size == (size[0] + 2*pad, size[1] + 2*pad)
        assert final.getchannel('A').getbbox() == (pad, pad, pad+size[0], pad+size[1])
        assert final.crop((pad, pad, pad+size[0], pad+size[1])).tobytes() == image.tobytes()
        assert abs(final.info['dpi'][0] - 300) < .01
        pixels = np.array(final)
        assert not pixels[:pad, :, 3].any()
        assert not pixels[-pad:, :, 3].any()
        assert not pixels[:, :pad, 3].any()
        assert not pixels[:, -pad:, 3].any()
    # Processing an already padded PNG must not accumulate another border.
    second = tmp_path / 'again.png'
    worker._save_final_output(None, str(output), str(second), str(tmp_path), 2, 'file')
    with Image.open(output) as first, Image.open(second) as again:
        assert first.size == again.size
        assert first.tobytes() == again.tobytes()
    assert source.read_bytes() == original


@pytest.mark.parametrize('skip', ['disabled_trim', 'pattern', 'manual_transparency'])
def test_no_padding_when_trim_is_skipped(tmp_path, skip):
    source = tmp_path / 'source.png'
    image = Image.new('RGBA', (80, 90), (220, 190, 100, 255))
    image.save(source)
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'trim_enabled': skip != 'disabled_trim', 'trim_padding_percent': 1})
    worker._item_context.preserve_surface = skip == 'pattern'
    worker._item_context.manual_transparency_required = skip == 'manual_transparency'
    output = tmp_path / 'ready.png'
    worker._save_final_output(None, str(source), str(output), str(tmp_path), 1, 'file')
    with Image.open(output) as final:
        assert final.size == image.size
        assert final.tobytes() == image.tobytes()


def test_padding_policy_roundtrips_and_old_projects_default_to_zero():
    assert ImageOperationData.from_dict({}).trim_padding_percent == 0
    assert ImageOperationData.from_v2_config({"trim_padding_percent": 1}).trim_padding_percent == 1
    data = ImageOperationData(trim_padding_percent=1)
    assert ImageOperationData.from_dict(data.to_dict()).trim_padding_percent == 1
    for invalid in ('invalid', -1, float('nan')):
        assert ImageOperationData.from_dict({'trim_padding_percent': invalid}).trim_padding_percent == 0


@pytest.mark.parametrize('failure', ['write_error', 'cancel'])
def test_padding_failure_preserves_previous_output(tmp_path, monkeypatch, failure):
    source = tmp_path / 'source.png'
    Image.new('RGBA', (100, 80), (210, 200, 190, 255)).save(source)
    source_bytes = source.read_bytes()
    output = tmp_path / 'ready.png'
    Image.new('RGBA', (3, 4), (100, 90, 80, 255)).save(output)
    previous_bytes = output.read_bytes()
    worker = main.WorkerThread('mode2_process', str(tmp_path), {
        'trim_enabled': True, 'trim_padding_percent': 1, 'export_300_dpi': True})
    if failure == 'write_error':
        original_save = worker._save_image_object_as_png

        def fail_padding_save(image, path):
            if image.size == (102, 82):
                raise OSError('padding write failed')
            return original_save(image, path)

        monkeypatch.setattr(worker, '_save_image_object_as_png', fail_padding_save)
        expected_error = OSError
    else:
        original_pad = worker._add_final_trim_padding

        def cancel_after_padding(path):
            original_pad(path)
            worker.stop()

        monkeypatch.setattr(worker, '_add_final_trim_padding', cancel_after_padding)
        expected_error = main.ProcessingCancelled
    with pytest.raises(expected_error):
        worker._save_final_output(None, str(source), str(output), str(tmp_path), 1, 'file')
    assert output.read_bytes() == previous_bytes
    assert source.read_bytes() == source_bytes
    assert not list(tmp_path.glob('.clipart-final-*.stage.png'))
