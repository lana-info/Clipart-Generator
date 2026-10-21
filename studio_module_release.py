"""Controlled official release preparation and authenticated draft upload.

Private keys stay outside the checkout. No command publishes a customer release.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib import request, parse

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, NoEncryption, load_pem_private_key,
)

from studio_module_delivery import OFFICIAL_PUBLISHER_KEYS
from studio_module_packaging import OFFICIAL_WORKFLOW_FILES, OFFICIAL_COMPONENT_FILES, prepare_official_workflow_release
from studio_modules import MAX_PACKAGE_BYTES, ModuleStore

SOURCE_ROOT = Path(__file__).resolve().parent


def initialize_key(path: Path) -> bytes:
    """Create once with owner-only permissions; return only the public key."""
    path = Path(path)
    if path.resolve().is_relative_to(SOURCE_ROOT):
        raise ValueError("Private keys must be outside the source checkout")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name == "posix" and path.parent.stat().st_mode & 0o077:
        raise ValueError("Signing directory must have owner-only permissions")
    key = Ed25519PrivateKey.generate()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
        handle.flush()
        os.fsync(handle.fileno())
    return key.public_key().public_bytes_raw()


def load_signing_key(path: Path, key_id: str, trusted_keys: dict[str, bytes]) -> Ed25519PrivateKey:
    path = Path(path)
    if path.resolve().is_relative_to(SOURCE_ROOT) or path.is_symlink():
        raise ValueError("Invalid signing key location")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384:
            raise ValueError("Invalid signing key file")
        if os.name == "posix" and (info.st_mode & 0o077 or info.st_uid != os.getuid()):
            raise ValueError("Signing key must be owned by this user with mode 0600")
        key = load_pem_private_key(handle.read(16385), password=None)
    if (not isinstance(key, Ed25519PrivateKey)
            or key.public_key().public_bytes_raw() != trusted_keys.get(key_id)):
        raise ValueError("Signing key is not pinned in this Studio release")
    return key


def prepare_release_set(*, output: Path, key_path: Path, key_id: str, version: str,
                        studio_min: str, studio_max_exclusive: str, platforms: list[str],
                        source_root: Path = SOURCE_ROOT, trusted_keys=None) -> list[dict]:
    keys = OFFICIAL_PUBLISHER_KEYS if trusted_keys is None else trusted_keys
    key = load_signing_key(key_path, key_id, keys)
    # Validate and build everything before creating any release output.
    artifacts = []
    for module_id in sorted({**OFFICIAL_WORKFLOW_FILES, **OFFICIAL_COMPONENT_FILES}):
        content = prepare_official_workflow_release(
            source_root=source_root, module_id=module_id, version=version,
            studio_min=studio_min, studio_max_exclusive=studio_max_exclusive,
            platforms=platforms, key_id=key_id, private_key=key,
        )
        row = dict(module_id=module_id, version=version, studio_min=studio_min,
                   studio_max_exclusive=studio_max_exclusive, platforms=platforms,
                   filename=f"{module_id}-{version}.zip", size=len(content),
                   sha256=hashlib.sha256(content).hexdigest(), key_id=key_id)
        artifacts.append((row, content))
    output = Path(output)
    output.mkdir(mode=0o700, parents=False, exist_ok=False)
    for row, content in artifacts:
        with (output / row["filename"]).open("xb") as handle:
            handle.write(content)
    rows = [row for row, _ in artifacts]
    with (output / "release-set.json").open("x", encoding="utf-8") as handle:
        json.dump({"schema_version": 1, "releases": rows}, handle, indent=2)
        handle.write("\n")
    return rows


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Release upload redirects are forbidden")


class AdminDraftUploader:
    def __init__(self, base_url: str):
        url = parse.urlsplit(base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or "%" in url.path
                or any(part in {".", ".."} for part in url.path.split("/"))):
            raise ValueError("An HTTPS service base URL is required")
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = request.build_opener(NoRedirect(), request.HTTPCookieProcessor(self.cookies))
        self.csrf = None

    def _post(self, path: str, payload, *, binary=False):
        headers = {"Content-Type": "application/octet-stream" if binary else "application/json"}
        if self.csrf:
            headers["X-Admin-CSRF"] = self.csrf
        body = payload if binary else json.dumps(payload).encode("utf-8")
        req = request.Request(self.base_url + path, data=body, headers=headers, method="POST")
        with self.opener.open(req, timeout=60) as response:
            if response.status not in {200, 201}:
                raise ValueError("Admin request was not accepted")
            data = response.read(65537)
        if len(data) > 65536:
            raise ValueError("Admin response exceeded limit")
        result = json.loads(data)
        if not isinstance(result, dict):
            raise ValueError("Invalid admin response")
        return result

    def login(self, username: str, password: str, totp_code: str):
        result = self._post("/admin/login", dict(username=username, password=password,
                                               totp_code=totp_code, remember_browser=False))
        csrf = result.get("csrf_token")
        if not isinstance(csrf, str) or not csrf or len(csrf) > 256:
            raise ValueError("Missing admin session")
        self.csrf = csrf

    def upload(self, package: Path, *, product_id: str, platform: str,
               studio_version: str, notes: str = "", trusted_keys=None) -> dict:
        if not self.csrf:
            raise ValueError("Admin login required")
        # Inspect the exact in-memory bytes later sent, not a mutable source path.
        with Path(package).open("rb") as handle:
            content = handle.read(MAX_PACKAGE_BYTES + 1)
        if len(content) > MAX_PACKAGE_BYTES:
            raise ValueError("Module package exceeds limit")
        keys = OFFICIAL_PUBLISHER_KEYS if trusted_keys is None else trusted_keys
        with tempfile.TemporaryDirectory(prefix="vibix-publish-check-") as temp:
            root = Path(temp)
            snapshot = root / "package.zip"
            snapshot.write_bytes(content)
            store = ModuleStore(root / "inspection", studio_version=studio_version,
                                platform=platform, trusted_keys=keys)
            manifest = store.inspect_package(snapshot)
        if manifest["module_id"] not in {**OFFICIAL_WORKFLOW_FILES, **OFFICIAL_COMPONENT_FILES}:
            raise ValueError("Unknown official module")
        payload = {name: manifest[name] for name in (
            "module_id", "version", "studio_min", "studio_max_exclusive")}
        payload.update(product_code=product_id, platform=platform, channel="stable", notes=notes)
        row = self._post("/admin/releases", payload)
        release_id = row.get("id")
        if not isinstance(release_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", release_id):
            raise ValueError("Invalid draft identity")
        # A failed upload leaves a recoverable unpublished draft; never retry silently.
        print(json.dumps({"draft_id": release_id, "module_id": manifest["module_id"]}), flush=True)
        identity = {name: value for name, value in payload.items() if name != "notes"}
        if row.get("status") != "draft" or any(row.get(name) != value for name, value in identity.items()):
            raise ValueError("Server did not create the requested module draft")
        filename = f"{manifest['module_id']}-{manifest['version']}.zip"
        attached = self._post("/admin/releases/artifact?" + parse.urlencode({
            "release_id": release_id, "filename": filename}), content, binary=True)
        if (attached.get("id") != release_id
                or any(attached.get(name) != value for name, value in identity.items())
                or attached.get("artifact_sha256") != hashlib.sha256(content).hexdigest()
                or attached.get("artifact_size") != len(content) or attached.get("status") != "draft"):
            raise ValueError("Uploaded draft did not match the verified package")
        return {"draft_id": release_id, "module_id": manifest["module_id"], "status": "draft"}

    def close(self):
        self.csrf = None
        self.cookies.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init-key")
    init.add_argument("--key-file", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--key-file", type=Path, required=True)
    prepare.add_argument("--key-id", required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--version", required=True)
    prepare.add_argument("--studio-min", required=True)
    prepare.add_argument("--studio-max-exclusive", required=True)
    prepare.add_argument("--platform", action="append", required=True)
    upload = commands.add_parser("upload-draft")
    upload.add_argument("package", type=Path)
    upload.add_argument("--service-url", required=True)
    upload.add_argument("--product", default="clipart-generator")
    upload.add_argument("--platform", required=True)
    upload.add_argument("--studio-version", required=True)
    upload.add_argument("--username", default="admin")
    upload_set = commands.add_parser("upload-set")
    upload_set.add_argument("set_dir", type=Path)
    upload_set.add_argument("--service-url", required=True)
    upload_set.add_argument("--product", default="clipart-generator")
    upload_set.add_argument("--studio-version", required=True)
    upload_set.add_argument("--username", default="admin")
    args = parser.parse_args(argv)
    try:
        if args.command == "upload-set":
            if not sys.stdin.isatty():
                raise ValueError("Draft upload requires an interactive secure terminal")
            releases = json.loads((args.set_dir / "release-set.json").read_text(encoding="utf-8"))
            if isinstance(releases, dict):
                releases = releases.get("releases")
            uploader = AdminDraftUploader(args.service_url)
            try:
                uploader.login(args.username, getpass.getpass("Admin password: "), getpass.getpass("TOTP: "))
                for item in releases:
                    for platform in item["platforms"]:
                        print(json.dumps(uploader.upload(
                            args.set_dir / item["filename"], product_id=args.product,
                            platform=platform, studio_version=args.studio_version)), flush=True)
            finally:
                uploader.close()
        elif args.command == "init-key":
            print(json.dumps({"public_key_base64": base64.b64encode(initialize_key(args.key_file)).decode()}))
        elif args.command == "prepare":
            print(json.dumps(prepare_release_set(
                output=args.output, key_path=args.key_file, key_id=args.key_id, version=args.version,
                studio_min=args.studio_min, studio_max_exclusive=args.studio_max_exclusive,
                platforms=args.platform)))
        else:
            if not sys.stdin.isatty():
                raise ValueError("Draft upload requires an interactive secure terminal")
            uploader = AdminDraftUploader(args.service_url)
            try:
                uploader.login(args.username, getpass.getpass("Admin password: "), getpass.getpass("TOTP: "))
                print(json.dumps(uploader.upload(args.package, product_id=args.product,
                    platform=args.platform, studio_version=args.studio_version)))
            finally:
                uploader.close()
    except Exception:
        print("Release operation failed. No release was published; inspect any reported draft in admin.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
