"""Local, hash-bound processing receipts. These do not certify image quality.

Requested/observed removal background is not generation metadata: the original
generator's request is unknown here. No prompts, paths or credentials are saved.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from processing_contract import publish_atomic
from chroma_profile import PROFILE_VERSION
from studio_processing_api import valid_processing_profile

MAX_RECEIPT_BYTES = 8192
MAX_IMAGE_BYTES = 256 * 1024 * 1024
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_COLOR = re.compile(r"#[0-9A-F]{6}\Z")
_KEYS = {"schema_version", "profile", "status", "quality_status", "source_sha256",
         "result_sha256", "requested_removal_background", "observed_removal_background"}


def image_digest(path: str | Path) -> str:
    digest = hashlib.sha256()
    total = 0
    with Path(path).open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_IMAGE_BYTES:
                raise ValueError("Image is too large for a processing receipt")
            digest.update(chunk)
    return digest.hexdigest()


def receipt_path(image_path: str | Path) -> Path:
    path = Path(image_path)
    return path.with_name(path.name + ".chroma.json")


def _validate(payload: object) -> dict:
    if not isinstance(payload, dict) or set(payload) != _KEYS:
        raise ValueError("Invalid chroma receipt fields")
    if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
        raise ValueError("Unsupported chroma receipt version")
    if not valid_processing_profile(payload["profile"]) or payload["status"] != "processed":
        raise ValueError("Unsupported chroma processing profile or status")
    if payload["quality_status"] != "not_evaluated":
        raise ValueError("Receipt is not a quality certificate")
    for key, pattern in (("source_sha256", _HASH), ("result_sha256", _HASH),
                         ("requested_removal_background", _COLOR),
                         ("observed_removal_background", _COLOR)):
        if not isinstance(payload[key], str) or not pattern.fullmatch(payload[key]):
            raise ValueError("Invalid chroma receipt value")
    return dict(payload)


def write_receipt(result_path: str | Path, *, source_sha256: str,
                  requested_background: str, observed_background: str,
                  expected_result_sha256: str | None = None,
                  profile: str = PROFILE_VERSION) -> Path:
    target = receipt_path(result_path)
    result_digest = image_digest(result_path)
    if expected_result_sha256 is not None and result_digest != expected_result_sha256:
        raise ValueError("Export changed before its receipt was saved")
    payload = _validate({
        "schema_version": 1, "profile": profile, "status": "processed",
        "quality_status": "not_evaluated", "source_sha256": source_sha256,
        "result_sha256": result_digest,
        "requested_removal_background": requested_background,
        "observed_removal_background": observed_background,
    })
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    # No overwrite: preserve any existing receipt/user file. A stale receipt
    # cannot load successfully against different image bytes.
    with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".chroma-", delete=False) as stream:
        stage = Path(stream.name)
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            stream.close()
            stage.unlink(missing_ok=True)
            raise
    try:
        publish_atomic(stage, target, overwrite=False)
    finally:
        stage.unlink(missing_ok=True)
    return target


def load_receipt(image_path: str | Path) -> dict | None:
    """Missing, stale and unsupported local records are treated as unavailable."""
    target = receipt_path(image_path)
    try:
        if target.is_symlink():
            return None
        with target.open("rb") as stream:
            data = stream.read(MAX_RECEIPT_BYTES + 1)
        if len(data) > MAX_RECEIPT_BYTES:
            return None
        payload = _validate(json.loads(data))
        if payload["result_sha256"] != image_digest(image_path):
            return None
        return payload
    except (OSError, ValueError, RecursionError):
        return None
