"""Selective, pixel-preserving metadata cleanup for new PNG exports."""

from __future__ import annotations

import hashlib
import math
import os
import struct
import tempfile
from dataclasses import dataclass, fields
from os import PathLike
from pathlib import Path
from typing import Any
from xml.dom import minidom
from xml.parsers.expat import ExpatError

from PIL import Image, IptcImagePlugin, PngImagePlugin, UnidentifiedImageError

from metadata_inspector import inspect_image_metadata
from metadata_policy import (
    C2PA_XMP_REFERENCE_PROPERTIES,
    GENERATOR_EXIF_TAGS,
    GENERATOR_XMP_PROPERTIES,
    XmpPolicyError,
    is_generator_text_field,
    parse_xmp_root,
    xmp_text_for_png,
)


_XMP_TEXT_KEYS = frozenset({"xml:com.adobe.xmp", "xmp"})
_SUPPORTED_PIXEL_MODES = frozenset({"1", "L", "LA", "P", "RGB", "RGBA", "I;16"})
_MAX_SOURCE_BYTES = 512 * 1024 * 1024
_MAX_SOURCE_PIXELS = 70_000_000
_MAX_SOURCE_DIMENSION = 32_768
_FINGERPRINT_STRIPE_BYTES = 4 * 1024 * 1024
_MAX_PNG_METADATA_BYTES = 64 * 1024 * 1024
_MAX_PNG_METADATA_CHUNK_BYTES = 16 * 1024 * 1024
_MAX_PNG_CHUNKS = 100_000
_MAX_JPEG_METADATA_BYTES = 64 * 1024 * 1024
_MAX_JPEG_SEGMENTS = 100_000
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8"
_PNG_METADATA_CHUNKS = frozenset({b"eXIf", b"iCCP", b"tEXt", b"zTXt", b"iTXt"})
_PNG_TEXT_CHUNKS = frozenset({b"tEXt", b"zTXt", b"iTXt"})
_MAX_EXIF_IFDS = 64
_MAX_EXIF_ENTRIES = 4_096

_TextEntry = tuple[str, str, str, str]
_XmpEntry = tuple[str, bytes, str, str]

_TIFF_TYPE_SIZES = {
    1: 1,
    2: 1,
    3: 2,
    4: 4,
    5: 8,
    6: 1,
    7: 1,
    8: 2,
    9: 4,
    10: 8,
    11: 4,
    12: 8,
    13: 4,
}
_EXIF_PADDING_TAG = 0xEA1C


class MetadataCleanupError(RuntimeError):
    """Raised when a metadata-only export cannot be completed safely."""


@dataclass(frozen=True)
class MetadataCleanupOptions:
    remove_exif: bool = False
    remove_xmp: bool = False
    remove_iptc: bool = False
    remove_comments_text: bool = False
    remove_embedded_thumbnail: bool = False
    remove_generator_fields: bool = False
    preserve_icc: bool = True
    preserve_dpi: bool = True
    remove_embedded_c2pa: bool = False


def _validate_options(options: MetadataCleanupOptions) -> None:
    if not isinstance(options, MetadataCleanupOptions):
        raise TypeError("options must be MetadataCleanupOptions")
    for field in fields(options):
        if not isinstance(getattr(options, field.name), bool):
            raise TypeError(f"{field.name} must be bool")


def _preflight_source(path: Path) -> int:
    try:
        file_size = path.stat().st_size
    except OSError as error:
        raise MetadataCleanupError("metadata cleanup source is unreadable") from error
    if file_size > _MAX_SOURCE_BYTES:
        raise MetadataCleanupError("source file exceeds the metadata cleanup size limit")

    try:
        with path.open("rb") as stream:
            signature = stream.read(len(_PNG_SIGNATURE))
            if signature.startswith(_JPEG_SIGNATURE):
                stream.seek(len(_JPEG_SIGNATURE))
                metadata_bytes = 0
                comment_count = 0
                for _ in range(_MAX_JPEG_SEGMENTS):
                    prefix = stream.read(1)
                    if not prefix:
                        raise MetadataCleanupError("JPEG marker stream is truncated")
                    if prefix != b"\xff":
                        raise MetadataCleanupError("JPEG marker stream is malformed")
                    marker = stream.read(1)
                    while marker == b"\xff":
                        marker = stream.read(1)
                    if not marker:
                        raise MetadataCleanupError("JPEG marker stream is truncated")
                    marker_value = marker[0]
                    if marker_value in {0xD9, 0xDA}:
                        return comment_count
                    if marker_value == 0x01 or 0xD0 <= marker_value <= 0xD7:
                        continue
                    raw_length = stream.read(2)
                    if len(raw_length) != 2:
                        raise MetadataCleanupError("JPEG segment length is truncated")
                    segment_length = struct.unpack(">H", raw_length)[0]
                    if segment_length < 2 or stream.tell() + segment_length - 2 > file_size:
                        raise MetadataCleanupError("JPEG segment exceeds the source file")
                    payload_length = segment_length - 2
                    if 0xE0 <= marker_value <= 0xEF or marker_value == 0xFE:
                        metadata_bytes += payload_length
                        if metadata_bytes > _MAX_JPEG_METADATA_BYTES:
                            raise MetadataCleanupError("JPEG metadata exceeds the cleanup limit")
                    if marker_value == 0xFE:
                        comment_count += 1
                    stream.seek(payload_length, os.SEEK_CUR)
                raise MetadataCleanupError("JPEG contains too many metadata segments")
            if signature != _PNG_SIGNATURE:
                return 0
            metadata_bytes = 0
            text_keys: set[bytes] = set()
            for _ in range(_MAX_PNG_CHUNKS):
                header = stream.read(8)
                if len(header) != 8:
                    raise MetadataCleanupError("PNG chunk header is truncated")
                length, chunk_type = struct.unpack(">I4s", header)
                payload_end = stream.tell() + length
                if payload_end + 4 > file_size:
                    raise MetadataCleanupError("PNG chunk exceeds the source file")
                if chunk_type in _PNG_METADATA_CHUNKS:
                    metadata_bytes += length
                    if length > _MAX_PNG_METADATA_CHUNK_BYTES or metadata_bytes > _MAX_PNG_METADATA_BYTES:
                        raise MetadataCleanupError("PNG metadata exceeds the cleanup limit")
                if chunk_type in _PNG_TEXT_CHUNKS:
                    payload = stream.read(length)
                    keyword, separator, _ = payload.partition(b"\x00")
                    if not separator or not keyword:
                        raise MetadataCleanupError("PNG text metadata is malformed")
                    normalized_keyword = keyword.lower()
                    if normalized_keyword in text_keys:
                        raise MetadataCleanupError("duplicate PNG text keys cannot be preserved safely")
                    text_keys.add(normalized_keyword)
                else:
                    stream.seek(length, os.SEEK_CUR)
                if len(stream.read(4)) != 4:
                    raise MetadataCleanupError("PNG chunk checksum is truncated")
                if chunk_type == b"IEND":
                    return 0
            raise MetadataCleanupError("PNG contains too many chunks")
    except MetadataCleanupError:
        raise
    except (OSError, struct.error) as error:
        raise MetadataCleanupError("metadata cleanup source preflight failed") from error


def _is_generator_text_key(key: str) -> bool:
    return is_generator_text_field(key)


def _safe_xmp_text(payload: bytes) -> str:
    try:
        return xmp_text_for_png(payload)
    except XmpPolicyError as error:
        raise MetadataCleanupError(str(error)) from error


def _dom_property_name(node: Any) -> str:
    namespace = getattr(node, "namespaceURI", None)
    local_name = getattr(node, "localName", None)
    if namespace and local_name:
        return f"{{{namespace}}}{local_name}"
    return str(getattr(node, "nodeName", ""))


def _filter_xmp_properties(payload: bytes, properties: frozenset[str]) -> tuple[bytes, int]:
    text = xmp_text_for_png(payload)
    try:
        document = minidom.parseString(text.encode("utf-8"))
    except (ExpatError, TypeError, ValueError) as error:
        raise XmpPolicyError("XMP payload is malformed") from error
    removed = 0
    try:
        elements = list(document.getElementsByTagName("*"))
        for element in elements:
            attributes = [element.attributes.item(index) for index in range(element.attributes.length)]
            for attribute in attributes:
                if attribute is not None and _dom_property_name(attribute) in properties:
                    element.removeAttributeNode(attribute)
                    removed += 1
        for element in elements:
            if _dom_property_name(element) not in properties:
                continue
            if element.parentNode is document:
                raise XmpPolicyError("XMP root property cannot be removed safely")
            element.parentNode.removeChild(element)
            removed += 1
        if not removed:
            return payload, 0
        return document.toxml(encoding="utf-8"), removed
    finally:
        document.unlink()


def _filter_xmp_generator_fields(payload: bytes) -> tuple[bytes, int]:
    try:
        return _filter_xmp_properties(payload, frozenset(GENERATOR_XMP_PROPERTIES))
    except XmpPolicyError as error:
        raise MetadataCleanupError(str(error)) from error


def _filter_xmp_c2pa_references(payload: bytes) -> tuple[bytes, int]:
    try:
        return _filter_xmp_properties(payload, C2PA_XMP_REFERENCE_PROPERTIES)
    except XmpPolicyError as error:
        raise MetadataCleanupError(str(error)) from error


def _xmp_generator_field_count(payload: bytes) -> int:
    _, removed = _filter_xmp_generator_fields(payload)
    return removed


def _tiff_layout(exif_bytes: bytes) -> tuple[bytearray, int, str, int]:
    output = bytearray(exif_bytes)
    tiff_start = 6 if output.startswith(b"Exif\x00\x00") else 0
    if len(output) - tiff_start < 8:
        raise MetadataCleanupError("EXIF payload is malformed")
    byte_order_marker = bytes(output[tiff_start : tiff_start + 2])
    if byte_order_marker == b"II":
        byte_order = "<"
    elif byte_order_marker == b"MM":
        byte_order = ">"
    else:
        raise MetadataCleanupError("EXIF byte order is invalid")
    try:
        if struct.unpack_from(f"{byte_order}H", output, tiff_start + 2)[0] != 42:
            raise MetadataCleanupError("EXIF TIFF marker is invalid")
        ifd0_offset = struct.unpack_from(f"{byte_order}I", output, tiff_start + 4)[0]
    except struct.error as error:
        raise MetadataCleanupError("EXIF header is truncated") from error
    return output, tiff_start, byte_order, ifd0_offset


def _ifd_bounds(data: bytearray, tiff_start: int, byte_order: str, ifd_offset: int) -> tuple[int, int, int]:
    relative_size = len(data) - tiff_start
    if ifd_offset < 8 or ifd_offset + 2 > relative_size:
        raise MetadataCleanupError("EXIF IFD offset is out of bounds")
    try:
        entry_count = struct.unpack_from(f"{byte_order}H", data, tiff_start + ifd_offset)[0]
    except struct.error as error:
        raise MetadataCleanupError("EXIF IFD is truncated") from error
    entries_start = ifd_offset + 2
    entries_end = entries_start + (entry_count * 12)
    next_pointer = entries_end
    if entries_end + 4 > relative_size:
        raise MetadataCleanupError("EXIF IFD entries are out of bounds")
    return entry_count, entries_start, next_pointer


@dataclass(frozen=True)
class _ExifFieldRange:
    entry_offset: int
    tag: int
    payload_start: int | None
    payload_end: int | None


def _entry_layout(
    data: bytearray,
    tiff_start: int,
    byte_order: str,
    entry_offset: int,
) -> tuple[int, int, int, int | None, int | None]:
    absolute = tiff_start + entry_offset
    try:
        tag, value_type = struct.unpack_from(f"{byte_order}HH", data, absolute)
        count = struct.unpack_from(f"{byte_order}I", data, absolute + 4)[0]
    except struct.error as error:
        raise MetadataCleanupError("EXIF field is truncated") from error
    type_size = _TIFF_TYPE_SIZES.get(value_type)
    if type_size is None:
        raise MetadataCleanupError("EXIF field uses an unsupported TIFF type")
    payload_size = type_size * count
    if payload_size > len(data) - tiff_start:
        raise MetadataCleanupError("EXIF field size is out of bounds")
    if payload_size <= 4:
        return tag, value_type, count, None, None
    payload_start = struct.unpack_from(f"{byte_order}I", data, absolute + 8)[0]
    payload_end = payload_start + payload_size
    if payload_start < 8 or payload_end > len(data) - tiff_start:
        raise MetadataCleanupError("EXIF field payload is out of bounds")
    return tag, value_type, count, payload_start, payload_end


def _entry_ifd_pointers(
    data: bytearray,
    tiff_start: int,
    byte_order: str,
    entry_offset: int,
    value_type: int,
    count: int,
    payload_start: int | None,
) -> tuple[int, ...]:
    if value_type not in (4, 13) or count <= 0:
        return ()
    if count > _MAX_EXIF_IFDS:
        raise MetadataCleanupError("EXIF contains too many linked IFDs")
    values_start = tiff_start + (entry_offset + 8 if payload_start is None else payload_start)
    try:
        return tuple(struct.unpack_from(f"{byte_order}I", data, values_start + index * 4)[0] for index in range(count))
    except struct.error as error:
        raise MetadataCleanupError("EXIF IFD pointer is truncated") from error


def _collect_exif_ranges(
    data: bytearray,
    tiff_start: int,
    byte_order: str,
    ifd0_offset: int,
) -> tuple[list[tuple[int, int]], list[_ExifFieldRange]]:
    pending = [ifd0_offset]
    seen: set[int] = set()
    directories: list[tuple[int, int]] = [(0, 8)]
    fields_found: list[_ExifFieldRange] = []
    total_entries = 0
    pointer_tags = {0x014A, 0x8769, 0x8825, 0xA005}

    while pending:
        if len(seen) >= _MAX_EXIF_IFDS:
            raise MetadataCleanupError("EXIF contains too many linked IFDs")
        ifd_offset = pending.pop()
        if not ifd_offset:
            continue
        if ifd_offset in seen:
            raise MetadataCleanupError("EXIF contains an IFD cycle")
        seen.add(ifd_offset)
        entry_count, entries_start, next_pointer = _ifd_bounds(data, tiff_start, byte_order, ifd_offset)
        total_entries += entry_count
        if total_entries > _MAX_EXIF_ENTRIES:
            raise MetadataCleanupError("EXIF contains too many fields")
        directories.append((ifd_offset, next_pointer + 4))
        for index in range(entry_count):
            entry_offset = entries_start + index * 12
            tag, value_type, count, payload_start, payload_end = _entry_layout(
                data,
                tiff_start,
                byte_order,
                entry_offset,
            )
            fields_found.append(_ExifFieldRange(entry_offset, tag, payload_start, payload_end))
            if tag in pointer_tags:
                pending.extend(
                    _entry_ifd_pointers(
                        data,
                        tiff_start,
                        byte_order,
                        entry_offset,
                        value_type,
                        count,
                        payload_start,
                    )
                )
        next_ifd = struct.unpack_from(f"{byte_order}I", data, tiff_start + next_pointer)[0]
        if next_ifd:
            pending.append(next_ifd)
    return directories, fields_found


def _ranges_overlap(left: tuple[int, int], right: tuple[int, int]) -> bool:
    return left[0] < right[1] and right[0] < left[1]


def _assert_range_isolated(
    target: tuple[int, int],
    directories: list[tuple[int, int]],
    fields_found: list[_ExifFieldRange],
    *,
    target_entry_offset: int | None = None,
) -> None:
    if any(_ranges_overlap(target, directory) for directory in directories):
        raise MetadataCleanupError("EXIF removable payload overlaps an IFD directory")
    for field in fields_found:
        if field.payload_start is None or field.entry_offset == target_entry_offset:
            continue
        if _ranges_overlap(target, (field.payload_start, field.payload_end or field.payload_start)):
            raise MetadataCleanupError("EXIF removable payload overlaps preserved metadata")


def _entry_scalar(data: bytearray, tiff_start: int, byte_order: str, entry_offset: int) -> int | None:
    absolute = tiff_start + entry_offset
    value_type = struct.unpack_from(f"{byte_order}H", data, absolute + 2)[0]
    count = struct.unpack_from(f"{byte_order}I", data, absolute + 4)[0]
    if count != 1:
        return None
    if value_type == 3:
        return struct.unpack_from(f"{byte_order}H", data, absolute + 8)[0]
    if value_type in (4, 13):
        return struct.unpack_from(f"{byte_order}I", data, absolute + 8)[0]
    return None


def _zero_entry_payload(data: bytearray, tiff_start: int, byte_order: str, entry_offset: int) -> None:
    absolute = tiff_start + entry_offset
    value_type = struct.unpack_from(f"{byte_order}H", data, absolute + 2)[0]
    count = struct.unpack_from(f"{byte_order}I", data, absolute + 4)[0]
    type_size = _TIFF_TYPE_SIZES.get(value_type)
    if type_size is None:
        raise MetadataCleanupError("EXIF field uses an unsupported TIFF type")
    payload_size = type_size * count
    if payload_size > len(data) - tiff_start:
        raise MetadataCleanupError("EXIF field size is out of bounds")
    if payload_size > 4:
        payload_offset = struct.unpack_from(f"{byte_order}I", data, absolute + 8)[0]
        payload_end = payload_offset + payload_size
        if payload_offset < 8 or payload_end > len(data) - tiff_start:
            raise MetadataCleanupError("EXIF field payload is out of bounds")
        data[tiff_start + payload_offset : tiff_start + payload_end] = b"\x00" * payload_size
    struct.pack_into(f"{byte_order}HHI", data, absolute, _EXIF_PADDING_TAG, 7, 0)
    data[absolute + 8 : absolute + 12] = b"\x00" * 4


def _thumbnail_layout(
    data: bytearray,
    tiff_start: int,
    byte_order: str,
    next_pointer: int,
) -> tuple[list[int], tuple[int, int] | None]:
    ifd1_offset = struct.unpack_from(f"{byte_order}I", data, tiff_start + next_pointer)[0]
    if not ifd1_offset:
        return [], None
    ifd1_count, ifd1_entries_start, _ = _ifd_bounds(data, tiff_start, byte_order, ifd1_offset)
    thumbnail_entries: list[int] = []
    thumbnail_offset: int | None = None
    thumbnail_length: int | None = None
    for index in range(ifd1_count):
        entry_offset = ifd1_entries_start + index * 12
        tag = struct.unpack_from(f"{byte_order}H", data, tiff_start + entry_offset)[0]
        if tag == 0x0201:
            thumbnail_entries.append(entry_offset)
            thumbnail_offset = _entry_scalar(data, tiff_start, byte_order, entry_offset)
        elif tag == 0x0202:
            thumbnail_entries.append(entry_offset)
            thumbnail_length = _entry_scalar(data, tiff_start, byte_order, entry_offset)
    if thumbnail_offset is None or thumbnail_length is None or thumbnail_length <= 0:
        return thumbnail_entries, None
    thumbnail_end = thumbnail_offset + thumbnail_length
    if thumbnail_offset < 8 or thumbnail_end > len(data) - tiff_start:
        raise MetadataCleanupError("EXIF thumbnail is out of bounds")
    return thumbnail_entries, (thumbnail_offset, thumbnail_end)


def _sanitize_exif(
    exif_bytes: bytes,
    *,
    remove_generator_fields: bool,
    remove_thumbnail: bool,
) -> bytes:
    data, tiff_start, byte_order, ifd0_offset = _tiff_layout(exif_bytes)
    entry_count, entries_start, next_pointer = _ifd_bounds(data, tiff_start, byte_order, ifd0_offset)
    directories, fields_found = _collect_exif_ranges(data, tiff_start, byte_order, ifd0_offset)
    thumbnail_entries, thumbnail_range = _thumbnail_layout(data, tiff_start, byte_order, next_pointer)

    if remove_generator_fields:
        for index in range(entry_count):
            entry_offset = entries_start + (index * 12)
            tag = struct.unpack_from(f"{byte_order}H", data, tiff_start + entry_offset)[0]
            if tag in GENERATOR_EXIF_TAGS:
                field = next(item for item in fields_found if item.entry_offset == entry_offset)
                if field.payload_start is not None:
                    field_range = (field.payload_start, field.payload_end or field.payload_start)
                    if thumbnail_range is not None and _ranges_overlap(field_range, thumbnail_range):
                        raise MetadataCleanupError("EXIF generator payload overlaps the embedded thumbnail")
                    _assert_range_isolated(
                        field_range,
                        directories,
                        fields_found,
                        target_entry_offset=entry_offset,
                    )
                _zero_entry_payload(data, tiff_start, byte_order, entry_offset)

    if remove_thumbnail:
        if thumbnail_range is not None:
            _assert_range_isolated(thumbnail_range, directories, fields_found)
            start, end = thumbnail_range
            data[tiff_start + start : tiff_start + end] = b"\x00" * (end - start)
        for entry_offset in thumbnail_entries:
            struct.pack_into(f"{byte_order}HHI", data, tiff_start + entry_offset, _EXIF_PADDING_TAG, 7, 0)
            data[tiff_start + entry_offset + 8 : tiff_start + entry_offset + 12] = b"\x00" * 4

    return bytes(data)


def _hash_pixel_stripes(digest: Any, image: Image.Image, *, rgba: bool) -> None:
    source_bytes_per_pixel = 2 if image.mode == "I;16" else max(1, len(image.getbands()))
    bytes_per_pixel = 4 if rgba else source_bytes_per_pixel
    stripe_height = max(1, _FINGERPRINT_STRIPE_BYTES // max(1, image.width * bytes_per_pixel))
    for top in range(0, image.height, stripe_height):
        stripe = image.crop((0, top, image.width, min(image.height, top + stripe_height)))
        try:
            if rgba:
                rendered = stripe.convert("RGBA")
                try:
                    digest.update(rendered.tobytes())
                finally:
                    rendered.close()
            else:
                digest.update(stripe.tobytes())
        finally:
            stripe.close()


def _pixel_fingerprint(image: Image.Image) -> str:
    digest = hashlib.sha256()
    digest.update(image.mode.encode("ascii", errors="strict"))
    digest.update(struct.pack(">II", image.width, image.height))
    _hash_pixel_stripes(digest, image, rgba=False)
    _hash_pixel_stripes(digest, image, rgba=True)
    if image.mode == "P" and image.palette is not None:
        digest.update(image.palette.tobytes())
    transparency = image.info.get("transparency")
    if isinstance(transparency, bytes):
        digest.update(transparency)
    elif isinstance(transparency, int):
        digest.update(struct.pack(">I", transparency))
    elif isinstance(transparency, tuple) and all(isinstance(item, int) for item in transparency):
        digest.update(repr(transparency).encode("ascii"))
    return digest.hexdigest()


def _valid_dpi(value: Any) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        return None
    try:
        dpi = (float(value[0]), float(value[1]))
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(item) and item > 0 for item in dpi):
        return None
    return dpi


def _text_attributes(value: object) -> tuple[str, str]:
    language = getattr(value, "lang", "")
    translated_key = getattr(value, "tkey", "")
    return str(language or ""), str(translated_key or "")


def _collect_xmp_payloads(image: Image.Image, png_text: dict[str, str]) -> list[_XmpEntry]:
    payloads: list[_XmpEntry] = []
    for key, value in png_text.items():
        if key.casefold() in _XMP_TEXT_KEYS:
            language, translated_key = _text_attributes(value)
            payloads.append((key, str(value).encode("utf-8"), language, translated_key))
    raw_xmp = image.info.get("xmp")
    if isinstance(raw_xmp, str):
        raw_xmp = raw_xmp.encode("utf-8")
    if isinstance(raw_xmp, bytes) and not any(payload == raw_xmp for _, payload, _, _ in payloads):
        payloads.append(("XML:com.adobe.xmp", raw_xmp, "", ""))
    return payloads


def _collect_ordinary_text(image: Image.Image, png_text: dict[str, str]) -> list[_TextEntry]:
    entries = []
    for key, value in png_text.items():
        if key.casefold() not in _XMP_TEXT_KEYS:
            language, translated_key = _text_attributes(value)
            entries.append((key, str(value), language, translated_key))
    raw_comment = image.info.get("comment") if image.format == "JPEG" else None
    if isinstance(raw_comment, bytes):
        entries.append(("Comment", raw_comment.decode("latin-1"), "", ""))
    elif isinstance(raw_comment, str) and raw_comment:
        entries.append(("Comment", raw_comment, "", ""))
    return entries


def _exact_generator_count(
    raw_exif: bytes,
    text_entries: list[_TextEntry],
    xmp_payloads: list[_XmpEntry],
    *,
    strict_exif: bool,
    strict_xmp: bool,
) -> int:
    count = sum(1 for key, _, _, _ in text_entries if _is_generator_text_key(key))
    if raw_exif:
        exif = Image.Exif()
        try:
            exif.load(raw_exif)
            count += sum(1 for tag in GENERATOR_EXIF_TAGS if tag in exif)
        except (OSError, SyntaxError, ValueError):
            if strict_exif:
                raise MetadataCleanupError("EXIF payload is malformed")
    for _, payload, _, _ in xmp_payloads:
        try:
            count += _xmp_generator_field_count(payload)
        except MetadataCleanupError:
            if strict_xmp:
                raise
    return count


def _metadata_entries_digest(entries: list[_TextEntry]) -> str:
    digest = hashlib.sha256()
    for entry in sorted(entries):
        for value in entry:
            encoded = value.encode("utf-8")
            digest.update(struct.pack(">I", len(encoded)))
            digest.update(encoded)
    return digest.hexdigest()


def _category_action(before_present: bool, after_present: bool, selected: bool) -> str:
    if not before_present:
        return "absent"
    if selected:
        return "removed" if not after_present else "not_removed"
    return "preserved" if after_present else "not_preserved"


def _validate_cleanup_output(
    path: Path,
    *,
    source_mode: str,
    source_size: tuple[int, int],
    source_fingerprint: str,
    source_icc: bytes,
    source_dpi: tuple[float, float] | None,
    options: MetadataCleanupOptions,
    expected_categories: dict[str, bool],
    expected_exif: bytes,
    expected_text_digest: str,
    expected_xmp_digest: str,
) -> tuple[dict[str, Any], int]:
    generator_after = 0
    try:
        with Image.open(path) as output:
            output.load()
            if output.format != "PNG" or output.mode != source_mode or output.size != source_size:
                raise MetadataCleanupError("cleanup output changed the image layout")
            if _pixel_fingerprint(output) != source_fingerprint:
                raise MetadataCleanupError("cleanup output changed pixels or alpha")
            output_icc = output.info.get("icc_profile")
            if options.preserve_icc and source_icc and output_icc != source_icc:
                raise MetadataCleanupError("cleanup output did not preserve the ICC profile")
            if not options.preserve_icc and output_icc:
                raise MetadataCleanupError("cleanup output retained the ICC profile")
            output_dpi = _valid_dpi(output.info.get("dpi"))
            if options.preserve_dpi and source_dpi:
                if output_dpi is None or any(abs(left - right) > 0.05 for left, right in zip(output_dpi, source_dpi)):
                    raise MetadataCleanupError("cleanup output did not preserve DPI")
            if not options.preserve_dpi and output_dpi is not None:
                raise MetadataCleanupError("cleanup output retained DPI")
            checked_png_text = dict(getattr(output, "text", {}) or {})
            checked_exif = output.info.get("exif")
            if not isinstance(checked_exif, bytes):
                checked_exif = b""
            if checked_exif != expected_exif:
                raise MetadataCleanupError("cleanup output changed preserved EXIF metadata")
            checked_ordinary = _collect_ordinary_text(output, checked_png_text)
            if _metadata_entries_digest(checked_ordinary) != expected_text_digest:
                raise MetadataCleanupError("cleanup output changed preserved text metadata")
            checked_xmp = _collect_xmp_payloads(output, checked_png_text)
            checked_xmp_text = [
                (key, _safe_xmp_text(payload), language, translated_key)
                for key, payload, language, translated_key in checked_xmp
            ]
            if _metadata_entries_digest(checked_xmp_text) != expected_xmp_digest:
                raise MetadataCleanupError("cleanup output changed preserved XMP metadata")
            generator_after = _exact_generator_count(
                checked_exif,
                checked_ordinary,
                checked_xmp,
                strict_exif=options.remove_generator_fields,
                strict_xmp=options.remove_generator_fields,
            )
            if options.remove_generator_fields and generator_after:
                raise MetadataCleanupError("cleanup output retained allowlisted generator metadata")
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise MetadataCleanupError("cleanup output is not a valid PNG") from error

    after = inspect_image_metadata(path)
    if after["status"] != "ok" or after["format"] != "PNG":
        raise MetadataCleanupError("cleanup output failed metadata inspection")
    after_c2pa = after["c2pa"]
    if (
        after_c2pa["embedded_presence"] != "not_present"
        or after_c2pa["embedded_reference_presence"] != "not_present"
        or after_c2pa["external_reference_presence"] != "not_present"
        or after_c2pa["unclassified_reference_presence"] != "not_present"
    ):
        raise MetadataCleanupError("cleanup output retained a C2PA file structure or reference")
    after_categories = after["categories"]
    for category, expected in expected_categories.items():
        if bool(after_categories[category]["present"]) != expected:
            raise MetadataCleanupError(f"cleanup output has an unexpected {category} metadata state")
    return after, generator_after


def cleanup_image_metadata(
    source_path: str | PathLike[str],
    output_path: str | PathLike[str],
    options: MetadataCleanupOptions | None = None,
) -> dict[str, Any]:
    """Write a validated, atomic PNG export with selected metadata removed."""

    cleanup_options = options or MetadataCleanupOptions()
    _validate_options(cleanup_options)
    source = Path(source_path)
    destination = Path(output_path)
    if destination.suffix.casefold() != ".png":
        raise MetadataCleanupError("metadata cleanup output must use a .png extension")
    try:
        source_resolved = source.resolve(strict=True)
        destination_resolved = destination.resolve(strict=False)
    except OSError as error:
        raise MetadataCleanupError("metadata cleanup path is invalid") from error
    if os.path.normcase(str(source_resolved)) == os.path.normcase(str(destination_resolved)):
        raise MetadataCleanupError("metadata cleanup never overwrites the source file")

    jpeg_comment_count = _preflight_source(source_resolved)
    if jpeg_comment_count > 1 and not cleanup_options.remove_comments_text:
        raise MetadataCleanupError("multiple JPEG comments cannot be preserved safely in one PNG export")
    before = inspect_image_metadata(source_resolved)
    if before["status"] != "ok":
        raise MetadataCleanupError("source must be a supported single-frame PNG or JPEG")
    before_c2pa = before["c2pa"]
    if not cleanup_options.remove_embedded_c2pa and before_c2pa["presence"] != "not_present":
        raise MetadataCleanupError("C2PA input requires explicit C2PA cleanup")
    if cleanup_options.remove_embedded_c2pa:
        if before_c2pa["scan_status"] != "ok" or before_c2pa["embedded_presence"] == "unknown":
            raise MetadataCleanupError("embedded C2PA structure cannot be classified safely")
        if (
            "unknown"
            in {
                before_c2pa["embedded_reference_presence"],
                before_c2pa["external_reference_presence"],
            }
            or before_c2pa["unclassified_reference_presence"] != "not_present"
        ) and not cleanup_options.remove_xmp:
            raise MetadataCleanupError("C2PA XMP references cannot be classified safely")

    try:
        with Image.open(source_resolved) as source_image:
            if max(source_image.width, source_image.height) > _MAX_SOURCE_DIMENSION:
                raise MetadataCleanupError("source image exceeds the metadata cleanup dimension limit")
            if source_image.width * source_image.height > _MAX_SOURCE_PIXELS:
                raise MetadataCleanupError("source image exceeds the metadata cleanup pixel limit")
            source_image.load()
            if source_image.mode not in _SUPPORTED_PIXEL_MODES:
                raise MetadataCleanupError(f"source mode {source_image.mode} cannot be exported without pixel changes")
            source_mode = source_image.mode
            source_size = source_image.size
            source_fingerprint = _pixel_fingerprint(source_image)
            source_info = dict(source_image.info)
            source_icc = source_info.get("icc_profile")
            if not isinstance(source_icc, bytes):
                source_icc = b""
            source_dpi = _valid_dpi(source_info.get("dpi"))
            raw_exif = source_info.get("exif")
            if not isinstance(raw_exif, bytes):
                exif = source_image.getexif()
                raw_exif = exif.tobytes() if exif else b""
            png_text = dict(getattr(source_image, "text", {}) or {}) if source_image.format == "PNG" else {}
            xmp_payloads = _collect_xmp_payloads(source_image, png_text)
            ordinary_text = _collect_ordinary_text(source_image, png_text)
            try:
                iptc = IptcImagePlugin.getiptcinfo(source_image) or {}
            except (OSError, SyntaxError, ValueError):
                iptc = {}
            pixel_image = source_image.copy()
            transparency = source_info.get("transparency")
            pixel_image.info.clear()
    except MetadataCleanupError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, SyntaxError, ValueError) as error:
        raise MetadataCleanupError("source image could not be decoded safely") from error

    generator_before = _exact_generator_count(
        raw_exif,
        ordinary_text,
        xmp_payloads,
        strict_exif=cleanup_options.remove_generator_fields,
        strict_xmp=cleanup_options.remove_generator_fields,
    )
    output_exif = b""
    if raw_exif and not cleanup_options.remove_exif:
        if cleanup_options.remove_generator_fields or cleanup_options.remove_embedded_thumbnail:
            output_exif = _sanitize_exif(
                raw_exif,
                remove_generator_fields=cleanup_options.remove_generator_fields,
                remove_thumbnail=(
                    cleanup_options.remove_embedded_thumbnail
                    and before["categories"]["embedded_thumbnail"]["present"]
                ),
            )
        else:
            output_exif = raw_exif

    output_ordinary_text: list[_TextEntry] = []
    if not cleanup_options.remove_comments_text:
        output_ordinary_text = [
            (key, value, language, translated_key)
            for key, value, language, translated_key in ordinary_text
            if not (cleanup_options.remove_generator_fields and _is_generator_text_key(key))
        ]
    output_xmp_payloads: list[_XmpEntry] = []
    if not cleanup_options.remove_xmp:
        for key, payload, language, translated_key in xmp_payloads:
            if cleanup_options.remove_generator_fields:
                payload, _ = _filter_xmp_generator_fields(payload)
            if cleanup_options.remove_embedded_c2pa:
                payload, _ = _filter_xmp_c2pa_references(payload)
            output_xmp_payloads.append((key, payload, language, translated_key))

    output_xmp_text: list[_TextEntry] = [
        (key, _safe_xmp_text(payload), language, translated_key)
        for key, payload, language, translated_key in output_xmp_payloads
    ]

    pnginfo = PngImagePlugin.PngInfo()
    for key, value, language, translated_key in output_ordinary_text:
        pnginfo.add_itxt(key, value, language, translated_key)
    for key, value, language, translated_key in output_xmp_text:
        pnginfo.add_itxt(key, value, language, translated_key)

    save_kwargs: dict[str, Any] = {"pnginfo": pnginfo}
    if output_exif:
        save_kwargs["exif"] = output_exif
    if cleanup_options.preserve_icc and source_icc:
        save_kwargs["icc_profile"] = source_icc
    if cleanup_options.preserve_dpi and source_dpi:
        save_kwargs["dpi"] = source_dpi
    if transparency is not None and source_mode in {"1", "L", "P", "RGB"}:
        save_kwargs["transparency"] = transparency

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    generator_after = 0
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination.name}.",
            suffix=".tmp.png",
            dir=destination.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
        pixel_image.save(temporary_path, format="PNG", **save_kwargs)
        after, generator_after = _validate_cleanup_output(
            temporary_path,
            source_mode=source_mode,
            source_size=source_size,
            source_fingerprint=source_fingerprint,
            source_icc=source_icc,
            source_dpi=source_dpi,
            options=cleanup_options,
            expected_categories={
                "exif": bool(output_exif),
                "xmp": bool(output_xmp_payloads),
                "iptc": False,
                "comments_text": bool(output_ordinary_text),
                "embedded_thumbnail": bool(
                    output_exif
                    and before["categories"]["embedded_thumbnail"]["present"]
                    and not cleanup_options.remove_embedded_thumbnail
                ),
            },
            expected_exif=output_exif,
            expected_text_digest=_metadata_entries_digest(output_ordinary_text),
            expected_xmp_digest=_metadata_entries_digest(output_xmp_text),
        )
        os.replace(temporary_path, destination)
        temporary_path = None
    except MetadataCleanupError:
        raise
    except (OSError, SyntaxError, ValueError) as error:
        raise MetadataCleanupError("metadata cleanup could not publish the output") from error
    finally:
        pixel_image.close()
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass

    before_categories = before["categories"]
    after_categories = after["categories"]
    actions = {
        "exif": _category_action(
            before_categories["exif"]["present"],
            after_categories["exif"]["present"],
            cleanup_options.remove_exif,
        ),
        "xmp": _category_action(
            before_categories["xmp"]["present"],
            after_categories["xmp"]["present"],
            cleanup_options.remove_xmp,
        ),
        "comments_text": _category_action(
            before_categories["comments_text"]["present"],
            after_categories["comments_text"]["present"],
            cleanup_options.remove_comments_text,
        ),
        "embedded_thumbnail": _category_action(
            before_categories["embedded_thumbnail"]["present"],
            after_categories["embedded_thumbnail"]["present"],
            cleanup_options.remove_exif or cleanup_options.remove_embedded_thumbnail,
        ),
        "generator_fields": (
            "absent"
            if not generator_before
            else (
                "removed"
                if cleanup_options.remove_generator_fields
                else ("preserved" if generator_after else "removed_with_selected_category")
            )
        ),
        "icc_profile": (
            "absent"
            if not source_icc
            else ("preserved" if cleanup_options.preserve_icc else "removed")
        ),
        "dpi": (
            "absent"
            if source_dpi is None
            else ("preserved" if cleanup_options.preserve_dpi else "removed")
        ),
        "iptc": (
            "absent"
            if not iptc
            else ("removed" if cleanup_options.remove_iptc else "not_preserved_output_unsupported")
        ),
        "embedded_c2pa": (
            "removed"
            if before_c2pa["embedded_presence"] == "present" and cleanup_options.remove_embedded_c2pa
            else "absent"
        ),
        "c2pa_external_reference": (
            "removed_from_output"
            if before_c2pa["external_reference_presence"] == "present"
            and cleanup_options.remove_embedded_c2pa
            else (
                "unclassified_xmp_removed"
                if before_c2pa["external_reference_presence"] == "unknown"
                and cleanup_options.remove_embedded_c2pa
                and cleanup_options.remove_xmp
                else "absent"
            )
        ),
        "c2pa_embedded_reference": (
            "removed_from_output"
            if before_c2pa["embedded_reference_presence"] == "present"
            and cleanup_options.remove_embedded_c2pa
            else (
                "unclassified_xmp_removed"
                if before_c2pa["embedded_reference_presence"] == "unknown"
                and cleanup_options.remove_embedded_c2pa
                and cleanup_options.remove_xmp
                else "absent"
            )
        ),
        "c2pa_unclassified_reference": (
            "removed_with_xmp_category"
            if before_c2pa["unclassified_reference_presence"] != "not_present"
            and cleanup_options.remove_embedded_c2pa
            and cleanup_options.remove_xmp
            else "absent"
        ),
    }
    return {
        "status": "ok",
        "source_format": before["format"],
        "output_format": "PNG",
        "width": source_size[0],
        "height": source_size[1],
        "actions": actions,
        "c2pa_scope": {
            "remote_manifest": "not_deleted_or_accessed",
            "sidecar_manifest": "not_deleted_or_accessed",
            "pixel_soft_bindings": "not_removed_or_validated",
            "signature_validation": "not_performed",
        },
        "before": {"categories": before_categories, "c2pa": before_c2pa},
        "after": {"categories": after_categories, "c2pa": after["c2pa"]},
    }


__all__ = [
    "MetadataCleanupError",
    "MetadataCleanupOptions",
    "cleanup_image_metadata",
]
