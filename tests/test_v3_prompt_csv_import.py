import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

from v3_prompt_csv_import import (  # noqa: E402
    PromptCsvImportDialog,
    parse_prompt_csv,
    write_prompt_csv_atomic,
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

    def test_atomic_export_preserves_existing_csv_when_commit_fails(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-export-") as temp_dir:
            destination = Path(temp_dir) / "prompts.csv"
            destination.write_text("previous data", encoding="utf-8")

            with patch(
                "v3_prompt_csv_import.os.replace",
                side_effect=OSError("simulated replace failure"),
            ):
                with self.assertRaises(OSError):
                    write_prompt_csv_atomic(
                        destination,
                        [{"prompt": "bird", "references": ["bird.png"]}],
                    )

            self.assertEqual(destination.read_text(encoding="utf-8"), "previous data")
            self.assertEqual(list(destination.parent.glob(".prompts.*.tmp")), [])

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

    def test_dialog_shows_three_parsed_prompts_and_reference_mapping(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-preview-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            csv_path.write_text(
                "prompt,refs\n"
                "first prompt,first.png\n"
                "second prompt,\n"
                "third prompt,third.png\n"
                "fourth prompt,fourth.png\n",
                encoding="utf-8-sig",
                newline="",
            )

            dialog = PromptCsvImportDialog(csv_path)
            references_index = dialog.references_column_combo.findData(1)
            dialog.references_column_combo.setCurrentIndex(references_index)

        self.assertEqual(dialog.preview_table.rowCount(), 3)
        self.assertEqual(dialog.preview_table.item(0, 1).text(), "first prompt")
        self.assertEqual(dialog.preview_table.item(0, 2).text(), "first.png")
        self.assertEqual(dialog.preview_table.item(1, 1).text(), "second prompt")
        self.assertEqual(dialog.preview_table.item(1, 2).text(), "Нет референсов")
        self.assertEqual(dialog.preview_table.item(2, 1).text(), "third prompt")
        self.assertEqual(dialog.preview_table.item(2, 2).text(), "third.png")

    def test_dialog_keeps_long_preview_content_bounded(self):
        with tempfile.TemporaryDirectory(prefix="clipart-csv-long-preview-") as temp_dir:
            csv_path = Path(temp_dir) / "prompts.csv"
            prompt = "very long prompt " * 100
            csv_path.write_text(
                "prompt\n" + prompt + "\n",
                encoding="utf-8-sig",
                newline="",
            )

            dialog = PromptCsvImportDialog(csv_path)

        self.assertLessEqual(dialog.width(), 1000)
        self.assertFalse(hasattr(dialog, "preview_text"))
        self.assertTrue(dialog.preview_table.item(0, 1).text().endswith("…"))
        self.assertEqual(dialog.preview_table.item(0, 1).toolTip(), prompt.strip())


if __name__ == "__main__":
    unittest.main()
