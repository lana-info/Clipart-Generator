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

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric import rsa

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
            self.assertNotIn("cakey", message.casefold())


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


if __name__ == "__main__":
    unittest.main()
