from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from studio_project_documents import (
    PreparedProjectDocument,
    ProjectDocumentReadOnlyError,
    ProjectDocumentService,
)
from studio_projects import ProjectStore


class FakeTextAdapter:
    module_id = "text-probe"
    document_type = "note"
    current_version = 2

    def __init__(self):
        self.open_calls = 0
        self.before_save_calls = 0

    def open_state(self, state, version):
        self.open_calls += 1
        return dict(state)

    def prepare_save(self, state, source_version):
        return PreparedProjectDocument(self.current_version, dict(state))

    def before_save(self, store, existing, prepared):
        self.before_save_calls += 1


def test_missing_adapter_opens_opaque_document_read_only_without_mutation():
    with tempfile.TemporaryDirectory() as temp:
        store = ProjectStore(Path(temp) / "projects")
        record = store.create(
            "missing-module", "Unknown", {"opaque": {"value": 7}},
            document_type="note", document_version=4,
        )
        path = store.project_path(record.project_id)
        before = path.read_bytes()
        service = ProjectDocumentService(store, ())
        session = service.open(record.project_id)
        assert session.editable is False
        assert session.reason == "module_unavailable"
        assert session.state == record.state
        assert path.read_bytes() == before
        with pytest.raises(ProjectDocumentReadOnlyError):
            service.save(record.project_id, "Unknown", {"opaque": {"value": 8}})
        assert path.read_bytes() == before


def test_newer_document_version_is_read_only_without_calling_adapter():
    with tempfile.TemporaryDirectory() as temp:
        store = ProjectStore(Path(temp) / "projects")
        record = store.create(
            "text-probe", "Future", {"value": 3},
            document_type="note", document_version=3,
        )
        path = store.project_path(record.project_id)
        before = path.read_bytes()
        adapter = FakeTextAdapter()
        service = ProjectDocumentService(store, (adapter,))
        session = service.open(record.project_id)
        assert session.editable is False
        assert session.reason == "newer_document_version"
        assert adapter.open_calls == 0
        with pytest.raises(ProjectDocumentReadOnlyError):
            service.save(record.project_id, "Future", {"value": 2})
        assert adapter.before_save_calls == 0
        assert path.read_bytes() == before


def test_adapter_owns_document_validation_and_save_preparation():
    with tempfile.TemporaryDirectory() as temp:
        store = ProjectStore(Path(temp) / "projects")
        adapter = FakeTextAdapter()
        service = ProjectDocumentService(store, (adapter,))
        record = service.create("text-probe", "note", "Note", {"value": 1})
        assert record.document_version == 2
        session = service.open(record.project_id)
        assert session.editable is True
        assert session.state == {"value": 1}
        saved = service.save(record.project_id, "Note", {"value": 2})
        assert saved.document_version == 2
        assert saved.state == {"value": 2}
        assert adapter.open_calls == 1
        assert adapter.before_save_calls == 1


def test_v3_adapter_migrates_in_memory_and_backs_up_before_first_save():
    from v3_project_state import ProjectState, V3ProjectDocumentAdapter

    with tempfile.TemporaryDirectory() as temp:
        store = ProjectStore(Path(temp) / "projects")
        legacy = ProjectState().to_dict()
        legacy["clipart"]["export_membership"] = {
            "old.png": {"title": "Old", "included": False},
        }
        record = store.create("clipart", "Old", legacy)
        path = store.project_path(record.project_id)
        original = path.read_bytes()
        service = ProjectDocumentService(store, (V3ProjectDocumentAdapter("clipart"),))

        session = service.open(record.project_id)
        assert session.editable is True
        migrated = session.state["clipart"]["export_membership"]["old.png"]
        assert migrated["version"] == 2
        assert path.read_bytes() == original

        saved = service.save(record.project_id, "Old", session.state)
        backups = list(path.parent.glob("*.bak"))
        assert len(backups) == 1
        assert backups[0].read_bytes() == original
        assert saved.state == session.state


def test_v3_adapter_backup_failure_preserves_existing_envelope(monkeypatch):
    from studio_project_documents import ProjectDocumentError
    from v3_project_state import ProjectState, V3ProjectDocumentAdapter

    with tempfile.TemporaryDirectory() as temp:
        store = ProjectStore(Path(temp) / "projects")
        legacy = ProjectState().to_dict()
        legacy["clipart"]["export_membership"] = {
            "old.png": {"title": "Old", "included": False},
        }
        record = store.create("clipart", "Old", legacy)
        path = store.project_path(record.project_id)
        original = path.read_bytes()
        service = ProjectDocumentService(store, (V3ProjectDocumentAdapter("clipart"),))
        session = service.open(record.project_id)

        def fail(*_args, **_kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("studio_export_membership.backup_membership_migration", fail)
        with pytest.raises(ProjectDocumentError):
            service.save(record.project_id, "Old", session.state)
        assert path.read_bytes() == original
