import tempfile
import unittest
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, PrivateFormat, NoEncryption

from studio_module_packaging import (
    AUTO_CLIPART_STYLE_PREVIEWS, OFFICIAL_WORKFLOW_FILES, prepare_module_release, main,
)
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

    def test_official_cli_prepares_verified_package_without_overwriting_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "v3_processing_flow.py").write_text("raise RuntimeError('never execute during packaging')")
            key_path = root / "fixture.pem"
            key_path.write_bytes(self.key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()))
            output = root / "processing.zip"
            args = ["--module", "processing", "--version", "1.0.0", "--studio-min", "3.2.0",
                    "--studio-max-exclusive", "4.0.0", "--platform", "windows-x64", "--source-root", str(source),
                    "--key-id", "fixture", "--signing-key-file", str(key_path), "--output", str(output)]
            captured = io.StringIO()
            with redirect_stdout(captured):
                self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(captured.getvalue())["module_id"], "processing")
            original = output.read_bytes()
            store = ModuleStore(root / "store", studio_version="3.2.0", platform="windows-x64",
                                trusted_keys={"fixture": self.key.public_key().public_bytes_raw()})
            self.assertEqual(store.inspect_package(output)["module_id"], "processing")
            with self.assertRaises(FileExistsError):
                main(args)
            self.assertEqual(output.read_bytes(), original)

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

    def test_auto_clipart_preview_inventory_matches_style_library(self):
        from studio_style_profiles import all_style_profiles
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(set(AUTO_CLIPART_STYLE_PREVIEWS),
                         {profile.key for profile in all_style_profiles()})
        self.assertTrue(all((root / 'assets' / 'style_previews' / f'{key}.jpg').is_file()
                            for key in AUTO_CLIPART_STYLE_PREVIEWS))
        self.assertTrue({'studio_clipart_recipe.py', 'studio_clipart_references.py',
                         'studio_reference_editor.py', 'studio_palette_library.py',
                         'studio_clipart_recovery.py', 'studio_clipart_drop.py'}
                        <= set(OFFICIAL_WORKFLOW_FILES['auto-clipart']))


if __name__ == "__main__":
    unittest.main()
