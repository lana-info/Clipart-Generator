import tempfile
import unittest
from pathlib import Path

from config_schema import (
    PREFERENCES_SCHEMA_VERSION,
    load_preferences,
    migrate_preferences,
    resolve_output_directory,
    save_preferences_atomic,
)


class ConfigSchemaTests(unittest.TestCase):
    def test_migration_defaults_unknown_keys_and_malformed_modes(self):
        migrated = migrate_preferences({"last_work_dir": 42, "unknown": "drop", "clipart": []})
        self.assertEqual(migrated["schema_version"], PREFERENCES_SCHEMA_VERSION)
        self.assertEqual(migrated["last_work_dir"], "")
        self.assertEqual(migrated["clipart"], {})
        self.assertNotIn("unknown", migrated)

    def test_legacy_keys_future_versions_and_nested_secrets_are_safe(self):
        migrated = migrate_preferences({
            "schema_version": 99,
            "work_dir": "/legacy",
            "clipart": {"api_key": "secret", "operations": {"token": "secret", "enabled": True}},
        })
        self.assertEqual(migrated["last_work_dir"], "")
        self.assertEqual(migrated["clipart"], {})
        safe = migrate_preferences({
            "schema_version": 1,
            "clipart": {"api_key": "secret", "operations": {"token": "secret", "enabled": True}},
        })
        self.assertNotIn("api_key", safe["clipart"])
        self.assertEqual(safe["clipart"]["operations"], {"enabled": True})
        legacy = migrate_preferences({"work_dir": "/legacy", "output_dir": "/out"})
        self.assertEqual(legacy["last_work_dir"], "/legacy")
        self.assertEqual(legacy["last_output_dir"], "/out")

    def test_atomic_round_trip_and_corrupt_tail_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preferences.json"
            save_preferences_atomic(path, {"last_work_dir": directory, "clipart": {"output_dir": "x"}})
            self.assertEqual(load_preferences(path)["clipart"]["output_dir"], "x")
            path.write_text('{"schema_version": 1,', encoding="utf-8")
            self.assertEqual(load_preferences(path)["schema_version"], PREFERENCES_SCHEMA_VERSION)

    def test_output_dir_preserves_configured_path_with_writable_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            fallback = work / "output"
            fallback.mkdir()
            configured = work / "missing"
            self.assertEqual(resolve_output_directory(work, configured), configured)

    def test_output_dir_falls_back_when_configured_parent_is_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            fallback = work / "output"
            fallback.mkdir()
            configured = work / "missing-parent" / "missing"
            self.assertEqual(resolve_output_directory(work, configured), fallback)


if __name__ == "__main__":
    unittest.main()
