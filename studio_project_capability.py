"""Core-scoped projects.v1 facade over ProjectDocumentService."""
from __future__ import annotations

from studio_project_api import ProjectCapabilityError, ProjectDocument
from studio_project_documents import ProjectDocumentError, ProjectDocumentService


class ScopedProjectCapability:
    __slots__ = ("_module_id", "_service")

    def __init__(self, module_id: str, service: ProjectDocumentService) -> None:
        if not isinstance(module_id, str) or not module_id:
            raise TypeError("module_id is required")
        if not isinstance(service, ProjectDocumentService):
            raise TypeError("service must be ProjectDocumentService")
        self._module_id = module_id
        self._service = service

    @staticmethod
    def _view(record, *, state=None, editable=True, reason="") -> ProjectDocument:
        return ProjectDocument(
            record.project_id, record.module_id, record.document_type,
            record.document_version, record.name,
            record.state if state is None else state,
            editable=editable, read_only_reason=reason,
        )

    def create(self, document_type: str, name: str, state: dict) -> ProjectDocument:
        try:
            record = self._service.create(self._module_id, document_type, name, state)
        except (ProjectDocumentError, ValueError) as exc:
            raise ProjectCapabilityError("Project document could not be created") from exc
        return self._view(record)

    def _owned_record(self, project_id: str):
        try:
            record = self._service.store.load(project_id)
        except ValueError as exc:
            raise ProjectCapabilityError("Project document is unavailable") from exc
        if record.module_id != self._module_id:
            raise ProjectCapabilityError("Project belongs to another module")
        return record

    def open(self, project_id: str) -> ProjectDocument:
        record = self._owned_record(project_id)
        try:
            session = self._service.open(record.project_id)
        except ProjectDocumentError as exc:
            raise ProjectCapabilityError("Project document could not be opened") from exc
        return self._view(
            session.record, state=session.state, editable=session.editable,
            reason=session.reason,
        )

    def save(self, project_id: str, name: str, state: dict) -> ProjectDocument:
        self._owned_record(project_id)
        try:
            record = self._service.save(project_id, name, state)
        except (ProjectDocumentError, ValueError) as exc:
            raise ProjectCapabilityError("Project document could not be saved") from exc
        return self._view(record)
