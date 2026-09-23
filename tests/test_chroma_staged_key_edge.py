"""Regression for blue source mixtures restored as opaque feather pixels."""
import numpy as np
import pytest
from PIL import Image

from chroma_key import _remove_chroma_key_staged, _supported_key_edge


@pytest.mark.parametrize("key,order", [
    ("blue", [0, 1, 2]), ("red", [2, 0, 1]), ("green", [1, 2, 0]),
])
@pytest.mark.parametrize("x", [23, 25])
def test_enclosed_rim_mixture_is_not_restored_as_solid_key_colour(key, order, x):
    rgb = np.full((96, 96, 3), (20, 45, 240), np.uint8)
    rgb[20:76, 20:76] = (240, 210, 155)
    # A sampled source colour from the owner's ducklings. Texture makes its
    # foreground differ from the nearest pale interior; enclosure alone used
    # to promote this solved transition to RGBA (103,82,196,255).
    rgb[40:43, x:x+2] = (103, 82, 196)
    # A thin antialiased opening connects the feather gap to the actual key.
    rgb[40, 20:x] = (103, 82, 196)
    rgb = rgb[..., order]
    result = np.array(_remove_chroma_key_staged(
        Image.fromarray(rgb), key, opaque_subject=True,
    ))
    key_channel = order.index(2)
    others = [index for index in range(3) if index != key_channel]
    patch = result[40:43, x:x+2]
    assert np.all((patch[..., 3] > 0) & (patch[..., 3] < 240))
    assert np.all(patch[..., key_channel] <= np.max(patch[..., others], axis=2))
    np.testing.assert_array_equal(result[30:36, 40:60, :3], rgb[30:36, 40:60])
    assert np.all(result[30:36, 40:60, 3] == 255)
    assert np.all(result[:15, :, 3] == 0)


def test_provisional_internal_hole_is_not_external_key_evidence():
    rgb = np.full((96, 96, 3), (0, 0, 255), np.float32)
    rgb[15:81, 15:81] = (240, 210, 155)
    rgb[42:54, 42:54] = (40, 45, 135)  # Genuine blue eye/painted marking.
    alpha = np.zeros((96, 96), np.float32)
    alpha[15:81, 15:81] = 1
    alpha[42:54, 42:54] = .3
    alpha[46:50, 46:50] = 0
    supported = _supported_key_edge(rgb, alpha, np.array([0, 0, 255], np.float32))
    assert not np.any(supported[42:54, 42:54])


@pytest.mark.parametrize('textured', [False, True])
def test_blue_painted_detail_near_the_edge_keeps_its_colour(textured):
    rgb = np.full((96, 96, 3), (20, 45, 240), np.uint8)
    rgb[20:76, 20:76] = (240, 210, 155)
    rgb[40:47, 23:29] = (90, 85, 180)
    if textured:
        y, x = np.indices((7, 6))
        rgb[40:47, 23:29] += ((x+y)*2)[..., None].astype(np.uint8)
    result = np.array(_remove_chroma_key_staged(
        Image.fromarray(rgb), 'blue', opaque_subject=True,
    ))
    np.testing.assert_array_equal(result[40:47, 23:29, :3], rgb[40:47, 23:29])
    assert np.all(result[40:47, 23:29, 3] == 255)


def test_disconnected_detail_cannot_borrow_a_foreground_reference():
    rgb = np.full((96, 96, 3), (0, 0, 255), np.float32)
    rgb[20:76, 20:60] = (240, 210, 155)
    rgb[40:43, 62:64] = (103, 82, 196)
    alpha = np.zeros((96, 96), np.float32)
    alpha[20:76, 20:60] = 1
    alpha[40:43, 62:64] = .4
    supported = _supported_key_edge(rgb, alpha, np.array([0, 0, 255], np.float32))
    assert not np.any(supported[40:43, 62:64])
