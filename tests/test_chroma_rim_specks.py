"""Owner's duckling (2026-10-26): saturated dark lines from the generator stay opaque on the fur tips."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from chroma_key import remove_chroma_key_automatic, remove_chroma_key_with_rim_cleanup
from chroma_rim import recolour_rim_specks

SOURCE = Path(__file__).parent / "fixtures" / "chroma" / "duck_source_blue_20261026.png"
LUMA = np.array([0.3, 0.59, 0.11], dtype=np.float32)


def _saturated_dark_rim_share(image):
    arr = np.asarray(image.convert("RGBA")).astype(np.float32)
    alpha, rgb = arr[..., 3], arr[..., :3]
    depth = cv2.distanceTransform((alpha >= 250).astype(np.uint8), cv2.DIST_L2, 3)
    rim = (alpha > 0) & (depth <= 2.5)
    core = (depth >= 4).astype(np.float32)
    weight = cv2.blur(core, (15, 15))[..., None]
    reference = cv2.blur(rgb * core[..., None], (15, 15)) / np.maximum(weight, 1e-3)
    judged = rim & (weight[..., 0] > 0.05) & ((reference @ LUMA) >= 185.0)
    dark = judged & ((reference @ LUMA) - (rgb @ LUMA) > 45.0) & ((rgb.max(axis=2) - rgb.min(axis=2)) >= 45.0)
    return dark.sum() / max(judged.sum(), 1)


def test_production_entry_removes_saturated_rim_lines_but_keeps_alpha_and_interior():
    source = Image.open(SOURCE).convert("RGB")
    plain = remove_chroma_key_automatic(source, "blue", subject_profile="opaque_clipart")
    cleaned = remove_chroma_key_with_rim_cleanup(source, "blue", subject_profile="opaque_clipart")
    before, after = np.asarray(plain), np.asarray(cleaned)
    assert np.array_equal(before[..., 3], after[..., 3])
    depth = cv2.distanceTransform((before[..., 3] >= 250).astype(np.uint8), cv2.DIST_L2, 3)
    interior = depth > 3.0
    assert np.array_equal(before[interior], after[interior])
    plain_share, cleaned_share = _saturated_dark_rim_share(plain), _saturated_dark_rim_share(cleaned)
    assert plain_share > 0.05
    assert cleaned_share < plain_share / 3


def test_low_saturation_dark_stroke_is_kept():
    image = np.full((60, 60, 4), (250, 225, 183, 255), dtype=np.uint8)
    image[:, 10:12] = (80, 70, 90, 255)
    image[:, :8, 3] = 0
    result = recolour_rim_specks(Image.fromarray(image))
    assert np.array_equal(np.asarray(result), image)


def test_clean_image_is_returned_unchanged():
    flat = Image.new("RGBA", (40, 40), (240, 220, 190, 255))
    assert recolour_rim_specks(flat) is flat
