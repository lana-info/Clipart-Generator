"""Exact composites at RGB endpoints must survive the later staged despill."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import _remove_chroma_key_staged, remove_chroma_key_automatic


KEYS = [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])]


def exact_scene(core, paint, coverage, order, key_level=255):
    background = np.array([0, 0, key_level], dtype=float)[order]
    core = np.array(core, dtype=float)[order]
    paint = np.array(paint, dtype=float)[order]
    rgb = np.broadcast_to(background, (96, 96, 3)).copy()
    rgb[20:76, 20:76] = core
    observed = coverage * paint + (1 - coverage) * background
    np.testing.assert_allclose(observed, np.rint(observed), atol=1e-6)
    rgb[20, 20:76] = observed
    return Image.fromarray(np.rint(rgb).astype(np.uint8)), core, paint


@pytest.mark.parametrize('key,order', KEYS)
@pytest.mark.parametrize('coverage', [.2, .4, .6])
@pytest.mark.parametrize('paint', [
    [240, 210, 255], [200, 150, 255], [200, 200, 255],
    [255, 255, 255], [200, 150, 0],
])
def test_staged_preserves_exact_endpoint_paint(key, order, coverage, paint):
    source, core, expected = exact_scene(paint, paint, coverage, order)
    before = source.tobytes()
    result = np.asarray(_remove_chroma_key_staged(source, key, opaque_subject=True))
    assert np.max(abs(result[20, 30:66, :3].astype(float) - expected)) <= 2
    assert np.all(result[20, 30:66, 3] > 0)
    np.testing.assert_array_equal(result[30:70, 30:70, :3], np.broadcast_to(core, (40, 40, 3)))
    assert np.all(result[30:70, 30:70, 3] == 255)
    assert np.all(result[:15, :, 3] == 0)
    assert source.tobytes() == before


@pytest.mark.parametrize('key,order', KEYS)
@pytest.mark.parametrize('coverage', [.1, .2])
@pytest.mark.parametrize('entry', ['staged', 'automatic'])
def test_shaded_endpoint_is_preserved_through_automatic_pipeline(key, order, coverage, entry):
    source, core, expected = exact_scene([220, 220, 0], [200, 200, 0], coverage, order, 250)
    before = source.tobytes()
    stages = {}
    if entry == 'staged':
        result = _remove_chroma_key_staged(source, key, opaque_subject=True)
    else:
        result = remove_chroma_key_automatic(
            source, key, subject_profile='opaque_clipart',
            stage_observer=lambda name, image: stages.update({name: np.asarray(image)}),
        )
        assert np.max(abs(stages['staged_result'][20, 30:66, :3].astype(float) - expected)) <= 2
        assert np.max(abs(stages['opaque_boundary'][20, 30:66, :3].astype(float) - expected)) <= 2
    pixels = np.asarray(result)
    assert np.max(abs(pixels[20, 30:66, :3].astype(float) - expected)) <= 2
    if entry == 'automatic':
        recovered = stages['edge_chroma_repair']
        assert np.max(abs(recovered[20, 30:66, :3].astype(float) - expected)) <= 2
        assert np.max(abs(recovered[20, 30:66, 3].astype(float) - round(coverage * 255))) <= 1
        # Final selection deliberately discards the approved weak key boundary.
        assert np.all(pixels[20, 30:66, 3] == 0)
    else:
        assert np.all(pixels[20, 30:66, 3] > 0)
    np.testing.assert_array_equal(pixels[30:70, 30:70, :3], np.broadcast_to(core, (40, 40, 3)))
    assert np.all(pixels[30:70, 30:70, 3] == 255)
    assert source.tobytes() == before
