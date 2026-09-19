import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from studio_module_packaging import prepare_module_release
from studio_modules import ModuleStore, ModulePackageError


class ModulePackagingTests(unittest.TestCase):
    def setUp(self):
        self.key = Ed25519PrivateKey.generate()
        self.args = dict(module_id="sample", version="1.0.0", studio_min="3.2.0",
                         studio_max_exclusive="4.0.0", platforms=["windows-x64"],
                         entrypoint="entry.py", files={"entry.py": b"# signed source"},
                         key_id="publisher-test", private_key=self.key)

    def test_prepared_artifact_installs_updates_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            user_data = root / "project.txt"
            user_data.write_text("owner data")
            public = self.key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
            store = ModuleStore(root / "modules", studio_version="3.2.0",
                                platform="windows-x64", trusted_keys={"publisher-test": public})
            for version in ("1.0.0", "1.1.0"):
                path = root / (version + ".zip")
                path.write_bytes(prepare_module_release(**{**self.args, "version": version}))
                store.install(path, expected_module_id="sample", expected_version=version)
                store.activate("sample", version)
            self.assertEqual(store.state("sample")["active"], "1.1.0")
            store.rollback("sample")
            self.assertEqual(store.state("sample")["active"], "1.0.0")
            self.assertEqual(user_data.read_text(), "owner data")

    def test_payload_is_deterministic_and_never_executed(self):
        args = {**self.args, "files": {"entry.py": b"raise RuntimeError('must not run')"}}
        self.assertEqual(prepare_module_release(**args), prepare_module_release(**args))

    def test_rejects_unsafe_or_incompatible_input(self):
        cases = [
            {"files": {"../entry.py": b"x"}},
            {"files": {"entry.py": b"x", "ENTRY.py": b"y"}},
            {"files": {"entry.py": b"x", "manifest.json": b"override"}},
            {"files": {"entry.py": "not bytes"}},
            {"platforms": []},
            {"platforms": ["unknown"]},
            {"studio_max_exclusive": "3.2.0"},
            {"entrypoint": "missing.py"},
            {"module_id": "../bad"},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides), self.assertRaises(ModulePackageError):
                prepare_module_release(**{**self.args, **overrides})


if __name__ == "__main__":
    unittest.main()
