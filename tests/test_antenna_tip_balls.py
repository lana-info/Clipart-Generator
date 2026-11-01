"""The balls on the tips of thin antennae must survive the cleanup of stray islands.

The fixture is a crop of the owner's frame rough_10 after the edge matting: the two antennae of the ladybird are
one or two pixels thick, the matting leaves only a broken stalk, and the yellow balls on the tips come out as small
islands 10-14 px from the head. They used to go as generation debris.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from alpha_cleanup import DEBRIS_MIN_GAP, clean_alpha

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "antenna_balls_20261101.png"
BALLS = ((55, 49), (73, 52))  # x, y of the two tips in the crop


def _solid_near(alpha, x, y, radius=6):
    return int((alpha[y - radius:y + radius, x - radius:x + radius] >= 128).sum())


def test_antenna_tip_balls_are_kept():
    alpha = np.asarray(clean_alpha(Image.open(FIXTURE), island_min_gap=DEBRIS_MIN_GAP, antialias=True))[..., 3]
    for x, y in BALLS:
        assert _solid_near(alpha, x, y) >= 10, (x, y)


def test_one_pixel_specks_far_from_the_subject_still_go():
    rgba = np.zeros((80, 120, 4), np.uint8)
    rgba[40:, :, 3] = 255
    rgba[25, 60, 3] = 255
    kept = np.asarray(clean_alpha(Image.fromarray(rgba), island_min_gap=DEBRIS_MIN_GAP, antialias=True))[..., 3]
    assert kept[20:30, 55:65].max() == 0
