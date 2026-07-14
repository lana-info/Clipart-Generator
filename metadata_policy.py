"""Shared exact-match policy for known AI/service metadata fields."""

from __future__ import annotations

import re
from collections.abc import Iterable
from xml.etree import ElementTree


MAX_XMP_BYTES = 4 * 1024 * 1024

# The policy is deliberately exact after punctuation/case normalization. It
# must never classify arbitrary metadata values or substring matches.
GENERATOR_EXIF_TAGS = frozenset({305})  # EXIF Software
GENERATOR_FIELD_GROUPS = {
    "software": frozenset({"software", "creatortool"}),
    "prompt": frozenset({"prompt", "parameters", "workflow", "negativeprompt"}),
    "model": frozenset({"model", "modelname", "aisystemused"}),
    "digital_source_type": frozenset({"digitalsourcetype"}),
    "generator": frozenset({"generator", "aigc", "hfjobid", "signature"}),
}
GENERATOR_XMP_PROPERTIES = {
    "{http://ns.adobe.com/xap/1.0/}CreatorTool": "software",
    "{http://iptc.org/std/Iptc4xmpExt/2008-02-29/}DigitalSourceType": "digital_source_type",
}

_XML_DECLARATION_RE = re.compile(r"^\s*<\?xml\b[^?]*\?>", re.IGNORECASE)
_XML_ENCODING_RE = re.compile(
    r"(^\s*<\?xml\b[^?]*?\bencoding\s*=\s*)(['\"])([^'\"]+)(\2)",
    re.IGNORECASE,
)


class XmpPolicyError(ValueError):
    """Raised when XMP cannot be parsed within the cleanup safety policy."""


def normalize_generator_field_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def classify_generator_field_names(names: Iterable[str]) -> frozenset[str]:
    normalized = {normalize_generator_field_name(name) for name in names}
    return frozenset(
        group
        for group, allowed_names in GENERATOR_FIELD_GROUPS.items()
        if normalized.intersection(allowed_names)
    )


def is_generator_text_field(name: str) -> bool:
    normalized = normalize_generator_field_name(name)
    return any(normalized in allowed_names for allowed_names in GENERATOR_FIELD_GROUPS.values())


def decode_xmp_text(payload: bytes) -> str:
    if len(payload) > MAX_XMP_BYTES:
        raise XmpPolicyError("XMP payload exceeds the cleanup limit")
    if payload.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif payload.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    elif payload.startswith(b"<\x00"):
        encoding = "utf-16-le"
    elif payload.startswith(b"\x00<"):
        encoding = "utf-16-be"
    else:
        encoding = "utf-8"
    try:
        text = payload.decode(encoding, errors="strict")
    except UnicodeDecodeError as error:
        raise XmpPolicyError("XMP payload uses an unsupported encoding") from error
    lowered = text.casefold()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise XmpPolicyError("XMP payload contains unsupported declarations")
    return text


def parse_xmp_root(payload: bytes) -> ElementTree.Element:
    text = decode_xmp_text(payload)
    # ElementTree rejects an encoding declaration on a Unicode string. The
    # declaration is transport metadata, so remove only that leading token.
    parse_text = _XML_DECLARATION_RE.sub("", text, count=1)
    try:
        return ElementTree.fromstring(parse_text)
    except (ElementTree.ParseError, ValueError) as error:
        raise XmpPolicyError("XMP payload is malformed") from error


def xmp_text_for_png(payload: bytes) -> str:
    text = decode_xmp_text(payload)

    def replace_encoding(match: re.Match[str]) -> str:
        return f'{match.group(1)}{match.group(2)}UTF-8{match.group(4)}'

    return _XML_ENCODING_RE.sub(replace_encoding, text, count=1)


def classify_generator_xmp(root: ElementTree.Element) -> frozenset[str]:
    matches: set[str] = set()
    for element in root.iter():
        group = GENERATOR_XMP_PROPERTIES.get(element.tag)
        if group:
            matches.add(group)
        for attribute in element.attrib:
            group = GENERATOR_XMP_PROPERTIES.get(attribute)
            if group:
                matches.add(group)
    return frozenset(matches)


__all__ = [
    "GENERATOR_EXIF_TAGS",
    "GENERATOR_FIELD_GROUPS",
    "GENERATOR_XMP_PROPERTIES",
    "MAX_XMP_BYTES",
    "XmpPolicyError",
    "classify_generator_field_names",
    "classify_generator_xmp",
    "decode_xmp_text",
    "is_generator_text_field",
    "normalize_generator_field_name",
    "parse_xmp_root",
    "xmp_text_for_png",
]
