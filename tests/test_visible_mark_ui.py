import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main


class VisibleMarkUiTests(unittest.TestCase):
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

    def close_window(self, window):
        window.settings_save_timer.stop()
        window.api_key_mask_timer.stop()
        window.deleteLater()
        self.app.processEvents()

    def test_legacy_config_is_disabled_and_exposes_only_approved_modes(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-mark-ui-legacy-") as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "config.json").write_text(
                json.dumps({"upscale": False}),
                encoding="utf-8",
            )
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()

                self.assertFalse(window.chk_visible_mark_cleanup.isChecked())
                self.assertFalse(window.visible_mark_mode_combo.isEnabled())
                self.assertEqual(window.visible_mark_mode_combo.currentData(), "gemini_auto")
                self.assertEqual(
                    [
                        window.visible_mark_mode_combo.itemData(index)
                        for index in range(window.visible_mark_mode_combo.count())
                    ],
                    ["gemini_auto", "confirmed_area"],
                )
                self.assertNotIn(
                    "kie",
                    " ".join(
                        window.visible_mark_mode_combo.itemText(index).lower()
                        for index in range(window.visible_mark_mode_combo.count())
                    ),
                )

                window.resize(980, 860)
                window.tabs.setCurrentIndex(1)
                window.show()
                self.app.processEvents()

                self.assertLess(
                    window.chk_visible_mark_cleanup.geometry().top(),
                    window.chk_upscale.geometry().top(),
                )
                self.assertTrue(
                    window.process_flags_group.rect().contains(
                        window.chk_visible_mark_cleanup.geometry()
                    )
                )
                self.assertFalse(window.visible_mark_confirmation_label.isVisible())

                self.close_window(window)

    def test_mode_state_and_settings_persist(self):
        with tempfile.TemporaryDirectory(prefix="clipart-visible-mark-ui-settings-") as temp_dir:
            temp_path = Path(temp_dir)
            patches = self.isolated_paths(temp_path)
            with patches[0], patches[1], patches[2], patches[3], patches[4]:
                window = main.MainWindow()
                window.resize(980, 860)
                window.tabs.setCurrentIndex(1)
                window.show()
                self.app.processEvents()

                window.chk_visible_mark_cleanup.setChecked(True)
                confirmed_index = window.visible_mark_mode_combo.findData("confirmed_area")
                window.visible_mark_mode_combo.setCurrentIndex(confirmed_index)
                self.app.processEvents()

                self.assertTrue(window.visible_mark_mode_combo.isEnabled())
                self.assertTrue(window.visible_mark_confirmation_label.isVisible())
                self.assertIn("подтверж", window.visible_mark_confirmation_label.text().lower())

                window.settings_save_timer.stop()
                window.persist_ui_settings()
                saved_config = json.loads(
                    (temp_path / "config.json").read_text(encoding="utf-8")
                )
                self.assertTrue(saved_config["visible_mark_cleanup_enabled"])
                self.assertEqual(saved_config["visible_mark_cleanup_mode"], "confirmed_area")
                self.close_window(window)

                restored = main.MainWindow()
                restored.resize(980, 860)
                restored.tabs.setCurrentIndex(1)
                restored.show()
                self.app.processEvents()

                self.assertTrue(restored.chk_visible_mark_cleanup.isChecked())
                self.assertEqual(restored.visible_mark_mode_combo.currentData(), "confirmed_area")
                self.assertTrue(restored.visible_mark_confirmation_label.isVisible())

                restored.visible_mark_mode_combo.setCurrentIndex(
                    restored.visible_mark_mode_combo.findData("gemini_auto")
                )
                self.app.processEvents()
                self.assertFalse(restored.visible_mark_confirmation_label.isVisible())

                self.close_window(restored)


if __name__ == "__main__":
    unittest.main()
