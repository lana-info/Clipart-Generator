"""Navy-black shade pockets between subject parts are background, not subject.

The fixture is a real generated image: the generator painted a very dark navy
shadow in the gaps between a star, a flag and a bow. Those pockets lead in the
key channel only slightly and sit far from the key's chroma angle, so the
original hued-shade rule kept them as opaque dark-blue blotches.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from chroma_key import remove_chroma_key_automatic

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "navy_pocket_star_flag_20261101.png"
KEY = (0, 3, 253)
MARGIN = 40


def _cut_fixture():
    crop = Image.open(FIXTURE).convert("RGB")
    # The crop has no background of its own; a flat key margin lets the engine measure the key.
    padded = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    padded.paste(crop, (MARGIN, MARGIN))
    source = np.asarray(padded).astype(int)
    out = np.asarray(remove_chroma_key_automatic(padded, "blue", subject_profile="opaque_clipart")).astype(int)
    return source, out


def test_navy_pockets_are_cut_and_the_warm_subject_stays_opaque():
    source, out = _cut_fixture()
    r, g, b, alpha = (out[..., i] for i in range(4))
    navy_film = (alpha > 128) & (b > r + 15) & (b > g) & (r + g + b < 330)
    assert navy_film.sum() <= 250, f"{navy_film.sum()} dark-blue px stay visible (was ~740 before the fix)"
    warm = (source[..., 0] > 200) & (source[..., 2] < 170) & (source[..., 0] - source[..., 2] > 40)
    assert warm.sum() > 1000
    assert (alpha[warm] >= 250).all(), "gold/red subject pixels lost opacity"
