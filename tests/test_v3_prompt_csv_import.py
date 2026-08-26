import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from v3_prompt_csv_import import (  # noqa: E402
    PromptCsvImportDialog,
    parse_prompt_csv,
)


class PromptCsvImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_parse_supports_custom_headers_after_manual_mapping(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-map-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            csv_path.write_text(
                "title;assets\nbird;ref-a.png | https://example.test/ref.png\n",
                encoding="utf-8-sig",
                newline="",
            )

            result = parse_prompt_csv(
                csv_path,
                delimiter=";",
                has_header=True,
                prompt_column=0,
                references_column=1,
            )

        self.assertEqual(result.entries, [
            {
                "prompt": "bird",
                "references": ["ref-a.png", "https://example.test/ref.png"],
            }
        ])
        self.assertEqual(result.issues, [])

    def test_parse_keeps_references_optional_and_reports_row_numbers(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-issues-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            csv_path.write_text(
                "prompt,refs\nbird,\n,ref-a.png\ncat,a|b|c|d|e|f\n",
                encoding="utf-8-sig",
                newline="",
            )

            result = parse_prompt_csv(
                csv_path,
                delimiter=",",
                has_header=True,
                prompt_column=0,
                references_column=1,
            )

        self.assertEqual(result.entries, [{"prompt": "bird", "references": []}])
        self.assertEqual(
            [(issue.row_number, issue.message) for issue in result.issues],
            [
                (3, "пустой промпт"),
                (4, "референсов больше 5"),
            ],
        )

    def test_dialog_exposes_one_clear_import_action_and_brief_summary(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-dialog-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            csv_path.write_text(
                "prompt,refs\nbird,ref-a.png\n",
                encoding="utf-8-sig",
                newline="",
            )

            dialog = PromptCsvImportDialog(csv_path)

        self.assertEqual(dialog.import_button.text(), "Импортировать промпты")
        self.assertFalse(hasattr(dialog, "replace_button"))
        self.assertTrue(dialog.get_entries())
        self.assertIn("Найдено промптов: 1", dialog.summary_label.text())

    def test_dialog_keeps_long_content_bounded_without_prompt_preview(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-long-preview-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            csv_path.write_text(
                "prompt\n" + ("very long prompt " * 100) + "\n",
                encoding="utf-8-sig",
                newline="",
            )

            dialog = PromptCsvImportDialog(csv_path)

        self.assertLessEqual(dialog.width(), 1000)
        self.assertFalse(hasattr(dialog, "preview_text"))


if __name__ == "__main__":
    unittest.main()
