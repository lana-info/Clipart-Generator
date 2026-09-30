import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main


class CleanupUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = main.QApplication.instance() or main.QApplication([])

    def isolated_paths(self, root):
        return (
            patch.multiple(main, CONFIG_FILE=str(root / "config.json"), USER_DATA_DIR=str(root)),
            patch.object(main, "ENV_FILE", str(root / ".env")),
            patch.object(main, "PROMPTS_STORAGE_FILE", str(root / "prompts.json")),
            patch.object(main, "LICENSE_CACHE_FILE", str(root / "license_cache.json")),
            patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
            patch.object(main.QTimer, "singleShot"),
        )

    @staticmethod
    def cleanup_controls(window):
        return {"cleanup_remove_all": window.chk_cleanup_all}

    def test_legacy_config_uses_safe_defaults_and_compact_layout(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cleanup-ui-legacy-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "config.json").write_text(json.dumps({"upscale": False}), encoding="utf-8")
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()
                controls = self.cleanup_controls(window)

                for key, control in controls.items():
                    self.assertFalse(control.isChecked(), key)

                window.resize(980, 780)
                window.tabs.setCurrentIndex(1)
                window.show()
                self.app.processEvents()

                group_rect = window.cleanup_group.rect()
                control_rects = [control.geometry() for control in controls.values()]
                for control, rect in zip(controls.values(), control_rects):
                    self.assertTrue(group_rect.contains(rect), control.text())
                for index, rect in enumerate(control_rects):
                    for other_rect in control_rects[index + 1 :]:
                        self.assertFalse(rect.intersects(other_rect))

                window.settings_save_timer.stop()
                window.api_key_mask_timer.stop()
                window.close()
                window.deleteLater()
                self.app.processEvents()

    def test_full_cleanup_persists_as_one_choice(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cleanup-ui-settings-") as temp_dir:
            temp_path = Path(temp_dir)
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()
                window.chk_cleanup_all.setChecked(True)

                window.settings_save_timer.stop()
                window.persist_ui_settings()
                saved_config = json.loads((temp_path / "config.json").read_text(encoding="utf-8"))
                self.assertTrue(saved_config["cleanup_remove_all"])
                for key in (
                    "cleanup_remove_exif",
                    "cleanup_remove_xmp",
                    "cleanup_remove_iptc",
                    "cleanup_remove_comments_text",
                    "cleanup_remove_embedded_thumbnail",
                    "cleanup_remove_generator_fields",
                    "cleanup_remove_embedded_c2pa",
                ):
                    self.assertTrue(saved_config[key], key)
                self.assertTrue(saved_config["cleanup_preserve_icc"])
                self.assertTrue(saved_config["cleanup_preserve_dpi"])
                window.deleteLater()

                restored = main.MainWindow()
                self.assertTrue(restored.chk_cleanup_all.isChecked())
                restored.settings_save_timer.stop()
                restored.api_key_mask_timer.stop()
                restored.deleteLater()
                self.app.processEvents()

if __name__ == "__main__":
    unittest.main()
