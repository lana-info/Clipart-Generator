"""Do not subtract the key twice from already unmixed, shaded painted edges."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import _remove_chroma_key_staged, remove_chroma_key_automatic


def _painted_edge(core, foreground, background, coverage, spill=0):
    pixels = np.broadcast_to(background, (96, 96, 3)).copy().astype(np.uint8)
    pixels[20:76, 20:76] = core
    pixels[20, 20:76] = np.rint(coverage * foreground + (1 - coverage + spill) * background)
    return Image.fromarray(pixels)


def _remove(image, key, entry):
    if entry == 'staged':
        return np.array(_remove_chroma_key_staged(image, key, opaque_subject=True))
    stages = []
    result = remove_chroma_key_automatic(
        image, key, subject_profile='opaque_clipart',
        stage_observer=lambda name, snapshot: stages.append(name),
    )
    assert 'staged_result' in stages  # Exercise the real fallback, including subsequent refinements.
    return np.array(result)


@pytest.mark.parametrize('key,order', [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])])
@pytest.mark.parametrize('entry', ['staged', 'automatic'])
@pytest.mark.parametrize('core,foreground', [((220, 220, 220), (210, 210, 210)), ((200, 200, 100), (190, 190, 95))])
def test_ordinary_shaded_coverage_keeps_its_known_foreground_colour(key, order, entry, core, foreground):
    core = np.array(core)[order]
    foreground = np.array(foreground)[order]
    background = np.array((0, 0, 255))[order]
    image = _painted_edge(core, foreground, background, .6)
    original = image.tobytes()
    result = _remove(image, key, entry)
    # Foreground shading is deliberate. Fitting the brighter core again must
    # not turn neutral paint yellow/cyan/magenta or brighten golden paint.
    error = np.abs(result[20, 30:66, :3].astype(int) - foreground)
    assert error.max() <= 1
    assert np.all((result[20, 30:66, 3] >= 145) & (result[20, 30:66, 3] <= 157))
    np.testing.assert_array_equal(result[30:70, 30:70, :3], np.broadcast_to(core, (40, 40, 3)))
    assert np.all(result[30:70, 30:70, 3] == 255)
    assert np.all(result[:15, :, 3] == 0)
    assert image.tobytes() == original


@pytest.mark.parametrize('key,order', [('blue', [0, 1, 2]), ('red', [2, 0, 1]), ('green', [1, 2, 0])])
@pytest.mark.parametrize('entry', ['staged', 'automatic'])
@pytest.mark.parametrize('coverage', [.8, 1.0])
def test_additive_key_spill_still_removed_from_painted_edge(key, order, entry, coverage):
    foreground = np.array((240, 200, 70))[order]
    background = np.array((20, 45, 240))[order]
    image = _painted_edge(foreground, foreground, background, coverage, spill=.25)
    result = _remove(image, key, entry)
    assert np.abs(result[20, 48, :3].astype(int) - foreground).max() <= 2
    # Existing staged alpha cleanup is separate from this RGB correction.
    assert abs(int(result[20, 48, 3]) - round(coverage * 255)) <= 6
