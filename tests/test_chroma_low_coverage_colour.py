"""Numerical safeguards must not darken valid, low-coverage painted edges."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import _remove_chroma_key_staged, remove_chroma_key_automatic


@pytest.mark.parametrize('key,order', [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])])
@pytest.mark.parametrize('paint,coverage', [([200, 150, 80], .04), ([250, 200, 105], .04), ([200, 200, 55], .03)])
@pytest.mark.parametrize('entry', ['staged', 'automatic'])
def test_valid_low_coverage_keeps_known_paint_colour(key, order, paint, coverage, entry):
    background = np.array([0, 0, 255], dtype=float)[order]
    paint = np.array(paint, dtype=float)[order]
    source = np.broadcast_to(background, (96, 96, 3)).copy()
    source[20:76, 20:76] = paint
    observed = coverage * paint + (1 - coverage) * background
    # These samples have exact integer composites, avoiding a quantization oracle.
    np.testing.assert_allclose(observed, np.rint(observed), atol=1e-6)
    source[20, 20:76] = observed
    image = Image.fromarray(np.rint(source).astype(np.uint8))
    before = image.tobytes()
    if entry == 'staged':
        result = _remove_chroma_key_staged(image, key, opaque_subject=True)
    else:
        result = remove_chroma_key_automatic(image, key, subject_profile='opaque_clipart')
    pixels = np.asarray(result)
    assert np.max(np.abs(pixels[20, 30:66, :3].astype(float) - paint)) <= 2
    if entry == 'automatic':
        assert np.max(np.abs(pixels[20, 30:66, 3].astype(float) - 255 * coverage)) <= 1
    assert np.all(pixels[20, 30:66, 3] > 0)
    np.testing.assert_array_equal(pixels[30:70, 30:70, :3], np.broadcast_to(paint, (40, 40, 3)))
    assert np.all(pixels[30:70, 30:70, 3] == 255)
    assert np.all(pixels[:15, :, 3] == 0)
    assert image.tobytes() == before


@pytest.mark.parametrize('key,order', [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])])
@pytest.mark.parametrize('case,paint,background,spill,source_alpha,expected', [
    ('legacy', [200, 150, 80], [0, 0, 255], 0, 255, [160, 120, 64]),
    ('supplied_alpha', [200, 150, 80], [0, 0, 255], 0, 128, [160, 120, 64]),
    ('out_of_gamut', [255, 235, 180], [0, 0, 255], 0, 255, [200, 180, 140]),
    ('additive', [250, 240, 100], [20, 45, 240], .08, 255, [203, 182, 80]),
])
def test_weak_coverage_fix_preserves_excluded_cases(
        key, order, case, paint, background, spill, source_alpha, expected):
    paint = np.array(paint, dtype=float)[order]
    background = np.array(background, dtype=float)[order]
    rgb = np.broadcast_to(background, (96, 96, 3)).copy()
    rgb[20:76, 20:76] = paint
    rgb[20, 20:76] = np.rint(.04 * paint + (.96 + spill) * background)
    pixels = np.dstack([rgb.astype(np.uint8), np.full((96, 96), 255, dtype=np.uint8)])
    pixels[20, 20:76, 3] = source_alpha
    source = Image.fromarray(pixels)
    before = source.tobytes()
    result = np.asarray(_remove_chroma_key_staged(source, key, opaque_subject=case != 'legacy'))
    # Baseline results from31da612: uncertain/clipped fits and existing alpha
    # are deliberately outside this numerical fix; do not amplify their noise.
    expected_rgba = np.r_[np.array(expected)[order], 4]
    np.testing.assert_array_equal(result[20, 30:66], np.broadcast_to(expected_rgba, (36, 4)))
    assert source.tobytes() == before
