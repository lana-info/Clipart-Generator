"""Bounded RGB retouch for an explicitly selected transparency-editor region.

This proposes intentional paint replacement, not recovery of a known original
foreground. The caller owns preview, acceptance, revision checks and undo.
"""
from __future__ import annotations

from concurrent.futures import CancelledError
from dataclasses import dataclass
from typing import Callable

import cv2
import numpy as np
from PIL import Image


EDGE_COLOUR_BAND_WIDTH = 4
MAX_EDGE_COLOUR_CONTEXT_PIXELS = 1_048_576
_RELAXATION_STEPS = 4
_KERNEL = np.array([[1, 2, 1], [2, 4, 2], [1, 2, 1]], np.float32) / 16


@dataclass(frozen=True)
class EdgeColourProposal:
    bounds: tuple[int, int, int, int]
    image_patch: Image.Image
    changed_pixels: int
    effective_band_width: int


def propose_edge_colour(
    image: Image.Image,
    selection: Image.Image,
    bounds: tuple[int, int, int, int],
    *,
    alpha_mask: Image.Image | None = None,
    band_width: int = EDGE_COLOUR_BAND_WIDTH,
    cancel_check: Callable[[], bool | None] | None = None,
) -> EdgeColourProposal | None:
    """Propose a tight RGB patch; never mutate the image, selection or alpha.

    ``selection`` is an L image the size of ``bounds`` (PIL exclusive-right/
    bottom coordinates). Nonzero selection pixels authorize colour replacement.
    ``alpha_mask`` optionally supplies the editor's current full-size L mask;
    only its context crop is read. Otherwise alpha comes from ``image``.

    Colour propagates from opaque interior through visible neighbours, at most
    twelve pixels. Only selected visible pixels within four pixels of the opaque
    boundary, including supported partial coverage, can change. Unconnected
    components without interior donors stay unchanged. The last inward pixel
    fades to the source colour; deeper paint is exact. No alpha is returned.

    All arrays are bounded by the selection's tight box plus a fixed context
    halo. Oversized context raises ValueError before pixel arrays are allocated.
    A true cancel_check result raises CancelledError; callback exceptions also
    propagate. None means no supported change, including all-opaque/empty input.
    The only currently supported band width is four final-image pixels.
    """
    if not isinstance(image, Image.Image) or min(image.size) < 1:
        raise ValueError("Нужно непустое изображение")
    if (not isinstance(bounds, (tuple, list)) or len(bounds) != 4
            or any(type(value) is not int for value in bounds)):
        raise ValueError("Область должна содержать четыре целые координаты")
    left, top, right, bottom = bounds
    if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
        raise ValueError("Область выходит за границы изображения")
    if (not isinstance(selection, Image.Image) or selection.mode != "L"
            or selection.size != (right - left, bottom - top)):
        raise ValueError("Маска выделения должна соответствовать области")
    if alpha_mask is not None and (
        not isinstance(alpha_mask, Image.Image) or alpha_mask.mode != "L"
        or alpha_mask.size != image.size
    ):
        raise ValueError("Маска прозрачности должна соответствовать изображению")
    if type(band_width) is not int or band_width != EDGE_COLOUR_BAND_WIDTH:
        raise ValueError("Ширина этой коррекции должна быть 4 пикселя")
    if cancel_check is not None and not callable(cancel_check):
        raise TypeError("cancel_check must be callable")

    def check_cancelled() -> None:
        if cancel_check is not None and cancel_check():
            raise CancelledError()

    check_cancelled()
    selected_box = selection.getbbox()
    if selected_box is None:
        return None
    sl, st, sr, sb = selected_box
    selected_bounds = (left + sl, top + st, left + sr, top + sb)
    steps = 3 * band_width
    # Include every possible propagation/relaxation donor and the depth test.
    halo = steps + _RELAXATION_STEPS + band_width + 2
    x0, y0 = max(0, selected_bounds[0] - halo), max(0, selected_bounds[1] - halo)
    x1, y1 = min(image.width, selected_bounds[2] + halo), min(image.height, selected_bounds[3] + halo)
    if (x1 - x0) * (y1 - y0) > MAX_EDGE_COLOUR_CONTEXT_PIXELS:
        raise ValueError("Выберите меньший участок края для коррекции")
    check_cancelled()
    pixels = np.array(image.crop((x0, y0, x1, y1)).convert("RGBA"))
    alpha = (pixels[..., 3] if alpha_mask is None
             else np.array(alpha_mask.crop((x0, y0, x1, y1))))
    visible, opaque = alpha > 0, alpha == 255
    if not np.any(opaque) or np.all(opaque):
        return None
    depth = cv2.distanceTransform(opaque.astype(np.uint8), cv2.DIST_L2, 5)
    core = depth > band_width
    if not np.any(core):
        return None
    selected = np.zeros(alpha.shape, dtype=bool)
    sx, sy = selected_bounds[0] - x0, selected_bounds[1] - y0
    selected[sy:sy + sb - st, sx:sx + sr - sl] = np.array(selection.crop(selected_box)) > 0
    target = selected & visible & ~core
    if not np.any(target):
        return None

    reached = core.copy()
    colour = np.where(core[..., None], pixels[..., :3], 0).astype(np.float32)
    for _ in range(steps):
        check_cancelled()
        weight = cv2.filter2D(reached.astype(np.float32), -1, _KERNEL, borderType=cv2.BORDER_CONSTANT)
        summed = cv2.filter2D(colour, -1, _KERNEL, borderType=cv2.BORDER_CONSTANT)
        frontier = visible & ~reached & (weight > 0)
        if not np.any(frontier):
            break
        colour[frontier] = summed[frontier] / weight[frontier, None]
        reached |= frontier
    target &= reached
    if not np.any(target):
        return None
    extension = reached & ~core
    weight = cv2.filter2D(reached.astype(np.float32), -1, _KERNEL, borderType=cv2.BORDER_CONSTANT)
    for _ in range(_RELAXATION_STEPS):
        check_cancelled()
        summed = cv2.filter2D(colour, -1, _KERNEL, borderType=cv2.BORDER_CONSTANT)
        colour[extension] = summed[extension] / weight[extension, None]

    strength = np.clip(band_width - depth[target], 0.0, 1.0)[:, None]
    original = pixels[target, :3].astype(np.float32)
    repaired = np.rint(np.clip(original + strength * (colour[target] - original), 0, 255)).astype(np.uint8)
    changed = np.zeros(alpha.shape, dtype=bool)
    changed[target] = np.any(repaired != pixels[target, :3], axis=1)
    changed_count = int(np.count_nonzero(changed))
    if not changed_count:
        return None
    pixels[target, :3] = repaired
    rows, columns = np.nonzero(changed)
    lx, ty, rx, by = int(columns.min()), int(rows.min()), int(columns.max()) + 1, int(rows.max()) + 1
    check_cancelled()
    return EdgeColourProposal(
        bounds=(x0 + lx, y0 + ty, x0 + rx, y0 + by),
        image_patch=Image.fromarray(pixels[ty:by, lx:rx, :3].copy()),
        changed_pixels=changed_count,
        effective_band_width=band_width,
    )
