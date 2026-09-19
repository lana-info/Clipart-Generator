"""Publisher-side preparation of immutable, signed Studio module artifacts.

Only explicitly supplied payload bytes are included. This never walks a source
tree, imports module code, or reads the publisher's private key from disk.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import zipfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from studio_modules import (
    MAX_FILES, MAX_PACKAGE_BYTES, MAX_MANIFEST_BYTES,
    ModulePackageError, ModuleStore, canonical_manifest, _member, _version,
)


def prepare_module_release(
    *, module_id: str, version: str, studio_min: str, studio_max_exclusive: str,
    platforms: list[str], entrypoint: str, files: dict[str, bytes],
    key_id: str, private_key: Ed25519PrivateKey,
) -> bytes:
    """Return a signed artifact after verifying it with the client installer.

    The caller owns signing-key custody and selects the exact release payload.
    Output is deterministic for identical inputs. No source files or user data
    are modified and no payload code is executed.
    """
    if not isinstance(private_key, Ed25519PrivateKey):
        raise ModulePackageError("An Ed25519 publisher key is required")
    if not isinstance(key_id, str) or not key_id.strip() or len(key_id) > 128:
        raise ModulePackageError("Invalid publisher key identifier")
    if (not isinstance(platforms, list) or not platforms
            or any(p not in {"windows-x64", "macos-x64", "macos-arm64", "linux-x64"} for p in platforms)
            or len(set(platforms)) != len(platforms)):
        raise ModulePackageError("Invalid release platforms")
    if _version(studio_min) >= _version(studio_max_exclusive):
        raise ModulePackageError("Empty Studio compatibility range")
    if not isinstance(files, dict) or not files or len(files) + 2 > MAX_FILES:
        raise ModulePackageError("Invalid package inventory")
    payload = {}
    total = 0
    for name, content in files.items():
        _member(name)
        if name.casefold() in {"manifest.json", "signature.json"} or not isinstance(content, bytes):
            raise ModulePackageError("Invalid package payload")
        total += len(content)
        if total > MAX_PACKAGE_BYTES:
            raise ModulePackageError("Expanded package exceeds limit")
        payload[name] = content
    if len({name.casefold() for name in payload}) != len(payload):
        raise ModulePackageError("Case-colliding payload paths")
    if entrypoint not in payload:
        raise ModulePackageError("Missing entrypoint")
    manifest = {
        "schema_version": 1, "module_id": module_id, "version": version,
        "module_api": 1, "studio_min": studio_min,
        "studio_max_exclusive": studio_max_exclusive,
        "platforms": sorted(platforms), "entrypoint": entrypoint,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in payload.items()},
    }
    signed = canonical_manifest(manifest)
    if len(signed) > MAX_MANIFEST_BYTES:
        raise ModulePackageError("Manifest too large")
    signature = json.dumps({
        "key_id": key_id, "signature": base64.b64encode(private_key.sign(signed)).decode("ascii")
    }, sort_keys=True).encode("utf-8")
    payload.update({"manifest.json": signed, "signature.json": signature})
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted(payload):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload[name])
    artifact = output.getvalue()
    if len(artifact) > MAX_PACKAGE_BYTES:
        raise ModulePackageError("Package exceeds limit")
    public = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    with tempfile.TemporaryDirectory(prefix="vibix-module-check-") as temp:
        root = Path(temp)
        package = root / "release.zip"
        package.write_bytes(artifact)
        for platform in platforms:
            store = ModuleStore(root / "inspection", studio_version=studio_min,
                                platform=platform, trusted_keys={key_id: public})
            store.inspect_package(package)
    return artifact
