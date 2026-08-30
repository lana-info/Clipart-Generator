import os
import tempfile
import unittest
from pathlib import Path

from api_credentials import (
    ALL_PROVIDER_CREDENTIAL_KEYS,
    EnvCredentialStore,
    ProtectedCredentialStoreError,
    ProtectedFalCredentialStore,
    SECRET_CONFIG_KEYS,
)


class ApiCredentialKeysTests(unittest.TestCase):
    def test_fal_key_is_secret_and_available_to_provider_settings(self):
        self.assertIn("fal_api_key", SECRET_CONFIG_KEYS)
        self.assertIn("fal_api_key", ALL_PROVIDER_CREDENTIAL_KEYS)

    def test_legacy_plaintext_store_never_writes_fal_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            EnvCredentialStore(str(path)).save({"fal_api_key": "fal-secret"})
            self.assertNotIn("fal-secret", path.read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name != "nt", "non-Windows fallback contract")
    def test_fal_key_requires_protected_store_on_non_windows(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ProtectedCredentialStoreError):
                ProtectedFalCredentialStore(Path(temp) / "fal.bin").save(
                    {"fal_api_key": "fal-secret"}
                )

    @unittest.skipUnless(os.name == "nt", "Windows DPAPI contract")
    def test_fal_key_round_trips_through_dpapi_after_store_restart(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fal.bin"
            secret = "fal-restart-secret"

            ProtectedFalCredentialStore(path).save({"fal_api_key": secret})

            self.assertNotIn(secret.encode("utf-8"), path.read_bytes())
            restarted_store = ProtectedFalCredentialStore(path)
            self.assertEqual(restarted_store.load(), {"fal_api_key": secret})


if __name__ == "__main__":
    unittest.main()
