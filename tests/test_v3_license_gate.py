from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from license_client import LicenseAuthorization, LicenseError, LicenseUnavailableError
from v3_license import LicenseDialog, OnlineLicenseGate, SavedLicenseUnavailableDialog


def authorization(*, offline: bool = False) -> LicenseAuthorization:
    now = datetime.now(timezone.utc)
    return LicenseAuthorization(
        license_id="license-id",
        product_id="clipart-generator",
        device_key="device-key",
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        is_offline_grace=offline,
        last_verified_at=now if offline else None,
        grace_expires_at=now + timedelta(days=7) if offline else None,
    )


class FakeClient:
    def __init__(self, *, activated=False, failure=None, offline_failure=None):
        self.activated = activated
        self.failure = failure
        self.activation_keys = []
        self.validation_calls = 0
        self.offline_failure = offline_failure
        self.offline_calls = 0

    def has_activation(self):
        return self.activated

    def activate(self, key):
        self.activation_keys.append(key)
        if self.failure:
            raise self.failure
        self.activated = True
        return authorization()

    def validate(self):
        self.validation_calls += 1
        if self.failure:
            raise self.failure
        return authorization()

    def authorize_offline_grace(self):
        self.offline_calls += 1
        if self.offline_failure:
            raise self.offline_failure
        return authorization(offline=True)


class OnlineLicenseGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_successful_online_check_is_available_as_safe_in_memory_status(self):
        gate = OnlineLicenseGate(FakeClient())

        result = gate.activate("CG-TEST")

        self.assertIs(gate.current_authorization, result)
        self.assertIn("Проверено онлайн:", gate.verification_text)
        self.assertNotIn(result.license_id, gate.verification_text)
        self.assertNotIn("CG-TEST", gate.verification_text)

    def test_failed_online_check_clears_previous_verified_status(self):
        client = FakeClient()
        gate = OnlineLicenseGate(client)
        gate.activate("CG-TEST")
        client.failure = LicenseError("Сервер отклонил лицензию")

        with self.assertRaises(LicenseError):
            gate.authorize_run()

        self.assertIsNone(gate.current_authorization)
        self.assertEqual(gate.verification_text, "Онлайн-проверка не выполнена")

    def test_run_requires_prior_activation(self):
        gate = OnlineLicenseGate(FakeClient())
        with self.assertRaisesRegex(LicenseError, "Активируйте лицензию"):
            gate.authorize_run()

    def test_activation_and_every_run_use_the_online_client(self):
        client = FakeClient()
        gate = OnlineLicenseGate(client)

        activated = gate.activate("CG-TEST")
        first = gate.authorize_run()
        second = gate.authorize_run()

        self.assertEqual(activated.license_id, "license-id")
        self.assertEqual(first.license_id, "license-id")
        self.assertEqual(second.license_id, "license-id")
        self.assertEqual(client.activation_keys, ["CG-TEST"])
        self.assertEqual(client.validation_calls, 2)
        self.assertEqual(gate.status_text, "Лицензия активна")

    def test_temporary_server_outage_uses_bounded_offline_grace(self):
        client = FakeClient(
            activated=True,
            failure=LicenseUnavailableError("Сервер временно недоступен"),
        )
        gate = OnlineLicenseGate(client)

        result = gate.authorize_run()

        self.assertTrue(result.is_offline_grace)
        self.assertEqual(client.offline_calls, 1)
        self.assertEqual(gate.status_text, "Временный автономный доступ")
        self.assertIn("Последняя проверка:", gate.verification_text)
        self.assertIn("Доступ до:", gate.verification_text)

    def test_first_activation_outage_never_uses_offline_grace(self):
        client = FakeClient(
            failure=LicenseUnavailableError("Сервер временно недоступен")
        )
        gate = OnlineLicenseGate(client)

        with self.assertRaises(LicenseUnavailableError):
            gate.activate("CG-TEST")

        self.assertEqual(client.offline_calls, 0)
        self.assertFalse(client.activated)

    def test_explicit_server_denial_never_uses_offline_grace(self):
        client = FakeClient(
            activated=True,
            failure=LicenseError("Лицензия отклонена сервером"),
        )
        gate = OnlineLicenseGate(client)

        with self.assertRaisesRegex(LicenseError, "отклонена"):
            gate.authorize_run()

        self.assertEqual(client.offline_calls, 0)
        self.assertIsNone(gate.current_authorization)

    def test_expired_grace_stays_on_saved_license_retry_path(self):
        client = FakeClient(
            activated=True,
            failure=LicenseUnavailableError("Сервер временно недоступен"),
            offline_failure=LicenseError(
                "Срок временного автономного доступа завершён"
            ),
        )
        gate = OnlineLicenseGate(client)

        with self.assertRaisesRegex(
            LicenseUnavailableError,
            "автономного доступа завершён",
        ):
            gate.authorize_run()

        self.assertEqual(gate.status_text, "Требуется подключение")

    def test_expired_grace_dialog_matches_the_approved_compact_copy(self):
        dialog = SavedLicenseUnavailableDialog(
            "Срок временного автономного доступа завершён\n"
            "Последняя успешная проверка: 29.08.2026 20:30"
        )

        labels = [item.text() for item in dialog.findChildren(QLabel)]
        buttons = [item.text() for item in dialog.findChildren(QPushButton)]

        self.assertIn("Нужно восстановить соединение", labels)
        self.assertIn("Последняя успешная проверка: 29.08.2026 20:30", labels)
        self.assertIn("Повторить проверку", buttons)
        self.assertIn("Закрыть", buttons)
        dialog.deleteLater()

    def test_unexpected_errors_are_bounded_and_do_not_expose_key(self):
        secret = "CG-secret-must-not-leak"
        gate = OnlineLicenseGate(FakeClient(failure=RuntimeError(secret)))

        with self.assertRaises(LicenseError) as raised:
            gate.activate(secret)

        self.assertNotIn(secret, str(raised.exception))
        self.assertEqual(str(raised.exception), "Не удалось проверить лицензию")

    def test_safe_license_errors_are_preserved(self):
        gate = OnlineLicenseGate(
            FakeClient(failure=LicenseError("Не удалось связаться с сервером лицензий"))
        )
        with self.assertRaisesRegex(LicenseError, "сервером лицензий"):
            gate.activate("CG-TEST")


class LicenseDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_activation_failure_shows_and_copies_safe_error_code(self):
        gate = OnlineLicenseGate(
            FakeClient(
                failure=LicenseUnavailableError(
                    "Не удалось найти сервер лицензий по DNS.",
                    code="license_dns",
                )
            )
        )
        dialog = LicenseDialog(gate)
        dialog.license_key_input.setText("CG-TEST")

        with patch("v3_license.QMessageBox.warning") as warning:
            dialog._activate()

        self.assertEqual(dialog.error_code_label.text(), "Код ошибки: license_dns")
        self.assertFalse(dialog.copy_error_button.isHidden())
        self.assertTrue(dialog.copy_error_button.isEnabled())
        self.assertIn("Код ошибки: license_dns", warning.call_args.args[2])

        dialog._copy_error_code()

        self.assertEqual(QApplication.clipboard().text(), "license_dns")
        dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
