import unittest
import os
import json
import textwrap
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

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell is not available")
    def test_installed_verification_binds_optional_previous_installer(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text()
        step = workflow.split("- name: Verify installed Windows application", 1)[1]
        body = textwrap.dedent(step.split("run: |", 1)[1].split("\n      - name:", 1)[0])
        body = body.replace("${{ steps.version.outputs.app_version }}", "3.2.7")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "scripts").mkdir()
            (root / "scripts" / "verify_installed_windows_artifact.ps1").write_text(
                'param([string]$InstallerPath,[string]$ExpectedAppVersion,'
                '[string]$EvidenceDir,[string]$ExpectedProfile,[string]$PreviousInstallerPath)'
                '\n$PSBoundParameters | ConvertTo-Json -Compress'
            )
            script = root / "invoke.ps1"
            script.write_text("$ErrorActionPreference = 'Stop'\n" + body)
            for previous in ("", str(root / "old installer.exe")):
                with self.subTest(previous=bool(previous)):
                    result = subprocess.run(
                        [shutil.which("pwsh"), "-NoProfile", "-File", str(script)],
                        cwd=root, env=dict(os.environ, GITHUB_WORKSPACE=temp,
                            INSTALLER_BASENAME="VibixImages-Setup-3.2.7",
                            BUILD_PROFILE="production", PREVIOUS_INSTALLER_PATH=previous),
                        check=True, capture_output=True, text=True,
                    )
                    values = json.loads(result.stdout)
                    self.assertEqual(values["ExpectedAppVersion"], "3.2.7")
                    self.assertEqual(values["ExpectedProfile"], "production")
                    if previous:
                        self.assertEqual(values["PreviousInstallerPath"], previous)
                    else:
                        self.assertNotIn("PreviousInstallerPath", values)

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

    def test_azure_publishes_installed_core_ui_evidence(self):
        pipeline = Path("azure-pipelines.yml").read_text(encoding="utf-8")
        verifier = Path("scripts/verify_installed_windows_artifact.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("-EvidenceDir", pipeline)
        self.assertIn("ui-evidence", pipeline)
        self.assertIn("--ui-evidence-dir", verifier)
        for filename in (
            "mode-selection.png",
            "contour-editor.png",
            "contour-edited-alpha.png",
        ):
            self.assertIn(filename, verifier)

    def test_github_downloads_and_verifies_visual_cpp_prerequisite(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("https://aka.ms/vc14/vc_redist.x64.exe", workflow)
        self.assertIn("Get-AuthenticodeSignature", workflow)
        self.assertIn("Microsoft Corporation", workflow)
        self.assertIn("build-prerequisites", workflow)

    def test_github_stages_complete_pinned_realesrgan_runtime(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("realesrgan-ncnn-vulkan-v0.2.5.0-windows.zip", workflow)
        self.assertIn(
            "ABC02804E17982A3BE33675E4D471E91EA374E65B70167ABC09E31ACB412802D",
            workflow,
        )
        self.assertIn("python scripts/prepare_realesrgan_runtime.py", workflow)
        self.assertNotIn("Copy-Item -LiteralPath $exe.Directory.FullName", workflow)

    def test_github_runs_native_windows_security_contracts_before_build(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )
        credential_test = (
            "tests/test_api_credentials.py::ApiCredentialKeysTests::"
            "test_fal_key_round_trips_through_dpapi_after_store_restart"
        )
        installer_lock_test = (
            "tests/test_update_client.py::UpdateClientTests::"
            "test_verified_installer_is_immutable_until_protected_context_closes"
        )

        self.assertIn(credential_test, workflow)
        self.assertIn(installer_lock_test, workflow)
        self.assertLess(workflow.index(credential_test), workflow.index("Build app (PyInstaller)"))
        self.assertLess(workflow.index(installer_lock_test), workflow.index("Build app (PyInstaller)"))

    def test_azure_fallback_runs_native_windows_security_contracts_before_build(self):
        pipeline = Path("azure-pipelines.yml").read_text(encoding="utf-8")
        credential_test = (
            "tests/test_api_credentials.py::ApiCredentialKeysTests::"
            "test_fal_key_round_trips_through_dpapi_after_store_restart"
        )
        installer_lock_test = (
            "tests/test_update_client.py::UpdateClientTests::"
            "test_verified_installer_is_immutable_until_protected_context_closes"
        )

        self.assertIn(credential_test, pipeline)
        self.assertIn(installer_lock_test, pipeline)
        self.assertLess(pipeline.index(credential_test), pipeline.index("Build Windows application"))
        self.assertLess(pipeline.index(installer_lock_test), pipeline.index("Build Windows application"))

    def test_github_packaged_smoke_requires_rendered_mode_artwork(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )
        source = Path("main.py").read_text(encoding="utf-8")

        self.assertIn("packaged mode artwork", workflow)
        self.assertIn("artwork_is_rendered", source)
        self.assertIn("frozen_shell_has_no_workflow_sources()", source)

    def test_github_verifies_mode_artwork_from_the_installed_copy(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("Verify installed Windows application", workflow)
        self.assertIn("scripts\\verify_installed_windows_artifact.ps1", workflow)

        verifier = Path("scripts/verify_installed_windows_artifact.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("--release-entrypoint-smoke", verifier)
        self.assertIn("--local-processing-smoke", verifier)
        self.assertIn("RUNNER_TEMP", verifier)

    def test_azure_fallback_preserves_build_provenance_inputs_and_artifact(self):
        pipeline = Path("azure-pipelines.yml").read_text(encoding="utf-8")

        self.assertIn("task.setvariable variable=REAL_ESRGAN_ARCHIVE_URL", pipeline)
        self.assertIn("task.setvariable variable=REAL_ESRGAN_ARCHIVE_SHA256", pipeline)
        self.assertIn("$env:GITHUB_SHA = '$(Build.SourceVersion)'", pipeline)
        self.assertIn("$env:INSTALLER_SHA256 = $hash", pipeline)
        self.assertIn("release/build-provenance.json", pipeline)
        self.assertIn("release/VERSION.txt", pipeline)

    def test_github_waits_for_gui_installer_and_installed_smoke_processes(self):
        verifier = Path("scripts/verify_installed_windows_artifact.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("Start-Process", verifier)
        self.assertIn("WaitForExit", verifier)
        self.assertIn("-TimeoutSeconds 600", verifier)
        self.assertIn("-TimeoutSeconds 1200", verifier)

    def test_github_captures_windows_ui_with_native_font_rendering(self):
        workflow = Path(".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )
        verifier = Path("scripts/verify_installed_windows_artifact.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts\\verify_installed_windows_artifact.ps1", workflow)
        self.assertIn('$env:QT_QPA_PLATFORM = "windows"', verifier)


if __name__ == "__main__":
    unittest.main()
