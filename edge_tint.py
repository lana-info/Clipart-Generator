"""Pull the key-ward colour cast of a soft edge back to the colour of the subject next to it.

A hair tip one pixel wide never holds a pure subject pixel: its colour is the subject mixed with the key
(cream + blue = lilac), and no estimate from that pixel alone recovers the subject. The neighbouring subject
does: its hue is taken from the opaque pixels a little deeper inside, the pixel keeps its own lightness.

Only where that reference is trustworthy: the opaque neighbourhood must be one colour (cream fur, one leaf).
Where two colours meet (a leaf tip beside a red berry) the neighbourhood is a blend of both, there is no
reference and the pixels stay as they are. Only RGB changes, alpha never.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

from chroma_key import KEY_COLORS

ZONE_PIXELS = 8.0            # pixels this close to the silhouette are checked
SIGMA = 6.0                  # reach of the neighbouring-subject reference; widened where it finds nothing
FAR_REACH = 2.7              # widening factor for long hairs far from the opaque body
CAST_LO, CAST_HI = 3.0, 14.0     # Lab chroma shift toward the key that starts / fully triggers the correction
PARTIAL_CAST = 6.0           # a partial-alpha pixel is a mixture: this shift already means full correction
SPREAD_LO, SPREAD_HI = 7.0, 14.0  # Lab chroma spread of the reference: homogeneous below LO, none above HI
LIGHT_BELOW, LIGHT_ABOVE = 25.0, 15.0   # a corrected partial pixel stays this close to the reference lightness
PARTIAL_ALPHA = 0.98


def _blur(values: np.ndarray, sigma: float) -> np.ndarray:
    size = int(sigma * 6) | 1
    return cv2.GaussianBlur(values, (size, size), sigma)


def _lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2Lab)


def suppress_key_tint(image: Image.Image, key_color: str) -> Image.Image:
    """Return ``image`` (RGBA) with the key-ward cast of its soft edge corrected; ``image`` itself for an unknown key."""
    key = KEY_COLORS.get(str(key_color or "").strip().lower())
    if key is None:
        return image
    rgba = np.asarray(image.convert("RGBA"))
    alpha = rgba[..., 3].astype(np.float32) / 255.0
    rgb = rgba[..., :3].astype(np.float32) / 255.0
    lab = _lab(rgb)
    key_lab = _lab(np.array([[key]], np.float32) / 255.0)[0, 0]
    direction = key_lab[1:] / max(float(np.hypot(*key_lab[1:])), 1e-6)

    inside = cv2.distanceTransform((alpha >= 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    zone = (alpha > 0) & ((inside <= ZONE_PIXELS) | (alpha < 0.5))
    deep = ((alpha >= 1.0) & (inside > ZONE_PIXELS)).astype(np.float32)
    if not zone.any() or not deep.any():
        return image
    fields = np.dstack([lab[..., 0], lab[..., 1], lab[..., 2], lab[..., 1] ** 2, lab[..., 2] ** 2]) * deep[..., None]

    def reference(sigma):
        weight = _blur(deep, sigma)
        return _blur(fields, sigma) / np.maximum(weight, 1e-9)[..., None], weight

    near, near_weight = reference(SIGMA)
    far, far_weight = reference(SIGMA * FAR_REACH)
    use_near = near_weight >= 0.05
    ref = np.where(use_near[..., None], near, far)
    known = zone & (np.where(use_near, near_weight, far_weight) > 1e-4)

    ref_light, ref_a, ref_b = ref[..., 0], ref[..., 1], ref[..., 2]
    spread = np.sqrt(np.maximum(ref[..., 3] - ref_a ** 2, 0) + np.maximum(ref[..., 4] - ref_b ** 2, 0))
    cast = (lab[..., 1] - ref_a) * direction[0] + (lab[..., 2] - ref_b) * direction[1]
    partial = alpha < PARTIAL_ALPHA
    strength = np.clip((cast - CAST_LO) / (CAST_HI - CAST_LO), 0, 1)
    strength = np.maximum(strength, np.where(partial, np.clip(cast / PARTIAL_CAST, 0, 1), 0.0))
    strength = strength * (1 - np.clip((spread - SPREAD_LO) / (SPREAD_HI - SPREAD_LO), 0, 1))
    strength = np.where(known, strength, 0.0)
    if not strength.any():
        return image

    fixed = lab.copy()
    limited = np.clip(lab[..., 0], ref_light - LIGHT_BELOW, ref_light + LIGHT_ABOVE)
    fixed[..., 0] = lab[..., 0] + np.where(partial, strength, 0.0) * (limited - lab[..., 0])
    fixed[..., 1] = lab[..., 1] * (1 - strength) + ref_a * strength
    fixed[..., 2] = lab[..., 2] * (1 - strength) + ref_b * strength
    corrected = np.clip(cv2.cvtColor(fixed, cv2.COLOR_Lab2RGB), 0.0, 1.0)
    pixels = rgba.copy()
    changed = strength > 0
    pixels[changed, :3] = np.rint(corrected[changed] * 255.0).astype(np.uint8)
    result = Image.fromarray(pixels, "RGBA")
    result.info.update(image.info)
    return result
