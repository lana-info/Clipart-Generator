"""Shared prompt input/review UI used by independently owned image workflows."""
from __future__ import annotations

import csv
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from chroma_key import chroma_key_prompt_block
from chroma_key_selection import select_chroma_key_color
from v3_components import AdvancedSection, ButtonVariant, DEFAULT_TOKENS, V3Button, V3DesignTokens
from v3_flow_ui import ScrollableStepPage
from v3_image_generation_runtime import _reference_file_size_error, _split_user_prompt, _user_prompt_text
from v3_project_state import (
    MAX_CHROMA_KEY_MATERIALS, MAX_PROMPT_ENTRIES, MAX_PROMPT_GENERATOR_TEXT_LENGTH,
    MAX_REFERENCES_PER_PROMPT, MAX_TEXT_LENGTH, ProjectMode, ProjectState, PromptEntry, PromptGeneratorData,
)
from v3_prompt_csv_import import PromptCsvImportDialog
from v3_prompt_generator import PromptGeneratorError, generate_prompt_series, normalize_prompt_entries
from v3_provider_registry import CHROMA_KEY_COLOR_OPTIONS

MAX_CSV_BYTES = 2 * 1024 * 1024


CHROMA_KEY_MATERIAL_OPTIONS = (
    ("Акварель", "watercolor"),
    ("Тонкие листья", "thin_leaves"),
    ("Хвоя", "conifer_needles"),
    ("Металл", "metal"),
    ("Лента / сатин", "ribbon_satin"),
    ("Прозрачные детали", "transparent_details"),
    ("Снег / лёд", "snow_ice"),
)


def configure_chroma_material_buttons(buttons: Sequence[QPushButton]) -> None:
    """Keep the compact Chroma Key helper readable and prompt-safe."""

    def refresh() -> None:
        selected_count = sum(button.isChecked() for button in buttons)
        limit_reached = selected_count >= MAX_CHROMA_KEY_MATERIALS
        for button in buttons:
            button.setEnabled(button.isChecked() or not limit_reached)

    for button in buttons:
        button.setProperty("v3ChromaMaterial", True)
        button.setToolTip("Можно выбрать до трёх материалов")
        button.toggled.connect(refresh)
    refresh()


def apply_prompt_text_edit(
    entries: Sequence[PromptEntry], *, rows: Sequence[int], action: str,
    find_text: str, new_text: str,
) -> tuple[list[PromptEntry], int]:
    """Apply one text-only batch edit without changing references or order."""
    if action not in {"replace", "prepend", "append"}:
        raise ValueError("Unknown prompt text edit action")
    selected = {row for row in rows if 0 <= row < len(entries)}
    find_text, new_text = find_text.strip(), new_text.strip()
    result = [
        PromptEntry(
            prompt=entry.prompt,
            references=list(entry.references),
            chroma_key_color=entry.chroma_key_color,
            result_kind=entry.result_kind,
            object_id=entry.object_id,
        )
        for entry in entries
    ]
    matches = 0
    for row in selected:
        if action in {"prepend", "append"} and not new_text:
            continue
        prompt = result[row].prompt
        editable_prompt, chroma_suffix = _split_user_prompt(prompt)
        if action == "replace":
            if not find_text or find_text not in editable_prompt:
                continue
            editable_prompt = editable_prompt.replace(find_text, new_text)
        elif action == "prepend":
            editable_prompt = "\n".join(
                part for part in (new_text, editable_prompt) if part
            )
        else:
            editable_prompt = "\n".join(
                part for part in (editable_prompt, new_text) if part
            )
        updated_prompt = editable_prompt + chroma_suffix
        if updated_prompt == prompt:
            continue
        result[row].prompt = updated_prompt
        matches += 1
    return result, matches


def export_prompt_csv(
    entries: Sequence[PromptEntry],
    path: str | os.PathLike[str],
) -> None:
    """Write the prompt review table in the same format accepted by CSV import."""

    destination = Path(path)
    with destination.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("Prompt", "References"))
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "Prompt": _user_prompt_text(entry.prompt),
                    "References": "|".join(entry.references),
                }
            )


def _supported_local_reference(path: str) -> bool:
    source = Path(path)
    return source.is_file() and source.suffix.lower() in {
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
    }


def _reference_icon(path: str) -> QIcon:
    if _supported_local_reference(path):
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            return QIcon(pixmap.scaled(120, 120, Qt.AspectRatioMode.KeepAspectRatio))
    placeholder = QPixmap(120, 120)
    placeholder.fill()
    return QIcon(placeholder)


def _reference_label(path: str) -> str:
    name = Path(path).name or path
    if _supported_local_reference(path):
        return name
    return f"{name} (нет файла)"


def _reference_summary(paths: Sequence[str]) -> str:
    if not paths:
        return "Нет референсов"
    missing = sum(1 for path in paths if not _supported_local_reference(path))
    names = ", ".join(_reference_label(path) for path in paths[:3])
    if len(paths) > 3:
        names = f"{names}, …"
    if missing:
        return f"{len(paths)} референсов, {missing} недоступно: {names}"
    return f"{len(paths)} референсов: {names}"


def _review_action_icon(kind: str) -> QIcon:
    """Draw stable cross-platform review icons without relying on emoji fonts."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outline = QColor("#9fb3c8")
    accent = QColor("#2dd4bf")
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(outline, 2.0))

    is_reference = kind.startswith("reference_")
    operation = kind.split("_", 1)[1]
    if is_reference:
        painter.drawRoundedRect(QRectF(3.5, 5.5, 24, 19), 3, 3)
        painter.drawEllipse(QRectF(20, 8, 4, 4))
        painter.drawLine(6, 21, 12, 15)
        painter.drawLine(12, 15, 16, 19)
        painter.drawLine(16, 19, 20, 15)
        painter.drawLine(20, 15, 25, 21)
    elif operation in {"duplicate", "delete_all"}:
        painter.drawRoundedRect(QRectF(4.5, 7.5, 16, 19), 2.5, 2.5)
        painter.drawRoundedRect(QRectF(10.5, 3.5, 16, 19), 2.5, 2.5)
        painter.drawLine(14, 10, 23, 10)
        painter.drawLine(14, 14, 22, 14)
    else:
        painter.drawRoundedRect(QRectF(5.5, 3.5, 20, 24), 3, 3)
        painter.drawLine(10, 10, 21, 10)
        painter.drawLine(10, 15, 20, 15)
        painter.drawLine(10, 20, 17, 20)

    if operation in {"add", "delete", "delete_all", "replace"}:
        painter.setPen(QPen(accent, 2.4))
        painter.setBrush(QColor("#1f2937"))
        painter.drawEllipse(QRectF(18, 18, 12, 12))
        if operation == "add":
            painter.drawLine(21, 24, 27, 24)
            painter.drawLine(24, 21, 24, 27)
        elif operation in {"delete", "delete_all"}:
            painter.drawLine(21, 24, 27, 24)
        else:
            painter.drawArc(QRectF(20, 20, 8, 8), 30 * 16, 285 * 16)
            painter.drawLine(26, 20, 29, 20)
            painter.drawLine(29, 20, 29, 23)

    painter.end()
    return QIcon(pixmap)


def _review_action_divider() -> QFrame:
    divider = QFrame()
    divider.setProperty("v3Divider", True)
    divider.setFixedSize(1, 28)
    return divider


def _compact_review_action_button(kind: str, label: str) -> V3Button:
    button = V3Button("", ButtonVariant.SECONDARY)
    button.setIcon(_review_action_icon(kind))
    button.setIconSize(QSize(24, 24))
    button.setFixedSize(42, 38)
    button.setToolTip(label)
    button.setAccessibleName(label)
    return button


def _confirm_delete_all_prompts(parent: QWidget, count: int) -> bool:
    if count <= 0:
        return False
    answer = QMessageBox.question(
        parent,
        "Удалить все промпты?",
        (
            f"Из текущего проекта будут удалены все промпты ({count}) и их "
            "привязки к референсам. Файлы референсов на диске останутся."
        ),
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes


class _PromptReviewTable(QTableWidget):
    """Keep the prompt/reference columns at the product-defined 2:1 ratio."""

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        width = max(self.viewport().width(), 2)
        prompt_width = round(width * 2 / 3)
        self.setColumnWidth(0, prompt_width)
        self.setColumnWidth(1, width - prompt_width)


class _CsvDropZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("v3Status", True)
        self.setMinimumHeight(150)

    @staticmethod
    def _csv_paths(event: Any) -> list[str]:
        mime = event.mimeData()
        if not mime.hasUrls():
            return []
        return [
            url.toLocalFile()
            for url in mime.urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.casefold() == ".csv"
        ]

    def dragEnterEvent(self, event: Any) -> None:
        if self._csv_paths(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:
        paths = self._csv_paths(event)
        if not paths:
            event.ignore()
            return
        self.file_dropped.emit(paths[0])
        event.acceptProposedAction()


class PromptReferenceEditorDialog(QDialog):
    def __init__(
        self,
        entry: PromptEntry,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Редактор промпта")
        self._result_kind = entry.result_kind
        self._chroma_key_color = entry.chroma_key_color
        self._object_id = entry.object_id
        display_prompt, self._technical_prompt_suffix = _split_user_prompt(entry.prompt)
        self.setModal(True)
        self._prompt_edit = QPlainTextEdit(display_prompt)
        self._prompt_edit.setMinimumHeight(120)
        self._references = QListWidget()
        self._references.setIconSize(QSize(120, 120))
        self._references.setMinimumHeight(190)
        self._references.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._load_references(entry.references)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Промпт"))
        layout.addWidget(self._prompt_edit)
        layout.addWidget(QLabel("Референсы"))
        layout.addWidget(self._references, 1)
        self.reference_status_label = QLabel("")
        self.reference_status_label.setWordWrap(True)
        self.reference_status_label.setProperty("v3Status", True)
        self.reference_status_label.setProperty("state", "error")
        self.reference_status_label.hide()
        layout.addWidget(self.reference_status_label)

        buttons = QHBoxLayout()
        self.add_files_button = V3Button("Добавить файлы", ButtonVariant.SECONDARY)
        self.remove_button = V3Button("Удалить выбранные", ButtonVariant.SECONDARY)
        buttons.addWidget(self.add_files_button)
        buttons.addWidget(self.remove_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.add_files_button.clicked.connect(self._choose_files)
        self.remove_button.clicked.connect(self._remove_selected)

    def _load_references(self, references: Sequence[str]) -> None:
        self._references.clear()
        for reference in references:
            item = QListWidgetItem(_reference_icon(reference), _reference_label(reference))
            item.setData(Qt.ItemDataRole.UserRole, reference)
            item.setToolTip(reference)
            self._references.addItem(item)

    def _choose_files(self) -> None:
        selected, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите изображения",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
        )
        self.add_references(selected)

    def add_references(self, references: Sequence[str]) -> None:
        existing = [self._references.item(index).data(Qt.ItemDataRole.UserRole) for index in range(self._references.count())]
        errors: list[str] = []
        for reference in references:
            normalized = str(Path(reference))
            if (
                not normalized
                or normalized in existing
                or not _supported_local_reference(normalized)
            ):
                continue
            size_error = _reference_file_size_error(normalized)
            if size_error:
                errors.append(size_error)
                continue
            if len(existing) >= MAX_REFERENCES_PER_PROMPT:
                break
            item = QListWidgetItem(_reference_icon(normalized), _reference_label(normalized))
            item.setData(Qt.ItemDataRole.UserRole, normalized)
            item.setToolTip(normalized)
            self._references.addItem(item)
            existing.append(normalized)
        if errors:
            self.reference_status_label.setText(errors[0])
            self.reference_status_label.show()
        else:
            self.reference_status_label.clear()
            self.reference_status_label.hide()

    def _remove_selected(self) -> None:
        for item in list(self._references.selectedItems()):
            row = self._references.row(item)
            self._references.takeItem(row)

    def prompt_text(self) -> str:
        return self._prompt_edit.toPlainText().strip()[:MAX_TEXT_LENGTH]

    def references(self) -> list[str]:
        references: list[str] = []
        for index in range(self._references.count()):
            reference = str(
                self._references.item(index).data(Qt.ItemDataRole.UserRole) or ""
            ).strip()
            if reference:
                references.append(reference)
        return references[:MAX_REFERENCES_PER_PROMPT]

    def prompt_entry(self) -> PromptEntry:
        prompt = self.prompt_text() + self._technical_prompt_suffix
        return PromptEntry(prompt, self.references(),
                           chroma_key_color=self._chroma_key_color,
                           result_kind=self._result_kind, object_id=self._object_id)


class ReferenceScopeDialog(QDialog):
    def __init__(
        self,
        *,
        has_selection: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Область действия")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("К каким промптам применить изменения?"))

        self.scope_group = QButtonGroup(self)
        self.current_radio = QRadioButton("Текущая строка")
        self.selected_radio = QRadioButton("Выбранные строки")
        self.all_radio = QRadioButton("Все промпты")
        for index, button in enumerate(
            (self.current_radio, self.selected_radio, self.all_radio)
        ):
            self.scope_group.addButton(button, index)
            layout.addWidget(button)

        self.current_radio.setChecked(not has_selection)
        self.selected_radio.setChecked(has_selection)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def scope(self) -> str:
        if self.all_radio.isChecked():
            return "all"
        if self.selected_radio.isChecked():
            return "selected"
        return "current"


class PromptBatchEditDialog(QDialog):
    """Preview and configure one reversible edit of prompt text."""

    def __init__(
        self,
        entries: Sequence[PromptEntry],
        *,
        selected_rows: Sequence[int],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Найти и заменить")
        self.setModal(True)
        self.setMinimumWidth(620)
        self._entries = [
            PromptEntry(
                prompt=entry.prompt,
                references=list(entry.references),
                chroma_key_color=entry.chroma_key_color,
                result_kind=entry.result_kind,
                object_id=entry.object_id,
            )
            for entry in entries
        ]
        self._selected_rows = tuple(
            sorted({row for row in selected_rows if 0 <= row < len(entries)})
        )
        self._preview_entries = list(self._entries)
        self._affected_count = 0

        layout = QVBoxLayout(self)

        scope_row = QHBoxLayout()
        scope_row.addWidget(QLabel("Изменить:"))
        self.scope_group = QButtonGroup(self)
        self.selected_radio = QRadioButton(
            f"Выбранные ({len(self._selected_rows)})"
        )
        self.all_radio = QRadioButton(f"Все ({len(self._entries)})")
        self.scope_group.addButton(self.selected_radio)
        self.scope_group.addButton(self.all_radio)
        self.selected_radio.setEnabled(bool(self._selected_rows))
        self.selected_radio.setChecked(bool(self._selected_rows))
        self.all_radio.setChecked(not self._selected_rows)
        scope_row.addWidget(self.selected_radio)
        scope_row.addWidget(self.all_radio)
        scope_row.addStretch()
        layout.addLayout(scope_row)

        action_row = QHBoxLayout()
        action_row.addWidget(QLabel("Действие:"))
        self.action_group = QButtonGroup(self)
        self.replace_radio = QRadioButton("Заменить")
        self.prepend_radio = QRadioButton("В начало")
        self.append_radio = QRadioButton("В конец")
        for button in (
            self.replace_radio,
            self.prepend_radio,
            self.append_radio,
        ):
            self.action_group.addButton(button)
            action_row.addWidget(button)
        self.replace_radio.setChecked(True)
        action_row.addStretch()
        layout.addLayout(action_row)

        self.form = QFormLayout()
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Текст, который нужно найти")
        self.find_edit.setAccessibleName("Найти текст")
        self.new_text_edit = QPlainTextEdit()
        self.new_text_edit.setPlaceholderText("Новый текст")
        self.new_text_edit.setAccessibleName("Новый текст")
        self.new_text_edit.setMaximumHeight(110)
        self.form.addRow("Найти", self.find_edit)
        self.form.addRow("Текст", self.new_text_edit)
        layout.addLayout(self.form)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setProperty("v3Selection", True)
        layout.addWidget(self.summary_label)
        self.preview_list = QListWidget()
        self.preview_list.setAccessibleName("Предварительный результат")
        self.preview_list.setMinimumHeight(120)
        layout.addWidget(self.preview_list)

        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_button = V3Button("Отмена", ButtonVariant.GHOST)
        self.apply_button = V3Button("Применить", ButtonVariant.PRIMARY)
        self.cancel_button.clicked.connect(self.reject)
        self.apply_button.clicked.connect(self.accept)
        button_row.addWidget(self.cancel_button)
        button_row.addWidget(self.apply_button)
        layout.addLayout(button_row)

        for button in (
            self.selected_radio,
            self.all_radio,
            self.replace_radio,
            self.prepend_radio,
            self.append_radio,
        ):
            button.toggled.connect(self._refresh_preview)
        self.find_edit.textChanged.connect(self._refresh_preview)
        self.new_text_edit.textChanged.connect(self._refresh_preview)
        self._refresh_preview()

    def action(self) -> str:
        if self.prepend_radio.isChecked():
            return "prepend"
        if self.append_radio.isChecked():
            return "append"
        return "replace"

    def rows(self) -> tuple[int, ...]:
        if self.selected_radio.isChecked() and self._selected_rows:
            return self._selected_rows
        return tuple(range(len(self._entries)))

    def affected_count(self) -> int:
        return self._affected_count

    def edited_entries(self) -> tuple[list[PromptEntry], int]:
        return (
            [
                PromptEntry(
                    prompt=entry.prompt,
                    references=list(entry.references),
                    chroma_key_color=entry.chroma_key_color,
                    result_kind=entry.result_kind,
                    object_id=entry.object_id,
                )
                for entry in self._preview_entries
            ],
            self._affected_count,
        )

    def _refresh_preview(self, *_: Any) -> None:
        replace_action = self.action() == "replace"
        self.find_edit.setVisible(replace_action)
        find_label = self.form.labelForField(self.find_edit)
        if find_label is not None:
            find_label.setVisible(replace_action)

        rows = self.rows()
        self._preview_entries, self._affected_count = apply_prompt_text_edit(
            self._entries,
            rows=rows,
            action=self.action(),
            find_text=self.find_edit.text(),
            new_text=self.new_text_edit.toPlainText(),
        )
        too_long = any(
            len(self._preview_entries[row].prompt) > MAX_TEXT_LENGTH for row in rows
        )
        unchanged_rows = tuple(
            row
            for row in rows
            if self._entries[row].prompt == self._preview_entries[row].prompt
        )
        unchanged_row_labels = ", ".join(
            str(row + 1) for row in unchanged_rows[:10]
        )
        if len(unchanged_rows) > 10:
            unchanged_row_labels += ", …"
        self.preview_list.clear()
        for row in rows:
            before = self._entries[row].prompt
            after = self._preview_entries[row].prompt
            if before == after:
                continue
            before_preview = _user_prompt_text(before).replace("\n", " ")[:100]
            after_preview = _user_prompt_text(after).replace("\n", " ")[:100]
            self.preview_list.addItem(
                f"{row + 1}. {before_preview}  →  {after_preview}"
            )
            if self.preview_list.count() >= 3:
                break

        if too_long:
            summary = f"Текст превышает максимум {MAX_TEXT_LENGTH} символов"
        elif replace_action and not self.find_edit.text().strip():
            summary = "Введите текст, который нужно найти"
        elif not self.new_text_edit.toPlainText().strip() and not replace_action:
            summary = "Введите текст для добавления"
        elif not self._affected_count:
            summary = (
                "Совпадений не найдено"
                + (
                    f" · строки: {unchanged_row_labels}"
                    if unchanged_row_labels
                    else ""
                )
            )
        else:
            unchanged = len(rows) - self._affected_count
            summary = (
                f"Будет изменено: {self._affected_count} из {len(rows)}"
                + (
                    f" · без совпадений: {unchanged}"
                    f" · строки: {unchanged_row_labels}"
                    if replace_action and unchanged
                    else ""
                )
            )
        self.summary_label.setText(summary)
        has_required_text = (
            bool(self.find_edit.text().strip())
            if replace_action
            else bool(self.new_text_edit.toPlainText().strip())
        )
        self.apply_button.setEnabled(
            self._affected_count > 0 and has_required_text and not too_long
        )


class PromptInputPage(ScrollableStepPage):
    def _file_dialog_type(self):
        return QFileDialog

    def _csv_import_dialog_type(self):
        return PromptCsvImportDialog

    generator_mode: ProjectMode | None = None
    supports_prompt_chroma = True

    def __init__(
        self,
        state: ProjectState,
        data: Any,
        changed: Callable[[], None],
        *,
        advance: Callable[[], Any] | None = None,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Содержание",
            "Создайте серию, добавьте готовый промпт или импортируйте CSV.",
            tokens=tokens,
        )
        self.state = state
        self.data = data
        self.changed = changed
        self.advance = advance
        self.tokens = tokens
        self.progress_label = QLabel("Шаг 1 из 2 · Добавление промптов")
        self.progress_label.setProperty("v3Selection", True)
        self.progress_label.setAccessibleName(self.progress_label.text())
        self.add_widget(self.progress_label)
        source_choices = (
            "Сгенерировать серию",
            "Вставить готовый промпт",
            "Импортировать CSV",
        )
        source_row = QWidget()
        source_layout = QHBoxLayout(source_row)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(tokens.space_3)
        self.source_button_group = QButtonGroup(self)
        self.source_button_group.setExclusive(True)
        self.source_buttons: list[QPushButton] = []
        for index, title in enumerate(source_choices):
            button = QPushButton(title)
            button.setProperty("v3SourceChoice", True)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(title)
            button.clicked.connect(
                lambda checked=False, target=index: self._select_source(target)
            )
            self.source_button_group.addButton(button, index)
            self.source_buttons.append(button)
            source_layout.addWidget(button, 1)
        self.add_widget(source_row)

        self.source_combo = QComboBox()
        self.source_combo.setAccessibleName("Источник промптов")
        self.source_combo.addItem("Сгенерировать серию", "generator")
        self.source_combo.addItem("Вставить готовые промпты", "paste")
        self.source_combo.addItem("Импортировать CSV", "csv")
        self.source_combo.hide()

        self.source_stack = QStackedWidget()
        self.generator_widget = self._build_generator()
        self.paste_widget = self._build_paste()
        self.csv_widget = self._build_csv()
        for widget in (
            self.generator_widget,
            self.paste_widget,
            self.csv_widget,
        ):
            self.source_stack.addWidget(widget)
        if self.supports_prompt_chroma:
            source_area = QWidget()
            source_layout = QHBoxLayout(source_area)
            source_layout.setContentsMargins(0, 0, 0, 0)
            source_layout.setSpacing(tokens.space_3)
            source_layout.addWidget(self.source_stack, 2)
            self.chroma_advisor = self._build_chroma_advisor()
            source_layout.addWidget(self.chroma_advisor, 1)
            self.add_widget(source_area)
        else:
            self.add_widget(self.source_stack)
        self.source_combo.currentIndexChanged.connect(self._select_source)
        self.source_combo.setCurrentIndex(1)
        self._select_source(1)
        self.refresh_from_state()

    def refresh_from_state(self) -> None:
        if hasattr(self, "prompt_count_label"):
            self.prompt_count_label.setText(
                f"В проекте: {len(self.data.prompts)} промптов"
            )

    def _select_source(self, index: int) -> None:
        if not 0 <= index < self.source_stack.count():
            return
        self.source_stack.setCurrentIndex(index)
        if self.source_combo.currentIndex() != index:
            self.source_combo.blockSignals(True)
            self.source_combo.setCurrentIndex(index)
            self.source_combo.blockSignals(False)
        for button_index, button in enumerate(self.source_buttons):
            button.setChecked(button_index == index)
        if hasattr(self, "chroma_advisor"):
            self.chroma_advisor.setVisible(index in (0, 1))

    def _build_chroma_advisor(self) -> AdvancedSection:
        advisor = AdvancedSection("Прозрачный фон", tokens=self.tokens)
        advisor.setMinimumWidth(214)
        advisor.setMaximumWidth(280)
        advisor.toggle_button.setText("Прозрачный\nфон")
        advisor.toggle_button.setStyleSheet("font-size: 12px;")
        advisor.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        label = QLabel(
            "Приложение автоматически подготовит изображение для прозрачного PNG. "
            "После обработки проверьте края изображения."
        )
        label.setWordWrap(True)
        label.setProperty("v3Description", True)
        advisor.add_widget(label)
        advisor.set_expanded(True)
        return advisor

    def _build_chroma_color_buttons(
        self,
        combo: QComboBox,
    ) -> tuple[QWidget, dict[str, QPushButton]]:
        colors = {
            "blue": QColor("#0000FF"),
            "red": QColor("#FF0000"),
            "green": QColor("#00FF00"),
        }
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.tokens.space_2)
        group = QButtonGroup(widget)
        group.setExclusive(True)
        buttons: dict[str, QPushButton] = {}
        for label, value in CHROMA_KEY_COLOR_OPTIONS:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("v3ChromaMaterial", True)
            swatch = QPixmap(14, 14)
            swatch.fill(colors[value])
            button.setIcon(QIcon(swatch))
            button.setChecked(combo.currentData() == value)
            button.clicked.connect(
                lambda checked=False, selected=value: combo.setCurrentIndex(
                    combo.findData(selected)
                )
            )
            group.addButton(button)
            buttons[value] = button
            layout.addWidget(button)

        def sync_buttons() -> None:
            current = combo.currentData()
            if current in buttons:
                buttons[current].setChecked(True)

        combo.currentIndexChanged.connect(sync_buttons)
        combo.hide()
        return widget, buttons

    def _build_generator(self) -> QWidget:
        draft = self.data.prompt_generator
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Новая серия промптов")
        title.setProperty("v3Title", True)
        layout.addWidget(title)

        variable_group = QGroupBox("Меняется в каждом промпте")
        variable_layout = QGridLayout(variable_group)
        self.theme_edit = QLineEdit(draft.theme)
        self.subjects_edit = QPlainTextEdit("\n".join(draft.subjects))
        self.variations_edit = QPlainTextEdit("\n".join(draft.variations))
        for edit in (self.subjects_edit, self.variations_edit):
            edit.setMinimumHeight(115)
            edit.setMaximumHeight(115)
        subjects_label = QLabel("Объекты — каждый с новой строки")
        variations_label = QLabel("Варианты или позы — каждый с новой строки")
        variable_layout.addWidget(subjects_label, 0, 0)
        variable_layout.addWidget(variations_label, 0, 1)
        variable_layout.addWidget(self.subjects_edit, 1, 0)
        variable_layout.addWidget(self.variations_edit, 1, 1)
        self.combinations_label = QLabel()
        self.combinations_label.setProperty("v3Selection", True)
        variable_layout.addWidget(self.combinations_label, 2, 0, 1, 2)
        variable_layout.setColumnStretch(0, 1)
        variable_layout.setColumnStretch(1, 1)
        layout.addWidget(variable_group)

        fixed_group = QGroupBox("Остаётся одинаковым во всей серии")
        form = QFormLayout(fixed_group)
        self.style_edit = QLineEdit(draft.style)
        self.palette_edit = QLineEdit(draft.palette)
        self.composition_edit = QLineEdit(draft.composition)
        self.background_edit = QLineEdit(draft.background)
        self.consistency_edit = QLineEdit(draft.consistency)
        for edit in (
            self.theme_edit,
            self.style_edit,
            self.palette_edit,
            self.composition_edit,
            self.background_edit,
            self.consistency_edit,
        ):
            edit.setMaxLength(MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        self.restrictions_edit = QPlainTextEdit("\n".join(draft.restrictions))
        self.restrictions_edit.setMaximumHeight(72)
        self.restrictions_edit.setPlaceholderText(
            "Например: текст, рамки, водяные знаки"
        )
        fields = (
            ("Что нужно создать", self.theme_edit),
            ("Стиль", self.style_edit),
            ("Палитра", self.palette_edit),
            ("Композиция", self.composition_edit),
            ("Фон", self.background_edit),
            ("Единообразие серии", self.consistency_edit),
            ("Исключить", self.restrictions_edit),
        )
        for label, control in fields:
            control.setAccessibleName(label)
            form.addRow(label, control)
        layout.addWidget(fixed_group)

        key_group = QGroupBox("Прозрачный фон")
        key_form = QFormLayout(key_group)
        self.chroma_key_enabled = QCheckBox(
            "Подготовить прозрачный фон автоматически"
        )
        self.chroma_key_enabled.setChecked(draft.chroma_key_enabled)
        self.chroma_key_enabled.setAccessibleName(
            "Подготовить прозрачный фон автоматически"
        )
        self.chroma_key_color = QComboBox()
        for label, value in CHROMA_KEY_COLOR_OPTIONS:
            self.chroma_key_color.addItem(label, value)
        index = self.chroma_key_color.findData(draft.chroma_key_color)
        self.chroma_key_color.setCurrentIndex(index if index >= 0 else 0)
        self.chroma_key_color.setAccessibleName("Цвет chroma-key фона")
        color_buttons_widget, self.chroma_key_color_buttons = (
            self._build_chroma_color_buttons(self.chroma_key_color)
        )
        materials_widget = QWidget()
        materials_layout = QGridLayout(materials_widget)
        materials_layout.setContentsMargins(0, 0, 0, 0)
        materials_layout.setSpacing(self.tokens.space_2)
        self.chroma_material_buttons: list[QPushButton] = []
        for index, (label, value) in enumerate(CHROMA_KEY_MATERIAL_OPTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("chromaMaterial", value)
            button.setChecked(value in draft.chroma_key_materials)
            self.chroma_material_buttons.append(button)
            materials_layout.addWidget(button, index // 2, index % 2)
        configure_chroma_material_buttons(self.chroma_material_buttons)
        key_form.addRow(self.chroma_key_enabled)
        note = QLabel("Технический способ подготовки выбирается автоматически.")
        note.setProperty("v3Description", True)
        note.setWordWrap(True)
        key_form.addRow(note)
        color_buttons_widget.setParent(key_group)
        materials_widget.setParent(key_group)
        self._chroma_color_buttons_widget = color_buttons_widget
        self._chroma_materials_widget = materials_widget
        color_buttons_widget.hide()
        materials_widget.hide()
        for button in self.chroma_key_color_buttons.values():
            button.hide()
        for button in self.chroma_material_buttons:
            button.hide()
        layout.addWidget(key_group)

        self.preview_label = QLabel("Пример итогового промпта появится здесь.")
        self.preview_label.setWordWrap(True)
        self.preview_label.setProperty("v3Status", True)
        self.preview_label.setAccessibleName("Предпросмотр вариантов")
        layout.addWidget(self.preview_label)

        self.create_series_button = V3Button("Создать серию промптов")
        self.create_series_button.clicked.connect(self._create_series)
        layout.addWidget(self.create_series_button, 0, Qt.AlignmentFlag.AlignLeft)

        self._generated_variants: list[PromptEntry] = []
        for edit in (
            self.theme_edit,
            self.style_edit,
            self.palette_edit,
            self.composition_edit,
            self.background_edit,
            self.consistency_edit,
        ):
            edit.textChanged.connect(self._generator_changed)
        self.subjects_edit.textChanged.connect(self._generator_changed)
        self.variations_edit.textChanged.connect(self._generator_changed)
        self.restrictions_edit.textChanged.connect(self._generator_changed)
        self.chroma_key_enabled.toggled.connect(self._generator_changed)
        self.chroma_key_color.currentIndexChanged.connect(self._generator_changed)
        for button in self.chroma_material_buttons:
            button.toggled.connect(self._generator_changed)
        self._preview()
        return widget

    def _generator_data(self) -> PromptGeneratorData:
        return PromptGeneratorData(
            theme=self.theme_edit.text(),
            subjects=self.subjects_edit.toPlainText().splitlines(),
            variations=self.variations_edit.toPlainText().splitlines(),
            style=self.style_edit.text(),
            palette=self.palette_edit.text(),
            composition=self.composition_edit.text(),
            background=self.background_edit.text(),
            consistency=self.consistency_edit.text(),
            restrictions=self.restrictions_edit.toPlainText().splitlines(),
            chroma_key_enabled=self.chroma_key_enabled.isChecked(),
            chroma_key_color=self.chroma_key_color.currentData(),
            chroma_key_materials=[
                str(button.property("chromaMaterial"))
                for button in self.chroma_material_buttons
                if button.isChecked()
            ],
        )

    def _generator_changed(self, *_: Any) -> None:
        data = self._generator_data()
        self.data.prompt_generator = data
        if data.chroma_key_enabled:
            self.data.operations.remove_background = True
            self.data.operations.remove_background_provider = "local_chroma_key"
            self.data.operations.chroma_key_color = data.chroma_key_color
        elif self.data.operations.remove_background_provider == "local_chroma_key":
            # Turning off chroma-key generation must not leave the pipeline
            # silently removing an ordinary generated background by color.
            self.data.operations.remove_background = False
            self.data.operations.remove_background_provider = "kie"
        self._preview()
        self.changed()

    def _generate_series(self, data: PromptGeneratorData) -> list[PromptEntry]:
        if self.generator_mode is None:
            raise PromptGeneratorError("Prompt generator mode is not configured")
        return generate_prompt_series(self.generator_mode, data)

    def _preview(self, *_: Any) -> None:
        try:
            entries = self._generate_series(self._generator_data())
        except PromptGeneratorError as error:
            self._generated_variants = []
            self.preview_label.setText("Заполните хотя бы одно поле конструктора.")
            self.create_series_button.setEnabled(False)
            subjects = len([line for line in self.subjects_edit.toPlainText().splitlines() if line.strip()])
            variations = len([line for line in self.variations_edit.toPlainText().splitlines() if line.strip()]) or 1
            self.combinations_label.setText(
                f"{subjects} объектов × {variations} вариантов"
            )
            return
        self.card.set_state("default")
        self._generated_variants = entries
        example_lines = [f"{index}. {_user_prompt_text(entry.prompt)}" for index, entry in enumerate(entries[:2], 1)]
        self.preview_label.setText("Пример итогового промпта:\n" + "\n\n".join(example_lines))
        self.combinations_label.setText(f"Будет создано {len(entries)} промптов")
        self.create_series_button.setEnabled(True)

    def _create_series(self) -> None:
        self._preview()
        if self._generated_variants and self._store_entries(
            self._generated_variants,
            action="append",
        ):
            if self.advance is not None:
                self.advance()

    def _store_entries(
        self,
        entries: Sequence[PromptEntry],
        *,
        action: str,
        deduplicate: bool = True,
    ) -> bool:
        normalized = list(entries)
        if action == "append":
            if len(self.data.prompts) + len(normalized) > MAX_PROMPT_ENTRIES:
                self.card.set_state(
                    "error",
                    f"Максимум {MAX_PROMPT_ENTRIES} промптов. Уменьшите добавляемый список.",
                )
                return False
            normalized = list(self.data.prompts) + normalized
        if self.generator_mode is None:
            self.card.set_state("error", "Режим генерации промптов не настроен")
            return False
        self.data.prompts = normalize_prompt_entries(
            normalized, deduplicate=deduplicate
        )
        if self.supports_prompt_chroma and any(entry.chroma_key_color for entry in entries):
            self.data.operations.remove_background = True
            self.data.operations.remove_background_provider = "local_chroma_key"
        self.card.set_state("default")
        self.refresh_from_state()
        self.changed()
        return True

    def _generate(self) -> None:
        try:
            self._preview()
        except PromptGeneratorError as error:
            self.card.set_state("error", str(error))
            return

    def _build_paste(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.paste_edit = QPlainTextEdit()
        self.paste_edit.setPlaceholderText("Вставьте один готовый промпт. Он может занимать несколько строк.")
        self.paste_edit.setAccessibleName("Готовый промпт")
        self.paste_edit.setMinimumHeight(140)
        self.paste_edit.setMaximumHeight(180)
        layout.addWidget(self.paste_edit)
        actions = QWidget()
        actions.setMaximumHeight(self.tokens.control_height + 2)
        action_layout = QHBoxLayout(actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.add_references_button = V3Button(
            "Добавить референсы",
            ButtonVariant.SECONDARY,
        )
        self.add_references_button.clicked.connect(self._choose_paste_references)
        self.paste_references_label = QLabel("Референсы не выбраны")
        self.paste_references_label.setProperty("v3Small", True)
        self.clear_references_button = V3Button("Очистить", ButtonVariant.GHOST)
        self.clear_references_button.clicked.connect(self._clear_paste_references)
        self.clear_references_button.hide()
        action_layout.addWidget(self.add_references_button)
        action_layout.addWidget(self.paste_references_label, 1)
        action_layout.addWidget(self.clear_references_button)
        action_layout.addStretch()
        layout.addWidget(actions)
        if self.supports_prompt_chroma:
            self._add_prompt_chroma_controls(layout, "paste")
        self.add_prompt_button = V3Button("Добавить промпт")
        self.add_prompt_button.clicked.connect(self._apply_paste)
        layout.addWidget(self.add_prompt_button, 0, Qt.AlignmentFlag.AlignLeft)
        self.paste_status_label = QLabel("")
        self.paste_status_label.setWordWrap(True)
        self.paste_status_label.setProperty("v3Selection", True)
        layout.addWidget(self.paste_status_label)
        self._paste_references: list[str] = []
        layout.addStretch()
        return widget

    def _add_prompt_chroma_controls(self, layout: QVBoxLayout, prefix: str) -> None:
        group = QGroupBox("Прозрачный фон")
        form = QFormLayout(group)
        enabled = QCheckBox("Подготовить прозрачный фон автоматически")
        color = QComboBox()
        for label, value in CHROMA_KEY_COLOR_OPTIONS:
            color.addItem(label, value)
        color_buttons_widget, color_buttons = self._build_chroma_color_buttons(color)
        materials = QWidget()
        material_layout = QGridLayout(materials)
        material_layout.setContentsMargins(0, 0, 0, 0)
        material_layout.setSpacing(self.tokens.space_2)
        buttons: dict[str, QPushButton] = {}
        for index, (label, value) in enumerate(CHROMA_KEY_MATERIAL_OPTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            buttons[value] = button
            material_layout.addWidget(button, index // 2, index % 2)
        configure_chroma_material_buttons(tuple(buttons.values()))
        form.addRow(enabled)
        note = QLabel("Технический способ подготовки выбирается автоматически.")
        note.setProperty("v3Description", True)
        note.setWordWrap(True)
        form.addRow(note)
        color_buttons_widget.setParent(group)
        materials.setParent(group)
        setattr(self, f"{prefix}_chroma_color_buttons_widget", color_buttons_widget)
        setattr(self, f"{prefix}_chroma_materials_widget", materials)
        color_buttons_widget.hide()
        materials.hide()
        for button in color_buttons.values():
            button.hide()
        for button in buttons.values():
            button.hide()
        setattr(self, f"{prefix}_chroma_enabled", enabled)
        setattr(self, f"{prefix}_chroma_color", color)
        setattr(self, f"{prefix}_chroma_color_buttons", color_buttons)
        setattr(self, f"{prefix}_chroma_material_buttons", buttons)
        layout.addWidget(group)

    def _prompt_with_chroma(self, prompt: str, prefix: str) -> str:
        if not self.supports_prompt_chroma:
            return prompt
        enabled = getattr(self, f"{prefix}_chroma_enabled")
        if not enabled.isChecked():
            return prompt
        color = select_chroma_key_color(prompt).color
        combo = getattr(self, f"{prefix}_chroma_color")
        index = combo.findData(color)
        if index >= 0:
            combo.setCurrentIndex(index)
        return prompt + "\n" + chroma_key_prompt_block(color)

    def _choose_paste_references(self) -> None:
        selected, _ = self._file_dialog_type().getOpenFileNames(
            self,
            "Выберите до 5 референсов",
            self.state.common.work_dir or os.getcwd(),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
        )
        self._add_paste_references(selected)

    def _add_paste_references(self, references: Sequence[str]) -> None:
        errors: list[str] = []
        for reference in references:
            normalized = str(Path(reference))
            if normalized in self._paste_references or not _supported_local_reference(normalized):
                continue
            size_error = _reference_file_size_error(normalized)
            if size_error:
                errors.append(size_error)
                continue
            if len(self._paste_references) >= MAX_REFERENCES_PER_PROMPT:
                break
            self._paste_references.append(normalized)
        self._refresh_paste_references()
        if errors:
            self.card.set_state("error", errors[0])

    def _clear_paste_references(self) -> None:
        self._paste_references = []
        self._refresh_paste_references()

    def _refresh_paste_references(self) -> None:
        if not self._paste_references:
            self.paste_references_label.setText("Референсы не выбраны")
            self.paste_references_label.setToolTip("")
            self.clear_references_button.hide()
            return
        labels = []
        for reference in self._paste_references:
            name = Path(reference).name
            labels.append(name if len(name) <= 18 else "…" + name[-17:])
        self.paste_references_label.setText(" · ".join(labels))
        self.paste_references_label.setToolTip("\n".join(self._paste_references))
        self.clear_references_button.show()

    def _apply_paste(self) -> None:
        text = self.paste_edit.toPlainText()
        if len(text) > MAX_CSV_BYTES:
            self.card.set_state("error", "Вставленный текст превышает допустимый размер")
            return
        prompt = " ".join(text.split())
        if not prompt:
            self.card.set_state("error", "Введите промпт")
            return
        if len(prompt) > MAX_TEXT_LENGTH:
            self.card.set_state("error", "Промпт слишком длинный")
            return
        prompt = self._prompt_with_chroma(prompt, "paste")
        key_color = (
            self.paste_chroma_color.currentData()
            if self.paste_chroma_enabled.isChecked() else ""
        )
        if self._store_entries(
            [PromptEntry(prompt=prompt, references=self._paste_references,
                         chroma_key_color=key_color)],
            action="append",
            deduplicate=False,
        ):
            self.paste_edit.clear()
            self._clear_paste_references()
            self.paste_status_label.setText(
                "Промпт добавлен в проект. Вы сможете проверить и "
                "отредактировать его на следующем шаге."
            )

    def _build_csv(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.csv_drop_zone = _CsvDropZone()
        drop_layout = QVBoxLayout(self.csv_drop_zone)
        drop_layout.setContentsMargins(
            self.tokens.space_4,
            self.tokens.space_4,
            self.tokens.space_4,
            self.tokens.space_4,
        )
        text = QLabel("Перетащите CSV-файл сюда")
        text.setWordWrap(True)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(text)
        self.csv_button = V3Button("Выбрать CSV", ButtonVariant.PRIMARY)
        self.csv_button.clicked.connect(self._choose_csv)
        drop_layout.addWidget(self.csv_button, 0, Qt.AlignmentFlag.AlignCenter)
        mapping_hint = QLabel(
            "Перед импортом можно проверить разделитель и сопоставить колонки."
        )
        mapping_hint.setProperty("v3Small", True)
        mapping_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(mapping_hint)
        self.csv_drop_zone.file_dropped.connect(self._import_csv_file)
        layout.addWidget(self.csv_drop_zone)
        layout.addStretch(1)
        return widget

    def _choose_csv(self) -> None:
        selected, _ = self._file_dialog_type().getOpenFileName(
            self,
            "Импортировать CSV",
            self.state.common.work_dir or os.getcwd(),
            "CSV files (*.csv)",
        )
        if not selected:
            return
        self._import_csv_file(selected)

    def _import_csv_file(self, selected: str) -> None:
        try:
            dialog = self._csv_import_dialog_type()(selected, self)
        except RuntimeError as error:
            self.card.set_state("error", str(error))
            return
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entries = [PromptEntry.from_value(entry) for entry in dialog.get_entries()]
        normalized_entries = [entry for entry in entries if entry is not None]
        if not normalized_entries:
            self.card.set_state("error", "Не найдено ни одной валидной строки CSV")
            return
        imported = self._store_entries(
            normalized_entries,
            action="append",
            deduplicate=False,
        )
        if imported and self.advance is not None:
            self.advance()


class PromptReviewPage(ScrollableStepPage):
    def _file_dialog_type(self):
        return QFileDialog

    def __init__(
        self,
        state: ProjectState,
        data: Any,
        changed: Callable[[], None],
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(
            "Проверка промптов",
            "Редактируйте текст и референсы, удаляйте и меняйте порядок строк.",
            tokens=tokens,
        )
        # The step title already names this screen; keep the card name for assistive tech only.
        self.card.title_label.hide()
        self.card.description_label.hide()
        self.state = state
        self.data = data
        self.changed = changed
        self._updating = False
        self._batch_undo_snapshot: list[PromptEntry] | None = None
        self.progress_label = QLabel("Шаг 2 из 2 · Проверка серии")
        self.progress_label.setProperty("v3Selection", True)
        self.progress_label.setAccessibleName(self.progress_label.text())
        self.add_widget(self.progress_label)
        self.batch_edit_button = V3Button(
            "Найти и заменить",
            ButtonVariant.SECONDARY,
        )
        self.undo_batch_button = V3Button(
            "Отменить изменение",
            ButtonVariant.GHOST,
        )
        self.undo_batch_button.setEnabled(False)
        self.undo_batch_button.hide()
        search_row = QWidget()
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Найти промпт")
        self.search_edit.setAccessibleName("Поиск по промптам")
        self.search_result_label = QLabel()
        self.search_result_label.setProperty("v3Small", True)
        search_layout.addWidget(self.search_edit, 1)
        search_layout.addWidget(self.search_result_label)
        search_layout.addWidget(self.batch_edit_button)
        search_layout.addWidget(self.undo_batch_button)
        self.add_widget(search_row)
        self.table = _PromptReviewTable(0, 2)
        self.table.setHorizontalHeaderLabels(["Промпт", "Референсы"])
        self.table.setAccessibleName("Таблица промптов")
        self.table.setObjectName("promptReviewTable")
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.setMinimumHeight(360)
        self.table.setMaximumHeight(520)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive,
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.cellDoubleClicked.connect(self._edit_row)
        self.table.itemChanged.connect(self._table_changed)
        self.table.model().rowsMoved.connect(self._rows_moved)
        self.search_edit.textChanged.connect(self._apply_search)

        prompt_actions = QWidget()
        action_layout = QHBoxLayout(prompt_actions)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(tokens.space_2)
        prompt_actions_label = QLabel("Промпты")
        prompt_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(prompt_actions_label)
        self.add_button = _compact_review_action_button(
            "prompt_add",
            "Добавить промпт",
        )
        self.duplicate_button = _compact_review_action_button(
            "prompt_duplicate",
            "Дублировать выбранные промпты",
        )
        self.delete_button = _compact_review_action_button(
            "prompt_delete",
            "Удалить выбранные промпты",
        )
        self.delete_all_button = _compact_review_action_button(
            "prompt_delete_all",
            "Удалить все промпты",
        )
        for button in (
            self.add_button,
            self.duplicate_button,
            self.delete_button,
            self.delete_all_button,
        ):
            action_layout.addWidget(button)

        action_layout.addWidget(_review_action_divider())
        references_actions_label = QLabel("Референсы")
        references_actions_label.setProperty("v3Small", True)
        action_layout.addWidget(references_actions_label)
        self.add_refs_button = _compact_review_action_button(
            "reference_add",
            "Добавить референсы",
        )
        self.replace_refs_button = _compact_review_action_button(
            "reference_replace",
            "Заменить референсы",
        )
        self.delete_refs_button = _compact_review_action_button(
            "reference_delete",
            "Удалить референсы",
        )
        self.up_button = V3Button("Выше", ButtonVariant.GHOST)
        self.down_button = V3Button("Ниже", ButtonVariant.GHOST)
        self.up_button.hide()
        self.down_button.hide()
        for button in (
            self.add_refs_button,
            self.replace_refs_button,
            self.delete_refs_button,
        ):
            action_layout.addWidget(button)
        action_layout.addWidget(_review_action_divider())
        self.export_csv_button = V3Button("Экспорт CSV", ButtonVariant.SECONDARY)
        self.export_csv_button.setIcon(_review_action_icon("prompt_export"))
        self.export_csv_button.setIconSize(QSize(22, 22))
        self.export_csv_button.setFixedHeight(38)
        self.export_csv_button.setToolTip("Экспортировать все строки в CSV")
        self.export_csv_button.setAccessibleName(
            "Экспортировать все строки в CSV"
        )
        action_layout.addWidget(self.export_csv_button)
        action_layout.addStretch()
        self.add_widget(prompt_actions)
        self.add_widget(self.table)
        self.issues_label = QLabel()
        self.issues_label.setWordWrap(True)
        self.issues_label.setProperty("v3Small", True)
        self.add_widget(self.issues_label)

        self.add_button.clicked.connect(self._add)
        self.duplicate_button.clicked.connect(self._duplicate)
        self.delete_button.clicked.connect(self._delete)
        self.delete_all_button.clicked.connect(self._delete_all)
        self.batch_edit_button.clicked.connect(self._open_batch_editor)
        self.undo_batch_button.clicked.connect(self._undo_batch_edit)
        self.add_refs_button.clicked.connect(self._add_references)
        self.replace_refs_button.clicked.connect(self._replace_references)
        self.delete_refs_button.clicked.connect(self._delete_references)
        self.export_csv_button.clicked.connect(self._export_csv)
        self.refresh_from_state()

    def _open_batch_editor(self) -> None:
        if not self.data.prompts:
            self.card.set_state("error", "Сначала добавьте промпты")
            return
        dialog = PromptBatchEditDialog(
            self.data.prompts,
            selected_rows=self._selected_rows(),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        entries, affected_count = dialog.edited_entries()
        self._apply_batch_result(entries, affected_count=affected_count)

    def _apply_batch_result(
        self,
        entries: Sequence[PromptEntry],
        *,
        affected_count: int,
    ) -> None:
        if affected_count <= 0:
            return
        self._batch_undo_snapshot = [
            PromptEntry(
                prompt=entry.prompt,
                references=list(entry.references),
                chroma_key_color=entry.chroma_key_color,
                result_kind=entry.result_kind,
                object_id=entry.object_id,
            )
            for entry in self.data.prompts
        ]
        self.data.prompts = [
            PromptEntry(
                prompt=entry.prompt,
                references=list(entry.references),
                chroma_key_color=entry.chroma_key_color,
                result_kind=entry.result_kind,
                object_id=entry.object_id,
            )
            for entry in entries
        ]
        self.undo_batch_button.setEnabled(True)
        self.undo_batch_button.show()
        self.refresh_from_state()
        self.card.set_state("default", f"Изменено промптов: {affected_count}")
        self.changed()

    def _undo_batch_edit(self) -> None:
        if self._batch_undo_snapshot is None:
            return
        self.data.prompts = self._batch_undo_snapshot
        self._invalidate_batch_undo()
        self.refresh_from_state()
        self.card.set_state("default", "Массовое изменение отменено")
        self.changed()

    def _invalidate_batch_undo(self) -> None:
        self._batch_undo_snapshot = None
        self.undo_batch_button.setEnabled(False)
        self.undo_batch_button.hide()

    def _rows_moved(self, *_: Any) -> None:
        if self._updating:
            return
        # The references column is a display summary, not the source data.
        # Rebuilding entries from its text during drag/drop loses references
        # and can blank prompts while Qt is moving rows. Keep the original
        # entry index on the prompt item and only reorder existing entries.
        reordered: list[PromptEntry] = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            source_row = item.data(Qt.ItemDataRole.UserRole) if item else None
            if isinstance(source_row, int) and 0 <= source_row < len(self.data.prompts):
                reordered.append(self.data.prompts[source_row])
        if len(reordered) == len(self.data.prompts):
            self._invalidate_batch_undo()
            self.data.prompts = reordered
            self._updating = True
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is not None:
                    item.setData(Qt.ItemDataRole.UserRole, row)
            self._updating = False
            self._refresh_issues()
            self.changed()

    def refresh_from_state(self) -> None:
        self._updating = True
        self.table.setRowCount(len(self.data.prompts))
        for row, entry in enumerate(self.data.prompts):
            prompt_item = QTableWidgetItem(_user_prompt_text(entry.prompt))
            prompt_item.setData(Qt.ItemDataRole.UserRole, row)
            self.table.setItem(row, 0, prompt_item)
            refs_item = QTableWidgetItem(_reference_summary(entry.references))
            refs_item.setData(
                Qt.ItemDataRole.UserRole,
                tuple(entry.references),
            )
            refs_item.setFlags(
                refs_item.flags() & ~Qt.ItemFlag.ItemIsEditable
            )
            refs_item.setToolTip("\n".join(entry.references) or "Нет референсов")
            self.table.setItem(row, 1, refs_item)
        self._updating = False
        self._apply_search()
        self._refresh_issues()

    def _apply_search(self, *_: Any) -> None:
        query = self.search_edit.text().strip().casefold()
        visible = 0
        for row, entry in enumerate(self.data.prompts):
            haystack = " ".join((_user_prompt_text(entry.prompt), *entry.references)).casefold()
            matches = not query or query in haystack
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        self.search_result_label.setText(
            f"Показано {visible} из {len(self.data.prompts)}"
        )

    def _selected_rows(self) -> list[int]:
        rows = {
            index.row()
            for index in self.table.selectionModel().selectedRows()
            if 0 <= index.row() < len(self.data.prompts)
        }
        return sorted(rows)

    def _edit_row(self, row: int, *_: Any) -> None:
        if not 0 <= row < len(self.data.prompts):
            return
        entry = self.data.prompts[row]
        dialog = PromptReferenceEditorDialog(entry, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._invalidate_batch_undo()
        self.data.prompts[row] = dialog.prompt_entry()
        self.refresh_from_state()
        self.changed()

    def _pick_reference_scope(self) -> str | None:
        dialog = ReferenceScopeDialog(
            has_selection=bool(self.table.selectionModel().selectedRows()),
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.scope()

    def _choose_reference_files(self) -> list[str]:
        selected, _ = self._file_dialog_type().getOpenFileNames(
            self,
            "Выберите изображения",
            self.state.common.work_dir or os.getcwd(),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff)",
        )
        files = [str(Path(path)) for path in selected if path]
        accepted: list[str] = []
        errors: list[str] = []
        for path in files:
            if not _supported_local_reference(path):
                continue
            size_error = _reference_file_size_error(path)
            if size_error:
                errors.append(size_error)
                continue
            accepted.append(path)
        if errors:
            self.card.set_state("error", errors[0])
        return accepted

    def _apply_references(
        self,
        *,
        replace: bool,
    ) -> None:
        scope = self._pick_reference_scope()
        if scope is None:
            return
        if scope == "all":
            rows = list(range(len(self.data.prompts)))
        elif scope == "selected":
            rows = self._selected_rows()
        else:
            row = self._selected_row()
            rows = [row] if row >= 0 else []
        if not rows:
            return
        files = self._choose_reference_files()
        if not files or not rows:
            return
        changed_any = False
        for row in rows:
            entry = self.data.prompts[row]
            if replace:
                entry.references = list(files[:MAX_REFERENCES_PER_PROMPT])
            else:
                merged = list(entry.references)
                for reference in files:
                    if reference not in merged:
                        merged.append(reference)
                entry.references = merged[:MAX_REFERENCES_PER_PROMPT]
            changed_any = True
        if changed_any:
            self._invalidate_batch_undo()
            self.refresh_from_state()
            self.changed()

    def _add_references(self) -> None:
        self._apply_references(replace=False)

    def _replace_references(self) -> None:
        self._apply_references(replace=True)

    def _delete_references(self) -> None:
        if not self.data.prompts:
            return
        scope = self._pick_reference_scope()
        if scope is None:
            return
        if scope == "all":
            rows = range(len(self.data.prompts))
        elif scope == "selected":
            rows = self._selected_rows()
        else:
            row = self._selected_row()
            rows = [row] if row >= 0 else []
        rows = list(rows)
        if not rows:
            return
        self._invalidate_batch_undo()
        for row in rows:
            self.data.prompts[row].references = []
        self.refresh_from_state()
        self.changed()

    def _export_csv(self) -> None:
        if not self.data.prompts:
            self.card.set_state("error", "Сначала добавьте промпты")
            return
        initial_path = str(
            Path(self.state.common.work_dir or os.getcwd()) / "prompts.csv"
        )
        selected, _ = self._file_dialog_type().getSaveFileName(
            self,
            "Экспортировать промпты",
            initial_path,
            "CSV files (*.csv)",
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.casefold() != ".csv":
            destination = destination.with_suffix(".csv")
        try:
            export_prompt_csv(self.data.prompts, destination)
        except OSError:
            self.card.set_state("error", "Не удалось сохранить CSV")
            return
        self.card.set_state("default", f"CSV сохранён: {destination.name}")

    # Backward-compatible test and keyboard action name.
    def _delete_all_references(self) -> None:
        if not self.data.prompts:
            return
        self._invalidate_batch_undo()
        for entry in self.data.prompts:
            entry.references = []
        self.refresh_from_state()
        self.changed()

    def _table_changed(self, _: QTableWidgetItem) -> None:
        if self._updating:
            return
        self._invalidate_batch_undo()
        entries: list[PromptEntry] = []
        for row in range(self.table.rowCount()):
            prompt_item = self.table.item(row, 0)
            refs_item = self.table.item(row, 1)
            prompt = prompt_item.text() if prompt_item else ""
            stored_references = (
                refs_item.data(Qt.ItemDataRole.UserRole)
                if refs_item is not None
                else ()
            )
            references = [
                str(value)
                for value in (
                    stored_references
                    if isinstance(stored_references, (list, tuple))
                    else ()
                )
                if str(value)
            ]
            if len(prompt) > MAX_TEXT_LENGTH:
                self.card.set_state("error", "Промпт превышает допустимую длину")
                self.refresh_from_state()
                return
            if len(references) > MAX_REFERENCES_PER_PROMPT:
                self.card.set_state(
                    "error",
                    f"Максимум {MAX_REFERENCES_PER_PROMPT} референсов на промпт",
                )
                self.refresh_from_state()
                return
            if any(len(value) > MAX_TEXT_LENGTH for value in references):
                self.card.set_state("error", "Референс превышает допустимую длину")
                self.refresh_from_state()
                return
            original = self.data.prompts[row] if row < len(self.data.prompts) else PromptEntry()
            _display, technical_suffix = _split_user_prompt(original.prompt)
            entries.append(PromptEntry(prompt=prompt + technical_suffix, references=references,
                                       chroma_key_color=original.chroma_key_color,
                                       result_kind=original.result_kind,
                                       object_id=original.object_id))
        self.data.prompts = entries
        self._apply_search()
        self._refresh_issues()
        self.changed()

    def _selected_row(self) -> int:
        row = self.table.currentRow()
        return row if 0 <= row < len(self.data.prompts) else -1

    def _add(self) -> None:
        if len(self.data.prompts) >= MAX_PROMPT_ENTRIES:
            self.card.set_state("error", f"Максимум {MAX_PROMPT_ENTRIES} промптов")
            return
        self.card.set_state("default")
        self._invalidate_batch_undo()
        self.data.prompts.append(PromptEntry(prompt="Новый промпт"))
        self.refresh_from_state()
        self.table.setCurrentCell(len(self.data.prompts) - 1, 0)
        self.changed()

    def _duplicate(self) -> None:
        row = self._selected_row()
        if row < 0:
            return
        if len(self.data.prompts) >= MAX_PROMPT_ENTRIES:
            self.card.set_state("error", f"Максимум {MAX_PROMPT_ENTRIES} промптов")
            return
        self.card.set_state("default")
        self._invalidate_batch_undo()
        source = self.data.prompts[row]
        self.data.prompts.insert(
            row + 1,
            PromptEntry(
                prompt=source.prompt,
                references=list(source.references),
                chroma_key_color=source.chroma_key_color,
                result_kind=source.result_kind,
                object_id=source.object_id,
            ),
        )
        self.refresh_from_state()
        self.table.setCurrentCell(row + 1, 0)
        self.changed()

    def _delete(self) -> None:
        rows = self._selected_rows()
        if not rows:
            row = self._selected_row()
            rows = [row] if row >= 0 else []
        if not rows:
            return
        self._invalidate_batch_undo()
        for row in reversed(rows):
            del self.data.prompts[row]
        self.refresh_from_state()
        self.changed()

    def _delete_all(self) -> None:
        if not _confirm_delete_all_prompts(
            self,
            len(self.data.prompts),
        ):
            return
        self._invalidate_batch_undo()
        self.data.prompts = []
        self.refresh_from_state()
        self.changed()

    def _move(self, offset: int) -> None:
        row = self._selected_row()
        target = row + offset
        if row < 0 or not 0 <= target < len(self.data.prompts):
            return
        self._invalidate_batch_undo()
        prompts = self.data.prompts
        prompts[row], prompts[target] = prompts[target], prompts[row]
        self.refresh_from_state()
        self.table.setCurrentCell(target, 0)
        self.changed()

    def _refresh_issues(self) -> None:
        empty = 0
        duplicates = 0
        seen: set[str] = set()
        for entry in self.data.prompts:
            key = _user_prompt_text(entry.prompt).strip().casefold()
            if not key:
                empty += 1
            elif key in seen:
                duplicates += 1
            else:
                seen.add(key)
        text = (
            f"Строк: {len(self.data.prompts)} · "
            f"пустых: {empty} · дублей: {duplicates}"
        )
        self.issues_label.setText(text)
        self.issues_label.setAccessibleName(text)

    def validation_issues(self) -> tuple[str, ...]:
        if any(not _user_prompt_text(entry.prompt).strip() for entry in self.data.prompts):
            return ("prompt_empty",)
        return ()
