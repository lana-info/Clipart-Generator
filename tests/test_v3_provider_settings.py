from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class V3ProviderSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = main.QApplication.instance() or main.QApplication([])

    def isolated_paths(self, root):
        return (
            patch.object(main, "CONFIG_FILE", str(root / "config.json")),
            patch.object(main, "ENV_FILE", str(root / ".env")),
            patch.object(main, "PROMPTS_STORAGE_FILE", str(root / "prompts.json")),
            patch.object(main, "LICENSE_CACHE_FILE", str(root / "license_cache.json")),
            patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
            patch.object(main.QTimer, "singleShot"),
        )

    def test_protected_store_uses_the_same_directory_as_provider_settings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="provider-store-root-") as temp_dir:
            root = Path(temp_dir)
            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = self.isolated_paths(root)
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch, patch.object(main, "USER_DATA_DIR", str(root / "unrelated")):
                window = main.MainWindow()
                self.assertEqual(window.credential_store.fal.path, root / "fal_api_key.bin")
                self.assertEqual(Path(window.credential_store.env.path).parent, window.credential_store.fal.path.parent)
                self.assertEqual(window.credential_store_error, "")
                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_main_window_migrates_secret_keys_into_user_data_env(self) -> None:
        with tempfile.TemporaryDirectory(prefix="clipart-provider-settings-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "config.json").write_text(
                json.dumps(
                    {
                        "kie_api_key": "kie-secret",
                        "photoroom_api_key": "photoroom-secret",
                        "license_key": "license-secret",
                        "run_mode": "generate_only",
                    }
                ),
                encoding="utf-8",
            )

            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch:
                window = main.MainWindow()

                sanitized = json.loads((temp_path / "config.json").read_text(encoding="utf-8"))
                env_text = (temp_path / ".env").read_text(encoding="utf-8")

                self.assertNotIn("kie_api_key", sanitized)
                self.assertNotIn("photoroom_api_key", sanitized)
                self.assertNotIn("license_key", sanitized)
                self.assertIn("kie_api_key=kie-secret", env_text)
                self.assertIn("photoroom_api_key=photoroom-secret", env_text)
                self.assertNotIn("license_key=", env_text)
                self.assertEqual(window.kie_api_key_input.text(), "kie-secret")
                self.assertEqual(window.photoroom_api_key_input.text(), "photoroom-secret")

                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()

    def test_env_write_failure_blocks_network_start_without_deleting_legacy_key(self) -> None:
        with tempfile.TemporaryDirectory(prefix="clipart-provider-settings-fail-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "config.json").write_text(
                json.dumps(
                    {
                        "kie_api_key": "kie-secret",
                        "run_mode": "generate_only",
                    }
                ),
                encoding="utf-8",
            )

            config_patch, env_patch, prompts_patch, license_patch, migration_patch, timer_patch = (
                self.isolated_paths(temp_path)
            )
            with (
                config_patch,
                env_patch,
                prompts_patch,
                license_patch,
                migration_patch,
                timer_patch,
                patch.object(main.EnvCredentialStore, "save", side_effect=OSError("cannot write env")),
            ):
                window = main.MainWindow()
                window.work_dir = str(temp_path)
                window.generated_prompts = [{"prompt": "one prompt", "references": []}]
                window.kie_api_key_input.setText("kie-secret")
                window.validate_generation_selection = lambda: ""
                window._ensure_models_available_before_run = lambda *args, **kwargs: True
                window.get_list_mode_prompts = lambda: [{"prompt": "one prompt", "references": []}]
                window.log = lambda *_args, **_kwargs: None

                with patch.object(main.QMessageBox, "warning") as warning_mock:
                    window.start_work()

                self.assertTrue(warning_mock.called)
                self.assertIn("user-data .env", str(warning_mock.call_args.args[2]))
                self.assertIn("kie_api_key", (temp_path / "config.json").read_text(encoding="utf-8"))

                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
