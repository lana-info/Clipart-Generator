"""Edge matting in the local chroma cut-out and the local Real-ESRGAN pass that follows it."""
import numpy as np
import pytest
from PIL import Image

import main
from studio_processing_api import ProcessingEngine
from tests.test_chroma_matting import _scene


def make_worker(tmp_path, **settings):
    source, cutout, truth = _scene()
    path = tmp_path / 'source.png'
    source.save(path)

    def remove(_source, _color, *, subject_profile):
        return cutout.copy()

    engine = ProcessingEngine('opaque-clipart-v14', remove, lambda _source: (0, 0, 255))
    options = {
        'upscale': False, 'remove_bg': True, 'remove_bg_provider': 'local_chroma_key', 'chroma_key_color': 'blue',
        'trim_enabled': False, 'trim_mode': 'alpha',
    }
    options.update(settings)
    worker = main.WorkerThread('mode2_process', str(tmp_path), options, processing_engine=engine)
    for name in ('_kie_upload_file', '_download_file', '_fal_source_url', '_download_precleanup_result'):
        setattr(worker, name, lambda *_a, **_k: (_ for _ in ()).throw(AssertionError('provider call forbidden')))
    raw = tmp_path / 'raw'
    raw.mkdir()
    return worker, path, raw, cutout, truth


def cut(worker, path, raw):
    return worker._run_processing_pipeline(str(path), None, str(raw), 1, 'case',
                                           chroma_key_color='blue', result_kind='clipart')


def test_local_chroma_cutout_publishes_matted_soft_edges(tmp_path):
    worker, path, raw, cutout, truth = make_worker(tmp_path)

    with Image.open(cut(worker, path, raw)) as opened:
        alpha = np.asarray(opened.convert('RGBA').getchannel('A'), np.float32) / 255.0

    hard = np.asarray(cutout.getchannel('A'), np.float32) / 255.0
    partial = (truth > 0.1) & (truth < 0.9)
    assert np.abs(alpha - truth)[partial].mean() < 0.6 * np.abs(hard - truth)[partial].mean()


def test_a_matting_failure_falls_back_to_the_engine_cutout(tmp_path, monkeypatch):
    worker, path, raw, _, _ = make_worker(tmp_path)
    messages = []
    worker.progress.connect(messages.append)

    def refuse(*_args, **_kwargs):
        raise ValueError('band too wide')

    monkeypatch.setattr(main, 'matte_edges', refuse)

    with Image.open(cut(worker, path, raw)) as opened:
        alpha = np.asarray(opened.convert('RGBA').getchannel('A'))

    assert set(np.unique(alpha)) <= {0, 255}  # the engine's hard key, as before edge matting existed
    assert any('Матирование края пропущено' in message for message in messages)


def fake_realesrgan(worker, tmp_path):
    exe = tmp_path / 'realesrgan-ncnn-vulkan.exe'
    exe.write_bytes(b'')
    model = main.get_local_realesrgan_model_name(worker.local_realesrgan_profile, 2)
    (tmp_path / 'models').mkdir(exist_ok=True)
    for suffix in ('.bin', '.param'):
        (tmp_path / 'models' / (model + suffix)).write_bytes(b'')
    worker.local_realesrgan_dir = str(tmp_path)
    inputs = []

    def execute(_exe, input_path, output_path, _model, scale):
        with Image.open(input_path) as opened:
            image = opened.convert('RGB')
        inputs.append(image.copy())
        image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(output_path)

    worker._execute_realesrgan = execute
    return inputs


@pytest.fixture
def realesrgan_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(main, 'validate_local_realesrgan_exe', lambda _dir: (str(tmp_path / 'realesrgan-ncnn-vulkan.exe'), None))


def soft_cutout():
    image = Image.new('RGBA', (20, 12), (0, 0, 255, 0))
    image.paste((200, 150, 80, 255), (6, 2, 20, 10))
    image.paste((200, 150, 80, 100), (4, 2, 6, 10))
    return image


def test_matted_cutout_sends_its_soft_matte_through_the_network_too(tmp_path, realesrgan_exe):
    worker = make_worker(tmp_path, local_realesrgan_after_scale=2)[0]
    inputs = fake_realesrgan(worker, tmp_path)
    worker._item_context.edge_matted = True
    source = tmp_path / 'in.png'
    soft_cutout().save(source)
    output = tmp_path / 'out.png'

    worker._run_local_realesrgan(str(source), str(output), 2)

    assert len(inputs) == 2
    colour_input, mask_input = inputs
    assert np.asarray(colour_input)[0, 0].tolist() == [0, 0, 255]  # the colour under alpha zero is not repainted
    mask = np.asarray(mask_input)
    assert np.array_equal(mask[..., 0], mask[..., 1]) and mask[5, 4, 0] == 100
    with Image.open(output) as opened:
        assert opened.size == (40, 24)
        assert opened.convert('RGBA').getchannel('A').getpixel((9, 9)) == 100


def test_unmatted_cutout_keeps_the_single_pass_with_repainted_rim(tmp_path, realesrgan_exe):
    worker = make_worker(tmp_path, local_realesrgan_after_scale=2)[0]
    inputs = fake_realesrgan(worker, tmp_path)
    worker._item_context.edge_matted = False
    source = tmp_path / 'in.png'
    soft_cutout().save(source)

    worker._run_local_realesrgan(str(source), str(tmp_path / 'out.png'), 2)

    assert len(inputs) == 1
    assert np.asarray(inputs[0])[0, 0].tolist() == [200, 150, 80]  # blue key replaced by the nearest subject colour


def test_network_matte_cannot_leave_rings_around_the_subject(tmp_path):
    plain = Image.new('L', (40, 24), 0)
    plain.paste(255, (12, 4, 40, 20))
    drawn = Image.new('L', (40, 24), 90)  # network noise everywhere, also far from the subject

    bounded = np.asarray(main.WorkerThread._bound_model_alpha(drawn, plain, 2))

    assert bounded[0, 0] == 0 and bounded[12, 4] == 0
    assert bounded[12, 30] == 255


def test_matted_cutout_loses_haze_and_far_debris_but_keeps_hair_fragments(tmp_path, monkeypatch):
    worker, path, raw, _, _ = make_worker(tmp_path)

    def matted(_source, cutout, _key, **_kwargs):
        result = Image.new('RGBA', cutout.size, (0, 0, 0, 0))
        result.paste((200, 150, 80, 255), (30, 30, 70, 70))
        result.paste((200, 150, 80, 20), (2, 2, 20, 20))        # haze far from the subject
        result.paste((200, 150, 80, 255), (73, 40, 76, 43))     # a detached hair fragment 3 px from the body
        result.paste((200, 150, 80, 255), (90, 85, 93, 88))     # a stray dot, 20 px away
        return result

    monkeypatch.setattr(main, 'matte_edges', matted)

    with Image.open(cut(worker, path, raw)) as opened:
        alpha = np.asarray(opened.convert('RGBA').getchannel('A'))

    assert alpha[2:20, 2:20].max() == 0
    assert alpha[40:43, 73:76].min() == 255
    assert alpha[85:88, 90:93].max() == 0
    assert alpha[50, 50] == 255


def test_matted_cutout_narrows_a_smooth_edge(tmp_path, monkeypatch):
    worker, path, raw, _, _ = make_worker(tmp_path)

    def matted(_source, cutout, _key, **_kwargs):
        result = Image.new('RGBA', cutout.size, (0, 0, 0, 0))
        result.paste((200, 150, 80, 255), (40, 20, 80, 76))
        for step, alpha in enumerate([32, 80, 128, 176, 224]):  # a smooth edge about 5 px wide
            result.paste((200, 150, 80, alpha), (35 + step, 20, 36 + step, 76))
        return result

    monkeypatch.setattr(main, 'matte_edges', matted)

    with Image.open(cut(worker, path, raw)) as opened:
        row = np.asarray(opened.convert('RGBA').getchannel('A'))[48]

    assert int(((row > 0) & (row < 255)).sum()) <= 3


def test_matted_cutout_pulls_a_lilac_hair_tip_back_to_the_fur_hue(tmp_path, monkeypatch):
    worker, path, raw, _, _ = make_worker(tmp_path)
    cream = (230, 200, 160)

    def matted(_source, cutout, _key, **_kwargs):
        result = Image.new('RGBA', cutout.size, (0, 0, 0, 0))
        result.paste(cream + (255,), (20, 20, 76, 76))
        result.paste((150, 120, 170, 128), (76, 40, 79, 44))     # a tip: cream mixed with the blue key
        return result

    monkeypatch.setattr(main, 'matte_edges', matted)

    with Image.open(cut(worker, path, raw)) as opened:
        tip = opened.convert('RGBA').getpixel((77, 42))

    assert tip[2] < tip[1], tip   # fur is never bluer than green; the lilac tip had blue above green
