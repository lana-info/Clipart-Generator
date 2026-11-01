"""Cut-out edges on real owner frames: anti-aliased contours, thin lines in their own colour, one hidden colour.

The fixture is a crop of the owner's circus strip (rough_23): a one-to-two pixel red cord runs along a drum beside a
gold star. It used to come out as broken grey fragments with an orange splinter, because the colour of every thin
pixel was solved from the distant solid neighbours (the star, the drum).
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha, clean_alpha_array
from chroma_key import finish_rim_cleanup, remove_chroma_key_automatic
from chroma_matting import matte_edges
from tests.test_edge_matting_pipeline import cut, make_worker

import main

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "thin_cord_by_star_20261101.png"
KEY = (0, 3, 253)
MARGIN = 40
CORD_COLUMNS = (41, 47)      # fixture columns of the cord alone: the drum's body ends left of them, the star right
CORD_ROWS = (62, 100)


def _hard_step_share(alpha: np.ndarray) -> float:
    """Share of contour crossings that jump straight from empty to solid: what the eye reads as a staircase."""
    crossed = hard = 0
    for first, second in ((alpha[:, :-1], alpha[:, 1:]), (alpha[:-1], alpha[1:])):
        crossing = (first < 0.5) != (second < 0.5)
        crossed += int(crossing.sum())
        hard += int((crossing & (np.abs(first - second) > 0.9)).sum())
    return hard / max(crossed, 1)


def _stepped_disc(size: int = 160, radius: float = 50.0) -> np.ndarray:
    y, x = np.mgrid[:size, :size]
    return (np.hypot(x - size / 2, y - size / 2) <= radius).astype(np.float32)


def test_antialias_turns_a_staircase_into_a_soft_contour_without_moving_it():
    stepped = _stepped_disc()
    smooth = clean_alpha_array(stepped, island_min_gap=None, antialias=True)
    assert _hard_step_share(stepped) > 0.9
    assert _hard_step_share(smooth) < 0.1
    assert abs(smooth.sum() - stepped.sum()) / stepped.sum() < 0.01
    assert smooth[80, 80] == 1.0 and smooth[5, 5] == 0.0


def test_antialias_stays_off_by_default():
    stepped = _stepped_disc()
    assert _hard_step_share(clean_alpha_array(stepped, island_min_gap=None)) > 0.9


@pytest.mark.parametrize("width", [1, 2])
def test_antialias_keeps_a_thin_thread_exactly(width):
    alpha = np.zeros((64, 64), np.float32)
    alpha[:, 30:30 + width] = 1.0
    np.testing.assert_array_equal(clean_alpha_array(alpha, island_min_gap=None, antialias=True), alpha)


def test_antialias_keeps_soft_fur_exactly():
    x = np.arange(64, dtype=np.float32)
    alpha = np.repeat(np.clip((x - 20.0) / 12.0, 0.0, 1.0)[None, :], 64, axis=0)
    cleaned = clean_alpha_array(alpha, island_min_gap=None, antialias=True)
    band = (alpha > 0.1) & (alpha < 0.9)
    np.testing.assert_allclose(cleaned[band], alpha[band], atol=1e-6)


def test_antialias_leaves_no_faint_crumb_beside_the_contour():
    alpha = _stepped_disc()
    alpha[80, 133] = 0.74   # a lone pixel 3 px off the contour: the rebuild fades it, and a faint dot must not stay
    assert clean_alpha_array(alpha, island_min_gap=DEBRIS_MIN_GAP, antialias=True)[80, 133] == 0.0


def test_the_cutout_pipeline_antialiases_a_stepped_contour(tmp_path, monkeypatch):
    worker, path, raw, _, _ = make_worker(tmp_path)

    def matted(_source, cutout, _key, **_kwargs):
        y, x = np.mgrid[:cutout.height, :cutout.width]
        result = np.zeros((cutout.height, cutout.width, 4), np.uint8)
        result[..., :3] = (200, 150, 80)
        result[..., 3] = (np.hypot(x - cutout.width / 2, y - cutout.height / 2) <= 30) * 255
        return Image.fromarray(result, "RGBA")

    monkeypatch.setattr(main, "matte_edges", matted)
    with Image.open(cut(worker, path, raw)) as opened:
        alpha = np.asarray(opened.convert("RGBA").getchannel("A"), np.float32) / 255.0
    assert _hard_step_share(alpha) < 0.1


def test_the_published_cutout_carries_one_colour_under_transparency(tmp_path):
    worker, path, raw, _, _ = make_worker(tmp_path)
    with Image.open(cut(worker, path, raw)) as opened:
        pixels = np.asarray(opened.convert("RGBA"))
    hidden = pixels[pixels[..., 3] == 0][:, :3]
    assert hidden.size and len(np.unique(hidden, axis=0)) == 1


def _cut_cord():
    crop = Image.open(FIXTURE).convert("RGB")
    padded = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    padded.paste(crop, (MARGIN, MARGIN))
    engine = finish_rim_cleanup(remove_chroma_key_automatic(padded, "blue", subject_profile="opaque_clipart"),
                                "opaque_clipart")
    matted = matte_edges(padded, engine, "blue")
    result = clean_alpha(matted, island_min_gap=DEBRIS_MIN_GAP, antialias=True)
    area = (slice(MARGIN + CORD_ROWS[0], MARGIN + CORD_ROWS[1]), slice(MARGIN + CORD_COLUMNS[0], MARGIN + CORD_COLUMNS[1]))
    return np.asarray(padded).astype(int)[area], np.asarray(result).astype(int)[area]


def test_a_thin_cord_keeps_its_own_colour():
    source, result = _cut_cord()
    cord = (source[..., 0] > 110) & (source[..., 0] > 2 * source[..., 1]) & (source[..., 0] > 0.7 * source[..., 2])
    assert cord.sum() >= 8, "the fixture no longer shows the cord"
    assert (result[..., 3][cord] >= 128).all(), "the cord's own pixels must stay visible"
    # The cord is red-violet: its green stays far below its red, it never turns orange (the star) or grey (the drum).
    painted = result[cord]
    assert (painted[:, 0] >= 1.7 * painted[:, 1]).all(), painted[painted[:, 0] < 1.7 * painted[:, 1]]
    # Red paint mixed with a blue key looks violet; the key must not stay in it.
    assert (painted[:, 2] <= 0.7 * painted[:, 0]).all(), painted[painted[:, 2] > 0.7 * painted[:, 0]]


def test_a_thin_cord_is_not_broken_into_fragments():
    source, result = _cut_cord()
    alpha = result[..., 3]
    # Only rows where the source shows the cord at all.
    shown = ((source[..., 0] - source[..., 1]) >= 30).any(axis=1)
    assert shown.sum() >= 30, "the fixture no longer shows the cord"
    broken = shown & (alpha.max(axis=1) < 32)   # the cord fades in the drawing itself, down to about 40
    assert broken.sum() <= 2, f"{broken.sum()} of {shown.sum()} cord rows are empty"


def test_a_shade_of_the_key_is_not_read_as_a_thin_line():
    source = Image.new("RGB", (96, 96), KEY)
    source.paste((200, 150, 80), (10, 10, 40, 86))
    source.paste((20, 20, 150), (60, 10, 61, 86))    # a dark shade of the key: no paint in it, whatever its shape
    cutout = Image.new("RGBA", source.size, (0, 0, 0, 0))
    cutout.paste((200, 150, 80, 255), (10, 10, 40, 86))
    assert np.asarray(matte_edges(source, cutout, "blue"))[..., 3][:, 60].max() == 0


def test_a_pale_thread_stays_whole_and_pale():
    source = Image.new("RGB", (96, 96), KEY)
    source.paste((200, 150, 80), (10, 10, 40, 86))
    source.paste((240, 230, 200), (60, 10, 61, 86))
    cutout = Image.new("RGBA", source.size, (0, 0, 0, 0))
    cutout.paste((200, 150, 80, 255), (10, 10, 40, 86))
    result = np.asarray(matte_edges(source, cutout, "blue")).astype(int)
    line = result[12:84, 60]
    assert (line[:, 3] >= 200).all()
    assert (np.abs(line[:, :3] - (240, 230, 200)) <= 12).all()


def _line_on_key(*columns):
    """A key frame with a solid block and vertical one-pixel lines right of it; the engine cut only the block."""
    source = Image.new("RGB", (96, 96), KEY)
    source.paste((200, 150, 80), (10, 10, 40, 86))
    for index, colour in enumerate(columns):
        source.paste(colour, (60 + index, 10, 61 + index, 86))
    cutout = Image.new("RGBA", source.size, (0, 0, 0, 0))
    cutout.paste((200, 150, 80, 255), (10, 10, 40, 86))
    return np.asarray(matte_edges(source, cutout, "blue")).astype(int)


def test_a_two_toned_line_keeps_both_tones_and_stays_opaque():
    brown, yellow = (120, 70, 30), (240, 210, 60)
    result = _line_on_key(yellow, brown)
    assert (result[12:84, 60, 3] == 255).all() and (result[12:84, 61, 3] == 255).all()
    assert (np.abs(result[12:84, 61, :3] - brown) <= 6).all(), "the darker tone took the brighter one's colour"
    assert (np.abs(result[12:84, 60, :3] - yellow) <= 6).all()


def test_a_pale_pink_line_stays_pink():
    pink = (230, 120, 180)
    result = _line_on_key(pink)
    assert (np.abs(result[12:84, 60, :3] - pink) <= 12).all()


def test_pixels_the_antialias_reveals_take_the_subject_colour(tmp_path, monkeypatch):
    worker, path, raw, _, _ = make_worker(tmp_path)

    def matted(_source, cutout, _key, **_kwargs):
        y, x = np.mgrid[:cutout.height, :cutout.width]
        inside = np.hypot(x - cutout.width / 2, y - cutout.height / 2) <= 30
        result = np.zeros((cutout.height, cutout.width, 4), np.uint8)
        result[..., :3] = np.where(inside[..., None], (200, 150, 80), (60, 60, 200))  # key-tinted under alpha 0
        result[..., 3] = inside * 255
        return Image.fromarray(result, "RGBA")

    monkeypatch.setattr(main, "matte_edges", matted)
    with Image.open(cut(worker, path, raw)) as opened:
        pixels = np.asarray(opened.convert("RGBA")).astype(int)
    soft = (pixels[..., 3] > 0) & (pixels[..., 3] < 255)
    assert soft.sum() > 50
    assert (np.abs(pixels[soft][:, :3] - (200, 150, 80)) <= 12).all()


def test_the_worker_edge_chain_leaves_one_hidden_colour_on_a_real_frame():
    """The chain re-creates hidden colours (matting, anti-aliasing); its last step must flatten them again."""
    navy = Path(__file__).parent / "fixtures" / "chroma" / "navy_pocket_star_flag_20261101.png"
    crop = Image.open(navy).convert("RGB")
    source = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    source.paste(crop, (MARGIN, MARGIN))
    raw = remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart")
    engine_result = finish_rim_cleanup(raw, "opaque_clipart")
    done, matted = main.WorkerThread._matte_chroma_edges(
        type("W", (), {"progress": type("P", (), {"emit": staticmethod(lambda _text: None)})()})(),
        source, engine_result, "blue")
    assert matted
    pixels = np.asarray(done)
    hidden = pixels[pixels[..., 3] == 0][:, :3]
    assert len(hidden) > 10000 and len(np.unique(hidden, axis=0)) == 1
