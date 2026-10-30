"""Create a deterministic, secret-free build provenance document."""

from __future__ import annotations

import json
import os
import platform
import importlib.metadata
from urllib.parse import urlparse
from pathlib import Path


def build_provenance(*, commit: str, archive_url: str, archive_sha256: str) -> dict[str, object]:
    parsed = urlparse(archive_url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query:
        raise ValueError("provenance archive URL must be HTTPS and credential-free")
    packages = {}
    for name in ("PyQt6", "Pillow", "rembg", "onnxruntime", "opencv-python", "numpy", "cryptography", "rfc8785", "pyinstaller"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {
        "schema_version": 1,
        "commit": commit,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "archive": {"url": archive_url, "sha256": archive_sha256},
        "packages": packages,
        "tools": {"pyinstaller": packages.get("pyinstaller"), "inno_setup": os.environ.get("INNO_SETUP_VERSION", "workflow-managed")},
        "installer_sha256": os.environ.get("INSTALLER_SHA256", "not-built"),
        "secret_free": True,
    }


def main() -> None:
    output = Path(os.environ.get("PROVENANCE_OUTPUT", "release/build-provenance.json"))
    payload = build_provenance(
        commit=os.environ.get("GITHUB_SHA", "local"),
        archive_url=os.environ["REAL_ESRGAN_ARCHIVE_URL"],
        archive_sha256=os.environ["REAL_ESRGAN_ARCHIVE_SHA256"],
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
