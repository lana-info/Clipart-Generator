from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class BrandingTests(unittest.TestCase):
    def test_approved_product_identity_and_default_folder(self):
        import main
        from v3_mode_selection import default_work_directory

        self.assertEqual(main.APP_NAME, "Vibix Images")
        self.assertEqual(default_work_directory().name, "Vibix Images")

    def test_icon_source_has_approved_geometry(self):
        svg = (PROJECT_ROOT / "assets" / "vibix-images.svg").read_text(
            encoding="utf-8"
        )
        self.assertIn("M21 28H40L54 69L68 28H86L62 82H46Z", svg)
        self.assertIn('x="83" y="69" width="13" height="13"', svg)

    def test_generated_ico_contains_windows_icon_sizes(self):
        from PIL import Image

        icon_path = PROJECT_ROOT / "assets" / "vibix-images.ico"
        self.assertTrue(icon_path.is_file())
        with Image.open(icon_path) as icon:
            self.assertEqual(icon.format, "ICO")
            self.assertGreaterEqual(len(icon.info.get("sizes", ())), 7)

    def test_windows_packaging_uses_vibix_identity(self):
        build = (PROJECT_ROOT / "build.ps1").read_text(encoding="utf-8")
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")
        self.assertIn('--name "Vibix Images"', build)
        self.assertIn('--icon "assets/vibix-images.ico"', build)
        self.assertIn('--add-data "assets/vibix-images.ico;assets"', build)
        self.assertIn('#define AppName "Vibix Images"', installer)
        self.assertIn('#define AppExeName "Vibix Images.exe"', installer)
        self.assertIn('SetupIconFile=assets\\vibix-images.ico', installer)
        self.assertIn('Создать клипарт', installer)
        self.assertIn('Создать Pinterest-пины', installer)
        self.assertIn('Обработать изображения', installer)
        self.assertIn('Массовая генерация изображений', installer)
        self.assertIn('активируйте лицензию', installer)
        self.assertIn('WizardImageFile=assets\\installer-wizard-hq.png', installer)
        wizard_image = PROJECT_ROOT / "assets" / "installer-wizard-hq.png"
        self.assertTrue(wizard_image.is_file())
        self.assertGreater(wizard_image.stat().st_size, 1_000_000)

    def test_windows_installer_uses_approved_three_stage_dark_design(self):
        installer = (PROJECT_ROOT / "installer.iss").read_text(encoding="utf-8")

        self.assertIn(
            "WizardStyle=modern dark polar includetitlebar hidebevels",
            installer,
        )
        self.assertIn("WizardSizePercent=125,120", installer)
        self.assertIn("WizardResizable=no", installer)
        self.assertIn("DisableProgramGroupPage=yes", installer)
        self.assertIn("DisableReadyPage=yes", installer)
        self.assertIn("ButtonNext=Продолжить", installer)
        self.assertIn("ButtonInstall=Установить", installer)
        self.assertIn("ButtonFinish=Готово", installer)
        self.assertIn("1 из 3 · Добро пожаловать", installer)
        self.assertIn("2 из 3 · Установка", installer)
        self.assertIn("3 из 3 · Готово", installer)
        self.assertIn("procedure CurPageChanged(CurPageID: Integer);", installer)
        self.assertNotIn("WizardStyleFile=", installer)

    def test_windows_builds_pin_inno_setup_with_dark_style_support(self):
        github_workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release-multi-platform.yml"
        ).read_text(encoding="utf-8")
        azure_workflow = (PROJECT_ROOT / "azure-pipelines.yml").read_text(
            encoding="utf-8"
        )
        install_command = (
            "choco upgrade innosetup --version=6.7.1 -y --no-progress "
            "--allow-downgrade"
        )

        self.assertIn(install_command, github_workflow)
        self.assertIn(install_command, azure_workflow)

    def test_mode_illustrations_are_packaged_for_both_desktop_builds(self):
        for name in ("clipart", "pinterest", "processing"):
            asset = PROJECT_ROOT / "assets" / f"mode-{name}.png"
            self.assertTrue(asset.is_file())
            self.assertGreater(asset.stat().st_size, 1_000_000)

        build = (PROJECT_ROOT / "build.ps1").read_text(encoding="utf-8")
        mac_build = (PROJECT_ROOT / "azure-pipelines-macos.yml").read_text(encoding="utf-8")
        for name in ("clipart", "pinterest", "processing"):
            self.assertIn(f'assets/mode-{name}.png;assets', build)
            self.assertIn(f"assets/mode-{name}.png:assets", mac_build)

    def test_approved_mode_artwork_is_preserved_across_app_site_and_installer(self):
        approved = {
            "clipart": "4eb6d0247e6412cd19d388da2928fd058d34d5a52eb2b548dc7b6aeb95e32843",
            "pinterest": "ef221f2504f274be8849265240a287eaf8b51a252972d149b1bfa9d7afb32d96",
            "processing": "4a5fb6b4804e8f6a24e3c7c61bc92317022ea8e5d91db317b230ca0f78529bed",
        }

        for name, expected_sha256 in approved.items():
            app_asset = PROJECT_ROOT / "assets" / f"mode-{name}.png"
            site_asset = (
                PROJECT_ROOT
                / "website"
                / "vibix-download"
                / "assets"
                / f"mode-{name}-hq.png"
            )
            self.assertEqual(hashlib.sha256(app_asset.read_bytes()).hexdigest(), expected_sha256)
            self.assertEqual(site_asset.read_bytes(), app_asset.read_bytes())

        installer_art = PROJECT_ROOT / "assets" / "installer-wizard-hq.png"
        self.assertEqual(
            hashlib.sha256(installer_art.read_bytes()).hexdigest(),
            "577f19f18b35a753852081afa41b1d0139dcff642202aff03ddf098258a1c76b",
        )

        handoff = (
            PROJECT_ROOT / "docs" / "brand" / "VIBIX_PRODUCT_FAMILY_HANDOFF.md"
        ).read_text(encoding="utf-8")
        self.assertIn("Approved Vibix Images mode artwork", handoff)
        self.assertIn("must be used", handoff)
        self.assertIn("three-stage dark Inno Setup", handoff)

    def test_download_page_uses_approved_copy_platform_icons_and_future_help(self):
        page = (
            PROJECT_ROOT / "website" / "vibix-download" / "index.html"
        ).read_text(encoding="utf-8")

        self.assertIn("Массовая генерация изображений", page)
        self.assertIn("в том числе согласованные наборы клипартов", page)
        self.assertIn("в течение 24 часов", page)
        self.assertIn("Инструкция и видео — скоро", page)
        self.assertIn("Vibix Images развивается", page)
        self.assertIn('rel="icon" href="assets/vibix-images.svg"', page)
        self.assertIn('class="platform-logo"', page)
        self.assertNotIn('aria-hidden="true">⊞</span>', page)
        self.assertNotIn('aria-hidden="true">●</span>', page)


if __name__ == "__main__":
    unittest.main()
