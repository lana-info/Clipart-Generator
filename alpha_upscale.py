"""Alpha leg of the local Real-ESRGAN upscale (prototype AC-C1, path C; owner 2026-10-30).

The local upscale keeps the RGB leg it always had (Real-ESRGAN of the colour input,
`_prepare_upscale_rgb` fills the subject colour under the alpha). What changes is only
how the cut-out matte reaches the 4x grid: the bilinear stretch multiplied the faint
key remnants x178 on the owner's files (the grey "film") and drew hard stairs instead
of a contour. The alpha leg is a pure-alpha reconstruction:

1. Lanczos resize keeps one clean contour at the upscaled grid;
2. remnants of the key below ``REMNANT_TAU`` are dropped (the film defect, the same
   faint floor the delivery cut already applies as ``alpha_cleanup.HAZE_FLOOR``) and
   alpha above ``OPAQUE_SNAP`` is fully opaque;
3. interior holes smaller than ``MIN_INTERIOR_HOLE_PIXELS`` are closed; the transparent
   periphery (any ``alpha == 0`` region touching the frame) is never touched.

Intentional soft alpha between the tau floor and the opaque snap (fur, down, watercolour
washes) passes the leg without being re-valued. ``REMNANT_TAU_STRICT`` is not the product
default: it zeroes every remnant on the prototype files, but a misted "fur" matte shows
it dries soft tips — the negative control in tests/test_local_upscale_alpha_leg.py.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image

REMNANT_TAU = 40               # bytes; alpha < tau is a remnant of the key (≈ alpha_cleanup.HAZE_FLOOR 0.16)
REMNANT_TAU_STRICT = 64        # bytes; ≈ 0.25 — zeroes every remnant, dries soft tips (tests only)
OPAQUE_SNAP = 200              # bytes; alpha above this is practically opaque and becomes 255
MIN_INTERIOR_HOLE_PIXELS = 32  # upscaled px; ≈ 2x2 native px at x4 (prototype AC-C1: N=32)


def count_interior_holes(alpha: np.ndarray, *, max_area_px: int = MIN_INTERIOR_HOLE_PIXELS) -> int:
    """Count transparent components smaller than ``max_area_px`` that do not touch the frame."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        (alpha == 0).astype(np.uint8), connectivity=4
    )
    peripheral = np.zeros(count, dtype=bool)
    peripheral[np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))] = True
    areas = stats[:, cv2.CC_STAT_AREA]
    return int(np.count_nonzero(~peripheral[1:] & (areas[1:] < max_area_px)))


def upscale_alpha(alpha: Image.Image, scale: int, *, tau: int | None = None,
                  opaque_snap: int | None = None, close_holes_px: int | None = None) -> Image.Image:
    """Return the alpha leg at ``scale`` times the size of ``alpha``.

    ``alpha`` is the native cut-out matte (mode "L"). The tau gate and the hole closing
    read the module constants at call time, so a negative control can turn either off
    with ``monkeypatch`` and watch its test fail.
    """
    tau = REMNANT_TAU if tau is None else int(tau)
    opaque_snap = OPAQUE_SNAP if opaque_snap is None else int(opaque_snap)
    close_holes_px = MIN_INTERIOR_HOLE_PIXELS if close_holes_px is None else int(close_holes_px)

    size = (alpha.width * scale, alpha.height * scale)
    out = np.asarray(alpha.resize(size, Image.Resampling.LANCZOS)).copy()
    out[out < tau] = 0
    out[out > opaque_snap] = 255
    if close_holes_px > 0:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            (out == 0).astype(np.uint8), connectivity=4
        )
        if count > 1:
            peripheral = np.zeros(count, dtype=bool)
            peripheral[np.unique(np.concatenate(
                [labels[0], labels[-1], labels[:, 0], labels[:, -1]]
            ))] = True
            areas = stats[:, cv2.CC_STAT_AREA]
            fill_ids = np.flatnonzero(~peripheral[1:] & (areas[1:] < close_holes_px)) + 1
            if fill_ids.size:
                fill = np.zeros(count, dtype=bool)
                fill[fill_ids] = True
                out[fill[labels]] = 255
    return Image.fromarray(out)
