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
            patch.object(main, "CONFIG_FILE", str(root / "config.json")),
            patch.object(main, "PROMPTS_STORAGE_FILE", str(root / "prompts.json")),
            patch.object(main, "LICENSE_CACHE_FILE", str(root / "license_cache.json")),
            patch.object(main.MainWindow, "_migrate_legacy_local_files", return_value=None),
            patch.object(main.QTimer, "singleShot"),
        )

    @staticmethod
    def cleanup_controls(window):
        return {
            "cleanup_remove_exif": window.chk_cleanup_remove_exif,
            "cleanup_remove_xmp": window.chk_cleanup_remove_xmp,
            "cleanup_remove_iptc": window.chk_cleanup_remove_iptc,
            "cleanup_remove_comments_text": window.chk_cleanup_remove_comments_text,
            "cleanup_remove_embedded_thumbnail": window.chk_cleanup_remove_thumbnail,
            "cleanup_remove_generator_fields": window.chk_cleanup_remove_generator,
            "cleanup_remove_embedded_c2pa": window.chk_cleanup_remove_c2pa,
            "cleanup_preserve_icc": window.chk_cleanup_preserve_icc,
            "cleanup_preserve_dpi": window.chk_cleanup_preserve_dpi,
        }

    def test_legacy_config_uses_safe_defaults_and_compact_layout(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cleanup-ui-legacy-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "config.json").write_text(json.dumps({"upscale": False}), encoding="utf-8")
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()
                controls = self.cleanup_controls(window)

                for key, control in controls.items():
                    expected = key in {"cleanup_preserve_icc", "cleanup_preserve_dpi"}
                    self.assertEqual(control.isChecked(), expected, key)

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

    def test_cleanup_choices_are_independent_and_persist(self):
        with tempfile.TemporaryDirectory(prefix="clipart-cleanup-ui-settings-") as temp_dir:
            temp_path = Path(temp_dir)
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()
                controls = self.cleanup_controls(window)
                removal_keys = [key for key in controls if key.startswith("cleanup_remove_")]

                for active_key in removal_keys:
                    for key in removal_keys:
                        controls[key].setChecked(key == active_key)
                    self.assertEqual(
                        {key for key in removal_keys if controls[key].isChecked()},
                        {active_key},
                    )

                expected = {
                    "cleanup_remove_exif": True,
                    "cleanup_remove_xmp": False,
                    "cleanup_remove_iptc": True,
                    "cleanup_remove_comments_text": False,
                    "cleanup_remove_embedded_thumbnail": True,
                    "cleanup_remove_generator_fields": False,
                    "cleanup_remove_embedded_c2pa": True,
                    "cleanup_preserve_icc": False,
                    "cleanup_preserve_dpi": True,
                }
                for key, value in expected.items():
                    controls[key].setChecked(value)

                window.settings_save_timer.stop()
                window.persist_ui_settings()
                saved_config = json.loads((temp_path / "config.json").read_text(encoding="utf-8"))
                for key, value in expected.items():
                    self.assertEqual(saved_config[key], value, key)
                window.deleteLater()

                restored = main.MainWindow()
                restored_controls = self.cleanup_controls(restored)
                for key, value in expected.items():
                    self.assertEqual(restored_controls[key].isChecked(), value, key)
                restored.settings_save_timer.stop()
                restored.api_key_mask_timer.stop()
                restored.deleteLater()
                self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
