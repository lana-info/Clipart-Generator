"""Owner's duckling (2026-10-26): grey-violet specks stay opaque on the fur tips after the chroma step."""
from pathlib import Path

import pytest

import cv2
import numpy as np
from PIL import Image

from chroma_rim import recolour_rim_specks

FIXTURE = Path(__file__).parent / "fixtures" / "chroma" / "duck_rim_specks_20261026.png"
# The source key was not supplied; magenta matches the tint of the specks (mean deviation +21/-13/+11).
KEY = (255, 0, 255)
LUMA = np.array([0.3, 0.59, 0.11], dtype=np.float32)


def _dark_rim_share(image):
    arr = np.asarray(image.convert("RGBA")).astype(np.float32)
    alpha, rgb = arr[..., 3], arr[..., :3]
    depth = cv2.distanceTransform((alpha >= 250).astype(np.uint8), cv2.DIST_L2, 3)
    rim = (alpha > 0) & (depth <= 2.5)
    core = (depth >= 4).astype(np.float32)
    weight = cv2.blur(core, (15, 15))[..., None]
    reference = cv2.blur(rgb * core[..., None], (15, 15)) / np.maximum(weight, 1e-3)
    judged = rim & (weight[..., 0] > 0.05) & ((reference @ LUMA) >= 185.0)
    dark = judged & ((reference @ LUMA) - (rgb @ LUMA) > 45.0)
    return dark.sum() / max(judged.sum(), 1)


@pytest.mark.xfail(reason='heuristic not final: tiny-blob rule leaves chained specks; not wired into the pipeline', strict=True)
def test_rim_specks_are_recoloured_without_touching_alpha_or_interior():
    source = Image.open(FIXTURE).convert("RGBA")
    fixed = recolour_rim_specks(source, KEY)
    before, after = np.asarray(source), np.asarray(fixed)
    assert np.array_equal(before[..., 3], after[..., 3])
    depth = cv2.distanceTransform((before[..., 3] >= 250).astype(np.uint8), cv2.DIST_L2, 3)
    interior = depth > 3.0
    assert np.array_equal(before[interior], after[interior])
    # Mild shading (a drop of 45-60 levels) is kept on purpose: it can be painted feather shadow.
    before_share, after_share = _dark_rim_share(source), _dark_rim_share(fixed)
    assert before_share > 0.10
    assert after_share < 0.06 and after_share < before_share / 3


def test_clean_image_is_returned_unchanged():
    flat = Image.new("RGBA", (40, 40), (240, 220, 190, 255))
    assert recolour_rim_specks(flat, KEY) is flat
