"""Safe visual previews for transparent Clipart results.

The preview background is never written into the source image or transparent
export. This module deliberately contains no provider or Qt dependencies so it
can be used by local, KIE, and Fal.ai workflows alike.
"""

from __future__ import annotations


from PIL import Image, ImageColor


PREVIEW_BACKGROUND_OPTIONS: tuple[tuple[str, str], ...] = (
    ("Шахматный", "checkerboard"),
    ("Чёрный", "#000000"),
    ("Белый", "#ffffff"),
    ("Зелёный", "#00a651"),
    ("Ярко-розовый", "#E040A0"),
    ("Голубой", "#55c7f7"),
)


def _background_value(label: str) -> str:
    for option_label, value in PREVIEW_BACKGROUND_OPTIONS:
        if option_label == label:
            return value
    raise ValueError("Неизвестный фон предпросмотра")


def preview_background_color(label: str) -> tuple[int, int, int] | None:
    """Return an RGB color, or ``None`` for the checkerboard background."""
    value = _background_value(label)
    if value == "checkerboard":
        return None
    return ImageColor.getrgb(value)


def _checkerboard(size: tuple[int, int], tile_size: int) -> Image.Image:
    if tile_size < 1:
        raise ValueError("Размер клетки должен быть положительным")
    image = Image.new("RGB", size, (238, 238, 238))
    pixels = image.load()
    width, height = size
    dark = (204, 204, 204)
    for y in range(height):
        for x in range(width):
            if (x // tile_size + y // tile_size) % 2:
                pixels[x, y] = dark
    return image


def composite_on_preview(
    source: Image.Image,
    background: str,
    *,
    tile_size: int = 16,
) -> Image.Image:
    """Composite a defensive RGBA copy onto an inspection-only background."""
    rgba = source.convert("RGBA")
    color = preview_background_color(background)
    if color is None:
        canvas = _checkerboard(rgba.size, tile_size).convert("RGBA")
    else:
        canvas = Image.new("RGBA", rgba.size, (*color, 255))
    return Image.alpha_composite(canvas, rgba)
