"""Owner-approved final selection removes weak key rims, not retained paint RGB."""
import numpy as np
import pytest
from PIL import Image

import chroma_key


KEYS = [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])]


@pytest.mark.parametrize('key,order', KEYS)
@pytest.mark.parametrize('route', ['precise', 'staged'])
def test_public_removes_weak_background_boundary_after_colour_stages(key, order, route):
    level = 255 if route == 'precise' else 250
    background = np.array([0, 0, level], dtype=float)[order]
    paint = np.array([200, 150, 255] if route == 'precise' else [200, 200, 0], dtype=float)[order]
    core = paint if route == 'precise' else np.array([220, 220, 0], dtype=float)[order]
    source = np.broadcast_to(background, (96, 96, 3)).copy()
    source[20:76, 20:76] = core
    source[20, 20:76] = .2 * paint + .8 * background
    image = Image.fromarray(np.rint(source).astype(np.uint8))
    before = image.tobytes()
    stages = {}
    result = np.asarray(chroma_key.remove_chroma_key_automatic(
        image, key, subject_profile='opaque_clipart',
        stage_observer=lambda name, snapshot: stages.update({name: np.array(snapshot)}),
    ))
    assert route + '_result' in stages
    assert np.all(result[20, 30:66, 3] == 0)
    assert 'opaque_edge_cleanup' in stages
    previous = stages['edge_chroma_repair']
    np.testing.assert_array_equal(result[..., :3], previous[..., :3])
    np.testing.assert_array_equal(result[previous[..., 3] >= 128], previous[previous[..., 3] >= 128])
    assert np.all(previous[20, 30:66, 3] > 0)
    assert np.max(abs(previous[20, 30:66, :3].astype(float) - paint)) <= 2
    np.testing.assert_array_equal(result, stages['opaque_edge_cleanup'])
    assert image.tobytes() == before


def boundary_fixture(order, origin=(20, 20), source_alpha=255):
    x, y = origin
    shape = (610, 610) if max(origin) > 100 else (96, 96)
    key = np.array([0, 0, 255], dtype=float)[order]
    paint = np.array([60, 45, 30], dtype=float)[order]
    source = np.empty((*shape, 4), dtype=np.uint8)
    source[:] = np.r_[key, 255]
    source[y:y+56, x:x+56, :3] = paint
    result = np.zeros((*shape, 4), dtype=np.uint8)
    result[y:y+56, x:x+56] = np.r_[paint, 255]
    for offset, alpha in enumerate([0, 1, 127, 128, 254, 255]):
        a = alpha / 255
        source[y, x+16+offset, :3] = np.rint(a*paint + (1-a)*key)
        result[y, x+16+offset] = np.r_[paint, alpha]
    source[0, 0, 3] = source_alpha
    return Image.fromarray(source), Image.fromarray(result), key


@pytest.mark.parametrize('key,order', KEYS)
@pytest.mark.parametrize('origin', [(20, 20), (500, 500), (512, 512), (510, 508)])
def test_final_selection_has_exact_half_coverage_bounds_and_preserves_rgb(key, order, origin):
    source, provisional, measured = boundary_fixture(order, origin)
    before = source.tobytes(), provisional.tobytes()
    cleaned = chroma_key._clean_opaque_key_boundary(source, provisional, measured)
    result = np.asarray(cleaned)
    assert cleaned.info['vibix:precleanup_alpha'].mode == 'L'
    assert cleaned.info['vibix:precleanup_alpha'].tobytes() == provisional.getchannel('A').tobytes()
    x, y = origin
    np.testing.assert_array_equal(result[y, x+16:x+22, 3], [0, 0, 0, 128, 254, 255])
    np.testing.assert_array_equal(result[..., :3], np.asarray(provisional)[..., :3])
    stronger = np.asarray(provisional)[..., 3] >= 128
    np.testing.assert_array_equal(result[stronger], np.asarray(provisional)[stronger])
    assert before == (source.tobytes(), provisional.tobytes())


@pytest.mark.parametrize('source_alpha', [0, 1, 128, 254])
def test_any_supplied_source_alpha_bypasses_final_selection(source_alpha):
    source, provisional, measured = boundary_fixture([0, 1, 2], source_alpha=source_alpha)
    result = chroma_key._clean_opaque_key_boundary(source, provisional, measured)
    assert result.tobytes() == provisional.tobytes()


def test_weak_non_key_coloured_paint_is_retained():
    source, provisional, measured = boundary_fixture([0, 1, 2])
    pixels = np.array(source)
    pixels[20, 36:38, :3] = [80, 120, 40]
    source = Image.fromarray(pixels)
    result = np.asarray(chroma_key._clean_opaque_key_boundary(source, provisional, measured))
    np.testing.assert_array_equal(result[20, 36:38], np.asarray(provisional)[20, 36:38])


@pytest.mark.parametrize('mode', ['LA', 'P'])
@pytest.mark.parametrize('alpha', [0, 128, 254])
def test_supplied_alpha_in_other_pillow_modes_bypasses_selection(mode, alpha):
    source, provisional, measured = boundary_fixture([0, 1, 2])
    if mode == 'LA':
        source = source.convert('LA')
        source.putpixel((0, 0), (255, alpha))
    else:
        source = source.convert('RGB').convert('P', palette=Image.Palette.ADAPTIVE)
        index = source.getpixel((0, 0))
        transparency = bytearray([255] * 256)
        transparency[index] = alpha
        source.info['transparency'] = bytes(transparency)
    before = source.tobytes()
    result = chroma_key._clean_opaque_key_boundary(source, provisional, measured)
    assert result.tobytes() == provisional.tobytes()
    assert source.tobytes() == before


@pytest.mark.parametrize('size', [(1, 1), (1, 3), (3, 1)])
def test_uniform_background_has_no_boundary_even_in_small_images(size):
    source = Image.new('RGB', size, (0, 0, 255))
    provisional = Image.new('RGBA', size, (100, 80, 30, 64))
    result = chroma_key._clean_opaque_key_boundary(source, provisional, np.array([0, 0, 255]))
    assert result.tobytes() == provisional.tobytes()
