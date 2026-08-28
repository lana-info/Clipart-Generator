"""Provider-independent alpha-mask editing primitives for Clipart."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


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
) -> Image.Image:
    """Apply one hard-edged add/remove brush stroke to a defensive mask copy."""
    if mask.mode != "L":
        raise ValueError("Маска должна быть в режиме L")
    if radius < 1:
        raise ValueError("Радиус кисти должен быть положительным")
    if action not in {"add", "remove"}:
        raise ValueError("Действие кисти должно быть add или remove")
    result = mask.copy()
    value = 255 if action == "add" else 0
    ImageDraw.Draw(result).ellipse(
        (
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        ),
        fill=value,
    )
    return result


def apply_mask_to_image(image: Image.Image, mask: Image.Image) -> Image.Image:
    """Return an RGBA copy using only ``mask`` as its alpha channel."""
    if image.size != mask.size:
        raise ValueError("Размер маски не совпадает с изображением")
    if mask.mode != "L":
        raise ValueError("Маска должна быть в режиме L")
    result = image.convert("RGBA")
    result.putalpha(mask.copy())
    return result


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
