"""Final alpha clean-up for cut-out clipart: remove faint haze, tighten smooth edges.

Three independent steps, applied only to the alpha channel (RGB is never touched):

1. Haze: weak alpha (below ``haze_floor``) farther than ``haze_distance`` px from
   the solid subject is set to zero, together with tiny weak specks.
2. Smooth edges: where the transition band is narrow (hard-edged objects such as
   leaves, ribbons, feet) it is steepened around 50 % so it spans about 1-2 px
   (``gain`` 2.0; ``gain`` 1.0 switches this off and keeps the soft transition, which the
   delivery cut uses). Wide bands (fur, down, soft pom-poms) are left exactly as they are.
3. Opaque ceiling: alpha that is practically opaque becomes 255.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

HAZE_FLOOR = 0.16          # alpha below this is "faint"
HAZE_DISTANCE = 3.0        # px from the solid core before faint alpha counts as haze
MIN_SPECK_PIXELS = 48      # weak connected blobs smaller than this are dropped
MIN_ISLAND_PIXELS = 64     # detached solid islands smaller than this (or the fraction below) are debris
MIN_ISLAND_FRACTION = 1e-4 # of the canvas area
HARD_EDGE_MAX_WIDTH = 9.0  # px, 2 %-98 % band width up to which an edge is "smooth"
EDGE_GAIN = 2.0            # steepening around 50 % alpha
DELIVERY_EDGE_GAIN = 1.0   # the pipeline keeps the soft transition of fur and edges (owner 2026-10-28)
OPAQUE_CEILING = 0.985


def _distance_to_zero(mask: np.ndarray) -> np.ndarray:
    """Distance of every True pixel to the nearest False pixel."""
    return cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)


def clean_alpha_array(alpha: np.ndarray, *, haze_floor: float = HAZE_FLOOR,
                      haze_distance: float = HAZE_DISTANCE,
                      hard_max_width: float = HARD_EDGE_MAX_WIDTH,
                      gain: float = EDGE_GAIN) -> np.ndarray:
    """Return a cleaned copy of ``alpha`` (float32 in 0..1)."""
    a = np.clip(alpha.astype(np.float32), 0.0, 1.0)
    if not a.any():
        return a

    # 1. haze: faint alpha away from the solid subject, and tiny weak specks.
    core = a >= 0.5
    distance_from_core = _distance_to_zero(~core)
    a[(a < haze_floor) & (distance_from_core > haze_distance)] = 0.0
    a[a < 0.03] = 0.0
    count, labels, stats, _ = cv2.connectedComponentsWithStats((a > 0).astype(np.uint8), connectivity=8)
    if count > 1:
        small = np.flatnonzero(stats[1:, cv2.CC_STAT_AREA] < MIN_SPECK_PIXELS) + 1
        if small.size:
            weak = np.isin(labels, small) & (a < 0.5)
            # A speck is dropped only if no pixel of its blob is solid.
            solid_labels = np.unique(labels[a >= 0.5])
            weak &= ~np.isin(labels, solid_labels)
            a[weak] = 0.0

    # 1b. stray solid islands (generation debris): drop them with a thin ring around them.
    solid = (a >= 0.5).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=4)
    if count > 2:
        min_island = max(MIN_ISLAND_PIXELS, int(MIN_ISLAND_FRACTION * a.size))
        small = np.flatnonzero(stats[1:, cv2.CC_STAT_AREA] < min_island) + 1
        # The largest component is always the subject; never treat it as debris.
        small = small[small != 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))]
        if small.size:
            removed = np.isin(labels, small)
            ring = cv2.dilate(removed.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
            kept_solid = (solid > 0) & ~removed
            a[ring & ~kept_solid] = 0.0

    # 2. smooth edges: steepen narrow bands only.
    partial = (a > 0.02) & (a < 0.98)
    if partial.any():
        to_solid = _distance_to_zero(a < 0.98)       # inside the band: distance to solid
        to_empty = _distance_to_zero(a > 0.02)       # distance to empty
        width = np.where(partial, to_solid + to_empty, 0.0).astype(np.float32)
        # A pixel is "smooth" only if no wide band lies in its neighbourhood.
        widest_nearby = cv2.dilate(width, np.ones((9, 9), np.uint8))
        smooth = partial & (widest_nearby <= hard_max_width)
        steep = np.clip((a - 0.5) * gain + 0.5, 0.0, 1.0)
        a = np.where(smooth, steep, a)

    # 3. practically opaque -> fully opaque.
    a[a >= OPAQUE_CEILING] = 1.0
    return a


def clean_alpha(image: Image.Image, *, clear_hidden_rgb: bool = False, **options) -> Image.Image:
    """Return an RGBA copy of ``image`` with cleaned alpha.

    RGB is unchanged, except that ``clear_hidden_rgb`` blanks the colour of pixels whose
    alpha is now zero (no stray tint under fully transparent pixels).
    """
    rgba = image.convert("RGBA")
    pixels = np.array(rgba)
    cleaned = clean_alpha_array(pixels[..., 3].astype(np.float32) / 255.0, **options)
    pixels[..., 3] = np.rint(cleaned * 255.0).astype(np.uint8)
    if clear_hidden_rgb:
        pixels[pixels[..., 3] == 0] = 0
    return Image.fromarray(pixels, mode="RGBA")


KEY_CHANNEL = {"red": 0, "green": 1, "blue": 2}
KEY_RESIDUE_DOMINANCE = 40   # how far the key channel must lead the others to count as leftover background
KEY_RESIDUE_PURITY = 0.4     # strongest other channel / key channel at most this for leftover background
KEY_RESIDUE_MAX_HALF_WIDTH = 2.5  # leftover slivers are thin; a wider patch of key-like colour is subject


def remove_key_residue(image: Image.Image, key_color: str) -> Image.Image:
    """Drop thin slivers of leftover chroma-key background (e.g. dark-blue lines between ribbon strands).

    Only thin runs (at most ~5 px wide) of nearly pure key hue that touch transparency are removed.
    Wider key-like areas (a blue flower, green leaves under a green key) are subject and stay. Only
    alpha changes.
    """
    channel = KEY_CHANNEL.get(str(key_color or "").strip().lower())
    if channel is None:
        return image
    rgba = image.convert("RGBA")
    pixels = np.array(rgba)
    rgb = pixels[..., :3].astype(np.int16)
    others = np.delete(rgb, channel, axis=2).max(axis=2)
    lead = rgb[..., channel] - others
    visible = pixels[..., 3] > 0
    candidate = visible & (lead >= KEY_RESIDUE_DOMINANCE) & (others <= KEY_RESIDUE_PURITY * rgb[..., channel])
    if not candidate.any():
        return image
    mask = candidate.astype(np.uint8)
    thickness = cv2.distanceTransform(mask, cv2.DIST_L2, 3)
    count, labels = cv2.connectedComponents(mask, connectivity=8)
    widest = np.zeros(count, np.float32)
    np.maximum.at(widest, labels.ravel(), thickness.ravel())
    near_clear = cv2.dilate((~visible).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    touches = np.zeros(count, bool)
    touches[np.unique(labels[candidate & near_clear])] = True
    thin = (widest <= KEY_RESIDUE_MAX_HALF_WIDTH) & touches
    thin[0] = False
    drop = candidate & thin[labels]
    if not drop.any():
        return image
    pixels[drop, 3] = 0
    result = Image.fromarray(pixels, mode="RGBA")
    result.info.update(image.info)
    return result
