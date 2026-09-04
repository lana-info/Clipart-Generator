import unittest
from pathlib import Path

from release_contract import resolve_release_version


class MacOSReleaseWorkflowTests(unittest.TestCase):
    def test_macos_preview_build_uses_the_checked_out_source_version(self):
        project_root = Path(__file__).resolve().parents[1]
        version = resolve_release_version(project_root / "release")
        workflow = (project_root / ".github/workflows/release-multi-platform.yml").read_text(
            encoding="utf-8"
        )
        windows_job = workflow.split("  build-windows:\n", 1)[1].split(
            "  build-macos:\n", 1
        )[0]
        macos_job = workflow.split("  build-macos:\n", 1)[1]

        self.assertTrue(version)
        self.assertTrue(windows_job.startswith("    if: ${{ false }}\n"))
        self.assertTrue(macos_job.startswith("    runs-on: macos-15\n"))
        self.assertNotIn("github.event.inputs.app_version", macos_job)
        self.assertIn('VERSION="$(tr -d \'\\r\\n\' < release/VERSION.txt)"', macos_job)
        self.assertIn('--name "Vibix Images"', macos_job)
        self.assertIn('dist/Vibix Images.app/Contents/Info.plist', macos_job)
        self.assertIn(f'VibixImages-macOS-${{{{ steps.version.outputs.app_version }}}}.zip', macos_job)


if __name__ == "__main__":
    unittest.main()
