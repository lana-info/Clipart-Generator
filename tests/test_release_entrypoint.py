import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QWidget
from PIL import Image

import main
from license_client import LicenseError, LicenseUnavailableError
from main import (
    APP_VERSION,
    create_authorized_v3_application_window,
    create_v3_application_window,
    resolve_app_version,
    run_packaged_entrypoint_check,
)
from v3_components import ModeCard
from v3_mode_selection import MODE_CARD_SPECS, V3ApplicationView
from v3_project_state import ProjectMode


class ReleaseEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_production_entrypoint_is_v3(self):
        window = create_v3_application_window()
        self.assertIsInstance(window, V3ApplicationView)
        self.assertEqual(window.windowTitle(), f"Vibix Images {APP_VERSION}")
        cards = list(window.mode_selection.mode_cards.values())
        self.assertEqual(set(window.mode_selection.mode_cards), set(MODE_CARD_SPECS))
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(isinstance(card, ModeCard) for card in cards))
        self.assertTrue(all(card.accessibleName() for card in cards))
        window.mode_selection.mode_cards[ProjectMode.CLIPART].start_button.click()
        self.app.processEvents()
        gate = window._license_gate
        self.assertIsNotNone(gate)
        controllers = [window.shell.clipart_flow_controller]
        self.assertFalse(hasattr(window.shell, "pinterest_flow_controller"))
        self.assertFalse(hasattr(window.shell, "processing_flow_controller"))
        for mode, attribute in (
            (ProjectMode.PINTEREST, "pinterest_flow_controller"),
            (ProjectMode.PROCESSING, "processing_flow_controller"),
        ):
            window.show_mode_switcher()
            window.mode_selection.mode_cards[mode].start_button.click()
            controllers.append(getattr(window.shell, attribute))
        self.assertTrue(
            all(
                getattr(controller.authorization_provider, "__self__", None) is gate
                for controller in controllers
            )
        )
        window.close()

    def test_v3_runtime_includes_bundled_local_realesrgan_path(self):
        with tempfile.TemporaryDirectory(prefix="vibix-config-") as temp_dir:
            with patch("main.CONFIG_FILE", str(Path(temp_dir) / "missing-config.json")):
                window = create_v3_application_window()
            try:
                self.assertEqual(
                    window._runtime_settings()["local_realesrgan_dir"],
                    main.bundled_local_realesrgan_dir(),
                )
            finally:
                window.close()

    def test_production_entrypoint_seeds_new_v3_project_from_legacy_settings(self):
        with tempfile.TemporaryDirectory(prefix="vibix-legacy-config-") as temp_dir:
            root = Path(temp_dir)
            config_path = root / "config.json"
            legacy_work = root / "legacy-work"
            legacy_work.mkdir()
            config_path.write_text(
                json.dumps(
                    {
                        "run_mode": "process_only",
                        "last_work_dir": str(legacy_work),
                        "upscale": False,
                        "remove_bg": True,
                        "remove_bg_provider": "local_rembg",
                        "local_rembg_model": "isnet-anime",
                        "trim_enabled": True,
                        "export_300_dpi": True,
                    }
                ),
                encoding="utf-8",
            )
            with patch("main.CONFIG_FILE", str(config_path)), patch.object(
                main.QStandardPaths, "writableLocation", return_value=str(root)
            ):
                window = create_v3_application_window()
            try:
                window._handle_mode_selected(ProjectMode.PROCESSING.value)
                operations = window.shell.state.processing.operations
                self.assertEqual(window.shell.state.common.work_dir, str(legacy_work))
                self.assertTrue(operations.remove_background)
                self.assertEqual(
                    operations.remove_background_provider, "local_rembg"
                )
                self.assertEqual(operations.local_rembg_model, "isnet-anime")
                self.assertTrue(operations.trim)
                self.assertTrue(operations.export_300_dpi)
            finally:
                window.close()

    def test_startup_does_not_open_application_when_license_is_rejected(self):
        window = QWidget()
        gate = Mock()
        gate.has_activation.return_value = False
        gate.authorize_run.side_effect = LicenseError(
            "Активируйте лицензию перед запуском"
        )
        window._license_gate = gate
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Rejected
        dialog_factory = Mock(return_value=dialog)

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=dialog_factory,
        )

        self.assertIsNone(result)
        gate.authorize_run.assert_called_once_with()
        dialog_factory.assert_called_once_with(gate, parent=window)
        window.deleteLater()

    def test_saved_license_outage_never_reopens_key_entry(self):
        window = QWidget()
        gate = Mock()
        gate.has_activation.return_value = True
        gate.authorize_run.side_effect = LicenseUnavailableError(
            "Сервер лицензий временно недоступен"
        )
        window._license_gate = gate
        key_dialog_factory = Mock()
        outage_dialog = Mock()
        outage_dialog.exec.return_value = QDialog.DialogCode.Rejected
        outage_dialog_factory = Mock(return_value=outage_dialog)

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=key_dialog_factory,
            unavailable_dialog_factory=outage_dialog_factory,
        )

        self.assertIsNone(result)
        key_dialog_factory.assert_not_called()
        outage_dialog_factory.assert_called_once_with(
            "Сервер лицензий временно недоступен",
            parent=window,
        )
        window.deleteLater()

    def test_saved_license_outage_retry_requires_fresh_success(self):
        window = QWidget()
        window.refresh_license_status = Mock()
        gate = Mock()
        gate.has_activation.return_value = True
        gate.authorize_run.side_effect = [
            LicenseUnavailableError("Сервер лицензий временно недоступен"),
            object(),
        ]
        window._license_gate = gate
        outage_dialog = Mock()
        outage_dialog.exec.return_value = QDialog.DialogCode.Accepted

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=Mock(),
            unavailable_dialog_factory=Mock(return_value=outage_dialog),
        )

        self.assertIs(result, window)
        self.assertEqual(gate.authorize_run.call_count, 2)
        window.refresh_license_status.assert_called_once_with()
        window.deleteLater()

    def test_startup_uses_saved_license_only_after_online_validation(self):
        window = QWidget()
        window.refresh_license_status = Mock()
        gate = Mock()
        gate.authorize_run.return_value = object()
        window._license_gate = gate
        dialog_factory = Mock()

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=dialog_factory,
        )

        self.assertIs(result, window)
        gate.authorize_run.assert_called_once_with()
        window.refresh_license_status.assert_called_once_with()
        dialog_factory.assert_not_called()
        window.deleteLater()

    def test_startup_revalidates_after_successful_key_activation(self):
        window = QWidget()
        window.refresh_license_status = Mock()
        gate = Mock()
        gate.has_activation.return_value = False
        gate.authorize_run.side_effect = [
            LicenseError("Активируйте лицензию перед запуском"),
            object(),
        ]
        window._license_gate = gate
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=Mock(return_value=dialog),
        )

        self.assertIs(result, window)
        self.assertEqual(gate.authorize_run.call_count, 2)
        window.refresh_license_status.assert_called_once_with()
        window.deleteLater()

    @patch("main.QMessageBox.warning")
    def test_startup_stays_closed_when_post_activation_validation_fails(
        self,
        warning,
    ):
        window = QWidget()
        gate = Mock()
        gate.has_activation.side_effect = [False, True]
        gate.authorize_run.side_effect = [
            LicenseError("Активируйте лицензию перед запуском"),
            LicenseUnavailableError("Не удалось связаться с сервером лицензий"),
        ]
        window._license_gate = gate
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted
        outage_dialog = Mock()
        outage_dialog.exec.return_value = QDialog.DialogCode.Rejected

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=Mock(return_value=dialog),
            unavailable_dialog_factory=Mock(return_value=outage_dialog),
        )

        self.assertIsNone(result)
        self.assertEqual(gate.authorize_run.call_count, 2)
        warning.assert_not_called()
        window.deleteLater()

    def test_saved_rejected_license_opens_replacement_key_flow(self):
        window = QWidget()
        gate = Mock()
        gate.has_activation.return_value = True
        gate.authorize_run.side_effect = LicenseError(
            "Лицензия отклонена сервером"
        )
        window._license_gate = gate
        key_dialog = Mock()
        key_dialog.exec.return_value = QDialog.DialogCode.Rejected
        key_dialog_factory = Mock(return_value=key_dialog)
        outage_dialog_factory = Mock()

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=key_dialog_factory,
            unavailable_dialog_factory=outage_dialog_factory,
        )

        self.assertIsNone(result)
        key_dialog_factory.assert_called_once_with(gate, parent=window)
        outage_dialog_factory.assert_not_called()
        window.deleteLater()

    def test_startup_fails_closed_when_license_gate_is_missing(self):
        window = QWidget()

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=Mock(),
        )

        self.assertIsNone(result)
        window.deleteLater()

    def test_packaged_smoke_checks_user_controls_paths_and_startup_barrier(self):
        self.assertEqual(run_packaged_entrypoint_check(APP_VERSION), 0)
        self.assertEqual(run_packaged_entrypoint_check("999.0"), 1)

    @patch("main.import_rembg_tools")
    @patch("main.validate_local_realesrgan_exe")
    def test_local_processing_smoke_checks_bundled_runtime_and_rembg_import(
        self,
        validate_realesrgan,
        import_rembg,
    ):
        validate_realesrgan.return_value = ("runtime/realesrgan-ncnn-vulkan.exe", "")
        buffer = main.BytesIO()
        Image.new("RGBA", (8, 8), (255, 0, 0, 128)).save(buffer, format="PNG")
        session = object()
        new_session = Mock(return_value=session)
        remove = Mock(return_value=buffer.getvalue())
        import_rembg.return_value = (new_session, remove)

        self.assertEqual(main.run_local_processing_entrypoint_check(), 0)
        validate_realesrgan.assert_called_once_with(main.bundled_local_realesrgan_dir())
        import_rembg.assert_called_once_with()
        new_session.assert_called_once_with("u2netp")
        self.assertIs(remove.call_args.kwargs["session"], session)

        validate_realesrgan.return_value = ("", "models missing")
        self.assertEqual(main.run_local_processing_entrypoint_check(), 1)

    def test_packaged_version_file_is_the_application_version_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            release_dir = Path(temporary, "release")
            release_dir.mkdir()
            Path(release_dir, "VERSION.txt").write_text("3.0.1\n", encoding="utf-8")
            self.assertEqual(resolve_app_version(temporary), "3.0.1")

            Path(release_dir, "VERSION.txt").write_text("unsafe-version\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_app_version(temporary)


if __name__ == "__main__":
    unittest.main()
