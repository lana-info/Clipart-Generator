"""Bounded, signed local module packages; no code execution or network access.

The application supplies trusted publisher keys. Installation never trusts a key
embedded in a downloaded archive. Runtime registration is a separate integration.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_FILES = 512
MAX_MANIFEST_BYTES = 128 * 1024
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")


class ModulePackageError(ValueError):
    pass


def _version(value: str) -> tuple[int, int, int]:
    if not isinstance(value, str) or not re.fullmatch(r"\d{1,5}\.\d{1,5}\.\d{1,5}", value):
        raise ModulePackageError("Expected numeric major.minor.patch version")
    return tuple(map(int, value.split(".")))


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ModulePackageError("Invalid module identifier")
    return value


def _member(name: str) -> str:
    p = PurePosixPath(name)
    if (not name or len(name) > 220 or p.is_absolute() or "\\" in name
            or any(part in ("", ".", "..") for part in name.split("/"))
            or any(ord(c) < 32 or c in ':*?"<>|' for c in name)):
        raise ModulePackageError("Unsafe package path")
    for part in p.parts:
        if part.endswith((" ", ".")) or part.split(".")[0].upper() in {
            "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }:
            raise ModulePackageError("Non-portable package path")
    return name


def canonical_manifest(manifest: dict) -> bytes:
    """Publisher and verifier use this exact version-1 signed representation."""
    return json.dumps(manifest, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique_object(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ModulePackageError("Duplicate JSON key")
        result[k] = v
    return result


class _InstalledPackage:
    """Read installed files through the same bounded verifier as ZIP packages."""

    def __init__(self, root: Path):
        self.root = root
        self.entries = {}
        visited = 0
        total = 0
        for directory, folders, files in os.walk(root, followlinks=False):
            for name in folders + files:
                visited += 1
                if visited > MAX_FILES * 2:
                    raise ModulePackageError("Installed package exceeds entry limit")
                path = Path(directory) / name
                mode = path.lstat().st_mode
                if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                    raise ModulePackageError("Unsafe installed package entry")
            for name in files:
                path = Path(directory) / name
                relative = path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(relative)
                info.file_size = path.stat().st_size
                total += info.file_size
                if len(self.entries) >= MAX_FILES or total > MAX_PACKAGE_BYTES:
                    raise ModulePackageError("Installed package exceeds size limit")
                self.entries[relative] = info

    def infolist(self):
        return list(self.entries.values())

    def getinfo(self, name):
        return self.entries[name]

    def read(self, name):
        path = self.root / name
        if not stat.S_ISREG(path.lstat().st_mode):
            raise ModulePackageError("Unsafe installed package file")
        with path.open("rb") as stream:
            data = stream.read(self.entries[name].file_size + 1)
        if len(data) != self.entries[name].file_size:
            raise ModulePackageError("Installed file changed during verification")
        return data


class ModuleStore:
    """Single-process store under a dedicated application-data directory.

    Caller serializes lifecycle operations on the UI/service thread. Packages
    are immutable; activation changes one atomic pointer. User projects belong
    outside this store and are never removed by disable/rollback.
    """

    def __init__(self, root: Path, *, studio_version: str, platform: str,
                 trusted_keys: dict[str, bytes]):
        self.root = Path(root).absolute()
        if self.root == Path(self.root.anchor) or self.root.is_symlink():
            raise ModulePackageError("Use a dedicated module-store directory")
        self.version = _version(studio_version)
        self.platform = platform
        self.trusted_keys = dict(trusted_keys)
        self.root.mkdir(parents=True, exist_ok=True)

    def _module_dir(self, module_id: str) -> Path:
        if self.root.is_symlink():
            raise ModulePackageError("Module store must not be a symlink")
        path = self.root / _identifier(module_id)
        if path.is_symlink():
            raise ModulePackageError("Module path must not be a symlink")
        return path

    def _verify(self, archive: zipfile.ZipFile) -> tuple[dict, bytes]:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_FILES:
            raise ModulePackageError("Package file count exceeds limit")
        names = [x.filename for x in entries]
        if len({n.casefold() for n in names}) != len(names):
            raise ModulePackageError("Duplicate/case-colliding package paths")
        if sum(x.file_size for x in entries) > MAX_PACKAGE_BYTES:
            raise ModulePackageError("Expanded package exceeds limit")
        for entry in entries:
            _member(entry.filename)
            mode = entry.external_attr >> 16
            if entry.is_dir() or (stat.S_IFMT(mode) not in (0, stat.S_IFREG)) or entry.flag_bits & 1:
                raise ModulePackageError("Only unencrypted regular file entries allowed")
        if "manifest.json" not in names or "signature.json" not in names:
            raise ModulePackageError("Unsigned package")
        for name in ("manifest.json", "signature.json"):
            if archive.getinfo(name).file_size > MAX_MANIFEST_BYTES:
                raise ModulePackageError("Manifest too large")
        try:
            manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=_unique_object)
            signature = json.loads(archive.read("signature.json"), object_pairs_hook=_unique_object)
            key = self.trusted_keys[signature["key_id"]]
            signed = canonical_manifest(manifest)
            Ed25519PublicKey.from_public_bytes(key).verify(
                base64.b64decode(signature["signature"], validate=True), signed)
        except Exception as exc:
            raise ModulePackageError("Invalid signature or manifest") from exc
        try:
            if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
                raise ModulePackageError("Unsupported manifest schema")
            _identifier(manifest["module_id"])
            _version(manifest["version"])
            if manifest["module_api"] != 1 or type(manifest["module_api"]) is not int:
                raise ModulePackageError("Unsupported module API")
            if not (_version(manifest["studio_min"]) <= self.version < _version(manifest["studio_max_exclusive"])):
                raise ModulePackageError("Incompatible Studio version")
            if not isinstance(manifest["platforms"], list) or self.platform not in manifest["platforms"]:
                raise ModulePackageError("Unsupported platform")
            # Inter-module dependencies are deliberately not implemented yet.
            if manifest.get("dependencies", []):
                raise ModulePackageError("Package dependencies are not supported yet")
            files = manifest["files"]
            if not isinstance(files, dict) or not files or set(names) != set(files) | {"manifest.json", "signature.json"}:
                raise ModulePackageError("Package inventory mismatch")
            if manifest["entrypoint"] not in files:
                raise ModulePackageError("Missing entrypoint")
            for name, digest in files.items():
                _member(name)
                if name in ("manifest.json", "signature.json") or not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
                    raise ModulePackageError("Invalid file digest")
                if hashlib.sha256(archive.read(name)).hexdigest() != digest:
                    raise ModulePackageError("File checksum mismatch")
        except (KeyError, TypeError) as exc:
            raise ModulePackageError("Incomplete manifest") from exc
        return manifest, signed

    def install(self, package: Path) -> dict:
        """Verify and stage a package. Does not activate or import its code."""
        package = Path(package)
        if package.stat().st_size > MAX_PACKAGE_BYTES:
            raise ModulePackageError("Package exceeds limit")
        with zipfile.ZipFile(package) as archive:
            manifest, _ = self._verify(archive)
            parent = self._module_dir(manifest["module_id"])
            parent.mkdir(exist_ok=True)
            destination = parent / manifest["version"]
            if destination.exists() or destination.is_symlink():
                raise ModulePackageError("Version is already installed")
            if shutil.disk_usage(parent).free < sum(x.file_size for x in archive.infolist()) + 1024 * 1024:
                raise ModulePackageError("Insufficient free space")
            staging = Path(tempfile.mkdtemp(prefix=".stage-", dir=parent))
            try:
                for info in archive.infolist():
                    target = staging / info.filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as out, archive.open(info) as source:
                        shutil.copyfileobj(source, out, length=1024 * 1024)
                os.replace(staging, destination)
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
        return manifest

    def state(self, module_id: str) -> dict:
        """Informational pointer only; loaders must call verified_active_path()."""
        path = self._module_dir(module_id) / "active.json"
        if path.is_symlink():
            raise ModulePackageError("Unsafe activation file")
        if not path.exists():
            return {"active": None, "previous": None, "enabled": False}
        if path.stat().st_size > 4096:
            raise ModulePackageError("Invalid activation state")
        try:
            value = json.loads(path.read_text("utf-8"), object_pairs_hook=_unique_object)
            if not isinstance(value, dict) or set(value) != {"active", "previous", "enabled"}:
                raise ModulePackageError("Invalid activation state")
            if type(value["enabled"]) is not bool:
                raise ModulePackageError("Invalid activation state")
            for field in ("active", "previous"):
                if value[field] is not None:
                    _version(value[field])
                    installed = self._module_dir(module_id) / value[field]
                    if installed.is_symlink() or not installed.is_dir():
                        raise ModulePackageError("Activation refers to a missing version")
            if value["enabled"] and value["active"] is None:
                raise ModulePackageError("Invalid activation state")
            return value
        except (ValueError, TypeError) as exc:
            raise ModulePackageError("Invalid activation state") from exc

    def _verified_version(self, module_id: str, version: str) -> Path:
        _version(version)
        path = self._module_dir(module_id) / version
        if path.is_symlink() or not path.is_dir():
            raise ModulePackageError("Version is not installed")
        manifest, _ = self._verify(_InstalledPackage(path))
        if manifest["module_id"] != module_id or manifest["version"] != version:
            raise ModulePackageError("Installed package identity mismatch")
        return path

    def verified_active_path(self, module_id: str) -> Path | None:
        """Reverify trust and files immediately before a future runtime loads code.

        This does not execute a module. The store is not an OS sandbox against
        another process with write access to the same application-data directory.
        """
        state = self.state(module_id)
        if not state["enabled"]:
            return None
        return self._verified_version(module_id, state["active"])

    def _write_state(self, module_id: str, state: dict) -> None:
        parent = self._module_dir(module_id)
        parent.mkdir(exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".active-", dir=parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, parent / "active.json")
        finally:
            Path(name).unlink(missing_ok=True)

    def activate(self, module_id: str, version: str, *, busy: bool = False) -> None:
        if busy:
            raise ModulePackageError("Module has running tasks")
        self._verified_version(module_id, version)
        previous = self.state(module_id)["active"]
        self._write_state(module_id, {"active": version,
                                     "previous": previous if previous != version else self.state(module_id)["previous"],
                                     "enabled": True})

    @contextmanager
    def activation_transaction(self, module_id: str, version: str, *, busy: bool = False):
        """Temporarily activate a verified version and restore exact prior state on failure."""
        previous_state = self.state(module_id)
        self.activate(module_id, version, busy=busy)
        try:
            yield
        except BaseException:
            self._write_state(module_id, previous_state)
            raise

    def rollback(self, module_id: str, *, busy: bool = False) -> None:
        previous = self.state(module_id)["previous"]
        if previous is None:
            raise ModulePackageError("No previous version")
        self.activate(module_id, previous, busy=busy)

    def disable(self, module_id: str, *, busy: bool = False) -> None:
        if busy:
            raise ModulePackageError("Module has running tasks")
        state = self.state(module_id)
        state["enabled"] = False
        self._write_state(module_id, state)
