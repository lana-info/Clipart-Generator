"""Known painted pale edges must not borrow a neighbouring material's hue."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import _remove_chroma_key_staged, remove_chroma_key_automatic
from chroma_rim import refine_edge_mixture

KEYS = [('blue', (0, 1, 2)), ('green', (0, 2, 1)), ('red', (2, 1, 0))]


@pytest.mark.parametrize('key,channels', KEYS)
@pytest.mark.parametrize('width', [1, 2, 3])
@pytest.mark.parametrize('colour', [(241, 241, 226), (245, 245, 241), (249, 246, 233)])
def test_thin_pale_painted_material_keeps_colour_and_coverage(key, channels, width, colour):
    source = np.zeros((128, 128, 4), np.uint8)
    source[:] = (0, 0, 255, 255)
    source[20:108, 30:98] = (240, 210, 130, 255)
    source[20:108, 30:30 + width] = (*colour, 255)
    source = source[..., list(channels) + [3]]
    image = Image.fromarray(source)
    staged = np.asarray(_remove_chroma_key_staged(image, key, opaque_subject=True))
    result = remove_chroma_key_automatic(image, key, subject_profile='opaque_clipart')
    # Check the first solver and the final saved RGBA, not just the guard.
    expected = source[24:104, 30:30 + width]
    np.testing.assert_array_equal(staged[24:104, 30:30 + width], expected)
    np.testing.assert_array_equal(np.asarray(result)[24:104, 30:30 + width], expected)
    assert np.all(np.asarray(result)[:10, :, 3] == 0)
    np.testing.assert_array_equal(np.asarray(image), source)


@pytest.mark.parametrize('key,channels', KEYS)
def test_bright_additive_coloured_material_is_still_cleaned(key, channels):
    measured_key = np.array((20, 45, 240), np.float32)[list(channels)]
    reference = np.array((180, 150, 50), np.float32)[list(channels)]
    clean = np.rint(reference * 1.3)
    source = np.broadcast_to(np.r_[measured_key, 255], (64, 64, 4)).astype(np.uint8).copy()
    provisional = np.zeros_like(source)
    source[12:52, 12:52, :3] = reference
    provisional[12:52, 12:52] = np.r_[reference, 255]
    source[12, 12:52, :3] = np.rint(clean + .25 * measured_key)
    provisional[12, 12:52] = source[12, 12:52]
    result = np.asarray(refine_edge_mixture(Image.fromarray(source), Image.fromarray(provisional), measured_key))
    np.testing.assert_allclose(result[12, 32, :3], clean, atol=2)
    assert result[12, 32, 3] == 255


@pytest.mark.parametrize('key,channels', KEYS)
@pytest.mark.parametrize('coverage', [.8, .85])
def test_real_pale_key_mixture_retains_fractional_coverage(key, channels, coverage):
    background = np.array((20, 45, 240))
    clean = np.array((249, 246, 233))
    source = np.full((96, 96, 3), background, dtype=np.uint8)
    source[20:76, 20:76] = np.rint(coverage * clean + (1 - coverage) * background)
    source[23:73, 23:73] = clean
    result = np.asarray(remove_chroma_key_automatic(
        Image.fromarray(source[..., list(channels)]), key, subject_profile='opaque_clipart',
    ))
    np.testing.assert_allclose(result[20, 40, :3], clean[list(channels)], atol=3)
    assert abs(int(result[20, 40, 3]) - round(coverage * 255)) <= 3


@pytest.mark.parametrize('key,channels', KEYS)
def test_weak_ambiguous_flat_pale_paint_is_preserved(key, channels):
    # These exact RGB bytes can also be a 95% white/key mix. A spatially flat
    # painted rim provides no evidence to choose that interpretation: preserve
    # its source paint under the agreed ambiguity policy, including alpha.
    background = np.array((20, 45, 240))
    clean = np.array((249, 246, 233))
    paint = np.rint(.95 * clean + .05 * background).astype(np.uint8)
    source = np.full((96, 96, 3), background, dtype=np.uint8)
    source[20:76, 20:76] = paint
    source[23:73, 23:73] = clean
    result = np.asarray(remove_chroma_key_automatic(
        Image.fromarray(source[..., list(channels)]), key, subject_profile='opaque_clipart',
    ))
    np.testing.assert_array_equal(result[20, 40, :3], paint[list(channels)])
    assert result[20, 40, 3] == 255
