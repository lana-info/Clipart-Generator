"""Edge matting of a keyed generation: soft alpha and key-free colour on fur-like edges.

Ground truth: hairs and a disc drawn at 4x, composited over the blue key and area-downsampled to the
native frame, as a generator renders them. The stand-in engine cut-out is the naive hard key (alpha 0 or
255 by distance to the key, source colour kept), which leaves blue-tinted hair tips fully opaque.
"""
import cv2
import numpy as np
import pytest
from PIL import Image

from chroma_matting import matte_edges

SCALE = 4
KEY = np.array([0, 0, 255], np.float32)
FUR = np.array([250, 220, 140], np.float32)


def _scene(size=96):
    big = size * SCALE
    fine = big * 4
    drawing = np.zeros((fine, fine), np.uint8)
    cv2.circle(drawing, (fine // 2, fine // 2), fine // 4, 255, -1)
    rng = np.random.default_rng(7)
    for angle in rng.uniform(0, 2 * np.pi, 60):
        start = np.array([fine / 2, fine / 2]) + np.array([np.cos(angle), np.sin(angle)]) * fine / 4.2
        end = start + np.array([np.cos(angle + 0.3), np.sin(angle + 0.3)]) * fine / 7
        cv2.line(drawing, tuple(int(v) for v in start), tuple(int(v) for v in end), 255, 10)
    truth = cv2.resize(drawing.astype(np.float32) / 255.0, (size, size), interpolation=cv2.INTER_AREA)
    rgb = truth[..., None] * FUR + (1 - truth[..., None]) * KEY
    source = Image.fromarray(np.rint(rgb).astype(np.uint8), "RGB")
    distance = np.linalg.norm(rgb - KEY, axis=2)
    hard = np.where(distance > 40, 255, 0).astype(np.uint8)
    cutout = Image.fromarray(np.dstack([np.asarray(source), hard]), "RGBA")
    return source, cutout, truth


def _edge_band(truth):
    partial = ((truth > 0.02) & (truth < 0.98)).astype(np.uint8)
    return cv2.dilate(partial, np.ones((3, 3), np.uint8)) > 0


def test_alpha_on_hair_edges_is_closer_to_truth_than_hard_key():
    source, cutout, truth = _scene()
    band = _edge_band(truth)

    result = matte_edges(source, cutout, "blue")

    alpha = np.asarray(result.getchannel("A"), np.float32) / 255.0
    hard = np.asarray(cutout.getchannel("A"), np.float32) / 255.0
    assert np.abs(alpha - truth)[band].mean() < 0.6 * np.abs(hard - truth)[band].mean()
    partial = (truth > 0.1) & (truth < 0.9)
    assert np.abs(alpha - truth)[partial].mean() < 0.3  # the hard key is off by 0.5 there


def test_edge_colour_has_no_blue_of_the_key():
    source, cutout, truth = _scene()
    seen = (truth > 0.3)

    result = np.asarray(matte_edges(source, cutout, "blue"), np.float32)
    naive = np.asarray(cutout, np.float32)
    visible = seen & (result[..., 3] > 0)

    colour_error = np.linalg.norm(result[..., :3] - FUR, axis=2)[visible].mean()
    naive_error = np.linalg.norm(naive[..., :3] - FUR, axis=2)[visible].mean()
    assert colour_error < 0.7 * naive_error
    assert colour_error < 25

    def key_tint(pixels):
        return (pixels[..., 2] - np.maximum(pixels[..., 0], pixels[..., 1]))[visible].mean()

    true_tint = FUR[2] - max(FUR[0], FUR[1])
    assert abs(key_tint(result) - true_tint) < 0.7 * abs(key_tint(naive) - true_tint)


def test_solid_core_and_clear_background_stay_exact():
    source, cutout, truth = _scene()

    result = np.asarray(matte_edges(source, cutout, "blue"))
    hard = np.asarray(cutout)

    core = cv2.erode((truth >= 0.999).astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    assert np.all(result[core][:, 3] == 255)
    assert np.array_equal(result[core][:, :3], hard[core][:, :3])
    far = cv2.dilate((truth > 0).astype(np.uint8), np.ones((9, 9), np.uint8)) == 0
    assert np.all(result[far][:, 3] == 0)


def test_unknown_key_colour_or_size_mismatch_returns_the_cutout():
    source, cutout, _ = _scene(32)

    assert matte_edges(source, cutout, "magenta") is cutout
    assert matte_edges(source.resize((16, 16)), cutout, "blue") is cutout


def test_image_without_an_edge_returns_the_cutout():
    source = Image.new("RGB", (24, 24), (0, 0, 255))
    cutout = Image.new("RGBA", (24, 24), (0, 0, 255, 0))

    assert matte_edges(source, cutout, "blue") is cutout


def test_too_many_unknown_pixels_is_refused_for_the_caller_to_fall_back():
    source, cutout, _ = _scene(64)

    with pytest.raises(ValueError):
        matte_edges(source, cutout, "blue", max_unknown=10)


def _leaf_with_gap():
    """Green leaf on blue key with a shaded-key gap enclosed by the leaf, as between overlapping leaves."""
    source = Image.new("RGB", (40, 40), (0, 0, 255))
    pixels = source.load()
    for y in range(8, 32):
        for x in range(8, 32):
            pixels[x, y] = (60, 140, 50)
    for y in range(18, 22):
        for x in range(18, 22):
            pixels[x, y] = (22, 45, 150)
    return source


@pytest.mark.parametrize("engine_alpha", [255, 160])
def test_shaded_key_gap_between_leaves_becomes_transparent(engine_alpha):
    source = _leaf_with_gap()
    cutout = Image.new("RGBA", source.size, (0, 0, 255, 0))
    cutout.paste(source.crop((8, 8, 32, 32)).convert("RGBA"), (8, 8))  # the engine kept the leaf, gap included
    cutout.paste((22, 45, 150, engine_alpha), (18, 18, 22, 22))

    result = matte_edges(source, cutout, "blue")

    assert result.getpixel((19, 19))[3] == 0
    assert result.getpixel((12, 12)) == (60, 140, 50, 255)


def test_key_like_pixels_the_engine_saw_as_a_mixture_are_not_deleted():
    """A violet object with a dark-blue edge line: the engine marked the line partly transparent."""
    source = Image.new("RGB", (40, 40), (0, 0, 255))
    source.paste((120, 80, 180), (8, 8, 32, 32))
    source.paste((61, 58, 215), (8, 8, 32, 9))
    cutout = Image.new("RGBA", source.size, (0, 0, 255, 0))
    cutout.paste(source.crop((8, 8, 32, 32)).convert("RGBA"), (8, 8))
    cutout.paste((123, 78, 152, 124), (8, 8, 32, 9))

    result = matte_edges(source, cutout, "blue")

    edge = result.getpixel((20, 8))
    assert 60 <= edge[3] <= 190
    assert max(abs(a - b) for a, b in zip(edge[:3], (120, 80, 180))) <= 12
