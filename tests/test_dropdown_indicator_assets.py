"""Offline checks for shipped dropdown chevrons, without PyQt on the VDS."""
from pathlib import Path
import struct
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ("dropdown-chevron.png", "dropdown-chevron-disabled.png")


class DropdownIndicatorContractTests(unittest.TestCase):
    def test_png_chevrons_have_valid_dimensions_and_pixels(self):
        for name in ASSETS:
            with self.subTest(name=name):
                data = (ROOT / "assets" / name).read_bytes()
                self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
                width, height, depth, channels = struct.unpack_from("!IIBB", data, 16)
                self.assertEqual((width, height, depth, channels), (28, 20, 8, 6))
                chunk = data.index(b"IDAT")
                length = struct.unpack_from("!I", data, chunk - 4)[0]
                decoded = zlib.decompress(data[chunk + 4:chunk + 4 + length])
                self.assertEqual(len(decoded), 20 * (28 * 4 + 1))
                self.assertTrue(any(decoded[4::4]))

    def test_all_packaging_routes_include_dropdown_icons(self):
        for build in ("build.ps1", "azure-pipelines-macos.yml"):
            with self.subTest(build=build):
                text = (ROOT / build).read_text(encoding="utf-8")
                for name in ASSETS:
                    self.assertIn("assets/" + name, text)
        source = (ROOT / "scripts/build_macos.py").read_text(encoding="utf-8")
        self.assertIn('"build.ps1"', source)
        self.assertIn('"add-data"', source)

    def test_theme_and_composer_share_one_icon_contract(self):
        theme = (ROOT / "v3_components.py").read_text(encoding="utf-8")
        composer = (ROOT / "prompt_composer/ui.py").read_text(encoding="utf-8")
        self.assertIn('dropdown_indicator_stylesheet("QComboBox", tokens)', theme)
        self.assertIn('dropdown_indicator_stylesheet("QWidget#promptComposerPage QComboBox")', composer)
        self.assertIn('::down-arrow:disabled', theme)


if __name__ == "__main__":
    unittest.main()
