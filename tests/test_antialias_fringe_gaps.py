"""The anti-aliasing of hard contours must not fill the narrow gaps between fringe strands.

The fixture is a crop of the owner's frame rough_22: gold fringe whose strands are 2-4 px apart with the blue key
showing between them. The smoothing used to lift the alpha in those slits from 0 to about 0.7, so the strands grew
together into a band.
"""
from pathlib import Path

import numpy as np
from PIL import Image

import main
from chroma_key import finish_rim_cleanup, remove_chroma_key_automatic

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "fringe_gaps_20261101.png"
KEY = (0, 3, 253)
MARGIN = 40


def _cut_fringe():
    crop = Image.open(FIXTURE).convert("RGB")
    source = Image.new("RGB", (crop.width + 2 * MARGIN, crop.height + 2 * MARGIN), KEY)
    source.paste(crop, (MARGIN, MARGIN))
    engine = finish_rim_cleanup(remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart"),
                                "opaque_clipart")
    worker = type("W", (), {"progress": type("P", (), {"emit": staticmethod(lambda _text: None)})()})()
    done, _ = main.WorkerThread._matte_chroma_edges(worker, source, engine, "blue")
    return np.asarray(source).astype(int), np.asarray(done).astype(int)[..., 3]


def test_slits_between_fringe_strands_stay_transparent():
    source, alpha = _cut_fringe()
    slit = source[..., 2] - np.maximum(source[..., 0], source[..., 1]) > 50
    assert slit.sum() > 5000, "the fixture no longer shows the key"
    filled = int((slit & (alpha > 127)).sum())
    assert filled <= 20, filled
