from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from main import EnvCredentialStore


class V3CredentialStoreTests(unittest.TestCase):
    def test_env_credential_store_round_trip_and_ignore_blank_values(self) -> None:
        with tempfile.TemporaryDirectory(prefix="clipart-env-store-") as temp:
            path = Path(temp) / ".env"
            store = EnvCredentialStore(str(path))
            store.save(
                {
                    "kie_api_key": "kie-secret",
                    "photoroom_api_key": "",
                    "license_key": "license-secret",
                }
            )

            content = path.read_text(encoding="utf-8")
            self.assertIn("kie_api_key=kie-secret", content)
            self.assertIn("license_key=license-secret", content)
            self.assertNotIn("photoroom_api_key=", content)

            loaded = store.load()
            self.assertEqual(loaded["kie_api_key"], "kie-secret")
            self.assertEqual(loaded["license_key"], "license-secret")
            self.assertNotIn("photoroom_api_key", loaded)


if __name__ == "__main__":
    unittest.main()
