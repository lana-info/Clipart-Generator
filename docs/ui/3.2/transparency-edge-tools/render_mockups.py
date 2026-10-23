"""Mockups for PRD items 2-4 (brush cursor, tool row, edge buttons) on the real window.

The real ClipartTransparencyEditorPage is changed only inside this script (hidden rows, inserted proposed
rows, a proposed brush ring). Nothing here is production code. Output: <out>/current-*.png and
<out>/proposed-*.png, then capture.py compose with the mockup labels.
  python render_mockups.py <out dir>
"""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import QPointF, QSize, Qt  # noqa: E402
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen  # noqa: E402
from PyQt6.QtWidgets import (QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel,  # noqa: E402
                             QPushButton, QToolButton, QVBoxLayout, QWidget)

app = QApplication.instance() or QApplication([])
from background_mask import soft_feather_width  # noqa: E402
from capture import BACKGROUNDS, H, W, flower  # noqa: E402
from studio_contour import BezierNode, BezierPath  # noqa: E402
from v3_components import apply_v3_theme  # noqa: E402
from v3_clipart_flow import ClipartTransparencyEditorPage  # noqa: E402

LASSO = [(120, 60), (420, 30), (700, 120), (720, 300), (560, 260), (400, 200), (230, 240), (90, 250), (120, 60)]


def window(picture, background="Шахматный"):
    dialog = QDialog()
    dialog.setWindowTitle("Проверка PNG")
    apply_v3_theme(dialog)
    editor = ClipartTransparencyEditorPage()
    QVBoxLayout(dialog).addWidget(editor)
    editor.set_files([picture], selected_index=0)
    dialog.resize(W, H)
    dialog.show()
    editor.background_buttons[background].click()
    for _ in range(4):
        app.processEvents()
    return dialog, editor


def save(dialog, out, name):
    for _ in range(6):
        app.processEvents()
    dialog.grab().save(str(out / f"{name}.png"))
    dialog.hide()


def hover(canvas, x, y):
    canvas._brush_scene_point = canvas._item.mapToScene(QPointF(x, y))
    canvas.viewport().update()


def two_ring_cursor(canvas):
    """Proposed ring: dark 3 px under light 1.5 px at the real diameter; soft edge as a dotted outer ring."""
    original = canvas.drawForeground

    def foreground(painter, rect):
        point = canvas._brush_scene_point
        canvas._brush_scene_point = None          # hide the current white ring
        original(painter, rect)
        canvas._brush_scene_point = point
        if point is None:
            return
        radius = canvas.brush_radius + 0.5
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for color, width in ((QColor(0, 0, 0, 210), 3.0), (QColor("#ffffff"), 1.5)):
            pen = QPen(color, width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawEllipse(point, radius, radius)
        if canvas.brush_hardness < 100:
            outer = radius + soft_feather_width(canvas.brush_radius, canvas.brush_hardness)
            for color, width in ((QColor(0, 0, 0, 170), 2.5), (QColor("#ffffff"), 1.0)):
                pen = QPen(color, width, Qt.PenStyle.DotLine)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawEllipse(point, outer, outer)

    canvas.drawForeground = foreground


def layout_of(editor):
    return editor.sharpen_edge_button.parentWidget().layout()


def index_of(layout, widget=None, sub=None):
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if (widget is not None and item.widget() is widget) or (sub is not None and item.layout() is sub):
            return i
    raise LookupError


def label_index(layout, text):
    for i in range(layout.count()):
        w = layout.itemAt(i).widget()
        if isinstance(w, QLabel) and w.text() == text:
            return i
    raise LookupError(text)


def text_button(text, tip, checked=None):
    button = QPushButton(text)
    button.setToolTip(tip)
    button.setStyleSheet("font-size:11px;padding:5px 2px;")
    if checked is not None:
        button.setCheckable(True)
        button.setChecked(checked)
    return button


def tool_button(icon, text, checked):
    button = QToolButton()
    button.setIcon(icon)
    button.setIconSize(QSize(24, 24))
    button.setText(text)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setMinimumHeight(52)
    button.setSizePolicy(button.sizePolicy().horizontalPolicy().Expanding, button.sizePolicy().verticalPolicy())
    return button


def proposed_panel(editor, tool, scope):
    """Item 3 tool row with Lasso, pen row without the wide lasso, item 4 edge block."""
    layout = layout_of(editor)
    # Item 4: the edge block (replaces 'Чётче'; 'Сгладить' stays).
    for i in range(layout.count()):
        sub = layout.itemAt(i).layout()
        if sub is not None and sub.indexOf(editor.sharpen_edge_button) >= 0:
            edge_index = i
    for button in (editor.sharpen_edge_button, editor.smooth_edge_button):
        button.hide()
    edge = QGridLayout()
    edge.setSpacing(4)
    for n, (text, tip) in enumerate((("Жёстче", "Края жёстче: переход уже, шаг за нажатие"),
                                     ("Мягче", "Края мягче: переход шире, шаг за нажатие"),
                                     ("Сгладить", "Сгладить углы края (как сейчас)"),
                                     ("Сузить", "Сузить край на 1 px"),
                                     ("Расширить", "Расширить край на 1 px"))):
        edge.addWidget(text_button(text, tip), n // 3, n % 3)
    layout.insertLayout(edge_index + 1, edge)
    editor.edge_scope_label.setText(scope)
    # Item 3: three tools in one row.
    tool_index = label_index(layout, "Инструмент") + 1
    for button in editor.tool_buttons.values():
        button.hide()
    row = QHBoxLayout()
    row.setSpacing(4)
    for key, text, icon in (("brush", "Кисть", editor._tool_icon("brush")),
                            ("pen", "Перо", editor._tool_icon("pen")),
                            ("lasso", "Лассо", editor._thin_icon("lasso"))):
        row.addWidget(tool_button(icon, text, key == tool))
    layout.insertLayout(tool_index + 1, row)
    # Pen: the lasso leaves the 'Контур' block, the two contour modes stay in one even row.
    editor.lasso_button.hide()
    if tool == "lasso":
        editor.brush_controls.hide()
        editor.pen_controls.hide()
        panel = QWidget()
        box = QVBoxLayout(panel)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(editor._small_label("Лассо"))
        hint = QLabel("Обведите область на картинке.\nShift — добавить к области.\nEsc — снять выделение.")
        hint.setStyleSheet("color:#7f90a6;font-size:9pt;")
        box.addWidget(hint)
        status = QLabel("Область выделена · точек контура в ней: 5")
        status.setWordWrap(True)
        status.setStyleSheet("color:#93a4b8;font-size:12px;")
        box.addWidget(status)
        box.addWidget(text_button("Снять выделение", "Esc"))
        layout.insertWidget(index_of(layout, editor.pen_controls) + 1, panel)


def area_overlay(canvas):
    original = canvas.drawForeground

    def foreground(painter, rect):
        original(painter, rect)
        path = QPainterPath(canvas._item.mapToScene(QPointF(*LASSO[0])))
        for p in LASSO[1:]:
            path.lineTo(canvas._item.mapToScene(QPointF(*p)))
        path.closeSubpath()
        for color, style in ((QColor(0, 0, 0, 200), Qt.PenStyle.SolidLine), (QColor("#ff38bb"), Qt.PenStyle.DashLine)):
            pen = QPen(color, 2.5 if style == Qt.PenStyle.SolidLine else 1.5, style)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(QColor(255, 56, 187, 26) if style == Qt.PenStyle.DashLine else Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

    canvas.drawForeground = foreground


def flower_contour(editor):
    nodes = tuple(BezierNode((400 + 330 * math.cos(k * math.pi / 8), 400 + 330 * math.sin(k * math.pi / 8)))
                  for k in range(16))
    path = BezierPath(nodes, 255, (800, 800))
    editor.canvas.contour.paths = [path]
    editor.canvas.contour.original = [path]


def main(out):
    out.mkdir(parents=True, exist_ok=True)
    picture = Path(tempfile.mkdtemp()) / "01_flower_ready.png"
    flower(picture)
    # Item 2: the brush ring on each background, hard 16 px and soft 40 px, zoom 200 % at the petal edge.
    for key, background in BACKGROUNDS:
        for hard, size in ((True, 16), (False, 40)):
            for state in ("current", "proposed"):
                dialog, editor = window(picture, background)
                editor._set_zoom(200)
                editor._set_diameter(size)
                editor._hardness_changed(100 if hard else 0)
                canvas = editor.canvas
                canvas.centerOn(canvas._item.mapToScene(QPointF(640, 560)))
                if state == "proposed":
                    two_ring_cursor(canvas)
                hover(canvas, 664, 590)
                save(dialog, out, f"{state}-2-cursor-{'hard16' if hard else 'soft40'}-{key}")
    # Items 3 and 4: the right panel for each tool.
    for tool in ("brush", "pen", "lasso"):
        for state in ("current", "proposed"):
            dialog, editor = window(picture)
            if tool != "brush":
                editor._set_tool("pen")
                flower_contour(editor)
                editor._refresh_history_buttons()
            if state == "proposed":
                proposed_panel(editor, tool, "Область лассо" if tool == "lasso" else "Всё изображение")
                if tool == "lasso":
                    area_overlay(editor.canvas)
                    editor.canvas.contour.select([(0, k) for k in (11, 12, 13, 14, 15)])
            elif tool == "lasso":
                editor.lasso_button.click()
            save(dialog, out, f"{state}-34-panel-{tool}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
