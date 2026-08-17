from __future__ import annotations

import base64
import sys
import tempfile
import threading
import unittest
import pytest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_client import LicenseClient, LicenseError


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SERVICE_SRC = PROJECT_ROOT / "license-service" / "src"
if SERVICE_SRC.is_dir():
    sys.path.insert(0, str(SERVICE_SRC))

try:
    from license_service.api import LicenseApi
    from license_service.http_server import make_server
    from license_service.licensing import InMemoryLicenseService
except ImportError:
    LicenseApi = None

pytestmark = pytest.mark.network


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@unittest.skipIf(LicenseApi is None, "sibling license-service source is unavailable")
class DesktopLicenseServiceContractTests(unittest.TestCase):
    def setUp(self):
        self.signing_key = Ed25519PrivateKey.generate()
        self.service = InMemoryLicenseService(b"contract-test-lookup-secret-32b!!")
        self.license_key, self.record = self.service.generate_license(
            "clipart-generator",
            datetime.now(timezone.utc),
        )
        self.api = LicenseApi(self.service, self.signing_key)
        self.server = make_server(self.api, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.temp = tempfile.TemporaryDirectory(prefix="clipart-contract-")
        self.client = LicenseClient(
            base_url=f"http://127.0.0.1:{self.server.server_address[1]}",
            state_path=str(Path(self.temp.name) / "license-state.json"),
            public_keys={
                "license-v1": encode(self.signing_key.public_key().public_bytes_raw())
            },
            product_id="clipart-generator",
        )

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def test_issue_activate_validate_revoke_then_fail_closed(self):
        activated = self.client.activate(self.license_key)
        validated = self.client.validate()

        self.assertEqual(activated.license_id, self.record.license_id)
        self.assertEqual(validated.license_id, self.record.license_id)
        self.assertEqual(validated.product_id, "clipart-generator")

        self.service.set_status(self.record.license_id, "revoked")

        with self.assertRaisesRegex(LicenseError, "отклонена"):
            self.client.validate()


if __name__ == "__main__":
    unittest.main()
