"""Opaque edge details must not be treated as another colour plus key spill."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import remove_chroma_key_automatic


def colored_edge_fixture(channels=(0, 1, 2), color=(240, 220, 20), stripe=False):
    source = np.full((64, 64, 3), (255, 0, 0), dtype=np.uint8)
    source[12:52, 12:52] = (40, 80, 180)
    detail = np.zeros((64, 64), dtype=bool)
    if stripe:
        detail[14:50, 13:16] = True
    else:
        detail[14:50:3, 13] = True
    source[detail] = color
    return Image.fromarray(source[..., channels]), detail


@pytest.mark.parametrize('key,channels', [
    ('red', (0, 1, 2)), ('green', (1, 0, 2)), ('blue', (2, 1, 0)),
])
@pytest.mark.parametrize('color', [(240, 220, 20), (180, 170, 160)])
@pytest.mark.parametrize('stripe', [False, True])
def test_unrelated_opaque_edge_colour_is_not_despilled(key, channels, color, stripe):
    source, detail = colored_edge_fixture(channels, color, stripe)
    stages = {}
    result = remove_chroma_key_automatic(source, key, subject_profile='opaque_clipart',
        stage_observer=lambda name, image: stages.update({name: np.array(image)}))
    for stage, pixels in stages.items():
        np.testing.assert_array_equal(pixels[..., :3][detail], np.asarray(source)[detail],
                                      err_msg=stage)
    pixels = np.asarray(result)
    assert np.all(pixels[..., 3][detail] == 255)
    expected_contour = np.zeros((64, 64), dtype=bool)
    expected_contour[12:52, 12:52] = True
    np.testing.assert_array_equal(pixels[..., 3] > 0, expected_contour)
    if not stripe:
        assert np.all(pixels[12:52, 12:52, 3] == 255)
    assert np.all(pixels[:10, :, 3] == 0)
