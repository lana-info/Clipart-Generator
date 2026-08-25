import unittest
import shutil
import subprocess
import tempfile
from pathlib import Path


class WindowsInstallerContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not available")
    def test_packaging_removes_shadowing_vc_runtime_duplicates_recursively(self):
        with tempfile.TemporaryDirectory(prefix="vibix-vc-runtime-") as temp:
            app_dir = Path(temp) / "Vibix Images"
            internal_dir = app_dir / "_internal"
            nested_dir = internal_dir / "PyQt6" / "Qt6" / "bin"
            nested_dir.mkdir(parents=True)
            for name in ("msvcp140.dll", "vcruntime140_1.dll", "onnxruntime.dll"):
                (internal_dir / name).write_bytes(b"fixture")
            (nested_dir / "MSVCP140.dll").write_bytes(b"fixture")
            hashed_runtime = internal_dir / "numpy.libs" / "msvcp140-ownedhash.dll"
            hashed_runtime.parent.mkdir()
            hashed_runtime.write_bytes(b"fixture")

            subprocess.run(
                [
                    shutil.which("pwsh"),
                    "-NoProfile",
                    "-File",
                    "scripts/remove_bundled_vc_runtime.ps1",
                    "-AppDir",
                    str(app_dir),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertFalse((internal_dir / "msvcp140.dll").exists())
            self.assertFalse((internal_dir / "vcruntime140_1.dll").exists())
            self.assertTrue((internal_dir / "onnxruntime.dll").exists())
            self.assertFalse((nested_dir / "MSVCP140.dll").exists())
            self.assertTrue(hashed_runtime.exists())

    def test_upgrade_removes_stale_native_runtime_before_copy(self):
        installer = Path("installer.iss").read_text(encoding="utf-8")

        self.assertIn('Type: filesandordirs; Name: "{app}\\_internal"', installer)

    def test_installer_runs_required_visual_cpp_runtime(self):
        installer = Path("installer.iss").read_text(encoding="utf-8")

        self.assertIn('Source: "build-prerequisites\\vc_redist.x64.exe"', installer)
        self.assertIn("function PrepareToInstall", installer)
        self.assertIn("ResultCode = 3010", installer)
        reboot_branch = installer.split("if ResultCode = 3010 then", 1)[1].split(
            "else if", 1
        )[0]
        self.assertIn("NeedsRestart := True", reboot_branch)
        self.assertIn("Result :=", reboot_branch)
        self.assertIn("перезагрузка Windows", reboot_branch)
        self.assertIn("ResultCode <> 1638", installer)
        self.assertNotIn('Filename: "{tmp}\\vc_redist.x64.exe"', installer)

    def test_installer_uses_graceful_application_shutdown(self):
        installer = Path("installer.iss").read_text(encoding="utf-8")

        self.assertIn("CloseApplications=yes", installer)
        self.assertNotIn("CloseApplications=force", installer)

    def test_azure_verifies_the_installed_copy_not_only_dist(self):
        pipeline = Path("azure-pipelines.yml").read_text(encoding="utf-8")

        self.assertIn("Verify installed Windows application", pipeline)
        self.assertIn("scripts\\verify_installed_windows_artifact.ps1", pipeline)

        verifier = Path("scripts/verify_installed_windows_artifact.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("WaitForExit", verifier)
        self.assertIn("local-processing-smoke-report", verifier)

    def test_github_downloads_and_verifies_visual_cpp_prerequisite(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("https://aka.ms/vc14/vc_redist.x64.exe", workflow)
        self.assertIn("Get-AuthenticodeSignature", workflow)
        self.assertIn("Microsoft Corporation", workflow)
        self.assertIn("build-prerequisites", workflow)

    def test_github_packaged_smoke_requires_rendered_mode_artwork(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )
        source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("packaged mode artwork", workflow)
        self.assertIn("mode_artwork_is_rendered", source)

    def test_github_verifies_mode_artwork_from_the_installed_copy(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Verify installed Windows application", workflow)
        self.assertIn("$installedExe", workflow)
        self.assertIn("--release-entrypoint-smoke", workflow)

    def test_github_waits_for_gui_installer_and_installed_smoke_processes(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn(
            "Start-Process -FilePath $setupPath -ArgumentList $setupArguments -Wait -PassThru",
            workflow,
        )
        self.assertIn(
            "Start-Process -FilePath $installedExe -ArgumentList $smokeArguments -Wait -PassThru",
            workflow,
        )

    def test_github_captures_windows_ui_with_native_font_rendering(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )
        installed_step = workflow.split(
            "- name: Verify installed Windows application", 1
        )[1].split("- name: Calculate setup hash", 1)[0]

        self.assertIn('$env:QT_QPA_PLATFORM = "windows"', installed_step)


if __name__ == "__main__":
    unittest.main()
