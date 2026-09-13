"""Core orchestration for opaque module-owned project documents."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from studio_projects import ProjectRecord, ProjectStore


class ProjectDocumentError(ValueError):
    pass


class ProjectDocumentReadOnlyError(ProjectDocumentError):
    pass


@dataclass(frozen=True, slots=True)
class PreparedProjectDocument:
    version: int
    state: dict[str, Any]

    def __post_init__(self) -> None:
        if type(self.version) is not int or not 1 <= self.version <= 65535:
            raise ProjectDocumentError("Prepared document version is invalid")
        if not isinstance(self.state, dict):
            raise ProjectDocumentError("Prepared document state must be an object")


@dataclass(frozen=True, slots=True)
class ProjectDocumentSession:
    record: ProjectRecord
    state: dict[str, Any]
    editable: bool
    reason: str = ""


class ProjectDocumentAdapter(Protocol):
    module_id: str
    document_type: str
    current_version: int

    def open_state(self, state: dict[str, Any], version: int) -> dict[str, Any]: ...
    def prepare_save(
        self, state: dict[str, Any], source_version: int | None,
    ) -> PreparedProjectDocument: ...
    def before_save(
        self, store: ProjectStore, existing: ProjectRecord | None,
        prepared: PreparedProjectDocument,
    ) -> None: ...


def _copy_state(value: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ProjectDocumentError("Document state must contain JSON values only") from exc


class ProjectDocumentService:
    """Apply module adapters around generic ProjectStore persistence."""

    def __init__(self, store: ProjectStore, adapters=()) -> None:
        if not isinstance(store, ProjectStore):
            raise TypeError("store must be a ProjectStore")
        self.store = store
        self._adapters: dict[tuple[str, str], ProjectDocumentAdapter] = {}
        for adapter in tuple(adapters):
            module_id = getattr(adapter, "module_id", None)
            document_type = getattr(adapter, "document_type", None)
            current_version = getattr(adapter, "current_version", None)
            if (
                not isinstance(module_id, str) or not module_id
                or not isinstance(document_type, str) or not document_type
                or type(current_version) is not int or not 1 <= current_version <= 65535
                or not all(callable(getattr(adapter, name, None)) for name in (
                    "open_state", "prepare_save", "before_save",
                ))
            ):
                raise TypeError("Invalid project document adapter")
            key = (module_id, document_type)
            if key in self._adapters:
                raise ValueError("Duplicate project document adapter")
            self._adapters[key] = adapter

    def _adapter(self, record: ProjectRecord):
        return self._adapters.get((record.module_id, record.document_type))

    @staticmethod
    def _read_only(record: ProjectRecord, reason: str) -> ProjectDocumentSession:
        return ProjectDocumentSession(record, _copy_state(record.state), False, reason)

    def open(self, project_id: str) -> ProjectDocumentSession:
        record = self.store.load(project_id)
        adapter = self._adapter(record)
        if adapter is None:
            return self._read_only(record, "module_unavailable")
        if record.document_version > adapter.current_version:
            return self._read_only(record, "newer_document_version")
        try:
            state = adapter.open_state(_copy_state(record.state), record.document_version)
        except Exception as exc:
            raise ProjectDocumentError("Document adapter rejected stored state") from exc
        if not isinstance(state, dict):
            raise ProjectDocumentError("Document adapter returned invalid state")
        return ProjectDocumentSession(record, _copy_state(state), True)

    def create(
        self, module_id: str, document_type: str, name: str, state: dict[str, Any],
    ) -> ProjectRecord:
        adapter = self._adapters.get((module_id, document_type))
        if adapter is None:
            raise ProjectDocumentReadOnlyError("Module document adapter is unavailable")
        try:
            prepared = adapter.prepare_save(_copy_state(state), None)
        except Exception as exc:
            raise ProjectDocumentError("Document adapter rejected new state") from exc
        self._validate_prepared(adapter, prepared, None)
        return self.store.create(
            module_id, name, prepared.state,
            document_type=document_type, document_version=prepared.version,
        )

    def save(self, project_id: str, name: str, state: dict[str, Any]) -> ProjectRecord:
        existing = self.store.load(project_id)
        adapter = self._adapter(existing)
        if adapter is None:
            raise ProjectDocumentReadOnlyError("Module document adapter is unavailable")
        if existing.document_version > adapter.current_version:
            raise ProjectDocumentReadOnlyError("Document version is newer than the installed module")
        try:
            prepared = adapter.prepare_save(_copy_state(state), existing.document_version)
        except Exception as exc:
            raise ProjectDocumentError("Document adapter rejected save state") from exc
        self._validate_prepared(adapter, prepared, existing.document_version)
        try:
            adapter.before_save(self.store, existing, prepared)
        except Exception as exc:
            raise ProjectDocumentError("Document adapter pre-save migration failed") from exc
        return self.store.save(
            existing.project_id, existing.module_id, name, prepared.state,
            document_type=existing.document_type, document_version=prepared.version,
        )

    @staticmethod
    def _validate_prepared(adapter, prepared, source_version: int | None) -> None:
        if not isinstance(prepared, PreparedProjectDocument):
            raise ProjectDocumentError("Document adapter returned invalid prepared state")
        if prepared.version != adapter.current_version:
            raise ProjectDocumentError("Document adapter did not prepare its current version")
        if source_version is not None and prepared.version < source_version:
            raise ProjectDocumentError("Document adapter attempted a version downgrade")
