"""Convert the pinned reverse-SynthID codebook to a pickle-free NPZ.

The upstream archive stores string arrays as NumPy object arrays, so its loader
uses ``allow_pickle=True``. This one-time converter accepts only the exact
reviewed archive, uses a class allowlist for those small object arrays, validates
that every object is a bounded string, and writes deterministic Unicode arrays.
The resulting archive is safe to load with ``allow_pickle=False``.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import pickle
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
from numpy._core import multiarray
from numpy.lib import format as numpy_format


SOURCE_SHA256 = "f105de83ae3aca85330793bf8780d4bcd364a1df009685c1abf24af26dbe5366"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 128 * 1024 * 1024
MAX_MEMBERS = 256
MAX_STRING_LENGTH = 160
ALLOWED_PICKLE_GLOBALS = {
    ("numpy._core.multiarray", "_reconstruct"): multiarray._reconstruct,
    ("numpy", "ndarray"): np.ndarray,
    ("numpy", "dtype"): np.dtype,
}


class RepackError(RuntimeError):
    """A bounded, path-safe codebook conversion failure."""


class _StringArrayUnpickler(pickle.Unpickler):
    def find_class(self, module: str, name: str) -> Any:
        allowed = ALLOWED_PICKLE_GLOBALS.get((module, name))
        if allowed is None:
            raise RepackError("Object array uses a forbidden pickle global")
        return allowed

    def persistent_load(self, _: object) -> Any:
        raise RepackError("Persistent pickle references are forbidden")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_header(stream: io.BytesIO) -> tuple[tuple[int, ...], bool, np.dtype[Any]]:
    try:
        version = numpy_format.read_magic(stream)
        if version == (1, 0):
            return numpy_format.read_array_header_1_0(stream)
        if version in {(2, 0), (3, 0)}:
            return numpy_format.read_array_header_2_0(stream)
    except (EOFError, ValueError) as error:
        raise RepackError("Codebook member has an invalid NPY header") from error
    raise RepackError("Codebook member uses an unsupported NPY version")


def _read_member(raw: bytes) -> np.ndarray[Any, Any]:
    stream = io.BytesIO(raw)
    shape, fortran_order, dtype = _read_header(stream)
    if any(dimension < 0 for dimension in shape):
        raise RepackError("Codebook member has an invalid shape")
    if dtype.hasobject:
        try:
            value = _StringArrayUnpickler(stream).load()
        except (pickle.UnpicklingError, AttributeError, EOFError, ValueError) as error:
            raise RepackError("Object array failed strict decoding") from error
        if stream.read(1):
            raise RepackError("Object array contains trailing pickle data")
        if type(value) is not np.ndarray or value.shape != shape:
            raise RepackError("Object array does not match its NPY header")
        strings = value.ravel(order="F" if fortran_order else "C").tolist()
        if not all(type(item) is str for item in strings):
            raise RepackError("Object array contains a non-string value")
        if any(len(item) > MAX_STRING_LENGTH for item in strings):
            raise RepackError("Object array contains an oversized string")
        max_length = max((len(item) for item in strings), default=1)
        return np.asarray(value, dtype=f"<U{max_length}", order="F" if fortran_order else "C")

    try:
        return numpy_format.read_array(
            io.BytesIO(raw),
            allow_pickle=False,
            max_header_size=10_000,
        )
    except (EOFError, ValueError) as error:
        raise RepackError("Numeric codebook member is invalid") from error


def _safe_members(source: Path) -> list[tuple[str, np.ndarray[Any, Any]]]:
    if source.stat().st_size > MAX_ARCHIVE_BYTES:
        raise RepackError("Source codebook exceeds the archive limit")
    members: list[tuple[str, np.ndarray[Any, Any]]] = []
    seen: set[str] = set()
    try:
        with zipfile.ZipFile(source) as archive:
            infos = archive.infolist()
            if not infos or len(infos) > MAX_MEMBERS:
                raise RepackError("Source codebook has an invalid member count")
            if sum(info.file_size for info in infos) > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise RepackError("Source codebook exceeds the expanded size limit")
            for info in infos:
                name = info.filename
                pure_name = Path(name)
                if (
                    name in seen
                    or not name.endswith(".npy")
                    or pure_name.is_absolute()
                    or ".." in pure_name.parts
                    or info.file_size > MAX_MEMBER_BYTES
                ):
                    raise RepackError("Source codebook has an unsafe member")
                seen.add(name)
                members.append((name, _read_member(archive.read(info))))
    except (OSError, zipfile.BadZipFile) as error:
        raise RepackError("Source codebook is not a valid NPZ archive") from error
    return members


def _write_deterministic_npz(
    destination: Path,
    members: list[tuple[str, np.ndarray[Any, Any]]],
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w+b",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            with zipfile.ZipFile(
                stream,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as archive:
                for name, array in members:
                    payload = io.BytesIO()
                    numpy_format.write_array(
                        payload,
                        np.asarray(array),
                        allow_pickle=False,
                    )
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = 0o600 << 16
                    archive.writestr(info, payload.getvalue(), compresslevel=9)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def repack(source: Path, destination: Path) -> str:
    source = source.resolve(strict=True)
    destination = destination.resolve(strict=False)
    if destination.exists():
        raise RepackError("Destination must not already exist")
    if sha256_file(source) != SOURCE_SHA256:
        raise RepackError("Source codebook does not match the reviewed SHA-256")
    members = _safe_members(source)
    _write_deterministic_npz(destination, members)

    try:
        with np.load(destination, allow_pickle=False) as archive:
            for key in archive.files:
                value = archive[key]
                if value.dtype.hasobject:
                    raise RepackError("Repacked codebook still contains objects")
    except (OSError, ValueError) as error:
        destination.unlink(missing_ok=True)
        raise RepackError("Repacked codebook failed pickle-free validation") from error
    return sha256_file(destination)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a pickle-free M1 codebook.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        digest = repack(args.source, args.destination)
    except (OSError, RepackError) as error:
        print(str(error))
        return 2
    print(digest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
