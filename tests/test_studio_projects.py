from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio_projects import ProjectStore, ProjectStoreError


class ProjectStoreTests(unittest.TestCase):
    def test_membership_paths_roundtrip_without_weakening_credential_guard(self):
        from v3_project_state import ProjectState, ProjectMode
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / 'projects')
            state = ProjectState(mode=ProjectMode.CLIPART)
            state.clipart.export_membership = {
                'secret-garden/result.png': {'title': 'Garden', 'included': True},
                'C:/Users/token/output/result.png': {'title': 'Garden', 'included': False},
            }
            record = store.create('clipart', 'Garden', state.to_dict())
            store.save(record.project_id, 'clipart', 'Garden', state.to_dict())
            restored = ProjectState.from_dict(ProjectStore(store.root).load(record.project_id).state)
            from studio_export_membership import validate_export_membership
            self.assertEqual(restored.clipart.export_membership,
                             validate_export_membership(state.clipart.export_membership))
            before = (store.root / f'{record.project_id}.json').read_bytes()
            for payload in (
                {'clipart': {'export_membership': {'x.png': {'api_key': 'fixture'}}}},
                {'elsewhere': {'export_membership': {'secret': 'fixture'}}},
                {'clipart': {'api_key': 'fixture', 'export_membership': {}}},
            ):
                with self.subTest(payload=payload), self.assertRaises(ProjectStoreError):
                    store.save(record.project_id, 'clipart', 'Garden', payload)
                self.assertEqual((store.root / f'{record.project_id}.json').read_bytes(), before)

    def test_round_trip_and_restart_load_json_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "projects"
            store = ProjectStore(root)
            saved = store.create("clipart", "Bird", {"prompt": "blue bird", "count": 2})

            self.assertEqual(saved.module_id, "clipart")
            self.assertEqual(saved.name, "Bird")
            self.assertEqual(store.load(saved.project_id).state, {"prompt": "blue bird", "count": 2})

            restarted = ProjectStore(root)
            loaded = restarted.load(saved.project_id)
            self.assertEqual(loaded.project_id, saved.project_id)
            self.assertEqual(loaded.state, saved.state)

    def test_recent_is_bounded_but_all_projects_remain_loadable(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            saved = [store.create("clipart", f"Project {index}", {"index": index}) for index in range(4)]

            self.assertEqual([item.name for item in store.recent()], ["Project 3", "Project 2", "Project 1"])
            self.assertEqual(len(store.recent(limit=99)), 4)
            self.assertEqual(store.load(saved[0].project_id).state, {"index": 0})

    def test_failed_atomic_save_preserves_existing_project(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            original = store.create("clipart", "Original", {"value": "old"})

            with patch("studio_projects.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaises(ProjectStoreError):
                    store.save(original.project_id, "clipart", "Changed", {"value": "new"})

            self.assertEqual(store.load(original.project_id).name, "Original")
            self.assertEqual(store.load(original.project_id).state, {"value": "old"})

    def test_unknown_schema_never_overwrites_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            original = store.create("clipart", "Original", {"value": "old"})
            path = store.root / f"{original.project_id}.json"
            path.write_text(json.dumps({"schema_version": 99}), encoding="utf-8")
            before = path.read_bytes()

            with self.assertRaisesRegex(ProjectStoreError, "schema"):
                store.save(original.project_id, "clipart", "Changed", {"value": "new"})

            self.assertEqual(path.read_bytes(), before)
            with self.assertRaisesRegex(ProjectStoreError, "schema"):
                store.load(original.project_id)

    def test_rejects_credentials_anywhere_in_state(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            with self.assertRaisesRegex(ProjectStoreError, "credential"):
                store.create("clipart", "Unsafe", {"nested": {"api_key": "not saved"}})
            with self.assertRaisesRegex(ProjectStoreError, "credential"):
                store.create("clipart", "Unsafe", {"items": [{"refresh_token": "not saved"}]})
            self.assertEqual(store.recent(), [])

    def test_rejects_cyclic_and_excessively_nested_state_as_store_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            cyclic: dict[str, object] = {}
            cyclic["self"] = cyclic
            with self.assertRaises(ProjectStoreError):
                store.create("clipart", "Cycle", cyclic)

            nested: dict[str, object] = {}
            cursor = nested
            for _ in range(65):
                child: dict[str, object] = {}
                cursor["child"] = child
                cursor = child
            with self.assertRaises(ProjectStoreError):
                store.create("clipart", "Deep", nested)

    def test_load_normalizes_timestamp_for_chronological_recent_sorting(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            first = store.create("clipart", "First", {"safe": True})
            second = store.create("clipart", "Second", {"safe": True})
            first_path = store.root / f"{first.project_id}.json"
            second_path = store.root / f"{second.project_id}.json"
            first_json = json.loads(first_path.read_text(encoding="utf-8"))
            second_json = json.loads(second_path.read_text(encoding="utf-8"))
            first_json["updated_at"] = "2026-01-01T02:00:00+02:00"
            second_json["updated_at"] = "2026-01-01T00:30:00Z"
            first_path.write_text(json.dumps(first_json), encoding="utf-8")
            second_path.write_text(json.dumps(second_json), encoding="utf-8")

            recent = store.recent()
            self.assertEqual([record.project_id for record in recent], [second.project_id, first.project_id])
            self.assertEqual(recent[1].updated_at, "2026-01-01T00:00:00.000000Z")

    def test_deep_corrupt_file_is_skipped_by_recent_and_load_is_clear_error(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            project_id = "123e4567-e89b-12d3-a456-426614174099"
            state = "{\"child\":" * 80 + "0" + "}" * 80
            payload = (
                '{"schema_version":1,"project_id":"' + project_id
                + '","module_id":"clipart","name":"Deep","updated_at":"2026-01-01T00:00:00Z","state":'
                + state + "}"
            )
            (store.root / f"{project_id}.json").write_text(payload, encoding="utf-8")

            self.assertEqual(store.recent(), [])
            with self.assertRaises(ProjectStoreError):
                store.load(project_id)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unavailable")
    def test_symlinks_never_escape_or_are_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "projects"
            store = ProjectStore(root)
            project_id = "123e4567-e89b-12d3-a456-426614174000"
            outside = Path(temp) / "outside.json"
            outside.write_text('{"safe": true}', encoding="utf-8")
            (root / f"{project_id}.json").symlink_to(outside)

            with self.assertRaisesRegex(ProjectStoreError, "symlink"):
                store.save(project_id, "clipart", "Unsafe", {"safe": True})
            with self.assertRaisesRegex(ProjectStoreError, "symlink"):
                store.load(project_id)
            self.assertEqual(json.loads(outside.read_text(encoding="utf-8")), {"safe": True})

            with self.assertRaises(ProjectStoreError):
                store.load("../../outside")

    def test_corrupt_projects_are_skipped_by_recent_but_reported_by_load(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            good = store.create("clipart", "Good", {"safe": True})
            bad_id = "123e4567-e89b-12d3-a456-426614174001"
            (store.root / f"{bad_id}.json").write_text("{broken", encoding="utf-8")

            self.assertEqual([item.project_id for item in store.recent()], [good.project_id])
            with self.assertRaisesRegex(ProjectStoreError, "corrupt"):
                store.load(bad_id)


    def test_document_envelope_records_generic_metadata_and_opaque_state(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            state = {"text": {"body": "hello"}, "custom": [1, 2, 3]}
            record = store.create(
                "text-probe", "Note", state,
                document_type="note", document_version=3,
            )
            self.assertEqual(record.module_id, "text-probe")
            self.assertEqual(record.document_type, "note")
            self.assertEqual(record.document_version, 3)
            self.assertEqual(record.state, state)
            raw = json.loads((store.root / f"{record.project_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["schema_version"], 2)
            self.assertEqual(raw["document_type"], "note")
            self.assertEqual(raw["document_version"], 3)
            self.assertEqual(raw["state"], state)

    def test_legacy_v1_envelope_loads_without_rewriting_opaque_state(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            project_id = "123e4567-e89b-12d3-a456-426614174111"
            payload = {
                "schema_version": 1, "project_id": project_id, "module_id": "clipart",
                "name": "Legacy", "updated_at": "2026-01-01T00:00:00Z",
                "state": {"legacy": {"value": 7}},
            }
            path = store.root / f"{project_id}.json"
            path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
            before = path.read_bytes()
            record = store.load(project_id)
            self.assertEqual(record.document_type, "project")
            self.assertEqual(record.document_version, 1)
            self.assertEqual(record.state, payload["state"])
            self.assertEqual(path.read_bytes(), before)

    def test_newer_document_version_cannot_be_silently_downgraded(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            record = store.create(
                "text-probe", "Future", {"value": "new"},
                document_type="note", document_version=5,
            )
            path = store.root / f"{record.project_id}.json"
            before = path.read_bytes()
            with self.assertRaisesRegex(ProjectStoreError, "newer|version"):
                store.save(
                    record.project_id, "text-probe", "Future", {"value": "old"},
                    document_type="note", document_version=4,
                )
            self.assertEqual(path.read_bytes(), before)

    def test_project_document_identity_cannot_change_on_save(self):
        with tempfile.TemporaryDirectory() as temp:
            store = ProjectStore(Path(temp) / "projects")
            record = store.create(
                "text-probe", "Note", {"value": 1},
                document_type="note", document_version=1,
            )
            path = store.root / f"{record.project_id}.json"
            before = path.read_bytes()
            for module_id, document_type in (("other", "note"), ("text-probe", "other")):
                with self.subTest(module_id=module_id, document_type=document_type):
                    with self.assertRaises(ProjectStoreError):
                        store.save(
                            record.project_id, module_id, "Note", {"value": 2},
                            document_type=document_type, document_version=1,
                        )
                    self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
