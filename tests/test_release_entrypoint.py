import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from license_client import LicenseError
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
        controllers = (
            window.shell.clipart_flow_controller,
            window.shell.pinterest_flow_controller,
            window.shell.processing_flow_controller,
        )
        self.assertTrue(
            all(
                getattr(controller.authorization_provider, "__self__", None) is gate
                for controller in controllers
            )
        )
        window.close()

    def test_startup_does_not_open_application_when_license_is_rejected(self):
        window = QWidget()
        gate = Mock()
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
        gate.authorize_run.side_effect = [
            LicenseError("Активируйте лицензию перед запуском"),
            LicenseError("Не удалось связаться с сервером лицензий"),
        ]
        window._license_gate = gate
        dialog = Mock()
        dialog.exec.return_value = QDialog.DialogCode.Accepted

        result = create_authorized_v3_application_window(
            window_factory=lambda: window,
            dialog_factory=Mock(return_value=dialog),
        )

        self.assertIsNone(result)
        self.assertEqual(gate.authorize_run.call_count, 2)
        warning.assert_called_once()
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

    def test_packaged_version_file_is_the_application_version_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            release_dir = Path(temporary, "release")
            release_dir.mkdir()
            Path(release_dir, "VERSION.txt").write_text("3.0.1\n", encoding="utf-8")
            self.assertEqual(resolve_app_version(temporary), "3.0.1")

            Path(release_dir, "VERSION.txt").write_text("unsafe-version\n", encoding="utf-8")
            self.assertEqual(resolve_app_version(temporary), "3.0")


if __name__ == "__main__":
    unittest.main()
