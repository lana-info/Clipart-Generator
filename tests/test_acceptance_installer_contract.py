import re
import unittest
from pathlib import Path


INSTALLER_PATH = Path("installer.iss")


def _active_installer_source(*, acceptance_build: bool) -> str:
    source = INSTALLER_PATH.read_text(encoding="utf-8")
    active = True
    branches = []
    output = []

    for line in source.splitlines():
        directive = line.strip()
        if directive == "#ifdef AcceptanceBuild":
            branches.append((active, acceptance_build))
            active = active and acceptance_build
        elif directive.startswith(("#ifdef ", "#ifndef ")):
            branches.append((active, None))
        elif directive == "#else":
            parent_active, condition = branches[-1]
            if condition is not None:
                active = parent_active and not condition
        elif directive == "#endif":
            active, _ = branches.pop()
        elif active:
            output.append(line)

    if branches:
        raise AssertionError("Unclosed ISPP conditional in installer.iss")
    return "\n".join(output)


def _define(source: str, name: str) -> str:
    match = re.search(
        rf'^\s*#define {re.escape(name)} "([^"]+)"$', source, re.MULTILINE
    )
    if match is None:
        raise AssertionError(f"Missing string define: {name}")
    return match.group(1)


class AcceptanceInstallerContractTests(unittest.TestCase):
    def test_production_profile_keeps_existing_identity_and_output_name(self):
        source = _active_installer_source(acceptance_build=False)

        self.assertEqual(_define(source, "AppName"), "Vibix Images")
        self.assertEqual(
            _define(source, "AppId"),
            "{{B8D6B3F4-4E5F-4B6E-9D13-9A8E3B2F3C7A}",
        )
        self.assertIn("AppId={#AppId}", source)
        self.assertIn("AppName={#AppName}", source)
        self.assertIn("OutputBaseFilename=VibixImages-Setup-{#AppVersion}", source)
        self.assertIn("DefaultDirName={autopf}\\{#AppName}", source)
        self.assertIn("DefaultGroupName={#AppName}", source)

    def test_acceptance_profile_has_a_fully_separate_installer_identity(self):
        source = _active_installer_source(acceptance_build=True)

        self.assertEqual(_define(source, "AppName"), "Vibix Studio Test")
        acceptance_app_id = _define(source, "AppId")
        self.assertRegex(
            acceptance_app_id,
            r"^\{\{[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}\}$",
        )
        self.assertNotEqual(
            acceptance_app_id, "{{B8D6B3F4-4E5F-4B6E-9D13-9A8E3B2F3C7A}"
        )
        self.assertIn("AppId={#AppId}", source)
        self.assertIn("AppName={#AppName}", source)
        self.assertIn(
            "OutputBaseFilename=VibixImages-Test-Setup-{#AppVersion}", source
        )
        self.assertIn("DefaultDirName={autopf}\\{#AppName}", source)
        self.assertIn("DefaultGroupName={#AppName}", source)
        self.assertIn(
            'Source: "dist\\Vibix Images\\*"; DestDir: "{app}"',
            source,
        )
        self.assertEqual(_define(source, "AppExeName"), "Vibix Images.exe")

    def test_acceptance_profile_refuses_every_known_production_install_location(self):
        source = _active_installer_source(acceptance_build=True)

        self.assertIn("function AcceptanceInstallConflict", source)
        self.assertIn("{autopf}\\Vibix Images", source)
        self.assertIn("ProductionUninstallKey", source)
        for registry_root in (
            "HKEY_LOCAL_MACHINE_64",
            "HKEY_LOCAL_MACHINE_32",
            "HKEY_CURRENT_USER_64",
            "HKEY_CURRENT_USER_32",
        ):
            self.assertIn(registry_root, source)
        self.assertIn("RegQueryStringValue", source)
        # Inno Setup 6.7.1 exposes registry roots as Integer, not HKEY.
        self.assertIn("RootKey: Integer;", source)
        self.assertNotIn("RootKey: HKEY;", source)
        self.assertIn("InstallLocation", source)
        self.assertIn("FileExists(AddBackslash(SelectedDir) + '{#AppExeName}')", source)
        self.assertIn("IsRegisteredAcceptanceInstallDir", source)
        self.assertIn("function NextButtonClick", source)
        self.assertIn("if CurPageID = wpSelectDir", source)
        prepare_to_install = source.split(
            "function PrepareToInstall(var NeedsRestart: Boolean): String;", 1
        )[1]
        self.assertIn("AcceptanceInstallConflict(WizardDirValue)", prepare_to_install)

    def test_production_profile_does_not_include_acceptance_only_guard(self):
        source = _active_installer_source(acceptance_build=False)

        self.assertNotIn("function AcceptanceInstallConflict", source)
        self.assertNotIn("IsRegisteredAcceptanceInstallDir", source)


if __name__ == "__main__":
    unittest.main()
