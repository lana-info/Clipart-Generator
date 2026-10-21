"""Final alpha clean-up for cut-out clipart: remove faint haze, tighten smooth edges.

Three independent steps, applied only to the alpha channel (RGB is never touched):

1. Haze: weak alpha (below ``haze_floor``) farther than ``haze_distance`` px from
   the solid subject is set to zero, together with tiny weak specks.
2. Smooth edges: where the transition band is narrow (hard-edged objects such as
   leaves, ribbons, feet) it is steepened around 50 % so it spans about 1-2 px.
   Wide bands (fur, down, soft pom-poms) are left exactly as they are.
3. Opaque ceiling: alpha that is practically opaque becomes 255.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

HAZE_FLOOR = 0.16          # alpha below this is "faint"
HAZE_DISTANCE = 3.0        # px from the solid core before faint alpha counts as haze
MIN_SPECK_PIXELS = 48      # weak connected blobs smaller than this are dropped
HARD_EDGE_MAX_WIDTH = 9.0  # px, 2 %-98 % band width up to which an edge is "smooth"
EDGE_GAIN = 2.0            # steepening around 50 % alpha
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


def clean_alpha(image: Image.Image, **options) -> Image.Image:
    """Return an RGBA copy of ``image`` with cleaned alpha; RGB is unchanged."""
    rgba = image.convert("RGBA")
    pixels = np.array(rgba)
    cleaned = clean_alpha_array(pixels[..., 3].astype(np.float32) / 255.0, **options)
    pixels[..., 3] = np.rint(cleaned * 255.0).astype(np.uint8)
    return Image.fromarray(pixels, mode="RGBA")
