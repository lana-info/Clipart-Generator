from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
import sys

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


@dataclass(frozen=True)
class V3DesignTokens:
    # Default dark theme tuned for strong contrast on Windows default dark mode.
    canvas: str = "#101827"
    surface: str = "#1f2937"
    surface_muted: str = "#273549"
    text: str = "#e5eef7"
    text_muted: str = "#92a2b3"
    border: str = "#304054"
    accent: str = "#2dd4bf"
    accent_hover: str = "#14b8a6"
    accent_soft: str = "#12363f"
    on_accent: str = "#06201c"
    focus: str = "#60a5fa"
    warning: str = "#f59e0b"
    warning_soft: str = "#4a2f0f"
    error: str = "#f87171"
    error_soft: str = "#441d1d"
    disabled: str = "#7c8a9a"
    disabled_soft: str = "#253242"

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


def dropdown_indicator_stylesheet(
    selector: str = "QComboBox",
    tokens: V3DesignTokens = DEFAULT_TOKENS,
) -> str:
    """Visible right-hand chevron for dropdowns across Studio and its modules."""
    asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
    arrow = (asset_root / "dropdown-chevron.png").as_posix()
    disabled_arrow = (asset_root / "dropdown-chevron-disabled.png").as_posix()
    return f"""
{selector} {{ padding-right: 36px; }}
{selector}::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    background: {tokens.surface_muted};
    border-left: 1px solid {tokens.border};
    border-top-right-radius: {tokens.radius_control}px;
    border-bottom-right-radius: {tokens.radius_control}px;
}}
{selector}::drop-down:hover {{ background: {tokens.accent_soft}; }}
{selector}::down-arrow {{
    image: url("{arrow}");
    width: 14px;
    height: 10px;
}}
{selector}::drop-down:disabled {{ background: {tokens.disabled_soft}; }}
{selector}::down-arrow:disabled {{ image: url("{disabled_arrow}"); }}
"""

# One geometry contract for the whole desktop application. Pages may scroll,
# but switching screens must never resize the top-level window.
V3_WINDOW_DEFAULT_SIZE = (1120, 780)
V3_WINDOW_MINIMUM_SIZE = (980, 700)


class _AspectRatioPixmapLabel(QLabel):
    """Display a raster illustration without stretching it."""

    def __init__(self, pixmap: QPixmap, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._source_pixmap = pixmap
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        super().setPixmap(pixmap)

    def resizeEvent(self, event) -> None:
        if not self._source_pixmap.isNull() and self.width() > 0 and self.height() > 0:
            super().setPixmap(
                self._source_pixmap.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        super().resizeEvent(event)


class V3StepLabel(QLabel):
    """Sidebar step row. The text keeps the "<marker> <n>. <title>" contract;
    painting renders the marker as a status badge so state is not colour-only."""

    clicked = pyqtSignal()
    _PATTERN = re.compile(r"^([✓●○✕])\s*(\d+)\.\s*(.*)$", re.S)
    _BADGE = 22
    _PAD_X = 10
    _PAD_Y = 8
    _GAP = 10

    def __init__(self, text: str = "", tokens: V3DesignTokens = DEFAULT_TOKENS) -> None:
        super().__init__(text)
        self._tokens = tokens
        self._clickable = False
        self.setWordWrap(True)

    def set_clickable(self, clickable: bool) -> None:
        self._clickable = bool(clickable)
        self.setCursor(Qt.CursorShape.PointingHandCursor if self._clickable else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt API
        if (self._clickable and event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API
        """A shell may rename a step after the row was created; the row height must follow the new title."""
        super().setText(text)
        self.updateGeometry()
        parent = self.parentWidget()
        if parent is not None and parent.layout() is not None:
            parent.layout().invalidate()

    def _parts(self) -> tuple[str, str, str] | None:
        match = self._PATTERN.match(self.text())
        return match.groups() if match else None

    def _title_width(self, width: int) -> int:
        return max(width - 2 * self._PAD_X - self._BADGE - self._GAP, 40)

    def _title_font(self, marker: str) -> QFont:
        font = QFont(self.font())
        font.setWeight(QFont.Weight.Bold if marker == "●" else QFont.Weight.Medium if marker in "✓✕" else QFont.Weight.Normal)
        return font

    def _title_height(self, title: str, marker: str, width: int) -> int:
        rect = QFontMetrics(self._title_font(marker), self).boundingRect(
            QRect(0, 0, self._title_width(width) - 8, 10000),  # safety margin: never measure wider than painted
            int(Qt.AlignmentFlag.AlignLeft) | int(Qt.TextFlag.TextWordWrap),
            title,
        )
        return rect.height()

    def hasHeightForWidth(self) -> bool:
        return self._parts() is not None

    def heightForWidth(self, width: int) -> int:
        parts = self._parts()
        if parts is None:
            return super().heightForWidth(width)
        return max(self._BADGE, self._title_height(parts[2], parts[0], width)) + 2 * self._PAD_Y

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        parts = self._parts()
        if parts is not None:
            hint.setHeight(self.heightForWidth(self.width() if self.width() > 100 else 208))
        return hint

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self.updateGeometry()

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        if self._parts() is not None:
            hint.setHeight(self._BADGE + 2 * self._PAD_Y)
        return hint

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        parts = self._parts()
        if parts is None:
            super().paintEvent(event)
            return
        marker, number, title = parts
        t = self._tokens
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if marker == "●":
            row = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(t.surface_muted))
            painter.drawRoundedRect(row, 6, 6)
            painter.setBrush(QColor(t.accent))
            painter.drawRoundedRect(QRectF(row.left(), row.top() + 6, 3, row.height() - 12), 1.5, 1.5)
        badge = QRectF(self._PAD_X, self._PAD_Y, self._BADGE, self._BADGE)
        fill, edge, glyph, text_color = {
            "✓": (t.accent_soft, t.accent, "✓", t.text),
            "●": (t.accent, t.accent, number, t.text),
            "○": (None, t.border, number, t.text_muted),
            "✕": (t.error_soft, t.error, "✕", t.error),
        }[marker]
        glyph_color = {"✓": t.accent, "●": t.on_accent, "○": t.text_muted, "✕": t.error}[marker]
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill) if fill else Qt.BrushStyle.NoBrush)
        painter.drawEllipse(badge.adjusted(0.5, 0.5, -0.5, -0.5))
        glyph_font = QFont(self.font())
        glyph_font.setPixelSize(12)
        glyph_font.setWeight(QFont.Weight.Bold)
        painter.setFont(glyph_font)
        painter.setPen(QColor(glyph_color))
        painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), glyph)
        painter.setFont(self._title_font(marker))
        painter.setPen(QColor(text_color))
        text_left = self._PAD_X + self._BADGE + self._GAP
        text_rect = QRect(text_left, self._PAD_Y, self._title_width(self.width()), self.height() - 2 * self._PAD_Y)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft) | int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.TextFlag.TextWordWrap),
            title,
        )
        painter.end()


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
QWidget {{
    color: {tokens.text};
}}
QMainWindow {{
    background: {tokens.canvas};
}}
QDialog,
QMessageBox {{
    background: {tokens.canvas};
    color: {tokens.text};
}}
QToolTip {{
    background: {tokens.surface_muted};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    padding: {tokens.space_1}px {tokens.space_2}px;
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
QLabel[v3ExternalLink="true"] {{
    color: {tokens.accent_hover};
    background: transparent;
    padding: {tokens.space_1}px;
}}
QLabel[v3ExternalLink="true"]:focus {{
    border: 2px solid {tokens.accent};
    border-radius: {tokens.radius_control}px;
}}
QLabel {{
    color: {tokens.text};
    background: transparent;
    border: none;
}}
QTabWidget::pane {{
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_card}px;
    top: -1px;
    background: {tokens.surface};
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {tokens.text_muted};
    padding: {tokens.space_2 + 1}px {tokens.space_4 + 2}px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: {tokens.font_weight_medium};
    margin-right: 2px;
}}
QTabBar::tab:selected {{
    color: {tokens.text};
    border-bottom: 2px solid {tokens.accent};
}}
QTabBar::tab:hover:!selected {{
    color: {tokens.text};
    background: {tokens.surface_muted};
}}
QAbstractScrollArea::corner {{
    background: transparent;
}}
QLabel[v3Section="true"] {{
    font-size: {tokens.font_size_title - 2}px;
    font-weight: {tokens.font_weight_bold};
}}
QLabel[v3Summary="true"] {{
    background: {tokens.surface_muted};
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_card}px;
    padding: {tokens.space_2}px {tokens.space_3}px;
}}
QLabel[v3CardTitle="true"] {{
    font-weight: {tokens.font_weight_bold};
}}
QLabel[v3StylePreview="true"] {{
    background: #ffffff;
    border-radius: 6px;
}}
QPushButton[v3StyleCard="true"], QPushButton[v3PaletteCard="true"] {{
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_card + 2}px;
    text-align: left;
    padding: 0;
}}
QPushButton[v3StyleCard="true"] {{
    min-height: 104px;
}}
QPushButton[v3PaletteCard="true"] {{
    min-height: 88px;
}}
QPushButton[v3StyleCard="true"]:hover, QPushButton[v3PaletteCard="true"]:hover {{
    border-color: {tokens.text_muted};
}}
QPushButton[v3StyleCard="true"]:checked, QPushButton[v3PaletteCard="true"]:checked {{
    background: {tokens.accent_soft};
    border: 2px solid {tokens.accent};
}}
QPushButton[v3StyleCard="true"]:focus, QPushButton[v3PaletteCard="true"]:focus {{
    border: 2px solid {tokens.focus};
}}
QPushButton[v3Chip="true"] {{
    background: transparent;
    color: {tokens.text};
    border: 1px solid {tokens.border};
    border-radius: 15px;
    min-height: 30px;
    padding: 2px 14px;
}}
/* Owner 2026-10-29: buttons in a block (marks on the PNG check) carry the same slight
   rounding and height as every other button of the app, not the pill shape. */
QPushButton[v3Chip="true"][v3ChipControl="true"] {{
    border-radius: {tokens.radius_control}px;
    min-height: {tokens.control_height}px;
    padding: 0 {tokens.space_4}px;
}}
QPushButton[v3Chip="true"]:hover {{
    border-color: {tokens.text_muted};
}}
QPushButton[v3Chip="true"]:checked {{
    background: {tokens.accent_soft};
    color: {tokens.accent};
    border: 1px solid {tokens.accent};
    font-weight: {tokens.font_weight_medium};
}}
QPushButton[v3Chip="true"]:focus {{
    border: 2px solid {tokens.focus};
}}
QPushButton[v3Chip="true"]:disabled {{
    color: {tokens.disabled};
    border-color: {tokens.disabled_soft};
}}
QFrame[v3Divider="true"] {{
    background: {tokens.border};
    border: none;
    min-width: 1px;
    max-width: 1px;
}}
QTableWidget#promptReviewTable::item {{
    padding: {tokens.space_2 - 2}px {tokens.space_3}px;
    border-bottom: 1px solid {tokens.border};
}}
QTableWidget#promptReviewTable::item:selected {{
    background: {tokens.accent_soft};
    color: {tokens.text};
}}
QGroupBox {{
    color: {tokens.text};
    background: transparent;
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_control}px;
    padding-top: 1.2em;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {tokens.space_3}px;
    padding: 0 {tokens.space_1}px;
    color: {tokens.text};
}}
QLineEdit,
QTextEdit,
QPlainTextEdit,
QComboBox,
QDateEdit,
QSpinBox,
QDoubleSpinBox,
QAbstractSpinBox {{
    background: {tokens.surface};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_control}px;
    padding: {tokens.space_1}px {tokens.space_2}px;
}}
QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus,
QDateEdit:focus,
QSpinBox:focus,
QDoubleSpinBox:focus,
QAbstractSpinBox:focus {{
    border-color: {tokens.accent};
}}
QLineEdit:disabled,
QTextEdit:disabled,
QPlainTextEdit:disabled,
QComboBox:disabled,
QDateEdit:disabled,
QSpinBox:disabled,
QDoubleSpinBox:disabled,
QAbstractSpinBox:disabled {{
    background: {tokens.surface_muted};
    color: {tokens.disabled};
}}
QComboBox QAbstractItemView {{
    background: {tokens.surface};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    selection-background-color: {tokens.accent_soft};
    selection-color: {tokens.text};
}}
{dropdown_indicator_stylesheet("QComboBox", tokens)}
QTableWidget,
QListWidget,
QListView {{
    background: {tokens.surface};
    color: {tokens.text};
    border: 1px solid {tokens.border};
    alternate-background-color: {tokens.surface_muted};
    selection-background-color: {tokens.accent_soft};
    selection-color: {tokens.text};
}}
QTableWidget::item,
QListWidget::item {{
    color: {tokens.text};
}}
QListWidget::item {{
    border-left: 3px solid transparent;
}}
QTableWidget::item:selected,
QListWidget::item:selected,
QTableWidget::item:selected:!active,
QListWidget::item:selected:!active {{
    background: {tokens.accent_soft};
    color: {tokens.text};
}}
QListWidget::item:selected,
QListWidget::item:selected:!active {{
    border-left: 3px solid {tokens.accent};
}}
QHeaderView::section {{
    color: {tokens.text};
    background: {tokens.surface_muted};
    border: 1px solid {tokens.border};
    padding: 4px;
}}
QCheckBox,
QRadioButton {{
    color: {tokens.text};
}}
QCheckBox::indicator,
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {tokens.border};
    background: {tokens.surface};
}}
QCheckBox::indicator:checked,
QRadioButton::indicator:checked {{
    background: {tokens.accent};
}}
QScrollBar:vertical {{
    background: {tokens.surface_muted};
    width: 14px;
    margin: 0;
    border-radius: 7px;
}}
QScrollBar:horizontal {{
    background: {tokens.surface_muted};
    height: 14px;
    margin: 0;
    border-radius: 7px;
}}
QScrollBar::handle:vertical {{
    background: {tokens.text_muted};
    border-radius: 5px;
    min-height: 36px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {tokens.text_muted};
    border-radius: 5px;
    min-width: 36px;
    margin: 2px;
}}
QScrollBar::handle:hover:vertical,
QScrollBar::handle:hover:horizontal,
QScrollBar::handle:pressed:vertical,
QScrollBar::handle:pressed:horizontal {{
    background: {tokens.accent};
}}
QScrollBar::add-line,
QScrollBar::sub-line {{
    width: 0;
    height: 0;
}}
QScrollBar::add-page,
QScrollBar::sub-page {{
    background: transparent;
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
QPushButton[v3Button="true"][variant="primary"]:pressed {{
    color: white;
    background: {tokens.accent_hover};
    border-color: {tokens.accent_hover};
}}
QPushButton[v3Button="true"][variant="secondary"]:pressed,
QPushButton[v3Button="true"][variant="ghost"]:pressed {{
    color: {tokens.text};
    background: {tokens.accent_soft};
    border-color: {tokens.accent};
}}
QPushButton[v3Button="true"]:disabled {{
    color: #aebccb;
    background: {tokens.disabled_soft};
    border: 1px solid {tokens.border};
}}
QPushButton[v3SourceChoice="true"] {{
    min-height: 68px;
    padding: {tokens.space_3}px {tokens.space_4}px;
    color: {tokens.text};
    background: {tokens.surface};
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_card}px;
    text-align: left;
    font-weight: {tokens.font_weight_medium};
}}
QPushButton[v3SourceChoice="true"]:hover {{
    background: {tokens.surface_muted};
    border-color: {tokens.text_muted};
}}
QPushButton[v3SourceChoice="true"]:checked {{
    color: {tokens.text};
    background: {tokens.accent_soft};
    border: 2px solid {tokens.accent};
}}
QPushButton[v3SourceChoice="true"]:focus {{
    border: {tokens.focus_width}px solid {tokens.focus};
}}
QPushButton[v3ChromaMaterial="true"] {{
    min-height: 32px;
    padding: 0 {tokens.space_3}px;
    color: {tokens.text};
    background: {tokens.surface_muted};
    border: 1px solid {tokens.border};
    border-radius: {tokens.radius_control}px;
}}
QPushButton[v3ChromaMaterial="true"]:hover {{
    border-color: {tokens.text_muted};
}}
QPushButton[v3ChromaMaterial="true"]:checked {{
    color: white;
    background: {tokens.accent_soft};
    border: 1px solid {tokens.accent};
}}
QPushButton[v3ChromaMaterial="true"]:checked:hover {{
    background: {tokens.accent_hover};
    border-color: {tokens.accent_hover};
}}
QPushButton[v3ChromaMaterial="true"]:disabled {{
    color: {tokens.disabled};
    background: {tokens.disabled_soft};
    border: 1px solid {tokens.border};
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
    app = QApplication.instance()
    if app is not None:
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(tokens.canvas))
        palette.setColor(QPalette.ColorRole.Base, QColor(tokens.surface))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(tokens.surface_muted))
        palette.setColor(QPalette.ColorRole.Text, QColor(tokens.text))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(tokens.text))
        palette.setColor(QPalette.ColorRole.Button, QColor(tokens.surface))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(tokens.text))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(tokens.accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(tokens.disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(tokens.disabled))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(tokens.disabled))
        app.setPalette(palette)
    root.setProperty("v3Root", True)
    root.setStyleSheet(build_v3_stylesheet(tokens))


def _refresh_style(widget: QWidget) -> None:
    style = widget.style()
    if style is not None:
        style.unpolish(widget)
        style.polish(widget)
    widget.update()


HEADER_ICON_KINDS = ("home", "key", "pulse", "folder", "update", "plus", "copy", "trash")


def header_icon(kind: str, color: str = "#2dd4bf", size: int = 24) -> QIcon:
    """Simple line icon for the shared Studio header (no image files needed)."""
    if kind not in HEADER_ICON_KINDS:
        raise ValueError(f"unknown header icon: {kind}")
    scale = 4
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(scale * size / 24, scale * size / 24)
    pen = QPen(QColor(color), 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "home":
        painter.drawPolyline(QPolygonF([QPointF(3, 11.5), QPointF(12, 4), QPointF(21, 11.5)]))
        painter.drawPolyline(QPolygonF([
            QPointF(5.5, 10), QPointF(5.5, 20), QPointF(18.5, 20), QPointF(18.5, 10)]))
        painter.drawPolyline(QPolygonF([QPointF(10, 20), QPointF(10, 14), QPointF(14, 14), QPointF(14, 20)]))
    elif kind == "key":
        painter.drawEllipse(QRectF(3.5, 7.5, 8, 8))
        painter.drawLine(QPointF(11.5, 11.5), QPointF(21, 11.5))
        painter.drawLine(QPointF(17, 11.5), QPointF(17, 15))
        painter.drawLine(QPointF(20, 11.5), QPointF(20, 14))
    elif kind == "pulse":
        painter.drawPolyline(QPolygonF([
            QPointF(2.5, 12), QPointF(7, 12), QPointF(9.5, 5.5), QPointF(13, 18.5),
            QPointF(15.5, 12), QPointF(21.5, 12)]))
    elif kind == "plus":
        painter.drawLine(QPointF(12, 5), QPointF(12, 19))
        painter.drawLine(QPointF(5, 12), QPointF(19, 12))
    elif kind == "copy":
        painter.drawRoundedRect(QRectF(8.5, 8.5, 11, 11), 2, 2)
        painter.drawPolyline(QPolygonF([QPointF(15.5, 5.5), QPointF(5.5, 5.5), QPointF(5.5, 15.5)]))
    elif kind == "trash":
        painter.drawLine(QPointF(4.5, 7), QPointF(19.5, 7))
        painter.drawPolyline(QPolygonF([QPointF(9.5, 7), QPointF(9.5, 4.5), QPointF(14.5, 4.5), QPointF(14.5, 7)]))
        painter.drawPolyline(QPolygonF([QPointF(6.5, 7), QPointF(7.5, 19.5), QPointF(16.5, 19.5), QPointF(17.5, 7)]))
        painter.drawLine(QPointF(10.5, 10.5), QPointF(10.5, 16.5))
        painter.drawLine(QPointF(13.5, 10.5), QPointF(13.5, 16.5))
    elif kind == "update":  # circular arrow: check for updates
        painter.drawArc(QRectF(4.5, 4.5, 15, 15), 40 * 16, 280 * 16)
        painter.drawPolyline(QPolygonF([QPointF(15.5, 2.8), QPointF(18.6, 6.2), QPointF(14.2, 7.6)]))
    else:  # folder with an arrow: continue saved work
        path = QPainterPath()
        path.moveTo(3, 18.5)
        path.lineTo(3, 6.5)
        path.lineTo(9, 6.5)
        path.lineTo(11, 9)
        path.lineTo(19, 9)
        path.lineTo(19, 11)
        painter.drawPath(path)
        painter.drawPolyline(QPolygonF([QPointF(3, 18.5), QPointF(6, 11), QPointF(21.5, 11), QPointF(18.5, 18.5), QPointF(3, 18.5)]))
        painter.drawLine(QPointF(11, 14.8), QPointF(16.5, 14.8))
        painter.drawPolyline(QPolygonF([QPointF(14.6, 12.9), QPointF(16.6, 14.8), QPointF(14.6, 16.7)]))
    painter.end()
    return QIcon(pixmap)


def make_icon_button(
    button: "QPushButton", kind: str, label: str, *, size: tuple[int, int] = (40, 36), caption: str = "",
) -> None:
    """Turn a text button into an icon button; the label stays as tooltip and accessible name.

    With ``caption`` a short word is drawn under the icon (V3Button.paintEvent) so the icon is not a riddle."""
    button.setText("")
    button.setIcon(header_icon(kind))
    button.setIconSize(QSize(22, 22) if size[0] <= 40 else QSize(26, 26))
    button.setFixedSize(*size)
    button.setToolTip(label)
    button.setAccessibleName(label)
    button.setProperty("iconLabel", label)
    if caption:
        button.setProperty("iconCaption", caption)
        button.setFixedSize(max(size[0], 72), max(size[1], 48))
        button.setStyleSheet(button.styleSheet() + "QPushButton {padding: 0 0 13px 0;}")


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

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        caption = self.property("iconCaption")
        if not caption:
            return
        painter = QPainter(self)
        font = QFont(self.font())
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(DEFAULT_TOKENS.text_muted))
        painter.drawText(
            QRect(0, self.height() - 16, self.width(), 13),
            int(Qt.AlignmentFlag.AlignHCenter) | int(Qt.AlignmentFlag.AlignVCenter),
            str(caption),
        )
        painter.end()

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
        illustration_path: str | Path | None = None,
        illustration_image: QPixmap | None = None,
        compact: bool = False,
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

        self.illustration = None
        if illustration_path or illustration_image is not None:
            resolved_path = Path(illustration_path) if illustration_path else None
            if illustration_image is not None:
                illustration = _AspectRatioPixmapLabel(illustration_image, self)
            elif resolved_path.suffix.lower() == ".svg":
                illustration = QSvgWidget(str(resolved_path), self)
                illustration.renderer().setAspectRatioMode(
                    Qt.AspectRatioMode.KeepAspectRatio
                )
            else:
                illustration = _AspectRatioPixmapLabel(
                    QPixmap(str(resolved_path)),
                    self,
                )
            illustration.setObjectName("modeIllustration")
            illustration.setAccessibleName(f"Иллюстрация режима: {title}")
            illustration.setMinimumHeight(112)
            illustration.setMaximumHeight(156)
            illustration.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            illustration.setStyleSheet("background: transparent; border: none;")
            self.illustration = illustration
            layout.addWidget(illustration)

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

        if compact:
            layout.setContentsMargins(12, 10, 12, 10)
            layout.setSpacing(6)
            self.setFixedHeight(248)
            if self.illustration is not None:
                self.illustration.setFixedHeight(112)
            self.description_label.setWordWrap(False)
            self.title_label.setWordWrap(False)
            self.title_label.setToolTip(title)
            self.description_label.setToolTip(description)
            self.result_label.hide()
            self.start_button.setText("Открыть")

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
