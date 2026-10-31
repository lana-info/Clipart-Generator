"""Colour hidden under transparency: one rule for the upscaler and the transparency editor.

A cut-out PNG stores an RGB value under every pixel, also under alpha == 0. Nobody sees it until the
brush of the transparency editor restores the area, or until an upscaler blends it into the edge.
Whatever the cut-out stage or an old upscale left there (provider junk, black, a mosaic of nearest
colours) must not leak: the colour is replaced here, the alpha is never touched.
"""
from __future__ import annotations

from PIL import Image

# Soft pixels (0 < alpha < 255) closer than this to the fully transparent field form the rim.
RIM_PIXELS = 3


def extend_foreground_rgb(source_rgba: Image.Image, rim_pixels: int = RIM_PIXELS) -> Image.Image:
    """Extend foreground RGB beneath alpha zero and the soft alpha rim.

    The rim keeps near-transparent pixels whose RGB is black or white junk;
    upscaling would blend it into the edge as a dark halo on light art, so
    its colour is replaced by the nearest opaque pixel. Alpha is restored
    from the original afterwards, so the rim shape is unchanged.

    The far background (alpha == 0 beyond the rim) is filled with the FLAT
    median colour of the opaque subject instead of the nearest-pixel smear:
    the transparency editor's brush reveals this RGB when the owner paints
    the background back, and the nearest-pixel Voronoi looked like a mess of
    mixed subject colours (owner report 2026-10-31). Without fully opaque
    pixels there is no trusted base, so the legacy nearest behaviour stays.
    """
    import cv2
    import numpy as np

    rgba = np.asarray(source_rgba, dtype=np.uint8)
    alpha = rgba[:, :, 3]
    transparent = alpha == 0
    if not np.any(transparent) or not np.any(alpha):
        return source_rgba.convert("RGB")
    trusted = alpha == 255
    has_trusted = bool(np.any(trusted))
    if not has_trusted:
        trusted = alpha > 0
        rim = np.zeros_like(transparent)
        refill = transparent
    else:
        # The rim is only the SOFT pixels (0 < alpha < 255) hugging the keyed-out
        # background; the fully transparent far field is NOT rim (the old formula
        # made every alpha==0 pixel "rim", so the flat-fill split never fired and
        # the brush kept revealing the nearest-colour mess).
        soft = ~trusted & ~transparent
        if np.any(soft):
            distance_to_transparent = cv2.distanceTransform(
                (~transparent).astype(np.uint8), cv2.DIST_L2, 3
            )
            rim = soft & (distance_to_transparent <= rim_pixels)
        else:
            rim = soft
        refill = transparent | rim
    _, labels = cv2.distanceTransformWithLabels(
        (~trusted).astype(np.uint8), cv2.DIST_L2, 5,
        labelType=cv2.DIST_LABEL_PIXEL,
    )
    rgb = rgba[:, :, :3].copy()
    palette = np.empty((int(labels.max()) + 1, 3), dtype=np.uint8)
    palette[labels[trusted]] = rgb[trusted]
    if has_trusted:
        far = transparent & ~rim
        if np.any(far):
            flat = np.median(rgb[trusted], axis=0).astype(np.uint8)
            rgb[far] = flat
        near = refill & ~far
        if np.any(near):
            rgb[near] = palette[labels[near]]
    else:
        rgb[refill] = palette[labels[refill]]
    return Image.fromarray(rgb)


def with_clean_hidden_rgb(image: Image.Image) -> Image.Image:
    """RGBA copy of ``image`` whose fully transparent pixels carry the extended colour.

    Every pixel with alpha > 0 keeps its own RGB and alpha bit for bit, so nothing visible changes;
    only what a restoring brush could later reveal is replaced.
    """
    import numpy as np

    rgba = image.convert("RGBA")
    pixels = np.array(rgba)
    hidden = pixels[:, :, 3] == 0
    if not hidden.any():
        return rgba
    pixels[hidden, :3] = np.asarray(extend_foreground_rgb(rgba))[hidden]
    return Image.fromarray(pixels)
