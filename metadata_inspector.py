"""Read-only, value-safe metadata inspection for supported image inputs."""

from __future__ import annotations

import struct
from os import PathLike, fstat
from typing import Any

from PIL import ExifTags, Image, IptcImagePlugin, UnidentifiedImageError

from metadata_policy import (
    GENERATOR_EXIF_TAGS,
    XmpPolicyError,
    classify_generator_field_names,
    classify_generator_xmp,
    parse_xmp_root,
)


SCHEMA_VERSION = 2
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
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8"
_C2PA_UUID = bytes.fromhex("6332706100110010800000aa00389b71")
_MAX_CONTAINER_ENTRIES = 100_000
_MAX_JPEG_FILL_BYTES = 1_024
_MAX_C2PA_SEGMENTS = 1_024
_MAX_C2PA_DECLARED_BYTES = 64 * 1024 * 1024
_MAX_JPEG_PREFIX_BYTES = 96
_MAX_PNG_CHUNK_LENGTH = 0x7FFFFFFF


def _c2pa_summary(
    presence: str = "unknown",
    *,
    scan_status: str = "not_scanned",
    reason: str | None = None,
    item_count: int = 0,
    segment_count: int = 0,
    size_bytes: int = 0,
    containers: tuple[str, ...] = (),
) -> dict[str, Any]:
    return {
        "presence": presence,
        "validation": "not_validated",
        "scan_status": scan_status,
        "reason": reason,
        "item_count": max(0, int(item_count)),
        "segment_count": max(0, int(segment_count)),
        "size_bytes": max(0, int(size_bytes)),
        "containers": list(containers),
    }


def _c2pa_scan_result(
    found_count: int,
    segment_count: int,
    size_bytes: int,
    container: str,
    *,
    scan_status: str = "ok",
    reason: str | None = None,
) -> dict[str, Any]:
    presence = "present" if found_count else ("not_present" if scan_status == "ok" else "unknown")
    return _c2pa_summary(
        presence,
        scan_status=scan_status,
        reason=reason,
        item_count=found_count,
        segment_count=segment_count,
        size_bytes=size_bytes,
        containers=(container,) if found_count else (),
    )


def _scan_png_c2pa(stream: Any, file_size: int) -> dict[str, Any]:
    found_count = 0
    found_size = 0
    position = len(_PNG_SIGNATURE)
    entry_count = 0
    first_chunk = True

    while position < file_size:
        entry_count += 1
        if entry_count > _MAX_CONTAINER_ENTRIES:
            return _c2pa_scan_result(
                found_count,
                found_count,
                found_size,
                "png_cabx",
                scan_status="limit_exceeded",
                reason="too_many_png_chunks",
            )

        stream.seek(position)
        header = stream.read(8)
        if len(header) != 8:
            return _c2pa_scan_result(
                found_count,
                found_count,
                found_size,
                "png_cabx",
                scan_status="malformed",
                reason="truncated_png_chunk_header",
            )
        chunk_length, chunk_type = struct.unpack(">I4s", header)
        if chunk_length > _MAX_PNG_CHUNK_LENGTH:
            return _c2pa_scan_result(
                found_count,
                found_count,
                found_size,
                "png_cabx",
                scan_status="limit_exceeded",
                reason="png_chunk_length_exceeds_spec",
            )

        chunk_end = position + 12 + chunk_length
        if chunk_end > file_size:
            return _c2pa_scan_result(
                found_count,
                found_count,
                found_size,
                "png_cabx",
                scan_status="malformed",
                reason="truncated_png_chunk",
            )
        if first_chunk and (chunk_type != b"IHDR" or chunk_length != 13):
            return _c2pa_scan_result(
                found_count,
                found_count,
                found_size,
                "png_cabx",
                scan_status="malformed",
                reason="invalid_png_ihdr",
            )
        first_chunk = False

        if chunk_type == b"caBX":
            found_count += 1
            found_size += chunk_length
        if chunk_type == b"IEND":
            if chunk_length != 0:
                return _c2pa_scan_result(
                    found_count,
                    found_count,
                    found_size,
                    "png_cabx",
                    scan_status="malformed",
                    reason="invalid_png_iend",
                )
            return _c2pa_scan_result(found_count, found_count, found_size, "png_cabx")
        position = chunk_end

    return _c2pa_scan_result(
        found_count,
        found_count,
        found_size,
        "png_cabx",
        scan_status="malformed",
        reason="missing_png_iend",
    )


def _box_header(data: bytes, offset: int) -> tuple[int | None, bytes, int] | None:
    if offset < 0 or offset + 8 > len(data):
        return None
    size_32, box_type = struct.unpack_from(">I4s", data, offset)
    if size_32 == 1:
        if offset + 16 > len(data):
            return None
        size_64 = struct.unpack_from(">Q", data, offset + 8)[0]
        if size_64 < 16:
            return None
        return size_64, box_type, 16
    if size_32 == 0:
        return None, box_type, 8
    if size_32 < 8:
        return None
    return size_32, box_type, 8


def _jpeg_c2pa_start(
    data: bytes,
    payload_length: int,
) -> tuple[tuple[bytes, bytes, int, int] | None, str | None, bool]:
    if len(data) < 8 or data[:2] != b"JP" or struct.unpack_from(">I", data, 4)[0] != 1:
        return None, None, False

    outer = _box_header(data, 8)
    if outer is None:
        return None, None, False
    outer_size, outer_type, outer_header_size = outer
    if outer_type != b"jumb":
        return None, None, False

    description_offset = 8 + outer_header_size
    description = _box_header(data, description_offset)
    if description is None:
        return None, None, False
    description_size, description_type, description_header_size = description
    if description_type != b"jumd":
        return None, None, False

    uuid_offset = description_offset + description_header_size
    uuid_end = uuid_offset + len(_C2PA_UUID)
    if uuid_end > len(data) or data[uuid_offset:uuid_end] != _C2PA_UUID:
        return None, None, False

    label_end = uuid_end + 1 + len(b"c2pa\x00")
    if label_end > len(data):
        return None, "truncated_jumbf_description", True
    toggles = data[uuid_end]
    if toggles & 0x03 != 0x03:
        return None, "invalid_jumbf_toggles", True
    if data[uuid_end + 1 : label_end] != b"c2pa\x00":
        return None, "invalid_c2pa_jumbf_label", True

    required_outer_size = label_end - 8
    required_description_size = label_end - description_offset
    if outer_size is None:
        return None, "unbounded_c2pa_jumbf_box", True
    if outer_size < required_outer_size:
        return None, "invalid_c2pa_jumbf_length", True
    if description_size is None:
        return None, "unbounded_c2pa_description_box", True
    if description_size < required_description_size:
        return None, "invalid_c2pa_description_length", True
    if description_offset + description_size > 8 + outer_size:
        return None, "c2pa_description_exceeds_outer_box", True

    received_size = max(0, payload_length - 8)
    return (data[2:4], data[8:16], outer_size, received_size), None, True


def _jpeg_c2pa_continuation(data: bytes, instance: bytes, expected_sequence: int, box_header: bytes) -> bool:
    return (
        len(data) >= 16
        and data[:2] == b"JP"
        and data[2:4] == instance
        and struct.unpack_from(">I", data, 4)[0] == expected_sequence
        and data[8:16] == box_header
    )


def _jpeg_xt_identity(data: bytes) -> tuple[bytes, int] | None:
    if len(data) < 8 or data[:2] != b"JP":
        return None
    return data[2:4], struct.unpack_from(">I", data, 4)[0]


def _scan_jpeg_c2pa(stream: Any, file_size: int) -> dict[str, Any]:
    found_count = 0
    segment_count = 0
    found_size = 0
    marker_count = 0
    active_instance: bytes | None = None
    active_box_header = b""
    active_declared_size = 0
    active_received_size = 0
    expected_sequence = 0
    completed_instance: bytes | None = None

    def malformed(reason: str) -> dict[str, Any]:
        return _c2pa_scan_result(
            found_count,
            segment_count,
            found_size,
            "jpeg_app11_jumbf",
            scan_status="malformed",
            reason=reason,
        )

    stream.seek(len(_JPEG_SIGNATURE))
    while stream.tell() < file_size:
        marker_count += 1
        if marker_count > _MAX_CONTAINER_ENTRIES:
            return _c2pa_scan_result(
                found_count,
                segment_count,
                found_size,
                "jpeg_app11_jumbf",
                scan_status="limit_exceeded",
                reason="too_many_jpeg_markers",
            )

        marker_prefix = stream.read(1)
        if marker_prefix != b"\xff":
            return _c2pa_scan_result(
                found_count,
                segment_count,
                found_size,
                "jpeg_app11_jumbf",
                scan_status="malformed",
                reason="invalid_jpeg_marker_prefix",
            )
        fill_count = 0
        marker_value = stream.read(1)
        while marker_value == b"\xff":
            fill_count += 1
            if fill_count > _MAX_JPEG_FILL_BYTES:
                return _c2pa_scan_result(
                    found_count,
                    segment_count,
                    found_size,
                    "jpeg_app11_jumbf",
                    scan_status="limit_exceeded",
                    reason="too_many_jpeg_fill_bytes",
                )
            marker_value = stream.read(1)
        if len(marker_value) != 1 or marker_value == b"\x00":
            return _c2pa_scan_result(
                found_count,
                segment_count,
                found_size,
                "jpeg_app11_jumbf",
                scan_status="malformed",
                reason="truncated_or_invalid_jpeg_marker",
            )

        marker = marker_value[0]
        if marker == 0xD9:
            if active_instance is not None:
                return malformed("truncated_c2pa_jumbf")
            return _c2pa_scan_result(found_count, segment_count, found_size, "jpeg_app11_jumbf")
        if marker == 0xD8 or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            if active_instance is not None:
                return malformed("noncontiguous_c2pa_jumbf")
            completed_instance = None
            continue

        length_bytes = stream.read(2)
        if len(length_bytes) != 2:
            return _c2pa_scan_result(
                found_count,
                segment_count,
                found_size,
                "jpeg_app11_jumbf",
                scan_status="malformed",
                reason="truncated_jpeg_segment_length",
            )
        segment_length = struct.unpack(">H", length_bytes)[0]
        if segment_length < 2:
            return _c2pa_scan_result(
                found_count,
                segment_count,
                found_size,
                "jpeg_app11_jumbf",
                scan_status="malformed",
                reason="invalid_jpeg_segment_length",
            )
        payload_length = segment_length - 2
        payload_start = stream.tell()
        segment_end = payload_start + payload_length
        if segment_end > file_size:
            return _c2pa_scan_result(
                found_count,
                segment_count,
                found_size,
                "jpeg_app11_jumbf",
                scan_status="malformed",
                reason="truncated_jpeg_segment",
            )

        if marker == 0xEB:
            prefix = stream.read(min(payload_length, _MAX_JPEG_PREFIX_BYTES))
            if active_instance is not None:
                if not _jpeg_c2pa_continuation(
                    prefix,
                    active_instance,
                    expected_sequence,
                    active_box_header,
                ):
                    identity = _jpeg_xt_identity(prefix)
                    reason = (
                        "invalid_c2pa_jumbf_sequence"
                        if identity is not None and identity[0] == active_instance
                        else "noncontiguous_c2pa_jumbf"
                    )
                    return malformed(reason)

                continuation_size = payload_length - 16
                if continuation_size <= 0:
                    return malformed("empty_c2pa_jumbf_continuation")
                segment_count += 1
                found_size += continuation_size
                active_received_size += continuation_size
                if active_received_size > active_declared_size:
                    return malformed("c2pa_jumbf_length_overrun")
                if active_received_size == active_declared_size:
                    completed_instance = active_instance
                    active_instance = None
                    active_box_header = b""
                    active_declared_size = 0
                    active_received_size = 0
                    expected_sequence = 0
                else:
                    expected_sequence += 1
            else:
                identity = _jpeg_xt_identity(prefix)
                if (
                    completed_instance is not None
                    and identity is not None
                    and identity[0] == completed_instance
                    and identity[1] > 1
                ):
                    return malformed("unexpected_c2pa_jumbf_continuation")

                start, start_error, is_c2pa_candidate = _jpeg_c2pa_start(prefix, payload_length)
                completed_instance = None
                if is_c2pa_candidate:
                    found_count += 1
                    segment_count += 1
                if start_error is not None:
                    return malformed(start_error)
                if start is not None:
                    instance, box_header, declared_size, received_size = start
                    found_size += received_size
                    if declared_size > _MAX_C2PA_DECLARED_BYTES:
                        return _c2pa_scan_result(
                            found_count,
                            segment_count,
                            found_size,
                            "jpeg_app11_jumbf",
                            scan_status="limit_exceeded",
                            reason="c2pa_jpeg_data_exceeds_scan_limit",
                        )
                    if received_size > declared_size:
                        return malformed("c2pa_jumbf_length_overrun")
                    if received_size == declared_size:
                        completed_instance = instance
                    else:
                        active_instance = instance
                        active_box_header = box_header
                        active_declared_size = declared_size
                        active_received_size = received_size
                        expected_sequence = 2
            if segment_count > _MAX_C2PA_SEGMENTS or found_size > _MAX_C2PA_DECLARED_BYTES:
                return _c2pa_scan_result(
                    found_count,
                    segment_count,
                    found_size,
                    "jpeg_app11_jumbf",
                    scan_status="limit_exceeded",
                    reason="c2pa_jpeg_data_exceeds_scan_limit",
                )
        else:
            if active_instance is not None:
                return malformed("noncontiguous_c2pa_jumbf")
            completed_instance = None

        stream.seek(segment_end)
        if marker == 0xDA:
            return _c2pa_scan_result(found_count, segment_count, found_size, "jpeg_app11_jumbf")

    if active_instance is not None:
        return malformed("truncated_c2pa_jumbf")
    return _c2pa_scan_result(
        found_count,
        segment_count,
        found_size,
        "jpeg_app11_jumbf",
        scan_status="malformed",
        reason="missing_jpeg_scan_or_eoi",
    )


def inspect_c2pa_presence(path: str | PathLike[str]) -> dict[str, Any]:
    """Detect bounded embedded C2PA containers without validating or fetching them."""

    try:
        with open(path, "rb") as stream:
            file_size = fstat(stream.fileno()).st_size
            signature = stream.read(len(_PNG_SIGNATURE))
            if signature == _PNG_SIGNATURE:
                return _scan_png_c2pa(stream, file_size)
            if signature.startswith(_JPEG_SIGNATURE):
                return _scan_jpeg_c2pa(stream, file_size)
            return _c2pa_summary(scan_status="unsupported", reason="unsupported_container")
    except (OSError, OverflowError, ValueError):
        return _c2pa_summary(scan_status="unreadable", reason="unreadable_file")


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


def _known_generator_fields(names: list[str], payloads: list[bytes] | None = None) -> tuple[str, ...]:
    matches = set(classify_generator_field_names(names))
    for payload in payloads or ():
        try:
            matches.update(classify_generator_xmp(parse_xmp_root(payload)))
        except XmpPolicyError:
            continue
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
        "c2pa": _c2pa_summary(),
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

    exif_names = [str(ExifTags.TAGS.get(tag, tag)) for tag in exif if tag in GENERATOR_EXIF_TAGS]
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
            result["c2pa"] = inspect_c2pa_presence(path)
            return result
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError):
        return _base_result("invalid", "unreadable_or_invalid_image")


__all__ = ["SCHEMA_VERSION", "SUPPORTED_FORMATS", "inspect_c2pa_presence", "inspect_image_metadata"]
