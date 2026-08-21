"""Validate and stage the pinned Windows Real-ESRGAN runtime archive."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


REQUIRED_FILES = (
    "realesrgan-ncnn-vulkan.exe",
    "models/realesr-animevideov3-x2.bin",
    "models/realesr-animevideov3-x2.param",
    "models/realesrgan-x4plus-anime.bin",
    "models/realesrgan-x4plus-anime.param",
)


def _safe_member_path(name: str) -> PurePosixPath:
    candidate = PurePosixPath(name.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts or not candidate.parts:
        raise ValueError(f"unsafe Real-ESRGAN archive member: {name}")
    return candidate


def _runtime_root(members: list[zipfile.ZipInfo]) -> PurePosixPath:
    executable_matches = []
    for member in members:
        path = _safe_member_path(member.filename)
        if path.name.casefold() == "realesrgan-ncnn-vulkan.exe":
            executable_matches.append(path.parent)
    if len(executable_matches) != 1:
        raise ValueError("Real-ESRGAN archive must contain exactly one Windows executable")
    return executable_matches[0]


def _validate_target(target: Path) -> Path:
    resolved = target.expanduser().resolve(strict=False)
    if resolved == Path(resolved.anchor) or resolved == Path.home().resolve():
        raise ValueError("unsafe Real-ESRGAN target directory")
    return resolved


def prepare_runtime(archive_path: Path, target_path: Path, expected_sha256: str) -> None:
    archive = archive_path.expanduser().resolve(strict=True)
    target = _validate_target(target_path)
    expected = str(expected_sha256 or "").strip().casefold()
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    if len(expected) != 64 or actual != expected:
        raise ValueError(f"Real-ESRGAN archive SHA-256 mismatch: {actual}")

    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        root = _runtime_root(members)
        relative_members: dict[str, zipfile.ZipInfo] = {}
        for member in members:
            path = _safe_member_path(member.filename)
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if not relative.parts or member.is_dir():
                continue
            mode = member.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"symlink is not allowed in Real-ESRGAN archive: {member.filename}")
            relative_members[relative.as_posix()] = member

        for required in REQUIRED_FILES:
            if required not in relative_members:
                raise ValueError(f"required Real-ESRGAN file is missing: {required}")

        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="realesrgan-stage-", dir=target.parent) as temporary:
            staging = Path(temporary) / "runtime"
            for relative_name, member in relative_members.items():
                destination = staging.joinpath(*PurePosixPath(relative_name).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)
            if target.exists():
                shutil.rmtree(target)
            shutil.move(str(staging), str(target))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args(argv)
    try:
        prepare_runtime(args.archive, args.target, args.sha256)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
