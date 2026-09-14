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
