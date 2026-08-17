"""Pure validation helpers for the source and packaged release contract."""

from __future__ import annotations

import json
import re
import argparse
from pathlib import Path
from urllib.parse import urlparse

VERSION_PATTERN = re.compile(r"\d+\.\d+(?:\.\d+)?\Z")
APP_EXECUTABLE_NAME = "Vibix Images.exe"
INSTALLER_NAME_TEMPLATE = "VibixImages-Setup-{version}.exe"


class ReleaseContractError(ValueError):
    """Raised when release metadata cannot be used safely."""


def parse_version(value: str) -> str:
    version = value.lstrip("\ufeff").strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ReleaseContractError("Version must match MAJOR.MINOR or MAJOR.MINOR.PATCH")
    return version


def resolve_release_version(release_root: str | Path) -> str:
    path = Path(release_root) / "VERSION.txt"
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise ReleaseContractError(f"Release version file is unavailable: {path}") from error
    return parse_version(raw)


def expected_installer_name(version: str) -> str:
    return INSTALLER_NAME_TEMPLATE.format(version=parse_version(version))


def validate_release_contract(
    version: str,
    *,
    installer_name: str | None = None,
    executable_path: str | Path | None = None,
    checksum_path: str | Path | None = None,
    manifest: dict | None = None,
) -> None:
    version = parse_version(version)
    if installer_name is not None and installer_name != expected_installer_name(version):
        raise ReleaseContractError(f"Installer name must be {expected_installer_name(version)}")
    if executable_path is not None:
        path = Path(executable_path)
        if path.name != APP_EXECUTABLE_NAME or path.parent.name != "Vibix Images":
            raise ReleaseContractError(
                "Packaged executable must be dist/Vibix Images/Vibix Images.exe"
            )
    if checksum_path is not None:
        checksum = Path(checksum_path)
        expected_name = expected_installer_name(version)
        if checksum.name != expected_name.replace(".exe", ".sha256"):
            raise ReleaseContractError("Checksum filename differs from the release artifact")
        try:
            line = checksum.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError) as error:
            raise ReleaseContractError("Release checksum sidecar is unavailable") from error
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+(.+)", line)
        if not match or Path(match.group(2)).name != expected_name:
            raise ReleaseContractError("Release checksum sidecar has an invalid format")
    if manifest is None:
        return
    latest = parse_version(str(manifest.get("latest_version", "")))
    if latest != version:
        raise ReleaseContractError("Update manifest version differs from the release version")
    url = manifest.get("download_url")
    if not isinstance(url, str) or urlparse(url).scheme != "https":
        raise ReleaseContractError("Update manifest download_url must be HTTPS")
    if Path(urlparse(url).path).name != expected_installer_name(version):
        raise ReleaseContractError("Update manifest artifact name differs from the release")
    checksum = str(manifest.get("sha256", ""))
    if not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        raise ReleaseContractError("Update manifest sha256 must be a 64-character hex digest")


def load_manifest(path: str | Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseContractError(f"Invalid release manifest: {path}") from error
    if not isinstance(payload, dict):
        raise ReleaseContractError("Release manifest must be a JSON object")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate the release contract")
    parser.add_argument("--version-file", required=True)
    parser.add_argument("--installer-name", required=True)
    parser.add_argument("--executable", required=True)
    parser.add_argument("--checksum")
    parser.add_argument("--manifest")
    args = parser.parse_args()
    release_version = resolve_release_version(Path(args.version_file).parent)
    validate_release_contract(
        release_version,
        installer_name=args.installer_name,
        executable_path=args.executable,
        checksum_path=args.checksum,
        manifest=load_manifest(args.manifest) if args.manifest else None,
    )
