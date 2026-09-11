"""Project journals must not share pending paid jobs, without any API calls."""
import tempfile
import unittest
import uuid

from main import WorkerThread


class ProjectJobIsolationTests(unittest.TestCase):
    def test_same_folder_isolates_projects_and_preserves_restart_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            first_id, second_id = str(uuid.uuid4()), str(uuid.uuid4())
            first = WorkerThread("generate", folder, {}, project_id=first_id)
            second = WorkerThread("generate", folder, {}, project_id=second_id)
            restored = WorkerThread("generate", folder, {}, project_id=first_id)
            legacy = WorkerThread("generate", folder, {})
            for provider in ("fal", "kie"):
                journals = [getattr(w, f"{provider}_task_journal") for w in (first, second, restored, legacy)]
                self.assertEqual(journals[0].path, journals[2].path)
                self.assertEqual(len({j.path for j in journals}), 3)
                self.assertEqual(journals[3].path.name, f".vibix_{provider}_tasks.json")
                journals[0].upsert("request-one", "generate", "test/model", "queued", input_fingerprint="a" * 64)
                self.assertEqual([r.request_id for r in journals[2].pending()], ["request-one"])
                self.assertEqual(journals[1].pending(), ())
                self.assertEqual(journals[3].pending(), ())

    def test_invalid_project_id_is_rejected_before_journal_access(self):
        for value in ("../escape", "", "not-uuid", 42, str(uuid.uuid4()).upper()):
            with self.subTest(value=value), self.assertRaises(ValueError):
                WorkerThread("generate", "/unused", {}, project_id=value)
