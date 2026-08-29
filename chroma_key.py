"""Local chroma-key removal for clipart rendered on a solid key color."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

from PIL import Image


KEY_COLORS: Final[dict[str, tuple[int, int, int]]] = {
    "blue": (0, 0, 255),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
}
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")

MATERIAL_PROMPT_CLAUSES: Final[dict[str, str]] = {
    "watercolor": (
        " Watercolor texture belongs to the subject only; the background "
        "has no paper texture, paper grain, wash or painted variation."
    ),
    "thin_leaves": (
        " Leaves are thick flat blades with rounded tips, solid and opaque, "
        "never hair-thin, wispy or feathery."
    ),
    "conifer_needles": (
        " Needles are short, broad and thick, each a solid opaque blade with "
        "a blunt rounded tip, never fine or feathery."
    ),
    "metal": (
        " Metal elements are matte brushed metal with a soft satin finish, "
        "no mirror reflections or background-colour glints."
    ),
    "ribbon_satin": (
        " Ribbon is matte woven fabric with crisp folded edges and no sheen "
        "or reflection."
    ),
    "transparent_details": (
        " Translucent details have crisp defined edges, no background-colour "
        "reflection, tint or glow."
    ),
    "snow_ice": (
        " Snow and ice are opaque with crisp defined edges, no mist, haze, "
        "glitter particles or background-colour glow."
    ),
}


def parse_key_color(value: object) -> tuple[int, int, int]:
    """Parse a named or hex RGB key color."""
    normalized = str(value or "").strip().lower()
    if normalized in KEY_COLORS:
        return KEY_COLORS[normalized]
    if _HEX_COLOR.fullmatch(normalized):
        return tuple(int(normalized[index : index + 2], 16) for index in (1, 3, 5))
    raise ValueError("Цвет chroma key должен быть blue, red, green или #RRGGBB")


def remove_chroma_key(
    image: Image.Image,
    key_color: object = "blue",
    *,
    tolerance: int = 32,
    softness: int = 8,
) -> Image.Image:
    """Return RGBA with pixels close to ``key_color`` made transparent.

    This is deliberately deterministic and CPU-only. RGB values are copied
    from the source; only alpha is calculated, including semi-transparent
    transition pixels. Existing alpha is respected.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL image")
    if type(tolerance) is not int or not 0 <= tolerance <= 255:
        raise ValueError("tolerance must be between 0 and 255")
    if type(softness) is not int or not 0 <= softness <= 255:
        raise ValueError("softness must be between 0 and 255")
    red, green, blue = parse_key_color(key_color)
    source = image.convert("RGBA")
    pixels = source.load()
    for y in range(source.height):
        for x in range(source.width):
            src_red, src_green, src_blue, src_alpha = pixels[x, y]
            distance = (
                (src_red - red) ** 2
                + (src_green - green) ** 2
                + (src_blue - blue) ** 2
            ) ** 0.5
            if distance <= tolerance:
                alpha = 0
            elif softness and distance < tolerance + softness:
                alpha = round(255 * (distance - tolerance) / softness)
            else:
                alpha = 255
            pixels[x, y] = (src_red, src_green, src_blue, min(src_alpha, alpha))
    return source


def chroma_key_prompt_block(
    key_color: object = "blue",
    *,
    watercolor: bool = False,
    materials: Iterable[object] = (),
) -> str:
    """Return a provider-ready prompt suffix for a removable flat background."""
    rgb = parse_key_color(key_color)
    color_name = next((name for name, value in KEY_COLORS.items() if value == rgb), None)
    label = color_name or "custom"
    hex_color = "#%02X%02X%02X" % rgb
    block = (
        f"Isolated on a completely flat, uniform, solid pure {label} "
        f"({hex_color}) digital chroma-key background. The background fills "
        "the image edge to edge with no gradient and stays fully bright inside "
        "every gap and opening. No reflection, tint, shadow, glow, haze or "
        "color spill on the subject. Crisp hard edges, everything in sharp "
        "focus, the complete subject centered with at least 10% empty margin, "
        "nothing cropped, no text, no watermark, no stray fragments."
    )
    selected = {str(item).strip().casefold() for item in materials}
    if watercolor:
        selected.add("watercolor")
    for material in MATERIAL_PROMPT_CLAUSES:
        if material in selected:
            block += MATERIAL_PROMPT_CLAUSES[material]
    return block


__all__ = [
    "KEY_COLORS",
    "MATERIAL_PROMPT_CLAUSES",
    "chroma_key_prompt_block",
    "parse_key_color",
    "remove_chroma_key",
]
