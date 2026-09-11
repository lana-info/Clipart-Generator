"""Minimal generation intent and hash-bound chroma handoff, not a QC certificate.

Pending records precede paid submission. Completed records bind the requested
colour to downloaded source bytes. Neither contains credentials or prompt text.
They do not replace the provider job journal or authorize resubmission.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from chroma_key import KEY_COLORS
from chroma_provenance import image_digest
from processing_contract import publish_atomic

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {"schema_version", "requested_color", "prompt_sha256", "source_sha256"}


def record_path(image_path, *, pending=False) -> Path:
    path = Path(image_path)
    suffix = ".generation-request.json" if pending else ".generation.json"
    return path.with_name(path.name + suffix)


def _validate(data, *, pending=False):
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise ValueError("Invalid generation background record")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported generation background record")
    if not isinstance(data["requested_color"], str) or data["requested_color"] not in KEY_COLORS:
        raise ValueError("Unsupported requested chroma colour")
    for field in ("prompt_sha256", "source_sha256"):
        value = data[field]
        if field == "source_sha256" and pending and value is None:
            continue
        if not isinstance(value, str) or not _HASH.fullmatch(value):
            raise ValueError("Invalid generation background hash")
    return dict(data)


def _write(target, data):
    # Reuse the project's no-clobber publication contract. Never replace an
    # earlier attempt or a user's file when an output name collides.
    stage = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".generation-", delete=False) as stream:
            stage = Path(stream.name)
            stream.write((json.dumps(data, indent=2) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        publish_atomic(stage, target, overwrite=False)
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def write_generation_intent(image_path, *, color: str, prompt: str) -> dict:
    data = _validate({
        "schema_version": 1,
        "requested_color": color,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "source_sha256": None,
    }, pending=True)
    _write(record_path(image_path, pending=True), data)
    return data


def bind_generation_record(image_path, intent: dict) -> None:
    data = _validate(intent, pending=True)
    data["source_sha256"] = image_digest(image_path)
    _write(record_path(image_path), _validate(data))


def load_generation_color(image_path) -> str | None:
    """Missing is legacy; malformed/stale data must not pick a different key."""
    path = record_path(image_path)
    if path.is_symlink():
        raise ValueError("Недопустимая ссылка в сведениях о фоне генерации")
    try:
        with path.open("rb") as stream:
            raw = stream.read(4097)
    except FileNotFoundError:
        pending = record_path(image_path, pending=True)
        if pending.exists() or pending.is_symlink():
            raise ValueError("Фон генерации ещё не привязан к исходному изображению")
        return None
    try:
        if len(raw) > 4096:
            raise ValueError("Record too large")
        data = _validate(json.loads(raw))
        if data["source_sha256"] != image_digest(image_path):
            raise ValueError("Source changed")
        return data["requested_color"]
    except (OSError, ValueError, RecursionError) as error:
        raise ValueError(
            "Сведения о фоне генерации повреждены или относятся к другому файлу; "
            "исходник сохранён, автоматический выбор по этим сведениям остановлен"
        ) from error
