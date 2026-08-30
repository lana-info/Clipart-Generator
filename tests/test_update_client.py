import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

import license_client
import update_client
from update_client import UpdateClient, UpdateError, current_platform_id


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


class Response:
    def __init__(self, payload: bytes, content_type="application/json"):
        self.payload = payload
        self.position = 0
        self.headers = {"Content-Length": str(len(payload)), "Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, limit=-1):
        if limit < 0:
            limit = len(self.payload) - self.position
        chunk = self.payload[self.position : self.position + limit]
        self.position += len(chunk)
        return chunk


class Opener:
    def __init__(self, responder):
        self.responder = responder
        self.requests = []

    def open(self, req, timeout=None):
        self.requests.append((req, timeout))
        return self.responder(req)


class UpdateClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.license_key = Ed25519PrivateKey.generate()
        self.update_key = Ed25519PrivateKey.generate()
        self.license = license_client.LicenseClient(
            base_url="https://license.example",
            state_path=str(self.root / "license.json"),
            public_keys={"license-v1": encode(self.license_key.public_key().public_bytes_raw())},
            product_id="clipart-generator",
        )
        private = self.license._state.load_or_create_private_key()
        self.license._state.save_activation(private, "license-id")
        self.client = UpdateClient(
            self.license,
            {"updates-v1": encode(self.update_key.public_key().public_bytes_raw())},
            current_version="3.0",
            download_directory=self.root / "updates",
        )
        self.installer = b"windows-installer-3.1"

    def manifest_response(self, req, *, mutate=None, key_id="updates-v1"):
        requested = json.loads(req.data.decode("utf-8"))
        is_macos = requested["platform"].startswith("macos-")
        filename = "VibixImages-macOS-3.1.0-x64.zip" if is_macos else "VibixImages-Setup-3.1.exe"
        payload = {
            "license_id": requested["license_id"],
            "product_id": requested["product_id"],
            "device_key": requested["device_key"],
            "nonce": requested["nonce"],
            "platform": requested["platform"],
            "correlation_id": "correlation-1",
            "releases": [
                {
                    "version": "3.1.0",
                    "channel": "stable",
                    "platform": requested["platform"],
                    "filename": filename,
                    "size": len(self.installer),
                    "sha256": hashlib.sha256(self.installer).hexdigest(),
                    "notes": "Исправления",
                    "download_url": "https://license.example/downloads/token-1",
                }
            ],
        }
        if mutate:
            mutate(payload)
        envelope = {
            "schema_version": 1,
            "algorithm": "Ed25519",
            "kid": key_id,
            "payload": payload,
            "signature": encode(self.update_key.sign(rfc8785.dumps(payload))),
        }
        return Response(json.dumps(envelope).encode("utf-8"))

    def delegated_key_response(self, key_id="updates-v1"):
        payload = {
            "purpose": "clipart-update-manifest",
            "algorithm": "Ed25519",
            "kid": key_id,
            "public_key": encode(self.update_key.public_key().public_bytes_raw()),
        }
        envelope = {
            "schema_version": 1,
            "algorithm": "Ed25519",
            "kid": "license-v1",
            "payload": payload,
            "signature": encode(self.license_key.sign(rfc8785.dumps(payload))),
        }
        return Response(json.dumps(envelope).encode("utf-8"))

    def test_check_selects_newer_signed_release_without_downloading(self) -> None:
        opener = Opener(self.manifest_response)
        with patch.object(license_client.request, "build_opener", return_value=opener):
            release = self.client.check()
        self.assertEqual(release.version, "3.1.0")
        self.assertEqual(len(opener.requests), 1)
        self.assertFalse((self.root / "updates").exists())

    def test_macos_uses_platform_release_and_downloads_zip(self) -> None:
        client = UpdateClient(
            self.license,
            {"updates-v1": encode(self.update_key.public_key().public_bytes_raw())},
            current_version="3.0",
            download_directory=self.root / "mac-updates",
            platform_id="macos-x64",
        )
        manifest_opener = Opener(self.manifest_response)
        with patch.object(license_client.request, "build_opener", return_value=manifest_opener):
            release = client.check()
        download_opener = Opener(lambda _req: Response(self.installer, "application/zip"))
        with patch.object(update_client.request, "build_opener", return_value=download_opener):
            path = client.download(release)

        self.assertEqual(path.name, "VibixImages-macOS-3.1.0-x64.zip")
        self.assertEqual(path.read_bytes(), self.installer)
        self.assertEqual(download_opener.requests[0][0].headers["Accept"], "application/zip")

    def test_current_platform_identifies_apple_silicon(self) -> None:
        with patch.object(update_client.sys, "platform", "darwin"), patch.object(
            update_client.platform, "machine", return_value="arm64"
        ):
            self.assertEqual(current_platform_id(), "macos-arm64")

    def test_current_platform_identifies_intel_macos(self) -> None:
        with patch.object(update_client.sys, "platform", "darwin"), patch.object(
            update_client.platform, "machine", return_value="x86_64"
        ):
            self.assertEqual(current_platform_id(), "macos-x64")

    def test_update_key_is_accepted_only_through_license_signed_delegation(self) -> None:
        client = UpdateClient(
            self.license,
            current_version="3.0",
            download_directory=self.root / "updates",
        )

        def responder(req):
            if req.full_url.endswith("/api/v1/releases/key"):
                return self.delegated_key_response()
            return self.manifest_response(req)

        opener = Opener(responder)
        with patch.object(license_client.request, "build_opener", return_value=opener):
            release = client.check()
        self.assertEqual(release.version, "3.1.0")
        self.assertEqual(len(opener.requests), 2)

    def test_delegated_v2_key_is_stored_under_its_signed_key_id(self) -> None:
        client = UpdateClient(
            self.license,
            current_version="3.0",
            download_directory=self.root / "updates-v2",
        )

        def responder(req):
            if req.full_url.endswith("/api/v1/releases/key"):
                return self.delegated_key_response("updates-v2")
            return self.manifest_response(req, key_id="updates-v2")

        opener = Opener(responder)
        with patch.object(license_client.request, "build_opener", return_value=opener):
            release = client.check()

        self.assertEqual(release.version, "3.1.0")
        self.assertIn("updates-v2", client._public_keys)

    def test_manifest_rejects_wrong_nonce_and_external_download_url(self) -> None:
        mutations = (
            lambda payload: payload.update(nonce="replayed"),
            lambda payload: payload["releases"][0].update(download_url="https://evil.example/setup.exe"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                opener = Opener(lambda req, mutate=mutate: self.manifest_response(req, mutate=mutate))
                with patch.object(license_client.request, "build_opener", return_value=opener):
                    with self.assertRaises(UpdateError):
                        self.client.check()

    def test_download_is_atomic_verified_and_reports_progress(self) -> None:
        manifest_opener = Opener(self.manifest_response)
        with patch.object(license_client.request, "build_opener", return_value=manifest_opener):
            release = self.client.check()
        progress = []
        download_opener = Opener(lambda _req: Response(self.installer, "application/vnd.microsoft.portable-executable"))
        with patch.object(update_client.request, "build_opener", return_value=download_opener):
            path = self.client.download(release, progress=lambda done, total: progress.append((done, total)))
        self.assertEqual(path.read_bytes(), self.installer)
        self.assertEqual(progress[-1], (len(self.installer), len(self.installer)))
        self.assertFalse(any(path.parent.glob("*.part")))

    def test_prelaunch_verification_rejects_a_tampered_download(self) -> None:
        release = update_client.UpdateRelease(
            version="3.1.0",
            filename="VibixImages-Setup-3.1.exe",
            size=len(self.installer),
            sha256=hashlib.sha256(self.installer).hexdigest(),
            download_url="https://license.example/downloads/token-1",
        )
        path = self.root / "updates" / release.filename
        path.parent.mkdir()
        path.write_bytes(self.installer)
        self.client.verify_download(release, path)
        path.write_bytes(b"tampered")

        with self.assertRaisesRegex(UpdateError, "проверку"):
            self.client.verify_download(release, path)

    def test_cancel_and_checksum_mismatch_remove_partial_file(self) -> None:
        manifest_opener = Opener(self.manifest_response)
        with patch.object(license_client.request, "build_opener", return_value=manifest_opener):
            release = self.client.check()
        for cancelled, payload in ((lambda: True, self.installer), (lambda: False, b"wrong-installer-bytes")):
            with self.subTest(cancelled=cancelled()):
                opener = Opener(lambda _req, payload=payload: Response(payload))
                with patch.object(update_client.request, "build_opener", return_value=opener):
                    with self.assertRaises(UpdateError):
                        self.client.download(release, cancelled=cancelled)
                self.assertFalse(any((self.root / "updates").glob("*")))


if __name__ == "__main__":
    unittest.main()
