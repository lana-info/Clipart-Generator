from __future__ import annotations

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
        self.assertIn('WizardImageFile=assets\\installer-wizard-hq.png', installer)
        wizard_image = PROJECT_ROOT / "assets" / "installer-wizard-hq.png"
        self.assertTrue(wizard_image.is_file())
        self.assertGreater(wizard_image.stat().st_size, 1_000_000)

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


if __name__ == "__main__":
    unittest.main()
