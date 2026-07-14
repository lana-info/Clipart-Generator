"""Read-only, value-safe metadata inspection for supported image inputs."""

from __future__ import annotations

import re
import struct
from os import PathLike
from typing import Any

from PIL import ExifTags, Image, IptcImagePlugin, UnidentifiedImageError


SCHEMA_VERSION = 1
SUPPORTED_FORMATS = frozenset({"PNG", "JPEG"})
CATEGORY_NAMES = (
    "exif",
    "xmp",
    "iptc",
    "comments_text",
    "embedded_thumbnail",
    "icc_profile",
    "dpi",
    "generator_fields",
)

_XMP_KEYS = frozenset({"xml:com.adobe.xmp", "xmp"})
_GENERATOR_FIELD_PATTERNS = {
    "software": ("software", "creatortool"),
    "prompt": ("prompt", "parameters", "workflow"),
    "model": ("model", "aisystemused"),
    "digital_source_type": ("digitalsourcetype",),
    "generator": ("generator", "aigc", "hfjobid", "signature"),
}


def _empty_category() -> dict[str, Any]:
    return {"present": False, "item_count": 0, "size_bytes": 0}


def _empty_categories() -> dict[str, dict[str, Any]]:
    return {name: _empty_category() for name in CATEGORY_NAMES}


def _category(item_count: int = 0, size_bytes: int = 0, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "present": item_count > 0 or size_bytes > 0,
        "item_count": max(0, int(item_count)),
        "size_bytes": max(0, int(size_bytes)),
    }
    result.update(extra)
    return result


def _value_size(value: Any) -> int:
    if isinstance(value, bytes):
        return len(value)
    if isinstance(value, str):
        return len(value.encode("utf-8", errors="replace"))
    if isinstance(value, (tuple, list)):
        return sum(_value_size(item) for item in value)
    return 0


def _normalized_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _known_generator_fields(names: list[str], payloads: list[bytes] | None = None) -> tuple[str, ...]:
    normalized_names = [_normalized_field_name(name) for name in names]
    searchable_payload = b"\n".join(payloads or ()).lower()
    matches: set[str] = set()
    for canonical_name, patterns in _GENERATOR_FIELD_PATTERNS.items():
        for pattern in patterns:
            normalized_pattern = _normalized_field_name(pattern)
            if any(normalized_pattern in name for name in normalized_names):
                matches.add(canonical_name)
                break
            if normalized_pattern.encode("ascii") in searchable_payload:
                matches.add(canonical_name)
                break
    return tuple(sorted(matches))


def _read_tiff_integer(data: bytes, offset: int, byte_order: str, value_type: int, count: int) -> int | None:
    if count != 1:
        return None
    if value_type == 3 and offset + 2 <= len(data):
        return struct.unpack_from(f"{byte_order}H", data, offset)[0]
    if value_type == 4 and offset + 4 <= len(data):
        return struct.unpack_from(f"{byte_order}I", data, offset)[0]
    return None


def _exif_thumbnail_size(exif_bytes: bytes) -> int:
    """Return the bounded JPEG thumbnail size from EXIF IFD1, if present."""

    data = exif_bytes[6:] if exif_bytes.startswith(b"Exif\x00\x00") else exif_bytes
    if len(data) < 8:
        return 0
    if data[:2] == b"II":
        byte_order = "<"
    elif data[:2] == b"MM":
        byte_order = ">"
    else:
        return 0
    try:
        if struct.unpack_from(f"{byte_order}H", data, 2)[0] != 42:
            return 0
        ifd0_offset = struct.unpack_from(f"{byte_order}I", data, 4)[0]
        if ifd0_offset + 2 > len(data):
            return 0
        ifd0_count = struct.unpack_from(f"{byte_order}H", data, ifd0_offset)[0]
        next_ifd_position = ifd0_offset + 2 + (ifd0_count * 12)
        if next_ifd_position + 4 > len(data):
            return 0
        ifd1_offset = struct.unpack_from(f"{byte_order}I", data, next_ifd_position)[0]
        if not ifd1_offset or ifd1_offset + 2 > len(data):
            return 0
        ifd1_count = struct.unpack_from(f"{byte_order}H", data, ifd1_offset)[0]
        entries_end = ifd1_offset + 2 + (ifd1_count * 12)
        if entries_end + 4 > len(data):
            return 0

        thumbnail_offset: int | None = None
        thumbnail_length: int | None = None
        for index in range(ifd1_count):
            entry_offset = ifd1_offset + 2 + (index * 12)
            tag, value_type = struct.unpack_from(f"{byte_order}HH", data, entry_offset)
            count = struct.unpack_from(f"{byte_order}I", data, entry_offset + 4)[0]
            value = _read_tiff_integer(data, entry_offset + 8, byte_order, value_type, count)
            if tag == 0x0201:
                thumbnail_offset = value
            elif tag == 0x0202:
                thumbnail_length = value

        if thumbnail_offset is None or thumbnail_length is None or thumbnail_length <= 0:
            return 0
        if thumbnail_offset + thumbnail_length > len(data):
            return 0
        return thumbnail_length
    except (struct.error, OverflowError, ValueError):
        return 0


def _base_result(status: str, reason: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "supported": status == "ok",
        "reason": reason,
        "format": None,
        "mode": None,
        "width": None,
        "height": None,
        "is_animated": False,
        "categories": _empty_categories(),
    }


def _png_text_entries(image: Image.Image) -> dict[str, str]:
    text = getattr(image, "text", None)
    if not isinstance(text, dict):
        return {}
    return {str(key): str(value) for key, value in text.items()}


def _xmp_payloads(image: Image.Image, png_text: dict[str, str]) -> list[bytes]:
    payloads: list[bytes] = []
    raw_xmp = image.info.get("xmp")
    if isinstance(raw_xmp, bytes):
        payloads.append(raw_xmp)
    elif isinstance(raw_xmp, str):
        payloads.append(raw_xmp.encode("utf-8", errors="replace"))
    for key, value in png_text.items():
        if key.lower() in _XMP_KEYS:
            payloads.append(value.encode("utf-8", errors="replace"))
    return payloads


def _inspect_supported_image(image: Image.Image) -> dict[str, dict[str, Any]]:
    categories = _empty_categories()
    png_text = _png_text_entries(image) if image.format == "PNG" else {}

    raw_exif = image.info.get("exif")
    if not isinstance(raw_exif, bytes):
        raw_exif = b""
    try:
        exif = image.getexif()
        exif_count = len(exif)
        if not raw_exif and exif_count:
            raw_exif = exif.tobytes()
    except (OSError, SyntaxError, ValueError):
        exif = {}
        exif_count = 0
    categories["exif"] = _category(exif_count, len(raw_exif))

    thumbnail_size = _exif_thumbnail_size(raw_exif) if raw_exif else 0
    categories["embedded_thumbnail"] = _category(1 if thumbnail_size else 0, thumbnail_size)

    xmp_payloads = _xmp_payloads(image, png_text)
    categories["xmp"] = _category(len(xmp_payloads), sum(map(len, xmp_payloads)))

    try:
        iptc = IptcImagePlugin.getiptcinfo(image) or {}
    except (OSError, SyntaxError, ValueError):
        iptc = {}
    categories["iptc"] = _category(len(iptc), sum(_value_size(value) for value in iptc.values()))

    ordinary_text = [(key, value) for key, value in png_text.items() if key.lower() not in _XMP_KEYS]
    raw_comment = image.info.get("comment")
    comment_count = 1 if isinstance(raw_comment, (bytes, str)) and raw_comment else 0
    text_size = sum(_value_size(key) + _value_size(value) for key, value in ordinary_text)
    categories["comments_text"] = _category(
        len(ordinary_text) + comment_count,
        text_size + _value_size(raw_comment),
    )

    raw_icc = image.info.get("icc_profile")
    categories["icc_profile"] = _category(1 if raw_icc else 0, _value_size(raw_icc))

    raw_dpi = image.info.get("dpi")
    dpi_present = isinstance(raw_dpi, (tuple, list)) and len(raw_dpi) >= 2
    categories["dpi"] = _category(1 if dpi_present else 0, 0)

    exif_names = [str(ExifTags.TAGS.get(tag, tag)) for tag in exif]
    metadata_names = exif_names + [key for key, _ in ordinary_text]
    generator_fields = _known_generator_fields(metadata_names, xmp_payloads)
    categories["generator_fields"] = _category(
        len(generator_fields),
        0,
        fields=list(generator_fields),
    )
    return categories


def inspect_image_metadata(path: str | PathLike[str]) -> dict[str, Any]:
    """Inspect supported metadata and return a JSON-compatible summary.

    The function opens the source read-only and returns counts/sizes instead of
    user-provided metadata values. Unsupported, animated, or invalid inputs are
    represented as structured results rather than partially inspected files.
    """

    try:
        with Image.open(path) as image:
            image_format = (image.format or "").upper()
            result = _base_result("ok")
            result.update(
                {
                    "format": image_format or None,
                    "mode": image.mode,
                    "width": image.width,
                    "height": image.height,
                    "is_animated": bool(getattr(image, "is_animated", False)),
                }
            )
            if image_format not in SUPPORTED_FORMATS:
                result.update({"status": "unsupported", "supported": False, "reason": "unsupported_format"})
                return result
            if result["is_animated"] or int(getattr(image, "n_frames", 1)) != 1:
                result.update({"status": "unsupported", "supported": False, "reason": "animated_not_supported"})
                return result
            result["categories"] = _inspect_supported_image(image)
            return result
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return _base_result("invalid", "unreadable_or_invalid_image")


__all__ = ["SCHEMA_VERSION", "SUPPORTED_FORMATS", "inspect_image_metadata"]
