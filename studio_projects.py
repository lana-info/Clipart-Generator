"""Bounded, JSON-only storage for Studio projects.

This is deliberately a persistence boundary, not a runtime boundary: loading a
project only parses and validates its stored JSON and never imports modules,
constructs pages, or starts jobs.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from studio_workflow_identity import LEGACY_WORKFLOW_IDS


SCHEMA_VERSION = 2
LEGACY_SCHEMA_VERSION = 1
# Keep the same per-file ceiling as the existing V3 draft boundary.
MAX_PROJECT_BYTES = 2 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_NAME_LENGTH = 200
_MODULE_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_DOCUMENT_TYPE = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
_FORBIDDEN_KEY_PARTS = (
    "apikey", "token", "password", "secret", "credential", "authorization", "bearer",
)
_OPAQUE_FILENAME_EXTENSIONS = frozenset({
    "ai", "bmp", "csv", "docx", "gif", "jpeg", "jpg", "json", "md", "pdf",
    "png", "psd", "svg", "tif", "tiff", "txt", "webp", "xls", "xlsx", "zip",
})
_RECORD_KEYS_V1 = frozenset({"schema_version", "project_id", "module_id", "name", "updated_at", "state"})
_RECORD_KEYS_V2 = frozenset({
    "schema_version", "project_id", "module_id", "document_type", "document_version",
    "name", "updated_at", "state",
})


class ProjectStoreError(ValueError):
    """A project cannot safely be saved or loaded."""


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    project_id: str
    module_id: str
    document_type: str
    document_version: int
    name: str
    updated_at: str
    state: dict[str, Any]


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProjectStoreError("Project JSON contains duplicate keys")
        result[key] = value
    return result


class ProjectStore:
    """A single-process store rooted at a caller-supplied dedicated directory."""

    def __init__(self, root: str | os.PathLike[str]):
        supplied_root = Path(root).absolute()
        if supplied_root == Path(supplied_root.anchor) or supplied_root.is_symlink():
            raise ProjectStoreError("Project store root must be a dedicated non-symlink directory")
        self.root = supplied_root.resolve(strict=False)
        self.root.mkdir(parents=True, exist_ok=True)
        self._assert_root()

    def create(
        self, module_id: str, name: str, state: dict[str, Any], *,
        document_type: str = "project", document_version: int = 1,
    ) -> ProjectRecord:
        """Create a new UUID-addressed project without running any module code."""
        return self._write(
            str(uuid.uuid4()), module_id, name, state,
            document_type=document_type, document_version=document_version, must_exist=False,
        )

    def save(
        self, project_id: str, module_id: str, name: str, state: dict[str, Any], *,
        document_type: str = "project", document_version: int = 1,
    ) -> ProjectRecord:
        """Atomically overwrite an existing project after validating its envelope."""
        return self._write(
            project_id, module_id, name, state,
            document_type=document_type, document_version=document_version, must_exist=True,
        )

    def load(self, project_id: str) -> ProjectRecord:
        """Return validated JSON state only; this method never invokes jobs or runtime code."""
        project_id = self._project_id(project_id)
        return self._read(self._path_for(project_id), expected_id=project_id)

    def recent(self, limit: int | None = 3) -> list[ProjectRecord]:
        """Newest valid projects, while leaving all project files retained on disk."""
        if limit is not None and (type(limit) is not int or limit < 0):
            raise ProjectStoreError("Recent project limit must be a non-negative integer or None")
        self._assert_root()
        records: list[ProjectRecord] = []
        try:
            entries = list(self.root.iterdir())
        except OSError as exc:
            raise ProjectStoreError("Project store cannot be read") from exc
        for path in entries:
            if path.suffix != ".json" or path.is_symlink():
                continue
            try:
                self._project_id(path.stem)
                records.append(self._read(path, expected_id=path.stem))
            except ProjectStoreError:
                # A damaged project must not break the project chooser.  It
                # remains available for an explicit load error and recovery.
                continue
        records.sort(key=lambda record: (record.updated_at, record.project_id), reverse=True)
        return records if limit is None else records[:limit]

    def _write(
        self, project_id: str, module_id: str, name: str, state: dict[str, Any], *,
        document_type: str, document_version: int, must_exist: bool,
    ) -> ProjectRecord:
        project_id = self._project_id(project_id)
        module_id = self._module_id(module_id)
        document_type = self._document_type(document_type)
        document_version = self._document_version(document_version)
        name = self._name(name)
        self._validate_state(state)
        self._assert_root()
        destination = self._path_for(project_id)
        exists = self._existing_destination(destination)
        if must_exist and not exists:
            raise ProjectStoreError("Project does not exist")
        if not must_exist and exists:
            raise ProjectStoreError("Project already exists")
        if exists:
            # Envelope validation happens before any temporary file or replace;
            # unknown/future schemas and newer document data are never silently overwritten.
            existing = self._read(destination, expected_id=project_id)
            if existing.document_type != document_type:
                raise ProjectStoreError("Project document identity cannot change")
            legacy_mode_switch = (
                existing.document_type == document_type == "project"
                and existing.document_version == document_version == 1
                and existing.module_id in LEGACY_WORKFLOW_IDS
                and module_id in LEGACY_WORKFLOW_IDS
            )
            if existing.module_id != module_id and not legacy_mode_switch:
                raise ProjectStoreError("Project document identity cannot change")
            if existing.document_version > document_version:
                raise ProjectStoreError("Project document version is newer and read-only")
        record = ProjectRecord(
            project_id, module_id, document_type, document_version, name,
            self._now(), self._copy_state(state),
        )
        payload = self._encode(record)
        self._atomic_replace(destination, payload)
        return record

    def _assert_root(self) -> None:
        try:
            self.root.lstat()
        except OSError as exc:
            raise ProjectStoreError("Project store root is unavailable") from exc
        if self.root.is_symlink() or not self.root.is_dir():
            raise ProjectStoreError("Project store root must be a non-symlink directory")

    def project_path(self, project_id: str) -> Path:
        """Return the validated envelope path for trusted Core document services."""
        return self._path_for(self._project_id(project_id))

    def _path_for(self, project_id: str) -> Path:
        self._assert_root()
        return self.root / f"{project_id}.json"

    def _existing_destination(self, path: Path) -> bool:
        try:
            path.lstat()
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise ProjectStoreError("Project path cannot be inspected") from exc
        if path.is_symlink():
            raise ProjectStoreError("Project path must not be a symlink")
        if not os.path.isfile(path):
            raise ProjectStoreError("Project path is not a regular file")
        return True

    def _read(self, path: Path, *, expected_id: str | None = None) -> ProjectRecord:
        self._assert_root()
        self._existing_destination(path)
        try:
            with path.open("rb") as stream:
                raw = stream.read(MAX_PROJECT_BYTES + 1)
        except OSError as exc:
            raise ProjectStoreError("Project cannot be read") from exc
        if len(raw) > MAX_PROJECT_BYTES:
            raise ProjectStoreError("Project is corrupt: file exceeds size limit")
        try:
            value = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicate_keys,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
            record = self._record_from_json(value)
            if expected_id is not None and record.project_id != expected_id:
                raise ProjectStoreError("Project is corrupt: filename and project id differ")
            return record
        except ProjectStoreError:
            raise
        except (UnicodeDecodeError, ValueError, TypeError, RecursionError, json.JSONDecodeError) as exc:
            raise ProjectStoreError("Project is corrupt or invalid JSON") from exc

    def _record_from_json(self, value: Any) -> ProjectRecord:
        if not isinstance(value, dict):
            raise ProjectStoreError("Project is corrupt: record must be an object")
        schema_version = value.get("schema_version")
        if type(schema_version) is not int or schema_version not in {LEGACY_SCHEMA_VERSION, SCHEMA_VERSION}:
            raise ProjectStoreError("Project schema version is unsupported")
        expected_keys = _RECORD_KEYS_V1 if schema_version == LEGACY_SCHEMA_VERSION else _RECORD_KEYS_V2
        if set(value) != expected_keys:
            raise ProjectStoreError("Project schema is unknown or incomplete")
        project_id = self._project_id(value["project_id"])
        module_id = self._module_id(value["module_id"])
        document_type = (
            "project" if schema_version == LEGACY_SCHEMA_VERSION
            else self._document_type(value["document_type"])
        )
        document_version = (
            1 if schema_version == LEGACY_SCHEMA_VERSION
            else self._document_version(value["document_version"])
        )
        name = self._name(value["name"])
        updated_at = self._timestamp(value["updated_at"])
        state = value["state"]
        self._validate_state(state)
        return ProjectRecord(
            project_id, module_id, document_type, document_version, name, updated_at,
            self._copy_state(state),
        )

    def _encode(self, record: ProjectRecord) -> bytes:
        try:
            value = {
                "schema_version": SCHEMA_VERSION,
                "project_id": record.project_id,
                "module_id": record.module_id,
                "document_type": record.document_type,
                "document_version": record.document_version,
                "name": record.name,
                "updated_at": record.updated_at,
                "state": record.state,
            }
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                                 allow_nan=False).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ProjectStoreError("Project state must contain JSON values only") from exc
        if len(payload) > MAX_PROJECT_BYTES:
            raise ProjectStoreError("Project exceeds size limit")
        return payload

    def _atomic_replace(self, destination: Path, payload: bytes) -> None:
        self._assert_root()
        temporary: Path | None = None
        try:
            fd, temporary_name = tempfile.mkstemp(prefix=".project-", suffix=".tmp", dir=self.root)
            temporary = Path(temporary_name)
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            # Do not replace an attacker-controlled symlink if one appeared
            # after validation.  os.replace does not follow it, but removing it
            # would still violate the store's symlink boundary.
            self._existing_destination(destination) if destination.exists() or destination.is_symlink() else None
            os.replace(temporary, destination)
            temporary = None
        except ProjectStoreError:
            raise
        except OSError as exc:
            raise ProjectStoreError("Project could not be saved") from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _project_id(value: Any) -> str:
        if not isinstance(value, str):
            raise ProjectStoreError("Project id must be a UUID")
        try:
            parsed = uuid.UUID(value)
        except (ValueError, AttributeError) as exc:
            raise ProjectStoreError("Project id must be a UUID") from exc
        if str(parsed) != value:
            raise ProjectStoreError("Project id must be a canonical UUID")
        return value

    @staticmethod
    def _module_id(value: Any) -> str:
        if not isinstance(value, str) or not _MODULE_ID.fullmatch(value):
            raise ProjectStoreError("Module id is invalid")
        return value

    @staticmethod
    def _document_type(value: Any) -> str:
        if not isinstance(value, str) or not _DOCUMENT_TYPE.fullmatch(value):
            raise ProjectStoreError("Document type is invalid")
        return value

    @staticmethod
    def _document_version(value: Any) -> int:
        if type(value) is not int or not 1 <= value <= 65535:
            raise ProjectStoreError("Document version is invalid")
        return value

    @staticmethod
    def _name(value: Any) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME_LENGTH:
            raise ProjectStoreError("Project name is invalid")
        if any(ord(character) < 32 for character in value):
            raise ProjectStoreError("Project name is invalid")
        return value

    @staticmethod
    def _timestamp(value: Any) -> str:
        if not isinstance(value, str):
            raise ProjectStoreError("Project timestamp is invalid")
        try:
            parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
        except ValueError as exc:
            raise ProjectStoreError("Project timestamp is invalid") from exc
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ProjectStoreError("Project timestamp must include timezone")
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def _validate_state(self, value: Any) -> None:
        if not isinstance(value, dict):
            raise ProjectStoreError("Project state must be a JSON object")
        self._validate_json(value, depth=0, ancestors=set())

    def _validate_json(self, value: Any, *, depth: int, ancestors: set[int],
                       path: tuple[str, ...] = ()) -> None:
        if depth > MAX_JSON_DEPTH:
            raise ProjectStoreError("Project state exceeds nesting limit")
        if value is None or type(value) in (bool, int, str):
            return
        if type(value) is float:
            if value != value or value in (float("inf"), float("-inf")):
                raise ProjectStoreError("Project state must contain JSON values only")
            return
        if isinstance(value, list):
            self._validate_container(value, depth, ancestors, path)
            return
        if isinstance(value, dict):
            self._validate_container(value, depth, ancestors, path)
            return
        raise ProjectStoreError("Project state must contain JSON values only")

    @staticmethod
    def _opaque_label_key(value: str) -> bool:
        if any(separator in value for separator in ("/", "\\", ":")):
            return True
        if "." not in value:
            return False
        extension = value.rsplit(".", 1)[-1].casefold()
        return extension in _OPAQUE_FILENAME_EXTENSIONS

    def _validate_container(self, value: list[Any] | dict[str, Any], depth: int,
                            ancestors: set[int], path: tuple[str, ...]) -> None:
        marker = id(value)
        if marker in ancestors:
            raise ProjectStoreError("Project state must not contain cycles")
        ancestors.add(marker)
        try:
            if isinstance(value, dict):
                for key, item in value.items():
                    if not isinstance(key, str):
                        raise ProjectStoreError("Project state object keys must be strings")
                    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
                    opaque_label_key = self._opaque_label_key(key)
                    if not opaque_label_key and any(part in normalized for part in _FORBIDDEN_KEY_PARTS):
                        raise ProjectStoreError("Project state contains a forbidden credential field")
                    self._validate_json(item, depth=depth + 1, ancestors=ancestors, path=path + (key,))
            else:
                for item in value:
                    self._validate_json(item, depth=depth + 1, ancestors=ancestors, path=path + ('[]',))
        finally:
            ancestors.remove(marker)

    def _copy_state(self, state: dict[str, Any]) -> dict[str, Any]:
        # Canonical JSON copying prevents caller mutation from changing a saved
        # record and proves the exposed state is JSON data rather than runtime objects.
        return json.loads(json.dumps(state, ensure_ascii=False, allow_nan=False))
