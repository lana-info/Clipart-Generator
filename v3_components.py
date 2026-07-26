from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class V3DesignTokens:
    canvas: str = "#f7f6f2"
    surface: str = "#ffffff"
    surface_muted: str = "#f3f4f6"
    text: str = "#17212b"
    text_muted: str = "#5f6b76"
    border: str = "#d7dce1"
    accent: str = "#0f9f90"
    accent_hover: str = "#0b8579"
    accent_soft: str = "#e5f7f4"
    focus: str = "#2563eb"
    warning: str = "#a15c00"
    warning_soft: str = "#fff7df"
    error: str = "#b42318"
    error_soft: str = "#fff0ee"
    disabled: str = "#8a949e"
    disabled_soft: str = "#eceff1"

    font_family: str = "Segoe UI"
    font_size_body: int = 14
    font_size_small: int = 12
    font_size_title: int = 18
    font_weight_regular: int = 400
    font_weight_medium: int = 600
    font_weight_bold: int = 700

    space_1: int = 4
    space_2: int = 8
    space_3: int = 12
    space_4: int = 16
    space_6: int = 24
    space_8: int = 32

    radius_control: int = 8
    radius_card: int = 8
    control_height: int = 38
    focus_width: int = 2


DEFAULT_TOKENS = V3DesignTokens()


class ButtonVariant(str, Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"
    GHOST = "ghost"
    DESTRUCTIVE = "destructive"


class CardState(str, Enum):
    DEFAULT = "default"
    WARNING = "warning"
    ERROR = "error"


def build_v3_stylesheet(tokens: V3DesignTokens = DEFAULT_TOKENS) -> str:
    return f"""
QWidget[v3Root="true"] {{
    background: {tokens.canvas};
    color: {tokens.text};
    font-family: "{tokens.font_family}";
    font-size: {tokens.font_size_body}px;
}}
QFrame[v3Card="true"] {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_card}px;
}}
QFrame[v3Card="true"][state="warning"] {{
    background: {tokens.warning_soft};
    border: 2px solid {tokens.warning};
}}
QFrame[v3Card="true"][state="error"] {{
    background: {tokens.error_soft};
    border: 2px solid {tokens.error};
}}
QFrame[v3Card="true"][selected="true"] {{
    background: {tokens.accent_soft};
    border: 2px solid {tokens.accent};
}}
QLabel[v3Title="true"] {{
    color: {tokens.text};
    font-size: {tokens.font_size_title}px;
    font-weight: {tokens.font_weight_bold};
    background: transparent;
    border: none;
}}
QLabel[v3Description="true"] {{
    color: {tokens.text_muted};
    font-size: {tokens.font_size_body}px;
    background: transparent;
    border: none;
}}
QLabel[v3Small="true"] {{
    color: {tokens.text_muted};
    font-size: {tokens.font_size_small}px;
    background: transparent;
    border: none;
}}
QLabel[v3Status="true"] {{
    font-weight: {tokens.font_weight_medium};
    padding: {tokens.space_2}px;
    border-radius: {tokens.radius_control}px;
}}
QLabel[v3Status="true"][state="warning"] {{
    color: {tokens.warning};
    background: {tokens.warning_soft};
    border: 1px solid {tokens.warning};
}}
QLabel[v3Status="true"][state="error"] {{
    color: {tokens.error};
    background: {tokens.error_soft};
    border: 1px solid {tokens.error};
}}
QLabel[v3Selection="true"] {{
    color: {tokens.accent_hover};
    font-weight: {tokens.font_weight_bold};
    background: transparent;
    border: none;
}}
QPushButton[v3Button="true"] {{
    min-height: {tokens.control_height}px;
    padding: 0 {tokens.space_4}px;
    border-radius: {tokens.radius_control}px;
    font-weight: {tokens.font_weight_medium};
}}
QPushButton[v3Button="true"][variant="primary"] {{
    color: white;
    background: {tokens.accent};
    border: 1px solid {tokens.accent};
}}
QPushButton[v3Button="true"][variant="primary"]:hover {{
    background: {tokens.accent_hover};
    border-color: {tokens.accent_hover};
}}
QPushButton[v3Button="true"][variant="secondary"] {{
    color: {tokens.text};
    background: {tokens.surface};
    border: 1px solid {tokens.border};
}}
QPushButton[v3Button="true"][variant="secondary"]:hover {{
    background: {tokens.surface_muted};
    border-color: {tokens.text_muted};
}}
QPushButton[v3Button="true"][variant="ghost"] {{
    color: {tokens.text};
    background: transparent;
    border: 1px solid transparent;
}}
QPushButton[v3Button="true"][variant="ghost"]:hover {{
    background: {tokens.surface_muted};
    border-color: {tokens.border};
}}
QPushButton[v3Button="true"][variant="destructive"] {{
    color: white;
    background: {tokens.error};
    border: 1px solid {tokens.error};
}}
QPushButton[v3Button="true"]:focus {{
    border: {tokens.focus_width}px solid {tokens.focus};
    padding: 0 {max(tokens.space_4 - tokens.focus_width, 0)}px;
}}
QPushButton[v3Button="true"]:disabled {{
    color: {tokens.disabled};
    background: {tokens.disabled_soft};
    border: 2px dashed {tokens.disabled};
}}
QToolButton[v3Disclosure="true"] {{
    min-height: {tokens.control_height}px;
    color: {tokens.text};
    background: transparent;
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_control}px;
    padding: 0 {tokens.space_3}px;
    text-align: left;
    font-weight: {tokens.font_weight_medium};
}}
QToolButton[v3Disclosure="true"]:hover {{
    background: {tokens.surface_muted};
}}
QToolButton[v3Disclosure="true"]:focus {{
    border: {tokens.focus_width}px solid {tokens.focus};
}}
QToolButton[v3Disclosure="true"]:disabled {{
    color: {tokens.disabled};
    background: {tokens.disabled_soft};
    border: 2px dashed {tokens.disabled};
}}
"""


def apply_v3_theme(
    root: QWidget,
    tokens: V3DesignTokens = DEFAULT_TOKENS,
) -> None:
    root.setProperty("v3Root", True)
    root.setStyleSheet(build_v3_stylesheet(tokens))


def _refresh_style(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


class V3Button(QPushButton):
    def __init__(
        self,
        text: str,
        variant: ButtonVariant = ButtonVariant.PRIMARY,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setProperty("v3Button", True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_variant(variant)
        self.setAccessibleName(text)

    @property
    def variant(self) -> ButtonVariant:
        return ButtonVariant(self.property("variant"))

    def set_variant(self, variant: ButtonVariant | str) -> None:
        normalized = (
            variant if isinstance(variant, ButtonVariant) else ButtonVariant(variant)
        )
        self.setProperty("variant", normalized.value)
        if normalized is ButtonVariant.DESTRUCTIVE:
            self.setAccessibleDescription("Опасное действие")
        else:
            self.setAccessibleDescription("")
        _refresh_style(self)


class FormCard(QFrame):
    def __init__(
        self,
        title: str,
        description: str = "",
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        self.setProperty("v3Card", True)
        self.setProperty("state", CardState.DEFAULT.value)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
        )
        self._layout.setSpacing(tokens.space_3)

        self.title_label = QLabel(title)
        self.title_label.setProperty("v3Title", True)
        self.title_label.setWordWrap(True)
        self._layout.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setProperty("v3Description", True)
        self.description_label.setWordWrap(True)
        self.description_label.setVisible(bool(description))
        self._layout.addWidget(self.description_label)

        self.status_label = QLabel()
        self.status_label.setProperty("v3Status", True)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        self._layout.addWidget(self.status_label)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(tokens.space_3)
        self._layout.addWidget(self.content)

        self.setAccessibleName(title)
        self.setAccessibleDescription(description)

    @property
    def state(self) -> CardState:
        return CardState(self.property("state"))

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def set_state(self, state: CardState | str, message: str = "") -> None:
        normalized = state if isinstance(state, CardState) else CardState(state)
        self.setProperty("state", normalized.value)
        self.status_label.setProperty("state", normalized.value)

        if normalized is CardState.WARNING:
            text = f"⚠ Предупреждение: {message or 'проверьте настройки'}"
        elif normalized is CardState.ERROR:
            text = f"✕ Ошибка: {message or 'исправьте отмеченные поля'}"
        else:
            text = ""

        self.status_label.setText(text)
        self.status_label.setVisible(bool(text))
        self.status_label.setAccessibleName(text)
        self.setAccessibleDescription(
            " — ".join(part for part in (self.description_label.text(), text) if part)
        )
        _refresh_style(self)
        _refresh_style(self.status_label)


class ModeCard(QFrame):
    selected = pyqtSignal(str)

    def __init__(
        self,
        mode_id: str,
        title: str,
        description: str,
        result_text: str,
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        self.mode_id = mode_id
        self.setProperty("v3Card", True)
        self.setProperty("selected", False)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
            tokens.space_4,
        )
        layout.setSpacing(tokens.space_3)

        self.title_label = QLabel(title)
        self.title_label.setProperty("v3Title", True)
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.description_label = QLabel(description)
        self.description_label.setProperty("v3Description", True)
        self.description_label.setWordWrap(True)
        layout.addWidget(self.description_label)

        self.result_label = QLabel(f"Результат: {result_text}")
        self.result_label.setProperty("v3Small", True)
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)
        layout.addStretch()

        self.selection_label = QLabel("✓ Выбран режим")
        self.selection_label.setProperty("v3Selection", True)
        self.selection_label.hide()
        layout.addWidget(self.selection_label)

        self.start_button = V3Button("Начать", ButtonVariant.PRIMARY)
        self.start_button.setAccessibleName(f"Начать: {title}")
        self.start_button.clicked.connect(lambda: self.selected.emit(self.mode_id))
        layout.addWidget(self.start_button)

        self.setAccessibleName(title)
        self.setAccessibleDescription(f"{description}. Результат: {result_text}")

    @property
    def is_selected(self) -> bool:
        return bool(self.property("selected"))

    def set_selected(self, selected: bool) -> None:
        normalized = bool(selected)
        self.setProperty("selected", normalized)
        self.selection_label.setVisible(normalized)
        self.setAccessibleDescription(
            (
                f"{self.description_label.text()}. {self.result_label.text()}. "
                + ("Выбран режим." if normalized else "Режим не выбран.")
            )
        )
        _refresh_style(self)


class AdvancedSection(QWidget):
    expanded_changed = pyqtSignal(bool)

    def __init__(
        self,
        title: str = "Дополнительно",
        parent: QWidget | None = None,
        *,
        tokens: V3DesignTokens = DEFAULT_TOKENS,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.space_2)

        self.toggle_button = QToolButton()
        self.toggle_button.setProperty("v3Disclosure", True)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle_button.setText(title)
        self.toggle_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggle_button.setAccessibleName(title)
        self.toggle_button.setAccessibleDescription("Раздел свёрнут")
        layout.addWidget(self.toggle_button)

        self.content = QFrame()
        self.content.setProperty("v3Card", True)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(
            tokens.space_3,
            tokens.space_3,
            tokens.space_3,
            tokens.space_3,
        )
        self.content_layout.setSpacing(tokens.space_2)
        self.content.hide()
        layout.addWidget(self.content)

        self.toggle_button.toggled.connect(self._on_toggled)

    @property
    def is_expanded(self) -> bool:
        return self.toggle_button.isChecked()

    def add_widget(self, widget: QWidget) -> None:
        self.content_layout.addWidget(widget)

    def set_expanded(self, expanded: bool) -> None:
        normalized = bool(expanded)
        if self.toggle_button.isChecked() != normalized:
            self.toggle_button.setChecked(normalized)
        else:
            self._apply_expanded(normalized)

    def _on_toggled(self, expanded: bool) -> None:
        self._apply_expanded(expanded)
        self.expanded_changed.emit(expanded)

    def _apply_expanded(self, expanded: bool) -> None:
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )
        self.toggle_button.setAccessibleDescription(
            "Раздел раскрыт" if expanded else "Раздел свёрнут"
        )
        self.content.setVisible(expanded)
