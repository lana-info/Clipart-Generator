import unittest
from pathlib import Path


class BuildConstraintsTests(unittest.TestCase):
    def test_constraints_use_only_pip_supported_package_pins(self):
        constraints = Path("constraints-build.txt").read_text(encoding="utf-8").splitlines()
        entries = [line.strip() for line in constraints if line.strip() and not line.startswith("#")]

        self.assertTrue(entries)
        self.assertTrue(all("[" not in entry and "]" not in entry for entry in entries))
        self.assertIn("rembg==2.0.67", entries)

    def test_ben2_onnx_packaging_does_not_add_pytorch(self):
        pipeline = Path("azure-pipelines.yml").read_text(encoding="utf-8")
        macos_pipeline = Path("azure-pipelines-macos.yml").read_text(encoding="utf-8")

        self.assertNotIn("torch==", pipeline)
        self.assertNotIn("requirements-ben2.txt", pipeline)
        self.assertNotIn("torch==", macos_pipeline)
        self.assertNotIn("requirements-ben2.txt", macos_pipeline)

    def test_windows_collects_scipy_array_api_compat_for_rembg(self):
        build_script = Path("build.ps1").read_text(encoding="utf-8")

        self.assertIn(
            '--collect-submodules "scipy._external.array_api_compat"',
            build_script,
        )


if __name__ == "__main__":
    unittest.main()
