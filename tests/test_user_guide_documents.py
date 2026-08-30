import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from scripts.generate_user_guide_documents import (
    SOURCE,
    TEMP_HTML,
    GUIDE_APP_VERSION,
    build_docx,
    build_pdf,
    find_browser,
    html_document,
    parse_markdown,
    png_size,
    resolve_asset,
    validate_inputs,
)


class UserGuideDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blocks = parse_markdown(SOURCE.read_text(encoding="utf-8"))

    def test_guide_contains_real_screenshots_and_required_workflows(self):
        validate_inputs(self.blocks)
        images = [block for block in self.blocks if block.kind == "image"]
        self.assertEqual(len(images), 14)
        self.assertTrue(all(resolve_asset(str(block.value)).is_file() for block in images))
        source = SOURCE.read_text(encoding="utf-8")
        for required in (
            "API-ключи",
            "Генератор промптов",
            "CSV: формат и импорт",
            "Chroma key",
            "Редактирование прозрачности",
            "Режим Pinterest",
            "Режим Processing",
            "Версия приложения: 3.1.0",
            "Проверить прозрачность",
        ):
            self.assertIn(required, source)
        self.assertNotIn("Версия приложения: 3.0.7", source)
        self.assertNotIn("редактор alpha-маски **временно скрыт**", source)

        release_version = (SOURCE.parent / "release" / "VERSION.txt").read_text(
            encoding="utf-8"
        ).strip()
        self.assertEqual(GUIDE_APP_VERSION, release_version)
        self.assertIn(f"Версия приложения: {release_version}", source)

        section_count = sum(block.kind == "heading2" for block in self.blocks)
        contents = source.split("## 1. Что умеет приложение", 1)[0]
        self.assertEqual(section_count, 20)
        self.assertEqual(len(re.findall(r"(?m)^\d+\. ", contents)), section_count)

    def test_html_contains_every_image_and_print_footer(self):
        document = html_document(self.blocks)
        self.assertEqual(document.count("<figure>"), 14)
        self.assertIn("Версия 3.1.0", document)
        self.assertIn("counter(pages)", document)
        self.assertIn("Vibix Images · Руководство пользователя", document)

    def test_docx_is_valid_ooxml_with_all_images(self):
        with tempfile.TemporaryDirectory(prefix="vibix-guide-docx-") as temp:
            destination = Path(temp) / "guide.docx"
            build_docx(self.blocks, destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertIsNone(archive.testzip())
                names = set(archive.namelist())
                media = [name for name in names if name.startswith("word/media/image")]
                self.assertEqual(len(media), 14)
                for name in names:
                    if name.endswith(".xml") or name.endswith(".rels"):
                        ET.fromstring(archive.read(name))

    def test_screenshot_capture_smoke(self):
        if importlib.util.find_spec("PyQt6") is None or importlib.util.find_spec("PIL") is None:
            self.skipTest("PyQt6 and Pillow are required for screenshot capture")
        script = SOURCE.parent / "scripts" / "capture_user_guide_screenshots.py"
        with tempfile.TemporaryDirectory(prefix="vibix-guide-capture-") as temp:
            destination = Path(temp) / "screenshots"
            environment = dict(os.environ)
            environment["QT_QPA_PLATFORM"] = "offscreen"
            result = subprocess.run(
                [sys.executable, str(script), "--output-dir", str(destination)],
                cwd=SOURCE.parent,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            images = sorted(destination.glob("*.png"))
            self.assertEqual(len(images), 14)
            self.assertTrue(all(width >= 900 and height >= 650 for width, height in map(png_size, images)))

    def test_pdf_render_smoke(self):
        if shutil.which("pdfinfo") is None:
            self.skipTest("pdfinfo is required for PDF validation")
        try:
            browser = find_browser()
        except RuntimeError as error:
            self.skipTest(str(error))
        with tempfile.TemporaryDirectory(prefix="vibix-guide-pdf-") as temp:
            destination = Path(temp) / "guide.pdf"
            try:
                build_pdf(html_document(self.blocks), destination, browser=browser)
            finally:
                TEMP_HTML.unlink(missing_ok=True)
            self.assertTrue(destination.read_bytes().startswith(b"%PDF"))
            info = subprocess.run(
                ["pdfinfo", str(destination)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            ).stdout
            pages = re.search(r"(?m)^Pages:\s+(\d+)$", info)
            self.assertIsNotNone(pages)
            self.assertGreaterEqual(int(pages.group(1)), 20)
            page_size = re.search(r"Page size:\s+([\d.]+) x ([\d.]+) pts \(A4\)", info)
            self.assertIsNotNone(page_size)
            self.assertAlmostEqual(float(page_size.group(1)), 595, delta=1)
            self.assertAlmostEqual(float(page_size.group(2)), 842, delta=1)


if __name__ == "__main__":
    unittest.main()
