"""Bounded, content-addressed storage for standalone Studio assets."""
from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
SCHEMA_VERSION = 1
DEFAULT_MAX_PER_ASSET = 256 * 1024 * 1024
_CHUNK_BYTES = 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_RECORD_KEYS = frozenset({"schema_version", "id", "sha256", "size", "filename", "media_type"})
_MAX_FILENAME_CHARS = 240
_MAX_FILENAME_UTF8_BYTES = 240
_WINDOWS_RESERVED_NAMES = frozenset({
    "con", "prn", "aux", "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
})


def _is_windows_reserved_filename(value: str) -> bool:
    stem = value.split(".", 1)[0].rstrip(". ").casefold()
    return stem in _WINDOWS_RESERVED_NAMES


def _fit_utf8(value: str, max_bytes: int, max_chars: int) -> str:
    result: list[str] = []
    used_bytes = 0
    for char in value:
        encoded_size = len(char.encode("utf-8"))
        if len(result) >= max_chars or used_bytes + encoded_size > max_bytes:
            break
        result.append(char)
        used_bytes += encoded_size
    return "".join(result)


class AssetStoreError(ValueError):
    """An asset cannot safely enter or leave the standalone asset store."""


@dataclass(frozen=True, slots=True)
class AssetRecord:
    id: str
    sha256: str
    size: int
    filename: str
    media_type: str

    def to_dict(self) -> dict[str, object]:
        self._validate()
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "sha256": self.sha256,
            "size": self.size,
            "filename": self.filename,
            "media_type": self.media_type,
        }

    @classmethod
    def from_dict(cls, value: object) -> "AssetRecord":
        if not isinstance(value, dict) or set(value) != _RECORD_KEYS:
            raise AssetStoreError("Asset record schema is unknown or incomplete")
        if type(value["schema_version"]) is not int or value["schema_version"] != SCHEMA_VERSION:
            raise AssetStoreError("Asset record schema version is unsupported")
        record = cls(value["id"], value["sha256"], value["size"],
                     value["filename"], value["media_type"])
        record._validate()
        return record

    def _validate(self) -> None:
        if type(self.id) is not str or not _DIGEST.fullmatch(self.id):
            raise AssetStoreError("Asset record id is invalid")
        if type(self.sha256) is not str or not _DIGEST.fullmatch(self.sha256):
            raise AssetStoreError("Asset record digest is invalid")
        if self.id != self.sha256:
            raise AssetStoreError("Asset record id and digest differ")
        if type(self.size) is not int or self.size < 0:
            raise AssetStoreError("Asset record size is invalid")
        if (type(self.filename) is not str or not self.filename
                or len(self.filename) > _MAX_FILENAME_CHARS
                or len(self.filename.encode("utf-8")) > _MAX_FILENAME_UTF8_BYTES):
            raise AssetStoreError("Asset record filename is invalid")
        if (any(ord(char) < 32 or char in '/\\<>:"|?*' for char in self.filename)
                or self.filename.endswith((".", " ")) or _is_windows_reserved_filename(self.filename)
                or self.filename in {".", ".."} or Path(self.filename).name != self.filename):
            raise AssetStoreError("Asset record filename must be a safe basename")
        if type(self.media_type) is not str or not self.media_type or len(self.media_type) > 255:
            raise AssetStoreError("Asset record media type is invalid")


class AssetStore:
    """Single-process immutable asset store rooted at a caller-owned directory."""

    def __init__(self, root: str | os.PathLike[str], *, max_per_asset: int = DEFAULT_MAX_PER_ASSET):
        if type(max_per_asset) is not int or max_per_asset < 0:
            raise AssetStoreError("Asset size limit must be a non-negative integer")
        supplied_root = Path(root).absolute()
        if supplied_root == Path(supplied_root.anchor):
            raise AssetStoreError("Asset store root must be a dedicated directory")
        self.root = supplied_root
        self.max_per_asset = max_per_asset
        try:
            if self.root.exists() and self.root.is_symlink():
                raise AssetStoreError("Asset store root must not be a symlink")
            self.root.mkdir(parents=True, exist_ok=True)
        except AssetStoreError:
            raise
        except OSError as exc:
            raise AssetStoreError("Asset store root cannot be created") from exc
        self._assert_root()

    def import_file(self, path: str | os.PathLike[str]) -> AssetRecord:
        """Copy a regular source file once, address it by SHA-256, and never mutate it."""
        source = Path(path)
        filename = self._sanitize_filename(source.name)
        self._assert_root()
        stage: Path | None = None
        try:
            stage, digest, size = self._stage_source(source)
            record = AssetRecord(digest, digest, size, filename, self._media_type(filename))
            destination = self._path_for(digest)
            if self._asset_exists(destination):
                self._verify_asset(destination, record)
                return record
            try:
                # link() creates the final name only if absent. Unlike replace(),
                # it cannot overwrite a concurrent or corrupt destination.
                os.link(stage, destination)
            except FileExistsError:
                self._verify_asset(destination, record)
                return record
            except OSError as exc:
                raise AssetStoreError("Asset publication failed") from exc
            self._fsync_directory()
            return record
        finally:
            if stage is not None:
                try:
                    stage.unlink(missing_ok=True)
                except OSError:
                    pass

    def resolve(self, record: AssetRecord) -> Path:
        """Return a verified immutable asset path, rechecking bytes before use."""
        if not isinstance(record, AssetRecord):
            raise AssetStoreError("Asset record is invalid")
        record._validate()
        if record.size > self.max_per_asset:
            raise AssetStoreError("Asset record exceeds size limit")
        self._assert_root()
        path = self._path_for(record.id)
        self._verify_asset(path, record)
        return path

    def _assert_root(self) -> None:
        try:
            info = self.root.lstat()
        except OSError as exc:
            raise AssetStoreError("Asset store root is unavailable") from exc
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
            raise AssetStoreError("Asset store root must be a non-symlink directory")

    def _stage_source(self, source: Path) -> tuple[Path, str, int]:
        self._assert_regular_source(source)
        stage: Path | None = None
        try:
            fd, name = tempfile.mkstemp(prefix=".asset-", suffix=".tmp", dir=self.root)
            stage = Path(name)
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(fd, "wb") as output_stream, self._open_source(source) as input_stream:
                while chunk := input_stream.read(_CHUNK_BYTES):
                    size += len(chunk)
                    if size > self.max_per_asset:
                        raise AssetStoreError("Asset exceeds size limit")
                    digest.update(chunk)
                    output_stream.write(chunk)
                output_stream.flush()
                os.fsync(output_stream.fileno())
            return stage, digest.hexdigest(), size
        except AssetStoreError:
            if stage is not None:
                stage.unlink(missing_ok=True)
            raise
        except OSError as exc:
            if stage is not None:
                stage.unlink(missing_ok=True)
            raise AssetStoreError("Asset source cannot be imported") from exc

    def _assert_regular_source(self, source: Path) -> None:
        try:
            info = source.lstat()
        except FileNotFoundError as exc:
            raise AssetStoreError("Asset source does not exist") from exc
        except OSError as exc:
            raise AssetStoreError("Asset source cannot be inspected") from exc
        if stat.S_ISLNK(info.st_mode):
            raise AssetStoreError("Asset source must not be a symlink")
        if not stat.S_ISREG(info.st_mode):
            raise AssetStoreError("Asset source must be a regular file")

    def _open_source(self, source: Path):
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(source, flags | nofollow)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise AssetStoreError("Asset source must be a regular file")
            stream = os.fdopen(descriptor, "rb")
            descriptor = None
            return stream
        except AssetStoreError:
            raise
        except OSError as exc:
            raise AssetStoreError("Asset source cannot be opened") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _asset_exists(self, path: Path) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise AssetStoreError("Asset path cannot be inspected") from exc
        if stat.S_ISLNK(info.st_mode):
            raise AssetStoreError("Asset path must not be a symlink")
        if not stat.S_ISREG(info.st_mode):
            raise AssetStoreError("Asset path must be a regular file")
        return True

    def _verify_asset(self, path: Path, record: AssetRecord) -> None:
        if not self._asset_exists(path):
            raise AssetStoreError("Asset is missing")
        descriptor: int | None = None
        try:
            digest = hashlib.sha256()
            size = 0
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(path, flags)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise AssetStoreError("Asset path must be a regular file")
            stream = os.fdopen(descriptor, "rb")
            descriptor = None
            with stream:
                while chunk := stream.read(_CHUNK_BYTES):
                    size += len(chunk)
                    if size > self.max_per_asset:
                        raise AssetStoreError("Asset integrity check exceeds size limit")
                    digest.update(chunk)
        except AssetStoreError:
            raise
        except OSError as exc:
            raise AssetStoreError("Asset cannot be read") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if size != record.size or digest.hexdigest() != record.sha256:
            raise AssetStoreError("Asset integrity check failed")

    def _path_for(self, digest: str) -> Path:
        if not _DIGEST.fullmatch(digest):
            raise AssetStoreError("Asset record id is invalid")
        return self.root / digest

    def _fsync_directory(self) -> None:
        # Windows does not permit opening a directory with os.open for fsync.
        # Publication is still no-clobber and file data is flushed first; the
        # POSIX directory-durability guarantee is intentionally unavailable.
        if os.name == "nt":
            return
        try:
            flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            descriptor = os.open(self.root, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as exc:
            raise AssetStoreError("Asset publication could not be synchronized") from exc

    @staticmethod
    def _sanitize_filename(value: str) -> str:
        # Source locations are never retained.  Replace separator and Windows-
        # reserved characters so archive records are portable when materialized.
        value = "".join("_" if ord(char) < 32 or char in '/\\<>:"|?*' else char for char in value)
        value = value.rstrip(". ")
        if value in {"", ".", ".."}:
            value = "asset"
        if _is_windows_reserved_filename(value):
            value = "_" + value
        extension_index = value.rfind(".")
        if extension_index > 0:
            stem, extension = value[:extension_index], value[extension_index:]
            extension = _fit_utf8(extension, 64, 64)
            stem = _fit_utf8(stem, _MAX_FILENAME_UTF8_BYTES - len(extension.encode("utf-8")),
                             _MAX_FILENAME_CHARS - len(extension))
            value = (stem or "asset") + extension
        else:
            value = _fit_utf8(value, _MAX_FILENAME_UTF8_BYTES, _MAX_FILENAME_CHARS)
        record = AssetRecord("0" * 64, "0" * 64, 0, value, "application/octet-stream")
        record._validate()
        return value

    @staticmethod
    def _media_type(filename: str) -> str:
        return mimetypes.guess_type(filename)[0] or "application/octet-stream"
