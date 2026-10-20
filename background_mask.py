"""Provider-independent alpha-mask editing primitives for Clipart."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
import math
from math import ceil, floor, hypot
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw


def mask_for_image(image: Image.Image) -> Image.Image:
    """Return a writable L-mode mask, reusing an existing image alpha channel."""
    if not isinstance(image, Image.Image):
        raise TypeError("Ожидается изображение PIL")
    if "A" in image.getbands():
        return image.getchannel("A").copy()
    return Image.new("L", image.size, 255)


def apply_mask_stroke(
    mask: Image.Image,
    center: tuple[int, int],
    *,
    radius: int,
    action: str,
    hardness: int = 100,
) -> Image.Image:
    """Apply one add/remove brush stamp to a defensive mask copy."""
    return apply_mask_path(
        mask,
        (center,),
        radius=radius,
        action=action,
        hardness=hardness,
    )


def _validate_brush(mask: Image.Image, radius: int, action: str, hardness: int) -> None:
    if mask.mode != "L":
        raise ValueError("Маска должна быть в режиме L")
    if radius < 0:
        raise ValueError("Радиус кисти не может быть отрицательным")
    if action not in {"add", "remove"}:
        raise ValueError("Действие кисти должно быть add или remove")
    if not 0 <= hardness <= 100:
        raise ValueError("Жёсткость кисти должна быть от 0 до 100")


SUBPIXEL_STEPS = 4
# Owner acceptance 2026-10-19: a soft edge on a tiny brush only looks ragged, so
# brushes up to 6 px across (radius <= 3) stay hard whatever hardness is chosen.
MIN_SOFT_RADIUS = 4


@lru_cache(maxsize=256)
def _brush_opacity(radius: int, hardness: int, qx: int = 0, qy: int = 0) -> Image.Image:
    """Brush stamp; ``qx``/``qy`` shift the disc by that many quarter pixels."""
    if radius == 0:
        # A single pixel has no feathered neighbours, regardless of hardness.
        return Image.new("L", (1, 1), 255)
    if radius < MIN_SOFT_RADIUS:
        hardness = 100
    fractional = bool(qx or qy)
    diameter = radius * 2 + (2 if fractional else 1)
    cx = radius + 0.5 + qx / SUBPIXEL_STEPS
    cy = radius + 0.5 + qy / SUBPIXEL_STEPS
    edge = radius + 0.5
    # Supersampling retains fractional pixel coverage even for a hard brush.
    scale = 4
    large = Image.new("L", (diameter * scale, diameter * scale), 0)
    ImageDraw.Draw(large).ellipse(
        ((cx - edge) * scale, (cy - edge) * scale,
         (cx + edge) * scale - 1, (cy + edge) * scale - 1), fill=255
    )
    shape = large.resize((diameter, diameter), Image.Resampling.LANCZOS)
    if hardness == 100:
        return shape
    # Falloff measured against the brush radius itself: fully opaque inside
    # ``hardness`` percent of the radius, then a gaussian-like fade that reaches
    # exactly 0 at the edge (gradual, no flat "stripe" and no hard step).
    core = hardness / 100
    edge = radius + 0.5
    floor_value = math.exp(-4.5)
    data = []
    for y in range(diameter):
        for x in range(diameter):
            ratio = hypot(x + 0.5 - cx, y + 0.5 - cy) / edge
            if ratio <= core:
                data.append(255)
            else:
                t = min(1.0, (ratio - core) / (1 - core))
                value = (math.exp(-4.5 * t * t) - floor_value) / (1 - floor_value)
                data.append(max(0, round(255 * value)))
    feather = Image.new("L", (diameter, diameter))
    feather.putdata(data)
    return ImageChops.multiply(shape, feather)


def apply_mask_path(
    mask: Image.Image,
    points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    *,
    radius: int,
    action: str,
    hardness: int = 100,
) -> Image.Image:
    """Apply a continuous add/remove stroke between sampled pointer points."""
    result = mask.copy()
    _paint_mask_path(
        result,
        points,
        radius=radius,
        action=action,
        hardness=hardness,
    )
    return result


def paint_mask_path(
    mask: Image.Image,
    points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    *,
    radius: int,
    action: str,
    hardness: int = 100,
) -> None:
    """Paint a continuous stroke directly into an owned writable mask."""
    _paint_mask_path(
        mask,
        points,
        radius=radius,
        action=action,
        hardness=hardness,
    )


def stamp_path_coverage(
    cover: Image.Image,
    points: tuple[tuple[float, float], ...] | list[tuple[float, float]],
    *,
    radius: int,
    hardness: int,
) -> None:
    """Merge a brush path into ``cover`` taking the maximum, never accumulating.

    Overlapping stamps of one stroke therefore keep the soft falloff of the
    brush instead of adding up to a hard edge. Centres may be fractional:
    stamps are placed with quarter-pixel precision so edges stay smooth.
    """
    if not points:
        return

    def stamp(x: float, y: float) -> None:
        if radius == 0:
            ix, iy, qx, qy = round(x), round(y), 0, 0
        else:
            ix, iy = floor(x), floor(y)
            qx = round((x - ix) * SUBPIXEL_STEPS)
            qy = round((y - iy) * SUBPIXEL_STEPS)
            if qx == SUBPIXEL_STEPS:
                ix, qx = ix + 1, 0
            if qy == SUBPIXEL_STEPS:
                iy, qy = iy + 1, 0
        opacity = _brush_opacity(radius, hardness, qx, qy)
        box = (ix - radius, iy - radius,
               ix - radius + opacity.width, iy - radius + opacity.height)
        clipped = (max(0, box[0]), max(0, box[1]),
                   min(cover.width, box[2]), min(cover.height, box[3]))
        if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
            return
        part = opacity.crop((clipped[0] - box[0], clipped[1] - box[1],
                             clipped[2] - box[0], clipped[3] - box[1]))
        cover.paste(ImageChops.lighter(cover.crop(clipped), part), clipped[:2])

    previous = (float(points[0][0]), float(points[0][1]))
    stamp(*previous)
    spacing = max(0.25, min(0.5, radius / 8))
    for raw_point in points[1:]:
        current = (float(raw_point[0]), float(raw_point[1]))
        distance = hypot(current[0] - previous[0], current[1] - previous[1])
        steps = max(1, ceil(distance / spacing))
        for step in range(1, steps + 1):
            stamp(
                previous[0] + (current[0] - previous[0]) * step / steps,
                previous[1] + (current[1] - previous[1]) * step / steps,
            )
        previous = current


def _paint_mask_path(
    mask: Image.Image,
    points: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    *,
    radius: int,
    action: str,
    hardness: int,
) -> None:
    _validate_brush(mask, radius, action, hardness)
    if not points:
        return
    cover = Image.new("L", mask.size, 0)
    stamp_path_coverage(cover, points, radius=radius, hardness=hardness)
    mask.paste(255 if action == "add" else 0, mask=cover)


def apply_mask_to_image(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Return an RGBA copy using only ``mask`` as its alpha channel."""
    if image.size != mask.size:
        raise ValueError("Размер маски не совпадает с изображением")
    if mask.mode != "L":
        raise ValueError("Маска должна быть в режиме L")
    result = image.convert("RGBA")
    result.putalpha(mask.copy())
    return result


def has_usable_alpha(image: Image.Image) -> bool:
    """Return whether an image contains at least one transparent pixel."""
    rgba = image.convert("RGBA")
    return rgba.getchannel("A").getextrema()[0] < 255


def save_mask_png(mask: Image.Image, path: str | Path) -> None:
    """Atomically save an alpha mask as a bounded PNG file."""
    if mask.mode != "L":
        raise ValueError("Маска должна быть в режиме L")
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{destination.stem}.",
        suffix=".tmp",
        dir=destination.parent,
    )
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        mask.save(temporary_path, format="PNG")
        os.replace(temporary_path, destination)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
