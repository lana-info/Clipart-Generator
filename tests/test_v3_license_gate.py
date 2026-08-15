from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from license_client import LicenseAuthorization, LicenseError
from v3_license import OnlineLicenseGate


def authorization() -> LicenseAuthorization:
    now = datetime.now(timezone.utc)
    return LicenseAuthorization(
        license_id="license-id",
        product_id="clipart-generator",
        device_key="device-key",
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )


class FakeClient:
    def __init__(self, *, activated=False, failure=None):
        self.activated = activated
        self.failure = failure
        self.activation_keys = []
        self.validation_calls = 0

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


class OnlineLicenseGateTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
