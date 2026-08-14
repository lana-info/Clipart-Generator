import base64
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib import error

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import license_client


DUMMY_LICENSE_KEY = "CG-test-license-secret-must-not-appear"


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class JsonResponse:
    def __init__(self, payload, *, declared_length=None):
        self.payload = json.dumps(payload).encode("utf-8")
        length = len(self.payload) if declared_length is None else declared_length
        self.headers = {"Content-Length": str(length)}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, limit=-1):
        return self.payload if limit < 0 else self.payload[:limit]


class FakeOpener:
    def __init__(self, responder=None, failure=None):
        self.responder = responder
        self.failure = failure
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        if self.failure is not None:
            raise self.failure
        return self.responder(req)


class SignedLicenseResponder:
    def __init__(self, private_key, *, mutate_payload=None, kid="license-v1"):
        self.private_key = private_key
        self.mutate_payload = mutate_payload
        self.kid = kid
        self.requests = []

    def __call__(self, req):
        request_payload = json.loads(req.data.decode("utf-8"))
        self.requests.append((req.full_url, request_payload))
        payload = {
            "license_id": "60bb44b8-938f-4c05-a95b-bb0e15383f40",
            "product_id": request_payload["product_id"],
            "device_key": request_payload["device_key"],
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
            "nonce": request_payload["nonce"],
            "correlation_id": "test-correlation",
        }
        if self.mutate_payload is not None:
            self.mutate_payload(payload)
        signature = self.private_key.sign(rfc8785.dumps(payload))
        return JsonResponse(
            {
                "schema_version": 1,
                "algorithm": "Ed25519",
                "kid": self.kid,
                "payload": payload,
                "signature": encode(signature),
            }
        )


class LicenseClientSecurityTests(unittest.TestCase):
    def setUp(self):
        self.server_private = Ed25519PrivateKey.generate()
        self.server_public = encode(self.server_private.public_key().public_bytes_raw())
        self.temp = tempfile.TemporaryDirectory(prefix="clipart-license-client-")
        self.addCleanup(self.temp.cleanup)
        self.state_path = str(Path(self.temp.name) / "license-state.json")

    def make_client(self, base_url="https://license.example"):
        return license_client.LicenseClient(
            base_url=base_url,
            state_path=self.state_path,
            public_keys={"license-v1": self.server_public},
            product_id="clipart-generator",
            timeout=3,
        )

    def activate(self, client=None, responder=None):
        client = client or self.make_client()
        responder = responder or SignedLicenseResponder(self.server_private)
        opener = FakeOpener(responder)
        with patch.object(license_client.request, "build_opener", return_value=opener):
            result = client.activate(DUMMY_LICENSE_KEY)
        return client, responder, opener, result

    def test_activation_uses_signed_device_proof_and_never_persists_license_key(self):
        client, responder, _, result = self.activate()

        self.assertEqual(result.product_id, "clipart-generator")
        self.assertTrue(client.has_activation())
        url, payload = responder.requests[0]
        self.assertEqual(url, "https://license.example/api/v1/licenses/activate")
        self.assertEqual(payload["license_key"], DUMMY_LICENSE_KEY)
        self.assertEqual(payload["product_id"], "clipart-generator")
        device_public = base64.urlsafe_b64decode(payload["device_key"] + "==")
        Ed25519PrivateKey.from_private_bytes(client._state.load()["device_private_key"]).public_key().verify(
            base64.urlsafe_b64decode(payload["proof"] + "=="),
            payload["nonce"].encode("utf-8"),
        )
        self.assertEqual(len(device_public), 32)
        state_text = Path(self.state_path).read_text(encoding="utf-8")
        self.assertNotIn(DUMMY_LICENSE_KEY, state_text)
        if os.name != "nt":
            self.assertEqual(Path(self.state_path).stat().st_mode & 0o777, 0o600)

    def test_validation_requires_network_and_uses_fresh_nonce(self):
        client, activation_responder, _, _ = self.activate()
        validation_responder = SignedLicenseResponder(self.server_private)
        opener = FakeOpener(validation_responder)
        with patch.object(license_client.request, "build_opener", return_value=opener):
            result = client.validate()

        self.assertEqual(result.license_id, "60bb44b8-938f-4c05-a95b-bb0e15383f40")
        url, payload = validation_responder.requests[0]
        self.assertEqual(url, "https://license.example/api/v1/licenses/validate")
        self.assertNotIn("license_key", payload)
        self.assertNotEqual(payload["nonce"], activation_responder.requests[0][1]["nonce"])

        with patch.object(
            license_client.request,
            "build_opener",
            return_value=FakeOpener(failure=TimeoutError("offline")),
        ):
            with self.assertRaisesRegex(license_client.LicenseError, "сервер"):
                client.validate()

    def test_tampered_signed_payload_is_rejected(self):
        responder = SignedLicenseResponder(self.server_private)
        original = responder.__call__

        def tampered(req):
            response = original(req)
            envelope = json.loads(response.payload)
            envelope["payload"]["product_id"] = "other-product"
            return JsonResponse(envelope)

        with patch.object(
            license_client.request,
            "build_opener",
            return_value=FakeOpener(tampered),
        ):
            with self.assertRaisesRegex(license_client.LicenseError, "подпись"):
                self.make_client().activate(DUMMY_LICENSE_KEY)

    def test_unknown_signing_key_is_rejected(self):
        responder = SignedLicenseResponder(self.server_private, kid="unknown-key")
        with patch.object(
            license_client.request,
            "build_opener",
            return_value=FakeOpener(responder),
        ):
            with self.assertRaisesRegex(license_client.LicenseError, "ключ подписи"):
                self.make_client().activate(DUMMY_LICENSE_KEY)

    def test_wrong_product_device_nonce_and_expiry_are_rejected(self):
        mutations = (
            (lambda payload: payload.update(product_id="other"), "продукт"),
            (lambda payload: payload.update(device_key=encode(b"x" * 32)), "устройств"),
            (lambda payload: payload.update(nonce="replayed"), "nonce"),
            (
                lambda payload: payload.update(
                    expires_at=(datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
                ),
                "истекло",
            ),
        )
        for mutate, message in mutations:
            with self.subTest(message=message):
                responder = SignedLicenseResponder(self.server_private, mutate_payload=mutate)
                with patch.object(
                    license_client.request,
                    "build_opener",
                    return_value=FakeOpener(responder),
                ):
                    with self.assertRaisesRegex(license_client.LicenseError, message):
                        self.make_client().activate(DUMMY_LICENSE_KEY)

    def test_remote_http_and_credential_urls_are_rejected_before_network(self):
        for url in ("http://license.example", "https://user:password@license.example"):
            with self.subTest(url=url):
                with patch.object(license_client.request, "build_opener") as opener_mock:
                    with self.assertRaises(license_client.LicenseError):
                        self.make_client(url).activate(DUMMY_LICENSE_KEY)
                opener_mock.assert_not_called()

    def test_http_error_body_and_license_key_are_not_exposed(self):
        body_marker = "private-provider-response-body"
        provider_error = error.HTTPError(
            "https://license.example/api/v1/licenses/activate",
            500,
            f"Server Error {DUMMY_LICENSE_KEY}",
            {},
            BytesIO(f"{body_marker} {DUMMY_LICENSE_KEY}".encode("utf-8")),
        )
        opener = FakeOpener(failure=provider_error)
        with patch.object(license_client.request, "build_opener", return_value=opener) as build_mock:
            with self.assertRaises(license_client.LicenseError) as raised:
                self.make_client().activate(DUMMY_LICENSE_KEY)

        rendered = str(raised.exception)
        self.assertNotIn(body_marker, rendered)
        self.assertNotIn(DUMMY_LICENSE_KEY, rendered)
        self.assertTrue(
            any(
                isinstance(handler, license_client.NoRedirectHandler)
                for handler in build_mock.call_args.args
            )
        )

    def test_license_response_read_is_bounded(self):
        response = JsonResponse({"ok": True}, declared_length=9)
        opener = FakeOpener(lambda _req: response)
        with (
            patch.object(license_client, "MAX_LICENSE_RESPONSE_BYTES", 8, create=True),
            patch.object(license_client.request, "build_opener", return_value=opener),
        ):
            with self.assertRaisesRegex(license_client.LicenseError, "размер"):
                self.make_client().activate(DUMMY_LICENSE_KEY)


if __name__ == "__main__":
    unittest.main()
