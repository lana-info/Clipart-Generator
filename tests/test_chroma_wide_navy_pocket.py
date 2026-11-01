"""Dark navy pockets under a star or a bow are background, not subject.

The fixtures are crops of a real generated image. The shade between a star, a
flag pole and a flag is navy-black and nearly flat in level, so it does not ramp
from mouth to depth; the shade under a bow is wider than a crack. The original
rules kept both as opaque dark-blue blotches.
"""
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chroma_key import remove_chroma_key_automatic

FIXTURES = Path(__file__).parent / "fixtures" / "chroma"
KEY = (0, 3, 253)
MARGIN = 50


@pytest.mark.parametrize(
    "name, visible_navy_limit",
    [
        ("navy_pocket_under_star_20261101.png", 60),  # flat level: no ramp (189 px before the fix)
        ("navy_pocket_wide_gap_20261101.png", 20),  # wider than 18 px (324 px before the fix)
    ],
)
def test_navy_pocket_is_cut_and_the_gold_subject_stays_opaque(name, visible_navy_limit):
    crop = Image.open(FIXTURES / name).convert("RGB")
    # The crop has no background of its own; a flat key margin lets the engine measure the key.
    padded = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    padded.paste(crop, (MARGIN, MARGIN))
    source = np.asarray(padded).astype(int)
    out = np.asarray(remove_chroma_key_automatic(padded, "blue", subject_profile="opaque_clipart")).astype(int)
    r, g, b, alpha = (out[..., i] for i in range(4))
    navy_film = (alpha > 128) & (b > r + 10) & (b > g) & (r + g + b < 330)
    assert navy_film.sum() <= visible_navy_limit, f"{navy_film.sum()} dark-blue px stay visible"
    warm = (source[..., 0] > 200) & (source[..., 2] < 170) & (source[..., 0] - source[..., 2] > 40)
    assert warm.sum() > 1000
    # A few anti-aliased contour pixels against the key are partly transparent by design.
    assert (alpha[warm] >= 128).all(), "gold/red subject pixels were cut"
    assert (alpha[warm] < 250).sum() <= 8, "gold/red subject pixels lost opacity"


def test_dark_slate_window_line_is_paint_not_a_navy_pocket():
    """A thin dark blue-grey mullion between light panes is subject paint.

    It is dark and leans blue, but sits ~40-55 degrees off the key's chroma; a
    navy shade of the key stays well below that. The crop is real (rough_23).
    """
    crop = Image.open(FIXTURES / "dark_mullion_line_20261101.png").convert("RGB")
    padded = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    padded.paste(crop, (MARGIN, MARGIN))
    out = np.asarray(remove_chroma_key_automatic(padded, "blue", subject_profile="opaque_clipart")).astype(int)
    inside = out[MARGIN + 3 : MARGIN + crop.height - 3, MARGIN + 3 : MARGIN + crop.width - 3, 3]
    assert (inside < 250).sum() <= 5, f"{(inside < 250).sum()} subject px cut out of the window"
