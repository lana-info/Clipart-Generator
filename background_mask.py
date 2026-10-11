"""Provider-independent alpha-mask editing primitives for Clipart."""

from __future__ import annotations

import os
import tempfile
from functools import lru_cache
from math import ceil, hypot
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


@lru_cache(maxsize=16)
def _brush_opacity(radius: int, hardness: int) -> Image.Image:
    if radius == 0:
        # A single pixel has no feathered neighbours, regardless of hardness.
        return Image.new("L", (1, 1), 255)
    diameter = radius * 2 + 1
    # Supersampling retains fractional pixel coverage even for a hard brush.
    scale = 4
    large = Image.new("L", (diameter * scale, diameter * scale), 0)
    ImageDraw.Draw(large).ellipse(
        (0, 0, diameter * scale - 1, diameter * scale - 1), fill=255
    )
    shape = large.resize((diameter, diameter), Image.Resampling.LANCZOS)
    if hardness == 100:
        return shape
    gradient = Image.radial_gradient("L").resize(
        (diameter, diameter),
        Image.Resampling.BILINEAR,
    )
    threshold = round(255 * hardness / 100)
    span = max(1, 255 - threshold)
    feather = gradient.point(
        lambda value: 255
        if value <= threshold
        else max(0, round(255 * (255 - value) / span))
    )
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
    opacity = _brush_opacity(radius, hardness)
    value = 255 if action == "add" else 0

    def stamp(x: int, y: int) -> None:
        mask.paste(
            value,
            (x - radius, y - radius, x + radius + 1, y + radius + 1),
            opacity,
        )

    previous = (int(points[0][0]), int(points[0][1]))
    stamp(*previous)
    spacing = max(1.0, radius / 3)
    for raw_point in points[1:]:
        current = (int(raw_point[0]), int(raw_point[1]))
        distance = hypot(current[0] - previous[0], current[1] - previous[1])
        steps = max(1, ceil(distance / spacing))
        for step in range(1, steps + 1):
            stamp(
                round(previous[0] + (current[0] - previous[0]) * step / steps),
                round(previous[1] + (current[1] - previous[1]) * step / steps),
            )
        previous = current


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
