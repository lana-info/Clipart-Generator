import unittest
from pathlib import Path


class BuildConstraintsTests(unittest.TestCase):
    def test_constraints_use_only_pip_supported_package_pins(self):
        constraints = Path("constraints-build.txt").read_text(encoding="utf-8").splitlines()
        entries = [line.strip() for line in constraints if line.strip() and not line.startswith("#")]

        self.assertTrue(entries)
        self.assertTrue(all("[" not in entry and "]" not in entry for entry in entries))
        self.assertIn("rembg==2.0.67", entries)


if __name__ == "__main__":
    unittest.main()
