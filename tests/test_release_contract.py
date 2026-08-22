import re
import tempfile
import unittest
from pathlib import Path

from release_contract import (
    ReleaseContractError,
    expected_installer_name,
    load_manifest,
    parse_version,
    resolve_release_version,
    validate_release_contract,
)


class ReleaseContractTests(unittest.TestCase):
    def test_azure_default_matches_release_version(self):
        project_root = Path(__file__).resolve().parents[1]
        version = resolve_release_version(project_root / "release")
        pipeline = (project_root / "azure-pipelines.yml").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"displayName:\s*App version.*?default:\s*['\"]([^'\"]+)['\"]",
            pipeline,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), version)

    def test_accepts_supported_versions_and_bom(self):
        self.assertEqual(parse_version(" 3.0\n"), "3.0")
        self.assertEqual(parse_version("\ufeff3.0.1"), "3.0.1")

    def test_rejects_invalid_or_missing_version(self):
        for value in ("", "3", "3.0.1.2", "unsafe-version"):
            with self.subTest(value=value), self.assertRaises(ReleaseContractError):
                parse_version(value)
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ReleaseContractError):
                resolve_release_version(root)

    def test_validates_packaging_matrix(self):
        version = resolve_release_version(Path("release"))
        self.assertEqual(
            expected_installer_name(version),
            "VibixImages-Setup-3.0.3.exe",
        )
        with tempfile.TemporaryDirectory() as root:
            installer_name = expected_installer_name(version)
            checksum = Path(root) / installer_name.replace(".exe", ".sha256")
            checksum.write_text(
                "a" * 64 + f"  {installer_name}\n",
                encoding="ascii",
            )
            validate_release_contract(
                version,
                installer_name=installer_name,
                executable_path="dist/Vibix Images/Vibix Images.exe",
                checksum_path=checksum,
                manifest={
                    "latest_version": version,
                    "download_url": f"https://updates.example/{installer_name}",
                    "sha256": "a" * 64,
                },
            )

    def test_rejects_stale_manifest(self):
        with self.assertRaises(ReleaseContractError):
            validate_release_contract(
                "3.0",
                manifest={
                    "latest_version": "2.0",
                    "download_url": "https://updates.example/VibixImages-Setup-2.0.exe",
                    "sha256": "b" * 64,
                },
            )

    def test_load_manifest_is_json_object(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "version.json"
            path.write_text('{"latest_version":"3.0"}', encoding="utf-8")
            self.assertEqual(load_manifest(path)["latest_version"], "3.0")

    def test_production_launcher_is_the_protected_main_module(self):
        launcher = Path("run_clipart_gui_v3.py").read_text(encoding="utf-8-sig")
        self.assertIn('runpy.run_module("main", run_name="__main__")', launcher)


if __name__ == "__main__":
    unittest.main()
