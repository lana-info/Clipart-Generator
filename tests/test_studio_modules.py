import base64
import hashlib
import json
import tempfile
import unittest
import zipfile
import pytest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from studio_modules import ModuleStore, ModulePackageError, canonical_manifest


class ModuleStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.key = Ed25519PrivateKey.generate()
        public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.store = ModuleStore(self.root / "modules", studio_version="3.2.0",
                                 platform="linux-x64", trusted_keys={"test": public})

    def package(self, module="clipart", version="1.0.0", *, overrides=None,
                content=b"# fixture, not executed", tamper=False, extra=None):
        manifest = {"schema_version": 1, "module_id": module, "version": version,
                    "module_api": 1, "studio_min": "3.2.0", "studio_max_exclusive": "4.0.0",
                    "platforms": ["linux-x64"], "entrypoint": "entry.py",
                    "files": {"entry.py": hashlib.sha256(content).hexdigest()}}
        manifest.update(overrides or {})
        signature = {"key_id": "test", "signature": base64.b64encode(
            self.key.sign(canonical_manifest(manifest))).decode()}
        path = self.root / f"{module}-{version}.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("manifest.json", json.dumps(manifest))
            z.writestr("signature.json", json.dumps(signature))
            z.writestr("entry.py", content + (b"tampered" if tamper else b""))
            if extra:
                z.writestr(extra, b"unsafe")
        return path

    def test_independent_install_update_rollback_disable(self):
        project = self.root / "project.png"
        project.write_bytes(b"user data")
        for module in ("clipart", "patterns"):
            self.store.install(self.package(module))
            self.assertIsNone(self.store.state(module)["active"])
            self.store.activate(module, "1.0.0")
        self.store.install(self.package(version="1.1.0"))
        self.store.activate("clipart", "1.1.0")
        self.assertEqual(self.store.state("patterns")["active"], "1.0.0")
        self.store.rollback("clipart")
        self.assertEqual(self.store.state("clipart")["active"], "1.0.0")
        self.store.disable("clipart")
        self.assertFalse(self.store.state("clipart")["enabled"])
        self.assertTrue(self.store.state("patterns")["enabled"])
        self.assertEqual(project.read_bytes(), b"user data")

    def test_busy_or_missing_activation_does_not_change_pointer(self):
        self.store.install(self.package())
        self.store.activate("clipart", "1.0.0")
        for version, busy in (("1.0.0", True), ("2.0.0", False)):
            with self.assertRaises(ModulePackageError):
                self.store.activate("clipart", version, busy=busy)
        self.assertEqual(self.store.state("clipart")["active"], "1.0.0")

    def test_signature_hash_and_compatibility(self):
        for overrides in ({"module_api": 2}, {"studio_min": "3.3.0"},
                          {"platforms": ["windows-x64"]}, {"dependencies": ["unavailable"]}):
            with self.subTest(overrides=overrides), self.assertRaises(ModulePackageError):
                self.store.install(self.package(overrides=overrides))
        with self.assertRaises(ModulePackageError):
            self.store.install(self.package(tamper=True))
        untrusted = ModuleStore(self.root / "other", studio_version="3.2.0",
                                platform="linux-x64", trusted_keys={})
        with self.assertRaises(ModulePackageError):
            untrusted.install(self.package())

    def test_unsafe_paths_are_rejected_without_writes(self):
        for name in ("../escape", "/absolute", "C:/evil", "folder\\escape", "CON", "a./b"):
            with self.subTest(name=name), self.assertRaises(ModulePackageError):
                self.store.install(self.package(extra=name))
        self.assertEqual(list((self.root / "modules").iterdir()), [])

    def test_immutable_installed_version(self):
        path = self.package()
        self.store.install(path)
        with self.assertRaises(ModulePackageError):
            self.store.install(path)
        self.assertEqual((self.root / "modules/clipart/1.0.0/entry.py").read_bytes(), b"# fixture, not executed")

    def test_symlink_module_directory_rejected(self):
        external = self.root / "external"
        external.mkdir()
        (self.root / "modules/clipart").symlink_to(external, target_is_directory=True)
        with self.assertRaises(ModulePackageError):
            self.store.install(self.package())
        self.assertEqual(list(external.iterdir()), [])

    def test_activation_rechecks_installed_integrity(self):
        self.store.install(self.package())
        entry = self.root / "modules/clipart/1.0.0/entry.py"
        entry.write_bytes(b"tampered after install")
        with self.assertRaises(ModulePackageError):
            self.store.activate("clipart", "1.0.0")
        self.assertIsNone(self.store.state("clipart")["active"])

    def test_loading_boundary_rechecks_after_activation(self):
        self.store.install(self.package())
        self.store.activate("clipart", "1.0.0")
        folder = self.store.verified_active_path("clipart")
        self.assertIsNotNone(folder)
        (folder / "entry.py").write_bytes(b"changed after activation")
        with self.assertRaises(ModulePackageError):
            self.store.verified_active_path("clipart")

    def test_activation_rechecks_current_compatibility_and_trust(self):
        self.store.install(self.package())
        self.store.version = (4, 0, 0)
        with self.assertRaises(ModulePackageError):
            self.store.activate("clipart", "1.0.0")
        self.store.version = (3, 2, 0)
        self.store.trusted_keys = {}
        with self.assertRaises(ModulePackageError):
            self.store.activate("clipart", "1.0.0")

    def test_installed_symlink_and_extra_file_rejected(self):
        self.store.install(self.package())
        folder = self.root / "modules/clipart/1.0.0"
        extra = folder / "extra.py"
        extra.write_bytes(b"unsigned")
        with self.assertRaises(ModulePackageError):
            self.store.activate("clipart", "1.0.0")
        extra.unlink()
        extra.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ModulePackageError):
            self.store.activate("clipart", "1.0.0")

    def test_malformed_state_is_rejected(self):
        self.store.install(self.package())
        state = self.root / "modules/clipart/active.json"
        for value in ({}, {"active": "../escape", "previous": None, "enabled": True},
                      {"active": "9.9.9", "previous": None, "enabled": True},
                      {"active": None, "previous": None, "enabled": True}):
            state.write_text(json.dumps(value))
            with self.assertRaises(ModulePackageError):
                self.store.state("clipart")


    def test_activation_transaction_restores_exact_prior_state_on_failure(self):
        self.store.install(self.package(version="1.0.0"))
        self.store.install(self.package(version="1.1.0"))
        self.store.activate("clipart", "1.0.0")
        self.store.disable("clipart")
        before = self.store.state("clipart")
        with self.assertRaisesRegex(RuntimeError, "probe failure"):
            with self.store.activation_transaction("clipart", "1.1.0"):
                self.assertEqual(self.store.state("clipart")["active"], "1.1.0")
                self.assertTrue(self.store.state("clipart")["enabled"] )
                raise RuntimeError("probe failure")
        self.assertEqual(self.store.state("clipart"), before)

    def test_activation_transaction_keeps_verified_activation_on_success(self):
        self.store.install(self.package(version="1.0.0"))
        self.store.install(self.package(version="1.1.0"))
        self.store.activate("clipart", "1.0.0")
        with self.store.activation_transaction("clipart", "1.1.0"):
            self.assertEqual(self.store.state("clipart")["active"], "1.1.0")
        self.assertEqual(self.store.state("clipart")["active"], "1.1.0")
        self.assertEqual(self.store.state("clipart")["previous"], "1.0.0")


if __name__ == "__main__":
    unittest.main()


def test_install_expected_identity_mismatch_writes_nothing(tmp_path):
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    store = ModuleStore(tmp_path / "modules", studio_version="3.2.0",
                        platform="linux-x64", trusted_keys={"test": public})
    # Reuse the class helper by constructing a temporary test case around this store.
    case = ModuleStoreTests(methodName="runTest")
    case.root = tmp_path
    case.key = private
    case.store = store
    package = case.package(module="patterns", version="1.0.0")
    with pytest.raises(ModulePackageError, match="identity"):
        store.install(package, expected_module_id="clipart", expected_version="1.0.0")
    assert not (store.root / "patterns").exists()
