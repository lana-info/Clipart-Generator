"""Fully opaque pixels keep the colour the artist painted: the key-tint step only touches soft edge pixels.

The fixture is a crop of the owner's frame rough_32: a pale pink ribbon (236, 185, 174) beside gold stars. The step
used to take the colour of the nearest solid body for every opaque pixel within 8 px of the contour; a ribbon too
narrow to hold a body of its own was then painted with the star's gold (233, 191, 96).
"""
from pathlib import Path

import numpy as np
from PIL import Image

import main
from chroma_key import finish_rim_cleanup, remove_chroma_key_automatic
from edge_tint import suppress_key_tint

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "ribbon_by_star_20261101.png"
KEY = (0, 2, 253)
MARGIN = 40
RIBBON = np.array([236, 185, 174])
GOLD = np.array([233, 191, 96])


def _cut_ribbon_frame():
    crop = Image.open(FIXTURE).convert("RGB")
    source = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    source.paste(crop, (MARGIN, MARGIN))
    engine = finish_rim_cleanup(remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart"),
                                "opaque_clipart")
    worker = type("W", (), {"progress": type("P", (), {"emit": staticmethod(lambda _text: None)})()})()
    done, _ = main.WorkerThread._matte_chroma_edges(worker, source, engine, "blue")
    return np.asarray(source).astype(int), np.asarray(done).astype(int)


def test_opaque_ribbon_pixels_keep_their_painted_colour_on_a_real_frame():
    source, result = _cut_ribbon_frame()
    ribbon = np.abs(source - RIBBON).max(axis=2) <= 14
    solid = ribbon & (result[..., 3] == 255)
    assert solid.sum() >= 300, "the fixture no longer shows the ribbon"
    drift = np.abs(result[..., :3] - source).max(axis=2)[solid]
    # a handful of pixels on the contour are re-coloured by the earlier matte steps, not by the tint step
    assert (drift > 4).mean() < 0.02 and drift.max() <= 20, (int((drift > 4).sum()), int(drift.max()))
    assert not (np.abs(result[..., :3][solid] - GOLD).max(axis=1) <= 25).any(), "the ribbon took the star's gold"


def _pale_ribbon_beside_gold(alpha):
    """A gold disc and a narrow pale ribbon beside it; the ribbon pixels have the given alpha."""
    size = 120
    image = np.zeros((size, size, 4), np.uint8)
    y, x = np.mgrid[:size, :size]
    image[np.hypot(x - 40, y - 60) <= 28] = (*GOLD, 255)
    image[(x >= 72) & (x < 76) & (y >= 20) & (y < 100)] = (*RIBBON, alpha)
    return Image.fromarray(image, "RGBA")


def test_an_opaque_ribbon_beside_a_gold_star_is_left_alone():
    image = _pale_ribbon_beside_gold(255)
    assert np.array_equal(np.asarray(suppress_key_tint(image, "blue")), np.asarray(image))
