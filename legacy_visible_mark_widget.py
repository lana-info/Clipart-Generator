"""Extracted, UX-preserving visible-mark settings widget for legacy UI."""

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget


class VisibleMarkSettingsWidget(QWidget):
    def __init__(self, mode: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("visibleMarkSettingsWidget")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.mode_combo = QComboBox(self)
        self.mode_combo.setObjectName("visibleMarkModeCombo")
        self.mode_combo.addItem("Автоматически (Gemini)", "gemini_auto")
        self.mode_combo.addItem("Выделенная область (с подтверждением)", "confirmed_area")
        index = self.mode_combo.findData(mode)
        self.mode_combo.setCurrentIndex(index if index >= 0 else 0)
        self.mode_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.mode_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.mode_combo.setFixedHeight(32)
        self.confirmation_label = QLabel("Нужно подтверждение", self)
        self.confirmation_label.setObjectName("visibleMarkConfirmationLabel")
        self.confirmation_label.setStyleSheet("color:#14b8a6; font-weight:600;")
        layout.addWidget(self.mode_combo)
        layout.addWidget(self.confirmation_label)
        layout.addStretch()
        self.mode_combo.currentIndexChanged.connect(
            lambda *_: self.set_enabled_state(self.mode_combo.isEnabled())
        )
        self.set_enabled_state(True)

    def set_enabled_state(self, enabled: bool) -> None:
        self.mode_combo.setEnabled(enabled)
        self.confirmation_label.setVisible(
            enabled and self.mode_combo.currentData() == "confirmed_area"
        )
