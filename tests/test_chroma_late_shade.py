"""Late AA fitting must distinguish paint brightness from key contamination."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import _refine_opaque_boundary, remove_chroma_key_automatic


KEYS = [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])]


def scene(core, paint, coverage, order):
    key = np.array([0, 0, 255], dtype=np.float32)[order]
    core = np.array(core, dtype=np.float32)[order]
    paint = np.array(paint, dtype=np.float32)[order]
    rgb = np.broadcast_to(key, (96, 96, 3)).copy().astype(np.uint8)
    rgb[20:76, 20:76] = core
    rgb[20, 20:76] = np.rint(coverage * paint + (1 - coverage) * key)
    provisional = np.zeros((96, 96, 4), dtype=np.uint8)
    provisional[20:76, 20:76, :3] = core
    provisional[20:76, 20:76, 3] = 255
    provisional[20, 20:76, :3] = paint
    provisional[20, 20:76, 3] = round(coverage * 255)
    return Image.fromarray(rgb), Image.fromarray(provisional), key, paint


@pytest.mark.parametrize('key_name,order', KEYS)
@pytest.mark.parametrize('coverage', [.2, .3, .4, .6])
@pytest.mark.parametrize('core,paint', [([220]*3, [210]*3), ([200, 180, 100], [190, 171, 95])])
def test_late_boundary_preserves_known_shaded_paint(key_name, order, coverage, core, paint):
    source, provisional, key, expected = scene(core, paint, coverage, order)
    before = source.tobytes(), provisional.tobytes()
    result = np.array(_refine_opaque_boundary(source, provisional, key))
    np.testing.assert_array_equal(result[20, 30:66, :3], np.broadcast_to(expected, (36, 3)))
    assert np.max(abs(result[20, 30:66, 3].astype(int) - round(coverage * 255))) <= 1
    protected = (np.array(provisional)[..., 3] == 0) | (np.array(provisional)[..., 3] == 255)
    np.testing.assert_array_equal(result[protected], np.array(provisional)[protected])
    assert before == (source.tobytes(), provisional.tobytes())


@pytest.mark.parametrize('key_name,order', KEYS)
@pytest.mark.parametrize('core,paint', [([220]*3, [210]*3), ([200, 180, 100], [190, 171, 95])])
def test_automatic_low_coverage_does_not_add_opponent_rim(key_name, order, core, paint):
    source, _provisional, _key, expected = scene(core, paint, .2, order)
    stages = {}
    result = np.array(remove_chroma_key_automatic(
        source, key_name, subject_profile='opaque_clipart',
        stage_observer=lambda name, image: stages.update({name: np.array(image)})))
    assert 'staged_result' in stages
    assert np.max(abs(result[20, 30:66, :3].astype(float) - expected)) <= 3
    assert np.max(abs(result[20, 30:66, 3].astype(int) - 51)) <= 2
    # Confirm the actual late stage as well as the exported public result.
    assert np.max(abs(stages['opaque_boundary'][20, 30:66, :3].astype(float) - expected)) <= 3


@pytest.mark.parametrize('key_name,order', KEYS)
@pytest.mark.parametrize('defect', ['wrong_rgb', 'wrong_coverage', 'source_mismatch'])
def test_late_boundary_still_repairs_unexplained_provisional(key_name, order, defect):
    source, provisional, key, expected = scene([220]*3, [220]*3, .2, order)
    pixels = np.array(provisional)
    if defect == 'wrong_rgb':
        pixels[20, 20:76, :3] = np.array([220, 220, 160])[order]
    elif defect == 'wrong_coverage':
        pixels[20, 20:76, 3] = 128
    else:
        pixels[20, 20:76, :3] = np.array([210, 220, 220])[order]
    result = np.array(_refine_opaque_boundary(source, Image.fromarray(pixels), key))
    assert np.max(abs(result[20, 30:66, :3].astype(float) - expected)) <= 2
    assert np.max(abs(result[20, 30:66, 3].astype(int) - 51)) <= 1
