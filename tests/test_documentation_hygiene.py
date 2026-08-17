import unittest
from pathlib import Path
import re


class DocumentationHygieneTests(unittest.TestCase):
    def test_runtime_processing_messages_have_no_placeholder_glyphs(self):
        source = Path("v3_processing_flow.py").read_text(encoding="utf-8")
        self.assertNotIn("????????", source)

    def test_artifact_inventory_exists(self):
        self.assertTrue(Path("docs/maintenance/artifact-inventory.md").is_file())

    def test_delivery_scope_and_installer_name_are_unambiguous(self):
        delivery = Path("CLIENT_DELIVERY.md").read_text(encoding="utf-8")
        self.assertIn("supported delivery targets for 3.0", delivery)
        self.assertIn("VibixImages-Setup-3.0.exe", delivery)
        self.assertNotIn("macOS Apple Silicon arm64 ZIP: build and packaging verified", delivery)

    def test_local_markdown_links_resolve(self):
        root = Path(".")
        pattern = re.compile(r"\[[^]]+\]\(([^)#]+)\)")
        missing = []
        for path in root.rglob("*.md"):
            if any(part in {".git", ".venv", ".pytest_cache"} for part in path.parts):
                continue
            for target in pattern.findall(path.read_text(encoding="utf-8", errors="ignore")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if not (path.parent / target).exists():
                    missing.append(f"{path}: {target}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
