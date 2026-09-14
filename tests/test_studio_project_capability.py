from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from studio_project_api import ProjectCapabilityError
from studio_project_capability import ScopedProjectCapability
from studio_project_documents import PreparedProjectDocument, ProjectDocumentService
from studio_projects import ProjectStore


class TextAdapter:
    module_id = "text-probe"
    document_type = "note"
    current_version = 1

    def open_state(self, state, version):
        return dict(state)

    def prepare_save(self, state, source_version):
        return PreparedProjectDocument(1, dict(state))

    def before_save(self, store, existing, prepared):
        return None


def test_scoped_project_capability_cannot_cross_module_ownership():
    with tempfile.TemporaryDirectory() as temp:
        store = ProjectStore(Path(temp) / "projects")
        service = ProjectDocumentService(store, (TextAdapter(),))
        projects = ScopedProjectCapability("text-probe", service)
        created = projects.create("note", "Note", {"body": "hello"})
        assert created.module_id == "text-probe"
        assert created.document_type == "note"
        assert created.state == {"body": "hello"}
        assert not hasattr(created, "path")

        foreign = store.create(
            "clipart", "Foreign", {"safe": True},
            document_type="project", document_version=1,
        )
        with pytest.raises(ProjectCapabilityError):
            projects.open(foreign.project_id)
        with pytest.raises(ProjectCapabilityError):
            projects.save(foreign.project_id, "Foreign", {"safe": False})
