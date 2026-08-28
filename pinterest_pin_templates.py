"""Deterministic Pillow layouts for vertical Pinterest pins."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont


_BASE_WIDTH: Final = 1000
_BASE_HEIGHT: Final = 1500


@dataclass(frozen=True, slots=True)
class PinTemplateSpec:
    template_id: str
    product_box: tuple[int, int, int, int]
    text_box: tuple[int, int, int, int]
    background_kind: str


_TEMPLATE_SPECS: Final[tuple[PinTemplateSpec, ...]] = (
    PinTemplateSpec(
        template_id="product-hero",
        product_box=(120, 350, 880, 1240),
        text_box=(100, 90, 900, 285),
        background_kind="hero",
    ),
    PinTemplateSpec(
        template_id="editorial-card",
        product_box=(145, 665, 855, 1335),
        text_box=(105, 105, 895, 535),
        background_kind="editorial",
    ),
    PinTemplateSpec(
        template_id="collage",
        product_box=(135, 385, 865, 1015),
        text_box=(90, 1090, 910, 1415),
        background_kind="collage",
    ),
)
_SPECS_BY_ID: Final[dict[str, PinTemplateSpec]] = {
    spec.template_id: spec for spec in _TEMPLATE_SPECS
}

_FONT_PATHS: Final[dict[bool, tuple[Path, ...]]] = {
    False: (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ),
    True: (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("C:/Windows/Fonts/arialbd.ttf"),
    ),
}


def pinterest_template_specs() -> tuple[PinTemplateSpec, ...]:
    """Return the stable, protected layout regions for each pin template."""

    return _TEMPLATE_SPECS


def _scaled_box(
    box: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    scale_x = width / _BASE_WIDTH
    scale_y = height / _BASE_HEIGHT
    return tuple(
        round(value * (scale_x if index % 2 == 0 else scale_y))
        for index, value in enumerate(box)
    )  # type: ignore[return-value]


def _font(size: int, *, bold: bool) -> ImageFont.ImageFont:
    for path in _FONT_PATHS[bold]:
        if path.is_file():
            return ImageFont.truetype(str(path), size=max(1, size))
    return ImageFont.load_default(size=max(1, size))


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> float:
    return draw.textlength(text, font=font)


def _fit_ellipsis(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> str:
    if _text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "…"
    while text and _text_width(draw, text + ellipsis, font) > max_width:
        text = text[:-1]
    return text + ellipsis if text else ""


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    *,
    max_width: int,
    max_lines: int,
) -> list[str]:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return []

    lines: list[str] = []
    current = ""
    for word in normalized.split(" "):
        candidate = word if not current else f"{current} {word}"
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines:
            break

    if len(lines) < max_lines and current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]

    lines = [_fit_ellipsis(draw, line, font, max_width) for line in lines]
    if len(lines) == max_lines and normalized not in " ".join(lines):
        lines[-1] = _fit_ellipsis(draw, lines[-1].rstrip("…") + "…", font, max_width)
    return lines


def _line_height(
    draw: ImageDraw.ImageDraw,
    font: ImageFont.ImageFont,
    text: str = "Ag",
) -> int:
    bbox = draw.textbbox((0, 0), text or "Ag", font=font, anchor="lt")
    return max(1, bbox[3] - bbox[1])


def _draw_text(
    image: Image.Image,
    box: tuple[int, int, int, int],
    *,
    title: str,
    subtitle: str,
    cta: str,
    scale: float,
) -> None:
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = box
    max_width = max(1, right - left)
    max_height = max(1, bottom - top)
    title_max = max(1, round(72 * scale))
    subtitle_size = max(1, round(27 * scale))
    cta_size = max(1, round(24 * scale))
    gap = min(12, max_height // 20)

    selected: tuple[ImageFont.ImageFont, list[str], ImageFont.ImageFont, list[str], ImageFont.ImageFont, list[str]] | None = None
    for title_size in range(title_max, 0, -1):
        title_font = _font(title_size, bold=True)
        subtitle_font = _font(min(subtitle_size, max(title_size // 2, 1)), bold=False)
        cta_font = _font(min(cta_size, max(title_size // 2, 1)), bold=True)
        title_lines = _wrap_text(draw, title, title_font, max_width=max_width, max_lines=3)
        subtitle_lines = _wrap_text(
            draw,
            subtitle,
            subtitle_font,
            max_width=max_width,
            max_lines=3,
        )
        cta_lines = _wrap_text(draw, cta, cta_font, max_width=max_width, max_lines=1)
        heights = [
            sum(_line_height(draw, title_font, line) for line in title_lines),
            sum(_line_height(draw, subtitle_font, line) for line in subtitle_lines),
            sum(_line_height(draw, cta_font, line) for line in cta_lines),
        ]
        gaps = gap * sum(bool(lines) for lines in (title_lines, subtitle_lines, cta_lines))
        if sum(heights) + gaps <= max_height:
            selected = (
                title_font,
                title_lines,
                subtitle_font,
                subtitle_lines,
                cta_font,
                cta_lines,
            )
            break

    if selected is None:
        return

    cursor_y = top
    for font, lines in (
        (selected[0], selected[1]),
        (selected[2], selected[3]),
        (selected[4], selected[5]),
    ):
        for line in lines:
            draw.text(
                (left, cursor_y),
                line,
                font=font,
                fill=(34, 43, 51, 255),
                anchor="lt",
            )
            cursor_y += _line_height(draw, font, line)
        if lines:
            cursor_y += gap


def _draw_background(
    image: Image.Image,
    *,
    background_kind: str,
    product_box: tuple[int, int, int, int],
    text_box: tuple[int, int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    if background_kind == "hero":
        draw.rectangle((0, 0, width, height), fill=(246, 235, 218, 255))
        draw.ellipse(
            (round(width * 0.54), round(height * 0.05), round(width * 0.94), round(height * 0.30)),
            fill=(246, 191, 116, 255),
        )
        draw.rounded_rectangle(product_box, radius=max(8, width // 32), fill=(255, 249, 239, 255))
    elif background_kind == "editorial":
        draw.rectangle((0, 0, width, height), fill=(222, 234, 236, 255))
        draw.rectangle((0, round(height * 0.43), width, height), fill=(248, 242, 229, 255))
        draw.line(
            (text_box[0], text_box[3] + max(10, width // 50), text_box[2], text_box[3] + max(10, width // 50)),
            fill=(212, 133, 92, 255),
            width=max(2, width // 250),
        )
        draw.rounded_rectangle(product_box, radius=max(8, width // 36), fill=(255, 255, 255, 255), outline=(197, 211, 211, 255), width=max(2, width // 250))
    else:
        draw.rectangle((0, 0, width, height), fill=(233, 239, 230, 255))
        draw.rounded_rectangle(
            (round(width * 0.04), round(height * 0.04), round(width * 0.96), round(height * 0.69)),
            radius=max(8, width // 28),
            fill=(250, 242, 222, 255),
        )
        draw.ellipse(
            (round(width * 0.69), round(height * 0.11), round(width * 0.92), round(height * 0.29)),
            fill=(224, 145, 135, 255),
        )
        draw.rounded_rectangle(product_box, radius=max(8, width // 36), fill=(255, 255, 255, 255))


def _place_product(
    canvas: Image.Image,
    product_rgba: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    box_width, box_height = right - left, bottom - top
    product = product_rgba.convert("RGBA")
    scale = min(box_width / product.width, box_height / product.height)
    if scale < 1:
        product = product.resize(
            (
                max(1, round(product.width * scale)),
                max(1, round(product.height * scale)),
            ),
            Image.Resampling.LANCZOS,
        )
    else:
        product = product.copy()
    position = (
        left + (box_width - product.width) // 2,
        top + (box_height - product.height) // 2,
    )
    canvas.alpha_composite(product, position)


def render_template_pin(
    product_rgba: Image.Image,
    *,
    title: str,
    subtitle: str,
    cta: str,
    template_id: str,
    width: int = 1000,
    height: int = 1500,
) -> Image.Image:
    """Render one deterministic vertical pin using a protected product region."""

    if not isinstance(product_rgba, Image.Image):
        raise TypeError("product_rgba must be a PIL Image")
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    try:
        spec = _SPECS_BY_ID[template_id]
    except KeyError as error:
        raise ValueError(f"unknown Pinterest template: {template_id}") from error

    product_box = _scaled_box(spec.product_box, width=width, height=height)
    text_box = _scaled_box(spec.text_box, width=width, height=height)
    canvas = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    _draw_background(
        canvas,
        background_kind=spec.background_kind,
        product_box=product_box,
        text_box=text_box,
    )
    _place_product(canvas, product_rgba, product_box)
    _draw_text(
        canvas,
        text_box,
        title=title,
        subtitle=subtitle,
        cta=cta,
        scale=min(width / _BASE_WIDTH, height / _BASE_HEIGHT),
    )
    return canvas


__all__ = [
    "PinTemplateSpec",
    "pinterest_template_specs",
    "render_template_pin",
]
