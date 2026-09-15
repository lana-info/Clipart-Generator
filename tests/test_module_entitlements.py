import base64
import hashlib
import json
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_client import LicenseClient, LicenseError
from studio_module_access import ModuleAccessPolicy
from tests.test_license_client_security import FakeOpener, SignedLicenseResponder


def encoded(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class ModuleEntitlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.key = Ed25519PrivateKey.generate()
        self.now = datetime.now(timezone.utc)
        self.client = LicenseClient(base_url="https://license.example", product_id="clipart-generator",
            state_path=str(Path(self.tmp.name) / "state.json"),
            public_keys={"test": encoded(self.key.public_key().public_bytes_raw())})

    def envelope(self, grants="missing"):
        payload = dict(license_id="fixture", product_id="clipart-generator", device_key="device",
                       nonce="nonce", issued_at=self.now.isoformat(),
                       expires_at=(self.now + timedelta(minutes=5)).isoformat())
        if grants != "missing":
            payload["module_entitlements"] = grants
        return dict(schema_version=1, algorithm="Ed25519", kid="test", payload=payload,
                    signature=encoded(self.key.sign(rfc8785.dumps(payload))))

    def grants(self, module="clipart", **updates):
        grant = dict(module_id=module, not_before=self.now.isoformat(),
                     expires_at=(self.now + timedelta(days=2)).isoformat())
        grant.update(updates)
        return dict(schema_version=1, grants=[grant])

    def verify(self, envelope):
        return self.client._verify_authorization(envelope, "device", "nonce", now=self.now)

    def test_license_service_backend_v1_wire_contract_parses_without_adapter(self):
        payload = {
            "license_id": "fixture",
            "product_id": "clipart-generator",
            "device_key": "device",
            "issued_at": self.now.isoformat(),
            "expires_at": (self.now + timedelta(minutes=5)).isoformat(),
            "nonce": "nonce",
            "correlation_id": "correlation",
            "module_entitlements": {
                "schema_version": 1,
                "grants": [{
                    "module_id": "clipart",
                    "not_before": self.now.isoformat(),
                    "expires_at": (self.now + timedelta(days=7)).isoformat(),
                }],
            },
        }
        envelope = {
            "schema_version": 1, "algorithm": "Ed25519", "kid": "test",
            "payload": payload, "signature": encoded(self.key.sign(rfc8785.dumps(payload))),
        }
        authorization = self.verify(envelope)
        self.assertTrue(authorization.allows_module("clipart", now=self.now))
        self.assertFalse(authorization.allows_module("pinterest", now=self.now))
        self.assertEqual(authorization.module_entitlements[0].expires_at, self.now + timedelta(days=7))

    def test_legacy_authorization_has_no_module_rights(self):
        auth = self.verify(self.envelope())
        self.assertFalse(auth.allows_module("clipart", now=self.now))
        self.assertEqual(auth.module_entitlements, ())

    def test_only_explicit_signed_matching_module_is_allowed(self):
        auth = self.verify(self.envelope(self.grants()))
        self.assertTrue(auth.allows_module("clipart", now=self.now))
        self.assertFalse(auth.allows_module("patterns", now=self.now))
        self.assertFalse(auth.allows_module("clipart", now=self.now + timedelta(minutes=5)))

    def test_tampered_grant_is_rejected_by_signature(self):
        envelope = self.envelope(self.grants())
        envelope["payload"]["module_entitlements"]["grants"][0]["module_id"] = "patterns"
        with self.assertRaises(LicenseError):
            self.verify(envelope)

    def test_invalid_schema_duplicates_and_unbounded_grants_are_rejected(self):
        duplicate = self.grants()
        duplicate["grants"] *= 2
        for claims in (None, {}, {"schema_version": True, "grants": []}, duplicate,
                       self.grants("../escape"), self.grants(expires_at=None),
                       {"schema_version": 2, "grants": []},
                       {"schema_version": 1, "grants": self.grants()["grants"] * 101}):
            with self.subTest(claims=claims), self.assertRaises(LicenseError):
                self.verify(self.envelope(claims))

    def test_expired_and_future_grants_are_not_active(self):
        expired = self.grants(not_before=(self.now - timedelta(days=2)).isoformat(),
                              expires_at=self.now.isoformat())
        future = self.grants(not_before=(self.now + timedelta(hours=1)).isoformat())
        for claims in (expired, future):
            self.assertFalse(self.verify(self.envelope(claims)).allows_module("clipart", now=self.now))

    def test_offline_reuses_exact_signed_grants_without_extending_their_expiry(self):
        responder = SignedLicenseResponder(self.key, kid="test", mutate_payload=lambda payload:
            payload.update(module_entitlements=self.grants()))
        with patch("license_client.request.build_opener", return_value=FakeOpener(responder)):
            online = self.client.activate("fixture-key")
        tomorrow = online.issued_at + timedelta(days=1)
        offline = self.client.authorize_offline_grace(now=tomorrow)
        self.assertEqual(offline.module_entitlements, online.module_entitlements)
        self.assertTrue(offline.allows_module("clipart", now=tomorrow))
        self.assertFalse(offline.allows_module("patterns", now=tomorrow))
        self.assertFalse(offline.allows_module("clipart", now=online.issued_at + timedelta(days=3)))

    def test_policy_reauthorizes_each_call_and_never_uses_cached_rights_after_denial(self):
        gate = Mock()
        gate.authorize_run.side_effect = [self.verify(self.envelope(self.grants())),
                                          self.verify(self.envelope()), LicenseError("denied")]
        policy = ModuleAccessPolicy(gate)
        self.assertTrue(policy("clipart", "load"))
        self.assertFalse(policy("clipart", "command:export"))
        with self.assertRaises(LicenseError):
            policy("clipart", "activate")
        self.assertEqual(gate.authorize_run.call_count, 3)

    def test_policy_blocks_unknown_actions_without_request(self):
        gate = Mock()
        self.assertFalse(ModuleAccessPolicy(gate)("clipart", "wildcard"))
        gate.authorize_run.assert_not_called()

    def test_signed_license_policy_gates_real_package_activation_and_commands(self):
        from studio_modules import ModuleStore, canonical_manifest
        from studio_module_runtime import ModuleRuntimeHost, ModuleAuthorizationError
        root = Path(self.tmp.name)
        store = ModuleStore(root / "modules", studio_version="3.2.0", platform="test",
            trusted_keys={"fixture": self.key.public_key().public_bytes_raw()})
        code = ("from studio_module_runtime import ModuleRegistration, CommandDeclaration\n"
                "def register(context):\n"
                " return ModuleRegistration(context.module_id, context.version, "
                "commands=(CommandDeclaration('export', lambda: 'ready'),))\n").encode()
        manifest = dict(schema_version=1, module_id="clipart", version="1.0.0", module_api=1,
            studio_min="3.2.0", studio_max_exclusive="4.0.0", platforms=["test"],
            entrypoint="entry.py", files={"entry.py": hashlib.sha256(code).hexdigest()})
        package = root / "fixture.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("signature.json", json.dumps(dict(key_id="fixture",
                signature=base64.b64encode(self.key.sign(canonical_manifest(manifest))).decode())))
            archive.writestr("entry.py", code)
        store.install(package)
        gate = Mock()
        gate.authorize_run.return_value = self.verify(self.envelope())
        host = ModuleRuntimeHost(store, ModuleAccessPolicy(gate))
        self.addCleanup(host.unload, "clipart")
        with self.assertRaises(ModuleAuthorizationError):
            host.activate("clipart", "1.0.0")
        self.assertIsNone(store.state("clipart")["active"])
        gate.authorize_run.return_value = self.verify(self.envelope(self.grants()))
        host.activate("clipart", "1.0.0")
        self.assertEqual(host.invoke_command("clipart", "export"), "ready")
        gate.authorize_run.return_value = self.verify(self.envelope())
        with self.assertRaises(ModuleAuthorizationError):
            host.invoke_command("clipart", "export")


if __name__ == "__main__":
    unittest.main()
