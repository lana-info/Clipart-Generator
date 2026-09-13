"""Hash-bound generation intent/result metadata, not a QC certificate.

Pending records precede paid submission. Schema v2 binds result intent and optional
chroma provenance to raw/final PNG bytes without storing credentials or prompt text.
Legacy schema v1 remains readable for chroma provenance only. These records do not
replace the provider job journal or authorize resubmission.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from contextlib import contextmanager
import re
import tempfile

from chroma_key import KEY_COLORS
from chroma_provenance import image_digest
from processing_contract import publish_atomic

_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS_V1 = {"schema_version", "requested_color", "prompt_sha256", "source_sha256"}
_FIELDS_V2 = _FIELDS_V1 | {"stage", "result_kind"}


def record_path(image_path, *, pending=False) -> Path:
    path = Path(image_path)
    suffix = ".generation-request.json" if pending else ".generation.json"
    return path.with_name(path.name + suffix)


def ensure_record_paths_available(*image_paths) -> None:
    """Fail before provider submission if any planned sidecar path is occupied."""
    for image_path in image_paths:
        for pending in (True, False):
            target = record_path(image_path, pending=pending)
            if target.exists() or target.is_symlink():
                raise FileExistsError(f"Generation record already exists: {target.name}")


def _validate(data, *, pending=False):
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int:
        raise ValueError("Invalid generation background record")
    version = data["schema_version"]
    if version == 1:
        if set(data) != _FIELDS_V1:
            raise ValueError("Invalid generation background record")
        if not isinstance(data["requested_color"], str) or data["requested_color"] not in KEY_COLORS:
            raise ValueError("Unsupported requested chroma colour")
    elif version == 2:
        if set(data) != _FIELDS_V2:
            raise ValueError("Invalid generation background record")
        if data["stage"] not in {"raw", "final"}:
            raise ValueError("Unsupported generation record stage")
        if pending and data["stage"] != "raw":
            raise ValueError("Pending generation record must describe raw output")
        color = data["requested_color"]
        if color is not None and (not isinstance(color, str) or color not in KEY_COLORS):
            raise ValueError("Unsupported requested chroma colour")
        from result_background_policy import keeps_background, validate_result_kind
        validate_result_kind(data["result_kind"])
        if keeps_background(data["result_kind"]) and color is not None:
            raise ValueError("Surface generation cannot request chroma colour")
    else:
        raise ValueError("Unsupported generation background record")
    for field in ("prompt_sha256", "source_sha256"):
        value = data[field]
        if field == "source_sha256" and pending and value is None:
            continue
        if not isinstance(value, str) or not _HASH.fullmatch(value):
            raise ValueError("Invalid generation background hash")
    return dict(data)


def _write(target, data, *, overwrite=False):
    # Reuse the project's atomic publication contract. Normal generation records
    # are no-clobber; trusted local edits may explicitly replace a captured v2 record.
    stage = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".generation-", delete=False) as stream:
            stage = Path(stream.name)
            stream.write((json.dumps(data, indent=2) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
        publish_atomic(stage, target, overwrite=overwrite)
    finally:
        if stage is not None:
            stage.unlink(missing_ok=True)


def write_generation_intent(image_path, *, color: str | None, prompt: str,
                            result_kind: str = "legacy") -> dict:
    from result_background_policy import validate_result_kind
    result_kind = validate_result_kind(result_kind)
    data = _validate({
        "schema_version": 2,
        "stage": "raw",
        "result_kind": result_kind,
        "requested_color": color,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "source_sha256": None,
    }, pending=True)
    _write(record_path(image_path, pending=True), data)
    return data


def discard_generation_intent(image_path, intent: dict) -> bool:
    """Remove only the caller-owned pending intent after a post-payment bind failure."""
    target = record_path(image_path, pending=True)
    if not target.exists() and not target.is_symlink():
        return False
    if target.is_symlink():
        raise ValueError("Недопустимая ссылка в сведениях о генерации")
    try:
        raw = target.read_bytes()
        if len(raw) > 4096:
            raise ValueError("Record too large")
        existing = _validate(json.loads(raw), pending=True)
        expected = _validate(intent, pending=True)
    except (OSError, ValueError, RecursionError, json.JSONDecodeError) as error:
        raise ValueError("Pending-сведения генерации изменились; удаление остановлено") from error
    if existing != expected:
        raise ValueError("Pending-сведения генерации изменились; удаление остановлено")
    target.unlink()
    return True


def bind_generation_record(image_path, intent: dict, *, stage: str = "raw") -> None:
    pending = isinstance(intent, dict) and intent.get("source_sha256") is None
    data = _validate(intent, pending=pending)
    if data["schema_version"] == 1:
        if stage != "raw":
            raise ValueError("Legacy generation record cannot describe final output")
    else:
        if stage not in {"raw", "final"}:
            raise ValueError("Unsupported generation record stage")
        data["stage"] = stage
    data["source_sha256"] = image_digest(image_path)
    _write(record_path(image_path), _validate(data))


def _load_bound_record(image_path):
    path = record_path(image_path)
    if path.is_symlink():
        raise ValueError("Недопустимая ссылка в сведениях о генерации")
    try:
        with path.open("rb") as stream:
            raw = stream.read(4097)
    except FileNotFoundError:
        pending = record_path(image_path, pending=True)
        if pending.exists() or pending.is_symlink():
            raise ValueError("Сведения генерации ещё не привязаны к исходному изображению")
        return None
    try:
        if len(raw) > 4096:
            raise ValueError("Record too large")
        data = _validate(json.loads(raw))
        if data["source_sha256"] != image_digest(image_path):
            raise ValueError("Source changed")
        return data
    except (OSError, ValueError, RecursionError) as error:
        raise ValueError(
            "Сведения генерации повреждены или относятся к другому файлу; "
            "исходник сохранён, автоматический выбор по этим сведениям остановлен"
        ) from error


def load_generation_color(image_path) -> str | None:
    """Return chroma intent only for raw sources; final PNGs must never be re-keyed."""
    data = _load_bound_record(image_path)
    if data is None:
        return None
    if data["schema_version"] == 1:
        return data["requested_color"]
    if data["stage"] != "raw":
        return None
    return data["requested_color"]


def load_generation_result_metadata(image_path) -> dict | None:
    """Return bounded v2 result intent/stage; legacy or missing records stay unknown."""
    data = _load_bound_record(image_path)
    if data is None or data["schema_version"] == 1:
        return None
    return {"result_kind": data["result_kind"], "stage": data["stage"]}


def load_generation_result_kind(image_path) -> str | None:
    """Return hash-bound result intent when schema v2 provides it; never guess legacy files."""
    metadata = load_generation_result_metadata(image_path)
    return metadata["result_kind"] if metadata is not None else None


def capture_generation_record(image_path) -> dict | None:
    """Capture a currently valid v2 record before a trusted local edit/copy."""
    data = _load_bound_record(image_path)
    if data is None or data["schema_version"] != 2:
        return None
    return dict(data)



def _file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_marker_path(destination: str | Path) -> Path:
    target = Path(destination)
    identity = hashlib.sha256(
        str(target.resolve(strict=False)).encode("utf-8")
    ).hexdigest()[:16]
    return target.parent / f".vibix-generation-copy-{identity}.json"


def _write_copy_marker(marker: Path, payload: dict, *, overwrite: bool) -> None:
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=marker.parent, prefix=f".{marker.name}.", suffix=".tmp", delete=False
        ) as stream:
            staged = Path(stream.name)
            stream.write((json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
            stream.flush(); os.fsync(stream.fileno())
        publish_atomic(staged, marker, overwrite=overwrite)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _generation_lock_path(image_path: str | Path) -> Path:
    target = record_path(image_path)
    return target.with_name(target.name + ".lock")


@contextmanager
def generation_transaction_lock(image_path: str | Path):
    """Hold a cross-process advisory lock for one PNG/provenance transaction.

    The lock file is intentionally persistent. Ownership lives on the open file
    descriptor, so the OS releases it automatically if the process exits or crashes.
    """
    lock_path = _generation_lock_path(image_path)
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    locked = False
    try:
        if os.name == "nt":
            import msvcrt
            if os.fstat(fd).st_size < 1:
                os.lseek(fd, 0, os.SEEK_SET)
                os.write(fd, b"\0")
                os.fsync(fd)
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError("Сведения генерации уже изменяются другим процессом") from error
            locked = True
        else:
            import fcntl
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError("Сведения генерации уже изменяются другим процессом") from error
            locked = True
        yield
    finally:
        if locked:
            try:
                if os.name == "nt":
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)


def _recover_generation_copy_unlocked(destination: str | Path) -> bool:
    """Recover a previous Save As after the destination advisory lock is held."""
    target = Path(destination)
    marker = _copy_marker_path(target)
    if not marker.is_file():
        return False
    sidecar = record_path(target)
    try:
        raw = marker.read_bytes()
        if len(raw) > 4096:
            raise ValueError("marker too large")
        payload = json.loads(raw)
        if (
            payload.get("schema_version") != 1
            or payload.get("phase") not in {"prepared", "committed"}
            or not _HASH.fullmatch(str(payload.get("image_sha256") or ""))
            or not _HASH.fullmatch(str(payload.get("record_sha256") or ""))
        ):
            raise ValueError("invalid marker")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise OSError("Не удалось восстановить прерванное сохранение PNG/provenance") from error

    expected = ((target, payload["image_sha256"]), (sidecar, payload["record_sha256"]))
    if payload["phase"] == "committed":
        if not all(path.is_file() and _file_sha256(path) == digest for path, digest in expected):
            raise OSError("Сохранение PNG/provenance было изменено извне; восстановление остановлено")
        marker.unlink(missing_ok=True)
        return True

    for path, digest in expected:
        if path.exists() or path.is_symlink():
            if path.is_symlink() or not path.is_file() or _file_sha256(path) != digest:
                raise OSError("Частично сохранённый PNG/provenance изменён извне; удаление остановлено")
            path.unlink()
    marker.unlink(missing_ok=True)
    return True


def recover_generation_copy(destination: str | Path) -> bool:
    """Recover an interrupted Save As only after acquiring its advisory lock."""
    if not _copy_marker_path(destination).is_file():
        return False
    with generation_transaction_lock(destination):
        return _recover_generation_copy_unlocked(destination)


def publish_generation_copy(staged_image_path: str | Path, destination: str | Path,
                            captured: dict, *, stage: str = "final") -> Path:
    """Publish a new PNG and its v2 sidecar as one locked recoverable unit."""
    source = Path(staged_image_path)
    target = Path(destination)
    if not source.is_file():
        raise FileNotFoundError(source)
    if target.suffix.casefold() != ".png":
        raise ValueError("Portable generation copy must be PNG")
    if not target.parent.is_dir():
        raise FileNotFoundError("destination directory does not exist")
    with generation_transaction_lock(target):
        _recover_generation_copy_unlocked(target)
        if target.exists() or target.is_symlink():
            raise FileExistsError(f"refusing to overwrite existing output: {target}")
        ensure_record_paths_available(target)
        staged_record = stage_rebound_generation_record(
            source, captured, stage=stage, directory=target.parent
        )
        sidecar = record_path(target)
        marker = _copy_marker_path(target)
        payload = {
            "schema_version": 1,
            "phase": "prepared",
            "image_sha256": _file_sha256(source),
            "record_sha256": _file_sha256(staged_record),
        }
        _write_copy_marker(marker, payload, overwrite=False)
        image_published = False
        sidecar_published = False
        try:
            publish_atomic(source, target, overwrite=False); image_published = True
            publish_atomic(staged_record, sidecar, overwrite=False); sidecar_published = True
            payload["phase"] = "committed"
            _write_copy_marker(marker, payload, overwrite=True)
            marker.unlink(missing_ok=True)
            return target
        except Exception:
            if sidecar_published and sidecar.is_file() and _file_sha256(sidecar) == payload["record_sha256"]:
                sidecar.unlink()
            if image_published and target.is_file() and _file_sha256(target) == payload["image_sha256"]:
                target.unlink()
            marker.unlink(missing_ok=True)
            raise
        finally:
            staged_record.unlink(missing_ok=True)


def _rebound_generation_data(image_path, captured: dict, *, stage: str = "final") -> dict:
    data = _validate(captured, pending=False)
    if data["schema_version"] != 2:
        raise ValueError("Legacy generation record has no confirmed result kind")
    if stage not in {"raw", "final"}:
        raise ValueError("Unsupported generation record stage")
    data["stage"] = stage
    data["source_sha256"] = image_digest(image_path)
    return _validate(data)


def stage_rebound_generation_record(image_path, captured: dict, *, stage: str = "final",
                                    directory: str | Path | None = None) -> Path:
    """Stage a complete rebound v2 record without publishing it."""
    data = _rebound_generation_data(image_path, captured, stage=stage)
    parent = Path(directory) if directory is not None else Path(image_path).parent
    with tempfile.NamedTemporaryFile(
        dir=parent, prefix=".generation-", suffix=".tmp", delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write((json.dumps(data, indent=2) + "\n").encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    return temporary


def rebind_generation_record(image_path, captured: dict, *, stage: str = "final",
                             overwrite: bool = True) -> None:
    """Bind captured v2 lineage to current bytes after a trusted local edit/copy."""
    data = _rebound_generation_data(image_path, captured, stage=stage)
    target = record_path(image_path)
    if not overwrite:
        _write(target, data, overwrite=False)
        return
    with generation_transaction_lock(image_path):
        if not target.exists() or target.is_symlink():
            raise ValueError("Сведения генерации исчезли или стали недопустимой ссылкой")
        try:
            raw = target.read_bytes()
            if len(raw) > 4096:
                raise ValueError("Record too large")
            existing = _validate(json.loads(raw))
        except (OSError, ValueError, RecursionError, json.JSONDecodeError) as error:
            raise ValueError("Сведения генерации изменились; обновление остановлено") from error
        if existing != captured:
            raise ValueError("Сведения генерации изменились; обновление остановлено")
        _write(target, data, overwrite=True)
