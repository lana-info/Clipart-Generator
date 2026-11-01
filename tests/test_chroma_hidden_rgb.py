"""The production cut-out carries one flat colour under full transparency, not key-blue junk.

remove_chroma_key_automatic leaves the despilled key and noise beneath alpha == 0. Every later
consumer (upscaler, the brush of the transparency editor, external editors) can reveal it as a mess
of odd colour patches, so the production step clears it where the cut-out is born.
"""
from pathlib import Path

import numpy as np
from PIL import Image

from chroma_key import finish_rim_cleanup, recolour_rim_specks, remove_chroma_key_automatic

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "navy_pocket_star_flag_20261101.png"
KEY = (0, 3, 253)
MARGIN = 40


def _cut():
    crop = Image.open(FIXTURE).convert("RGB")
    padded = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    padded.paste(crop, (MARGIN, MARGIN))
    raw = remove_chroma_key_automatic(padded, "blue", subject_profile="opaque_clipart")
    return recolour_rim_specks(raw), finish_rim_cleanup(raw, "opaque_clipart")


def test_hidden_colour_is_flat_and_not_key_blue_and_visible_pixels_are_untouched():
    before_image, done = _cut()
    before, after = np.asarray(before_image), np.asarray(done)
    hidden = after[..., 3] == 0
    assert hidden.sum() > 10000
    assert len(np.unique(after[hidden][:, :3], axis=0)) <= 1, "hidden colour is not one flat value"
    assert not (after[hidden][:, 2] > 200).any(), "key blue still sits under the transparency"
    # only the hidden colour changes: every pixel with alpha > 0, and the alpha itself, stay bit for bit
    assert (before[~hidden] == after[~hidden]).all()
    assert (before[..., 3] == after[..., 3]).all()
