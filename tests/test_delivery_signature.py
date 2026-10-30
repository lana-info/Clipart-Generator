"""Contract tests for the signed delivery manifest module (T-QUAL-8).

All signing keys here are disposable, generated in-process test keys;
nothing in this file embeds real or committed key material.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import rsa
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QWidget

import delivery_signature as ds


def generate_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def private_key_pem(key: Ed25519PrivateKey) -> bytes:
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def canonical_payload() -> dict:
    return {
        "product_id": "clipart-generator",
        "version": "3.2.54",
        "platform": "windows-x64",
        "filename": "VibixImages-Setup-3.2.54.exe",
        "size": 243_000_000,
        "sha256": "1" * 64,
        "download_url": "https://license.example/downloads/token-1",
    }


class DeliverySignatureContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = generate_key()
        self.foreign_key = generate_key()
        self.payload = canonical_payload()
        self.signature = ds.sign_manifest_payload(self.payload, self.key)

    def test_signature_is_detached_base64_and_payload_is_plain_json(self) -> None:
        self.assertRegex(self.signature, r"[A-Za-z0-9_-]{86}")
        # The payload itself stays a plain document: signature travels beside it.
        restored = json.loads(json.dumps(self.payload))
        ds.verify_manifest_signature(restored, self.signature, self.key.public_key())

    def test_signature_covers_canonical_payload_regardless_of_key_order(self) -> None:
        reordered = dict(reversed(list(self.payload.items())))
        ds.verify_manifest_signature(reordered, self.signature, self.key.public_key())

    def test_tampered_payload_is_rejected(self) -> None:
        tampered = {**self.payload, "sha256": "2" * 64}
        with self.assertRaisesRegex(ds.DeliverySignatureError, "проверить"):
            ds.verify_manifest_signature(tampered, self.signature, self.key.public_key())

    def test_foreign_key_signature_is_rejected(self) -> None:
        foreign_signature = ds.sign_manifest_payload(self.payload, self.foreign_key)
        with self.assertRaisesRegex(ds.DeliverySignatureError, "проверить"):
            ds.verify_manifest_signature(
                self.payload, foreign_signature, self.key.public_key()
            )

    def test_envelope_roundtrip_and_format_guards(self) -> None:
        envelope = ds.build_delivery_envelope(self.payload, self.key)
        self.assertEqual(
            ds.verify_delivery_envelope(
                envelope, {"delivery-v1": self.key.public_key()}
            ),
            self.payload,
        )
        for mutate in (
            lambda env: env.update(schema_version=2),
            lambda env: env.update(algorithm="Ed448"),
            lambda env: env.update(kid="../evil"),
            lambda env: env.pop("payload"),
            lambda env: env.update(payload="not-a-dict"),
            lambda env: env.update(signature=self.signature[:-2]),
        ):
            with self.subTest(mutate=mutate.__name__ if hasattr(mutate, "__name__") else "?"):
                broken = json.loads(json.dumps(envelope))
                mutate(broken)
                with self.assertRaises(ds.DeliverySignatureError):
                    ds.verify_delivery_envelope(
                        broken, {"delivery-v1": self.key.public_key()}
                    )

    def test_delivery_policy_matrix(self) -> None:
        self.assertTrue(
            ds.DeliveryPolicy().signature_required(has_public_key=True)
        )
        self.assertFalse(
            ds.DeliveryPolicy().signature_required(has_public_key=False)
        )
        disabled = ds.DeliveryPolicy(verify_enabled=False)
        self.assertFalse(disabled.signature_required(has_public_key=True))
        lenient = ds.DeliveryPolicy(reject_unsigned_with_configured_key=False)
        self.assertFalse(lenient.signature_required(has_public_key=True))

    def test_enforce_policy_demands_signature_only_with_configured_key(self) -> None:
        keys = {"delivery-v1": self.key.public_key()}
        with self.assertRaisesRegex(ds.DeliverySignatureError, "не сопровождено"):
            ds.enforce_delivery_policy(None, keys, ds.DeliveryPolicy())
        with self.assertRaisesRegex(ds.DeliverySignatureError, "не сопровождено"):
            ds.enforce_delivery_policy({}, keys, ds.DeliveryPolicy())
        self.assertIsNone(
            ds.enforce_delivery_policy(None, {}, ds.DeliveryPolicy())
        )

    def test_enforce_policy_disabled_skips_verification_entirely(self) -> None:
        envelope = ds.build_delivery_envelope(self.payload, self.foreign_key)
        self.assertIsNone(
            ds.enforce_delivery_policy(
                envelope,
                {"delivery-v1": self.key.public_key()},
                ds.DeliveryPolicy(verify_enabled=False),
            )
        )
        # The same tampered envelope is rejected the moment the policy is on,
        # proving the disabled mode is a real bypass, not a hidden no-op fix.
        with self.assertRaises(ds.DeliverySignatureError):
            ds.enforce_delivery_policy(
                envelope,
                {"delivery-v1": self.key.public_key()},
                ds.DeliveryPolicy(),
            )

    def test_enforce_policy_passes_valid_envelope_through(self) -> None:
        envelope = ds.build_delivery_envelope(self.payload, self.key)
        payload = ds.enforce_delivery_policy(
            envelope, {"delivery-v1": self.key.public_key()}, ds.DeliveryPolicy()
        )
        self.assertEqual(payload, self.payload)

    def test_key_file_helpers_roundtrip_without_printing_material(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            key_path = root / "signing.pem"
            key_path.write_bytes(private_key_pem(self.key))
            key_path.chmod(0o600)
            public_path = root / "signing.pub.pem"
            loaded = ds.load_signing_key_file(key_path)
            self.assertEqual(
                ds.public_key_b64(loaded.public_key()),
                ds.public_key_b64(self.key.public_key()),
            )
            ds.write_public_key_file(loaded.public_key(), public_path)
            self.assertEqual(
                ds.public_key_b64(ds.load_public_key_file(public_path)),
                ds.public_key_b64(self.key.public_key()),
            )

            foreign = generate_key()
            foreign_path = root / "foreign.pem"
            foreign_path.write_bytes(private_key_pem(foreign))
            self.assertEqual(
                ds.public_key_b64(ds.load_signing_key_file(foreign_path).public_key()),
                ds.public_key_b64(foreign.public_key()),
            )

    def test_non_ed25519_key_file_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            rsa_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            path = Path(temp) / "rsa.pem"
            path.write_bytes(
                rsa_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )
            with self.assertRaisesRegex(ds.DeliverySignatureError, "Ed25519"):
                ds.load_signing_key_file(path)
            with self.assertRaises(ds.DeliverySignatureError):
                ds.load_signing_key_file(Path(temp) / "missing.pem")

    def test_invalid_payload_never_enters_the_signature(self) -> None:
        with self.assertRaisesRegex(ds.DeliverySignatureError, "JSON-объектом"):
            ds.sign_manifest_payload("not-a-dict", self.key)
        with self.assertRaisesRegex(ds.DeliverySignatureError, "размер"):
            ds.sign_manifest_payload(
                {"blob": "x" * (ds.MAX_MANIFEST_PAYLOAD_BYTES + 1)}, self.key
            )

    def test_error_messages_carry_no_key_or_signature_material(self) -> None:
        signature_text = self.signature
        key_text = ds.public_key_b64(self.key.public_key())
        errors = []
        try:
            ds.verify_manifest_signature(
                {**self.payload, "sha256": "3" * 64},
                signature_text,
                self.key.public_key(),
            )
        except ds.DeliverySignatureError as exc:
            errors.append(str(exc))
        try:
            ds.verify_delivery_envelope(
                ds.build_delivery_envelope(self.payload, self.foreign_key),
                {"delivery-v1": self.key.public_key()},
            )
        except ds.DeliverySignatureError as exc:
            errors.append(str(exc))
        self.assertTrue(errors)
        for message in errors:
            self.assertNotIn(signature_text, message)
            self.assertNotIn(key_text, message)


class DeliverySignatureCliTests(unittest.TestCase):
    def run_cli(self, *arguments, extra_env=None) -> subprocess.CompletedProcess:
        environment = {**os.environ}
        if extra_env:
            environment.update(extra_env)
        return subprocess.run(
            [sys.executable, "delivery_signature.py", *arguments],
            capture_output=True,
            text=True,
            env=environment,
        )

    def test_sign_skip_verify_and_artifact_mismatch_paths(self) -> None:
        key = generate_key()
        payload = canonical_payload()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload_path = root / "manifest.json"
            payload_path.write_text(json.dumps(payload), encoding="utf-8")
            envelope_path = root / "manifest.envelope.json"
            public_path = root / "public.pem"
            ds.write_public_key_file(key.public_key(), public_path)

            skipped = self.run_cli(
                "sign", "--payload", str(payload_path),
                "--output", str(envelope_path), "--key-env", "T8_ABSENT_KEY_ENV",
            )
            self.assertEqual(skipped.returncode, 0)
            self.assertIn("SKIP", skipped.stdout)
            self.assertFalse(envelope_path.exists())

            signed = self.run_cli(
                "sign", "--payload", str(payload_path),
                "--output", str(envelope_path), "--key-env", "T8_TEST_KEY_ENV",
                extra_env={"T8_TEST_KEY_ENV": private_key_pem(key).decode("ascii")},
            )
            self.assertEqual(signed.returncode, 0)
            self.assertIn("SIGNED", signed.stdout)
            self.assertNotIn("BEGIN", signed.stdout)

            verified = self.run_cli(
                "verify", "--envelope", str(envelope_path),
                "--public-key-file", str(public_path),
                "--artifact-sha256", payload["sha256"],
            )
            self.assertEqual(verified.returncode, 0)
            self.assertIn("VERIFIED", verified.stdout)

            mismatched = self.run_cli(
                "verify", "--envelope", str(envelope_path),
                "--public-key-file", str(public_path),
                "--artifact-sha256", "9" * 64,
            )
            self.assertEqual(mismatched.returncode, 1)
            self.assertNotIn(payload["sha256"], mismatched.stdout)

            tampered = json.loads(envelope_path.read_text(encoding="utf-8"))
            tampered["payload"]["sha256"] = "8" * 64
            tampered_path = root / "tampered.json"
            tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
            refused = self.run_cli(
                "verify", "--envelope", str(tampered_path),
                "--public-key-file", str(public_path),
            )
            self.assertEqual(refused.returncode, 1)

    def test_cli_verify_refuses_invalid_envelope_file(self) -> None:
        key = generate_key()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            public_path = root / "public.pem"
            ds.write_public_key_file(key.public_key(), public_path)
            broken_path = root / "broken.json"
            broken_path.write_text("{}", encoding="utf-8")
            refused = self.run_cli(
                "verify", "--envelope", str(broken_path),
                "--public-key-file", str(public_path),
            )
            self.assertEqual(refused.returncode, 1)



class ImmediateCheckWorker(QObject):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self.client = client

    def start(self):
        self.completed.emit(self.client.checked_release)


class ImmediateDownloadWorker(QObject):
    progress = pyqtSignal(int, int)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, client, release, parent=None):
        super().__init__(parent)
        self.client = client
        self.release = release
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def start(self):
        self.progress.emit(self.release.size, self.release.size)
        self.completed.emit(str(self.client.installer_path))


class DeliveryFakeClient:
    current_version = "3.0"

    def __init__(self, release, installer_path, gate):
        from contextlib import contextmanager

        self.release = release
        self.checked_release = release
        self.installer_path = installer_path
        self._gate = gate
        self.delivery_calls = []

        @contextmanager
        def protected_download(_release, path):
            yield path

        self.protected_download = protected_download

    def verify_release_manifest(self, envelope, release):
        self.delivery_calls.append((envelope, release))
        self._gate(envelope, release)

    def cleanup_stale_downloads(self):
        pass


class UpdateControllerDeliveryGateTests(unittest.TestCase):
    """The controller refuses to launch an installer when the gate fails."""

    @classmethod
    def setUpClass(cls) -> None:
        from PyQt6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.launched = []
        self.signature_text = "B" * 86

    def release(self):
        from update_client import UpdateRelease

        return UpdateRelease(
            version="3.1.0",
            filename="VibixImages-Setup-3.1.exe",
            size=20,
            sha256="a" * 64,
            download_url="https://license.example/downloads/token",
            correlation_id="corr-1",
            delivery_envelope={"kid": "delivery-v1", "signature": self.signature_text},
        )

    def run_controller(self, client, journal) -> None:
        import v3_updater

        with patch("v3_updater.QMessageBox.warning"):
            controller = v3_updater.UpdateController(
                QWidget(),
                client,
                journal,
                prompt=lambda _release: True,
                check_worker_factory=ImmediateCheckWorker,
                download_worker_factory=ImmediateDownloadWorker,
                installer_launcher=self.launched.append,
            )
            controller.start_check()

    def test_failed_delivery_verification_never_starts_installer(self) -> None:
        from diagnostics import DiagnosticJournal
        from update_client import UpdateError

        with tempfile.TemporaryDirectory() as temp:
            installer = Path(temp) / "VibixImages-Setup-3.1.exe"
            installer.write_bytes(b"payload")
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            client = DeliveryFakeClient(
                self.release(), installer,
                lambda _envelope, _release: (_ for _ in ()).throw(
                    UpdateError("Не удалось проверить подпись манифеста")
                ),
            )
            self.run_controller(client, journal)
            self.assertEqual(self.launched, [])
            self.assertEqual(len(client.delivery_calls), 1)
            journal_text = json.dumps(journal.read_events(), default=str)
            self.assertIn("update_prelaunch_verification_failed", journal_text)
            self.assertNotIn(self.signature_text, journal_text)

    def test_passed_delivery_verification_launches_with_binding_arguments(self) -> None:
        from diagnostics import DiagnosticJournal

        with tempfile.TemporaryDirectory() as temp:
            installer = Path(temp) / "VibixImages-Setup-3.1.exe"
            installer.write_bytes(b"payload")
            journal = DiagnosticJournal(Path(temp), app_version="3.0")
            client = DeliveryFakeClient(
                self.release(), installer, lambda _envelope, _release: None,
            )
            self.run_controller(client, journal)
            self.assertEqual(self.launched, [installer])
            envelope_seen, release_seen = client.delivery_calls[0]
            self.assertEqual(envelope_seen, client.release.delivery_envelope)
            self.assertEqual(release_seen, client.release)


class UpdateDeliveryManifestGateTests(unittest.TestCase):
    """Negative controls for the client gate applied before an update runs."""

    def setUp(self) -> None:
        import base64 as b64
        import hashlib

        import license_client

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.encode = lambda raw: b64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
        self.license_key = Ed25519PrivateKey.generate()
        self.update_key = Ed25519PrivateKey.generate()
        self.delivery_key = Ed25519PrivateKey.generate()
        self.foreign_delivery_key = Ed25519PrivateKey.generate()
        self.license = license_client.LicenseClient(
            base_url="https://license.example",
            state_path=str(self.root / "license.json"),
            public_keys={
                "license-v1": self.encode(
                    self.license_key.public_key().public_bytes_raw()
                )
            },
            product_id="clipart-generator",
        )
        private = self.license._state.load_or_create_private_key()
        self.license._state.save_activation(private, "license-id")
        self.installer = b"windows-installer-3.1"
        self.installer_sha256 = hashlib.sha256(self.installer).hexdigest()
        self.client = self.build_client()
        self.release = self.client._parse_release(self.release_item(), "corr-1")

    def build_client(self, **overrides):
        from update_client import UpdateClient

        options = {
            "license_client": self.license,
            "public_keys": {
                "updates-v1": self.encode(
                    self.update_key.public_key().public_bytes_raw()
                )
            },
            "current_version": "3.0",
            "download_directory": self.root / "updates",
            "delivery_public_keys": {
                "delivery-v1": self.encode(
                    self.delivery_key.public_key().public_bytes_raw()
                )
            },
        }
        options.update(overrides)
        return UpdateClient(**options)

    def release_item(self, envelope=None) -> dict:
        item = {
            "version": "3.1.0",
            "channel": "stable",
            "platform": "windows-x64",
            "filename": "VibixImages-Setup-3.1.exe",
            "size": len(self.installer),
            "sha256": self.installer_sha256,
            "download_url": "https://license.example/downloads/token-1",
        }
        if envelope is not None:
            item["delivery_manifest"] = envelope
        return item

    def signed_envelope(self, release, *, key=None, sha256=None) -> dict:
        payload = {
            "product_id": "clipart-generator",
            "platform": "windows-x64",
            "version": release.version,
            "filename": release.filename,
            "size": release.size,
            "sha256": sha256 or release.sha256,
            "download_url": release.download_url,
        }
        return ds.build_delivery_envelope(payload, key or self.delivery_key)

    def test_valid_signed_manifest_passes_and_binds_to_release(self) -> None:
        envelope = self.signed_envelope(self.release)
        release = self.client._parse_release(self.release_item(envelope), "corr-1")
        self.assertEqual(release.delivery_envelope, envelope)
        payload = self.client.verify_release_manifest(
            release.delivery_envelope, release
        )
        self.assertEqual(payload["sha256"], release.sha256)

    def test_missing_signature_is_refused_when_delivery_key_is_pinned(self) -> None:
        from update_client import UpdateError

        with self.assertRaisesRegex(UpdateError, "не сопровождено"):
            self.client.verify_release_manifest(None, self.release)
        with self.assertRaisesRegex(UpdateError, "не сопровождено"):
            self.client.verify_release_manifest(
                self.release.delivery_envelope, self.release
            )

    def test_tampered_manifest_payload_is_refused(self) -> None:
        from update_client import UpdateError

        envelope = self.signed_envelope(self.release)
        envelope["payload"]["size"] += 1
        with self.assertRaisesRegex(UpdateError, "подпись"):
            self.client.verify_release_manifest(envelope, self.release)

    def test_manifest_signed_by_foreign_key_is_refused(self) -> None:
        from update_client import UpdateError

        envelope = self.signed_envelope(
            self.release, key=self.foreign_delivery_key
        )
        with self.assertRaisesRegex(UpdateError, "проверить"):
            self.client.verify_release_manifest(envelope, self.release)

    def test_altered_sha256_is_refused(self) -> None:
        from update_client import UpdateError

        # (a) a correctly signed manifest whose checksum contradicts the
        # accepted release row must not be applied;
        wrong_sha_envelope = self.signed_envelope(self.release, sha256="9" * 64)
        with self.assertRaisesRegex(UpdateError, "не соответствует"):
            self.client.verify_release_manifest(wrong_sha_envelope, self.release)
        # (b) a valid manifest bound to the release row still must match the
        # digest of the bytes that are actually on disk;
        envelope = self.signed_envelope(self.release)
        with self.assertRaisesRegex(UpdateError, "не соответствует"):
            self.client.verify_release_manifest(
                envelope, self.release, expected_sha256="8" * 64
            )
        # and the honest pair verifies.
        self.client.verify_release_manifest(
            envelope, self.release, expected_sha256=self.release.sha256
        )

    def test_unsigned_manifest_is_accepted_without_pinned_delivery_key(self) -> None:
        from delivery_signature import DeliveryPolicy

        legacy_client = self.build_client(delivery_public_keys=None)
        self.assertEqual(legacy_client.delivery_policy, DeliveryPolicy())
        legacy_release = legacy_client._parse_release(self.release_item(), "corr-1")
        self.assertIsNone(legacy_client.verify_release_manifest(None, legacy_release))
        self.assertIsNone(legacy_client.verify_release_manifest(
            self.signed_envelope(legacy_release), legacy_release
        ))

    def test_disabled_policy_skips_even_a_tampered_manifest(self) -> None:
        from delivery_signature import DeliveryPolicy

        from update_client import UpdateError

        bypassed_client = self.build_client(
            delivery_policy=DeliveryPolicy(verify_enabled=False)
        )
        envelope = self.signed_envelope(self.release)
        envelope["payload"]["sha256"] = "7" * 64
        self.assertIsNone(
            bypassed_client.verify_release_manifest(envelope, self.release)
        )
        # The very same tampered manifest fails as soon as the gate is on.
        with self.assertRaises(UpdateError):
            self.client.verify_release_manifest(envelope, self.release)

    def test_malformed_delivery_manifest_block_from_server_is_refused(self) -> None:
        from update_client import UpdateError

        for bad in ("not-a-dict", 42, [self.signed_envelope(self.release)]):
            with self.subTest(kind=type(bad).__name__):
                with self.assertRaisesRegex(UpdateError, "манифест"):
                    self.client._parse_release(self.release_item(bad), "corr-1")

    def test_gate_failures_leak_no_signature_or_key_material(self) -> None:
        from update_client import UpdateError

        envelope = self.signed_envelope(
            self.release, key=self.foreign_delivery_key
        )
        signature_text = envelope["signature"]
        public_text = self.encode(
            self.delivery_key.public_key().public_bytes_raw()
        )
        messages = []
        for broken in (envelope, None):
            try:
                self.client.verify_release_manifest(broken, self.release)
            except UpdateError as exc:
                messages.append(str(exc))
        self.assertTrue(messages)
        for message in messages:
            self.assertNotIn(signature_text, message)
            self.assertNotIn(public_text, message)


class DeliveryPrivacyRedactionTests(unittest.TestCase):
    """Delivery material behaves correctly through the redaction skew."""

    def setUp(self) -> None:
        from security_redaction import redact_text, redact_value

        self.redact_text = redact_text
        self.redact_value = redact_value
        self.key = Ed25519PrivateKey.generate()
        self.signature = ds.sign_manifest_payload(
            {"version": "3.1.0", "sha256": "a" * 64}, self.key
        )

    def test_public_signature_and_key_are_not_over_redacted(self) -> None:
        public_key_text = ds.public_key_b64(self.key.public_key())
        text = (
            f"manifest …{self.signature[:16]}… verified kid=delivery-v1 "
            f"key={public_key_text}"
        )
        self.assertEqual(self.redact_text(text), text)
        shape = {
            "signature": self.signature,
            "kid": "delivery-v1",
            "public_key": public_key_text,
        }
        self.assertEqual(self.redact_value(shape), shape)

    def test_private_key_named_fields_are_hidden_in_any_shape(self) -> None:
        private_material = ds.encode_key_b64(self.key.private_bytes_raw())
        shape = {
            "events": [
                {"private_key": private_material},
                {"signing_private_key": private_material},
            ],
            "signature": self.signature,
        }
        redacted = self.redact_value(shape)
        self.assertEqual(redacted["events"][0]["private_key"], "[hidden]")
        self.assertEqual(redacted["events"][1]["signing_private_key"], "[hidden]")
        self.assertEqual(redacted["signature"], self.signature)
        # The original nested mapping is not mutated by redaction.
        self.assertEqual(shape["events"][0]["private_key"], private_material)


if __name__ == "__main__":
    unittest.main()
