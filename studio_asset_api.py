"""Stable, path-free public asset handle used for inter-module handoff."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ASSET_HANDLE_SCHEMA_VERSION = 1
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MAX_FILENAME_CHARS = 240
_MAX_FILENAME_UTF8_BYTES = 240
_RECORD_KEYS = frozenset({
    "schema_version", "asset_id", "sha256", "size", "filename", "media_type",
})
_WINDOWS_RESERVED_NAMES = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
})


class AssetHandleError(ValueError):
    pass


def _windows_reserved(value: str) -> bool:
    stem = value.split(".", 1)[0].rstrip(". ").casefold()
    return stem in _WINDOWS_RESERVED_NAMES


@dataclass(frozen=True, slots=True)
class AssetHandle:
    """Immutable portable identity for bytes owned by Studio Core."""

    asset_id: str
    sha256: str
    size: int
    filename: str
    media_type: str

    def __post_init__(self) -> None:
        if not isinstance(self.asset_id, str) or not _DIGEST.fullmatch(self.asset_id):
            raise AssetHandleError("Asset handle id is invalid")
        if not isinstance(self.sha256, str) or not _DIGEST.fullmatch(self.sha256):
            raise AssetHandleError("Asset handle digest is invalid")
        if self.asset_id != self.sha256:
            raise AssetHandleError("Asset handle id and digest differ")
        if type(self.size) is not int or self.size < 0:
            raise AssetHandleError("Asset handle size is invalid")
        if (
            not isinstance(self.filename, str) or not self.filename
            or len(self.filename) > _MAX_FILENAME_CHARS
            or len(self.filename.encode("utf-8")) > _MAX_FILENAME_UTF8_BYTES
            or any(ord(char) < 32 or char in '/\\<>:"|?*' for char in self.filename)
            or self.filename.endswith((".", " "))
            or self.filename in {".", ".."}
            or Path(self.filename).name != self.filename
            or _windows_reserved(self.filename)
        ):
            raise AssetHandleError("Asset handle filename is invalid")
        if (
            not isinstance(self.media_type, str) or not self.media_type
            or len(self.media_type) > 255 or "/" not in self.media_type
            or any(char.isspace() for char in self.media_type)
        ):
            raise AssetHandleError("Asset handle media type is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": ASSET_HANDLE_SCHEMA_VERSION,
            "asset_id": self.asset_id,
            "sha256": self.sha256,
            "size": self.size,
            "filename": self.filename,
            "media_type": self.media_type,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "AssetHandle":
        if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
            raise AssetHandleError("Asset handle schema is unknown or incomplete")
        if type(value["schema_version"]) is not int or value["schema_version"] != ASSET_HANDLE_SCHEMA_VERSION:
            raise AssetHandleError("Asset handle schema version is unsupported")
        try:
            return cls(
                value["asset_id"], value["sha256"], value["size"],
                value["filename"], value["media_type"],
            )
        except (KeyError, TypeError) as exc:
            raise AssetHandleError("Asset handle is invalid") from exc


__all__ = ["ASSET_HANDLE_SCHEMA_VERSION", "AssetHandle", "AssetHandleError"]
