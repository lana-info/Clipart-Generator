"""Shared UI primitives for independently owned Studio workflows."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractScrollArea, QScrollArea, QSizePolicy, QWidget

from v3_components import DEFAULT_TOKENS, FormCard, V3DesignTokens


class ScrollableStepPage(QScrollArea):
    def __init__(
        self, title: str, description: str, *, tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setMinimumSize(0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.card = FormCard(title, description, tokens=tokens)
        self.setWidget(self.card)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

    def add_widget(self, widget: QWidget) -> None:
        self.card.add_widget(widget)

    def refresh_from_state(self) -> None:
        return


class ProjectDirectoryPage(ScrollableStepPage):
    """Shared project/work-directory editor with module-selected output mode."""

    def __init__(self, state, changed, *, output_mode, tokens=DEFAULT_TOKENS) -> None:
        from PyQt6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit
        from v3_components import ButtonVariant, V3Button

        super().__init__("Рабочая папка", "Выберите папку для записи результатов.", tokens=tokens)
        self.state = state
        self.changed = changed
        self.output_mode = output_mode
        form = QFormLayout()
        work_widget = QWidget()
        work_layout = QHBoxLayout(work_widget)
        work_layout.setContentsMargins(0, 0, 0, 0)
        self.work_dir_edit = QLineEdit(state.common.work_dir)
        self.work_dir_edit.setAccessibleName("Рабочая папка")
        self.browse_button = V3Button("Выбрать", ButtonVariant.SECONDARY)
        self.browse_button.clicked.connect(self._browse)
        work_layout.addWidget(self.work_dir_edit, 1)
        work_layout.addWidget(self.browse_button)
        form.addRow("Рабочая папка", work_widget)
        container = QWidget()
        container.setLayout(form)
        self.add_widget(container)
        self.path_status = QLabel()
        self.path_status.setWordWrap(True)
        self.path_status.setProperty("v3Small", True)
        self.add_widget(self.path_status)
        self.work_dir_edit.textChanged.connect(self._sync)
        self._refresh_status()

    def _browse(self) -> None:
        import os
        from PyQt6.QtWidgets import QFileDialog
        selected = QFileDialog.getExistingDirectory(
            self, "Выберите рабочую папку", self.work_dir_edit.text() or os.getcwd()
        )
        if selected:
            self.work_dir_edit.setText(selected)

    def _sync(self) -> None:
        from pathlib import Path
        self.state.common.work_dir = self.work_dir_edit.text().strip()
        self.state.set_output_dir_for_mode(
            str(Path(self.state.common.work_dir) / "output") if self.state.common.work_dir else "",
            self.output_mode,
        )
        self._refresh_status()
        self.changed()

    def _refresh_status(self) -> None:
        import os
        from pathlib import Path
        path = Path(self.work_dir_edit.text().strip()).expanduser()
        valid = path.is_dir() and os.access(path, os.W_OK)
        text = "✓ Папка доступна для записи." if valid else "✕ Выберите существующую папку, доступную для записи."
        self.path_status.setText(text)
        self.path_status.setAccessibleName(text)

    def validation_issues(self) -> tuple[str, ...]:
        import os
        from pathlib import Path
        path = Path(self.work_dir_edit.text().strip()).expanduser()
        if not path.is_dir() or not os.access(path, os.W_OK):
            return ("work_dir_unavailable",)
        return ()
