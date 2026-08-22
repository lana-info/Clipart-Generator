import unittest
from pathlib import Path


class WindowsInstallerContractTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
