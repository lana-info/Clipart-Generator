from __future__ import annotations

import csv
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_PREVIEW_ROWS = 8
MAX_CSV_PREVIEW_ISSUES = 12
MAX_TEXT_LENGTH = 5000
MAX_REFERENCES_PER_PROMPT = 5


def split_references(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, (list, tuple, set)):
        values = [str(item).strip() for item in raw_value]
    else:
        values = [part.strip() for part in str(raw_value).replace("\n", "|").split("|")]
    return [value for value in values if value]


def join_references(references: Any) -> str:
    return " | ".join(split_references(references))


@dataclass(slots=True)
class CsvImportIssue:
    row_number: int
    message: str


@dataclass(slots=True)
class CsvImportResult:
    headers: list[str]
    rows: list[list[str]]
    entries: list[dict[str, list[str] | str]]
    issues: list[CsvImportIssue]
    delimiter: str
    has_header: bool
    prompt_column: int
    references_column: int | None


def _read_text(path: str | Path) -> str:
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as error:
        raise RuntimeError("Не удалось прочитать CSV") from error
    if size > MAX_CSV_BYTES:
        raise RuntimeError("CSV превышает допустимый размер")
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp1251", "utf-8"):
        try:
            return source.read_text(encoding=encoding)
        except Exception as error:  # noqa: BLE001
            last_error = error
    raise RuntimeError(f"CSV должен быть корректным текстовым файлом: {last_error}")


def _detect_delimiter(text: str, selected: str = "auto") -> str:
    if selected and selected != "auto":
        return selected
    try:
        sniffed = csv.Sniffer().sniff(text[:4096], delimiters=[",", ";", "\t", "|"])
        return sniffed.delimiter
    except Exception:  # noqa: BLE001
        return ","


def _parse_rows(text: str, delimiter: str) -> list[list[str]]:
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    rows = [
        [str(cell) for cell in row]
        for row in reader
        if any(str(cell).strip() for cell in row)
    ]
    if not rows:
        raise RuntimeError("CSV-файл пуст или не содержит данных")
    return rows


def _normalize_headers(
    rows: list[list[str]],
    *,
    has_header: bool,
) -> tuple[list[str], list[list[str]], int]:
    if has_header:
        headers = [str(item).strip() or f"Колонка {index + 1}" for index, item in enumerate(rows[0])]
        data_rows = rows[1:]
        start_row_number = 2
    else:
        max_cols = max(len(row) for row in rows)
        headers = [f"Колонка {index + 1}" for index in range(max_cols)]
        data_rows = rows
        start_row_number = 1

    max_cols = max(len(headers), max((len(row) for row in data_rows), default=0))
    headers = headers + [f"Колонка {index + 1}" for index in range(len(headers), max_cols)]
    normalized_rows = [row + [""] * (max_cols - len(row)) for row in data_rows]
    return headers, normalized_rows, start_row_number


def _guess_column(headers: list[str], keywords: tuple[str, ...], default: int = 0) -> int:
    for index, header in enumerate(headers):
        normalized = header.casefold().replace(" ", "")
        if any(keyword in normalized for keyword in keywords):
            return index
    return min(default, max(len(headers) - 1, 0))


def parse_prompt_csv(
    path_or_text: str | Path,
    *,
    delimiter: str = "auto",
    has_header: bool = True,
    prompt_column: int | None = None,
    references_column: int | None = None,
) -> CsvImportResult:
    text = _read_text(path_or_text) if Path(str(path_or_text)).exists() else str(path_or_text)
    actual_delimiter = _detect_delimiter(text, delimiter)
    rows = _parse_rows(text, actual_delimiter)
    headers, normalized_rows, start_row_number = _normalize_headers(
        rows,
        has_header=has_header,
    )

    effective_prompt_column = (
        prompt_column
        if isinstance(prompt_column, int) and 0 <= prompt_column < len(headers)
        else _guess_column(headers, ("prompt", "promt", "subject", "text"))
    )
    effective_references_column = (
        references_column
        if isinstance(references_column, int) and 0 <= references_column < len(headers)
        else None
    )

    entries: list[dict[str, list[str] | str]] = []
    issues: list[CsvImportIssue] = []

    for row_number, row in enumerate(normalized_rows, start=start_row_number):
        prompt = row[effective_prompt_column].strip() if effective_prompt_column < len(row) else ""
        references = (
            split_references(row[effective_references_column])
            if effective_references_column is not None and effective_references_column < len(row)
            else []
        )

        row_issues: list[str] = []
        if not prompt:
            row_issues.append("пустой промпт")
        elif len(prompt) > MAX_TEXT_LENGTH:
            row_issues.append("промпт превышает допустимую длину")
        if len(references) > MAX_REFERENCES_PER_PROMPT:
            row_issues.append(
                f"референсов больше {MAX_REFERENCES_PER_PROMPT}"
            )
        if any(len(reference) > MAX_TEXT_LENGTH for reference in references):
            row_issues.append("один из референсов слишком длинный")

        if row_issues:
            issues.append(CsvImportIssue(row_number=row_number, message="; ".join(row_issues)))
            continue

        entries.append({"prompt": prompt, "references": references})

    if not entries and not issues:
        raise RuntimeError("CSV не содержит валидных строк")

    return CsvImportResult(
        headers=headers,
        rows=normalized_rows,
        entries=entries,
        issues=issues,
        delimiter=actual_delimiter,
        has_header=has_header,
        prompt_column=effective_prompt_column,
        references_column=effective_references_column,
    )


class PromptCsvImportDialog(QDialog):
    def __init__(self, file_path: str | Path, parent=None) -> None:
        super().__init__(parent)
        self.file_path = str(file_path)
        self._result: CsvImportResult | None = None
        self._action: str | None = None
        self.setWindowTitle("Импорт промптов из CSV")
        self.resize(840, 620)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.delimiter_combo = QComboBox()
        self.delimiter_combo.addItem("Авто", "auto")
        self.delimiter_combo.addItem(",", ",")
        self.delimiter_combo.addItem(";", ";")
        self.delimiter_combo.addItem("TAB", "\t")
        self.delimiter_combo.addItem("|", "|")

        self.header_checkbox = QCheckBox("Первая строка — заголовки")
        self.header_checkbox.setChecked(True)

        self.prompt_column_combo = QComboBox()
        self.references_column_combo = QComboBox()

        form.addRow("Разделитель:", self.delimiter_combo)
        form.addRow("Колонка с промптом:", self.prompt_column_combo)
        form.addRow("Колонка с референсами:", self.references_column_combo)
        form.addRow("", self.header_checkbox)
        layout.addLayout(form)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("Здесь будет предпросмотр импорта")
        layout.addWidget(self.preview_text, 1)

        self.button_box = QDialogButtonBox()
        self.add_button = QPushButton("Добавить к списку")
        self.replace_button = QPushButton("Заменить все промпты")
        self.cancel_button = QPushButton("Отмена")
        self.button_box.addButton(self.add_button, QDialogButtonBox.ButtonRole.AcceptRole)
        self.button_box.addButton(self.replace_button, QDialogButtonBox.ButtonRole.DestructiveRole)
        self.button_box.addButton(self.cancel_button, QDialogButtonBox.ButtonRole.RejectRole)
        layout.addWidget(self.button_box)

        self.delimiter_combo.currentIndexChanged.connect(self._reload)
        self.header_checkbox.toggled.connect(self._reload)
        self.prompt_column_combo.currentIndexChanged.connect(self._refresh_preview)
        self.references_column_combo.currentIndexChanged.connect(self._refresh_preview)
        self.add_button.clicked.connect(self._accept_append)
        self.replace_button.clicked.connect(self._accept_replace)
        self.cancel_button.clicked.connect(self.reject)

        self._reload()

    def _read_text(self) -> str:
        return _read_text(self.file_path)

    def _reload(self) -> None:
        previous_prompt = self.prompt_column_combo.currentData()
        previous_references = self.references_column_combo.currentData()
        try:
            self._result = parse_prompt_csv(
                self.file_path,
                delimiter=str(self.delimiter_combo.currentData() or "auto"),
                has_header=self.header_checkbox.isChecked(),
                prompt_column=previous_prompt if isinstance(previous_prompt, int) else None,
                references_column=previous_references if isinstance(previous_references, int) else None,
            )
        except Exception as error:  # noqa: BLE001
            self._result = None
            self.summary_label.setText(f"Ошибка импорта: {error}")
            self.preview_text.setPlainText("")
            self._set_buttons_enabled(False)
            return

        headers = self._result.headers if self._result else []
        self.prompt_column_combo.blockSignals(True)
        self.references_column_combo.blockSignals(True)
        self.prompt_column_combo.clear()
        self.references_column_combo.clear()
        for index, header in enumerate(headers):
            self.prompt_column_combo.addItem(header, index)
            self.references_column_combo.addItem(header, index)

        prompt_index = self._result.prompt_column if self._result else 0
        refs_index = self._result.references_column if self._result else None
        self.prompt_column_combo.setCurrentIndex(min(max(prompt_index, 0), max(len(headers) - 1, 0)))
        self.references_column_combo.addItem("Без референсов", -1)
        if refs_index is None:
            self.references_column_combo.setCurrentIndex(self.references_column_combo.count() - 1)
        else:
            match = self.references_column_combo.findData(refs_index)
            self.references_column_combo.setCurrentIndex(match if match >= 0 else self.references_column_combo.count() - 1)

        self.prompt_column_combo.blockSignals(False)
        self.references_column_combo.blockSignals(False)
        self._refresh_preview()

    def _selected_prompt_column(self) -> int:
        value = self.prompt_column_combo.currentData()
        return int(value) if isinstance(value, int) and value >= 0 else 0

    def _selected_references_column(self) -> int | None:
        value = self.references_column_combo.currentData()
        if isinstance(value, int) and value >= 0:
            return value
        return None

    def _refresh_preview(self) -> None:
        if self._result is None:
            return
        try:
            refreshed = parse_prompt_csv(
                self.file_path,
                delimiter=str(self.delimiter_combo.currentData() or "auto"),
                has_header=self.header_checkbox.isChecked(),
                prompt_column=self._selected_prompt_column(),
                references_column=self._selected_references_column(),
            )
        except Exception as error:  # noqa: BLE001
            self.summary_label.setText(f"Ошибка импорта: {error}")
            self.preview_text.setPlainText("")
            self._set_buttons_enabled(False)
            return

        self._result = refreshed
        self._set_buttons_enabled(bool(refreshed.entries))
        self.summary_label.setText(
            f"Строк данных: {len(refreshed.rows)} | Валидных: {len(refreshed.entries)} | Ошибок: {len(refreshed.issues)} | Разделитель: {refreshed.delimiter if refreshed.delimiter != '\\t' else 'TAB'}"
        )
        self.preview_text.setPlainText(self._build_preview_text(refreshed))

    def _build_preview_text(self, result: CsvImportResult) -> str:
        parts: list[str] = []
        valid_entries = result.entries[:MAX_CSV_PREVIEW_ROWS]
        if valid_entries:
            parts.append("Предпросмотр валидных строк:")
            for index, entry in enumerate(valid_entries, start=1):
                prompt = str(entry.get("prompt", "")).strip()
                references = join_references(entry.get("references", []))
                line = f"{index}. {prompt}"
                if references:
                    line += f"\n   Референсы: {references}"
                parts.append(line)
        if result.issues:
            parts.append("")
            parts.append("Ошибки:")
            for issue in result.issues[:MAX_CSV_PREVIEW_ISSUES]:
                parts.append(f"Строка {issue.row_number}: {issue.message}")
            if len(result.issues) > MAX_CSV_PREVIEW_ISSUES:
                parts.append(f"… и ещё {len(result.issues) - MAX_CSV_PREVIEW_ISSUES} строк с ошибками")
        return "\n".join(parts).strip()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        self.add_button.setEnabled(enabled)
        self.replace_button.setEnabled(enabled)

    def _accept_append(self) -> None:
        self._action = "append"
        self.accept()

    def _accept_replace(self) -> None:
        self._action = "replace"
        self.accept()

    def get_entries(self) -> list[dict[str, list[str] | str]]:
        if self._result is None:
            return []
        return [
            {
                "prompt": str(entry.get("prompt", "")).strip(),
                "references": split_references(entry.get("references", [])),
            }
            for entry in self._result.entries
        ]

    def get_issues(self) -> list[CsvImportIssue]:
        if self._result is None:
            return []
        return list(self._result.issues)

    def import_action(self) -> str | None:
        return self._action

