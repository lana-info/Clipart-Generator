"""Offline approval mockups: brush size slider, soft brush edge, Alt+wheel, Shift line.

The window is the real ClipartTransparencyEditorPage on a dummy PNG; the proposed
controls are added only inside this script. The soft-brush table is drawn with the
proposed formula (no production code changed). No provider requests, no user files.
Run: python docs/ui/3.2/transparency-brush-slider/render_mockups.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(__file__).parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageChops, ImageDraw
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QGridLayout, QHBoxLayout, QLabel, QSlider,
    QVBoxLayout, QWidget,
)

app = QApplication([])
from v3_components import apply_v3_theme  # noqa: E402
from v3_clipart_flow import ClipartTransparencyEditorPage  # noqa: E402

W, H = 1120, 780
SIZES = (1, 2, 3, 4, 6, 8, 12, 16, 24, 32, 48, 64)


def flower(path):
    im = Image.new("RGBA", (800, 800), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    for k in range(8):
        a = k * math.pi / 4
        x, y = 400 + 190 * math.cos(a), 400 + 190 * math.sin(a)
        d.ellipse((x - 120, y - 120, x + 120, y + 120), fill=(236, 150, 172, 255))
    d.ellipse((290, 290, 510, 510), fill=(250, 206, 96, 255))
    im.save(path)


# --- proposed size scale --------------------------------------------------------

def slider_to_size(pos):
    """Slider 0..100 -> 1..64 px; the first half of the track covers 1..16 px."""
    return max(1, min(64, round(1 + 63 * (pos / 100) ** 2)))


def size_to_slider(size):
    return round(100 * math.sqrt((size - 1) / 63))


def small(text, color="#a6b5c8", size=10, bold=False):
    label = QLabel(text)
    font = QFont(); font.setPointSize(size); font.setBold(bold)
    label.setFont(font)
    label.setStyleSheet(f"color: {color};")
    label.setWordWrap(True)
    return label


def size_row(size):
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(size_to_slider(size))
    slider.setToolTip("Диаметр кисти 1–64 px. Alt + колесо мыши — изменить")
    value = small(f"{size} px", "#e8eef6", 11, True)
    value.setMinimumWidth(48)
    value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    layout.addWidget(slider, 1)
    layout.addWidget(value)
    return row


def editor_window(path, size, *, soft=False):
    dialog = QDialog()
    dialog.setWindowTitle("Проверка PNG")
    apply_v3_theme(dialog)
    layout = QVBoxLayout(dialog)
    editor = ClipartTransparencyEditorPage()
    layout.addWidget(editor)
    editor.set_files([path], selected_index=0)
    # Replace the diameter buttons with the proposed slider.
    brush = editor.brush_controls.layout()
    for button in editor.diameter_buttons.values():
        button.hide()
    for index in range(brush.count()):
        widget = brush.itemAt(index).widget()
        if isinstance(widget, QLabel) and widget.text().startswith("Диаметр"):
            widget.setText("Диаметр кисти")
            brush.insertWidget(index + 1, size_row(size))
            break
    if soft:
        editor._hardness_changed(0)
    brush.addWidget(small("Alt + колесо — размер\nShift + щелчок — прямая линия", "#7f90a6", 9))
    editor.canvas.brush_radius = size / 2
    return dialog, editor


def save(widget, name):
    widget.resize(W, H)
    widget.show()
    for _ in range(4):
        app.processEvents()
    widget.grab().save(str(OUT / name))
    widget.hide()


def with_overlay(canvas, draw):
    original = canvas.drawForeground

    def foreground(painter, rect):
        original(painter, rect)
        painter.save()
        draw(painter)
        painter.restore()
    canvas.drawForeground = foreground


def cursor_at(canvas, x, y):
    canvas._brush_scene_point = QPointF(x, y)
    canvas.viewport().update()


# --- proposed soft brush --------------------------------------------------------

def stamp(size, fraction, soft):
    """Coverage of one dab: solid disc of ``size`` px plus an outward fade."""
    feather = max(1.0, size * fraction) if soft and size >= 4 else 0.0
    reach = size / 2 + feather
    side = math.ceil(reach * 2) + 2
    c = side / 2
    data = []
    for y in range(side):
        for x in range(side):
            best = 0.0
            for sy in range(4):
                for sx in range(4):
                    dist = math.hypot(x + (sx + .5) / 4 - c, y + (sy + .5) / 4 - c)
                    if dist <= size / 2 or (size == 1 and abs(x + .5 - c) < 1 and abs(y + .5 - c) < 1):
                        value = 1.0
                    elif feather:
                        t = min(1.0, (dist - size / 2) / feather)
                        value = 1 - t * t * (3 - 2 * t)
                    else:
                        value = 0.0
                    best += value / 16
            data.append(round(255 * best))
    im = Image.new("L", (side, side))
    im.putdata(data)
    return im


def stroke_tile(size, fraction, soft, zoom):
    """One dab erased from a pink area, magnified to fit the tile."""
    dab = stamp(size, fraction, soft)
    area = Image.new("L", (dab.width + 6, dab.height + 6), 0)
    area.paste(dab, (3, 3))
    alpha = area.point(lambda v: 255 - v).resize((area.width * zoom, area.height * zoom), Image.Resampling.NEAREST)
    pink = Image.new("RGBA", alpha.size, (236, 150, 172, 255))
    pink.putalpha(alpha)
    board = Image.new("RGBA", alpha.size, (255, 255, 255, 255))
    d = ImageDraw.Draw(board)
    cell = 6
    for y in range(0, board.height, cell):
        for x in range(0, board.width, cell):
            if (x // cell + y // cell) % 2:
                d.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(214, 220, 228, 255))
    board.alpha_composite(pink)
    return board, zoom


def pil_pixmap(image):
    data = image.convert("RGBA").tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimage.copy())


def soft_table():
    page = QWidget(); apply_v3_theme(page)
    page.setStyleSheet("background: #0b1626;")
    outer = QVBoxLayout(page)
    outer.setContentsMargins(24, 18, 24, 18)
    outer.addWidget(small("Мягкая кисть: один отпечаток ластика «Убрать» по розовому (в столбце одинаковое увеличение)", "#e8eef6", 14, True))
    outer.addWidget(small(
        "До 3 px включительно кисть всегда жёсткая. С 4 px — плотная часть ровно выбранного размера "
        "и мягкий край наружу. Ниже три варианта ширины края; сейчас в программе 40 % диаметра.",
        "#a6b5c8", 10))
    grid = QGridLayout()
    grid.setHorizontalSpacing(6); grid.setVerticalSpacing(4)
    shown = (1, 3, 4, 8, 16, 32, 64)
    rows = (("Жёсткая", 0, False), ("Мягкая, край 1/4\n(предлагаю)", 0.25, True),
            ("Мягкая, край 1/3", 1 / 3, True), ("Сейчас: край 40 %", 0.4, True))
    for col, size in enumerate(shown, start=1):
        grid.addWidget(small(f"{size} px", "#e8eef6", 11, True), 0, col, Qt.AlignmentFlag.AlignCenter)
    for row, (title, fraction, soft) in enumerate(rows, start=1):
        grid.addWidget(small(title, "#e8eef6" if row != 2 else "#24cabb", 10, True), row * 2 - 1, 0)
        for col, size in enumerate(shown, start=1):
            widest = stamp(size, 0.4, True).width + 6
            zoom = max(1, min(12, 118 // widest))
            tile, zoom = stroke_tile(size, fraction, soft, zoom)
            label = QLabel()
            label.setPixmap(pil_pixmap(tile))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedSize(132, 124)
            grid.addWidget(label, row * 2 - 1, col)
            feather = max(1.0, size * fraction) if soft and size >= 4 else 0
            text = f"×{zoom}" + (f" · край {feather:.0f} px" if feather else "")
            grid.addWidget(small(text, "#7f90a6", 8), row * 2, col, Qt.AlignmentFlag.AlignCenter)
    outer.addLayout(grid)
    outer.addStretch(1)
    return page


def main():
    folder = Path(tempfile.mkdtemp())
    path = folder / "01_flower_ready.png"
    flower(path)

    # Current window for comparison: fixed diameter buttons.
    current = QDialog(); current.setWindowTitle("Проверка PNG"); apply_v3_theme(current)
    page = ClipartTransparencyEditorPage()
    QVBoxLayout(current).addWidget(page)
    page.set_files([path], selected_index=0)
    page.canvas.brush_radius = 8
    cursor_at(page.canvas, 600, 330)
    save(current, "00-current-buttons-1120x780.png")

    dialog, editor = editor_window(path, 16)
    canvas = editor.canvas
    cursor_at(canvas, 600, 330)
    save(dialog, "01-slider-hard-16-1120x780.png")

    dialog, editor = editor_window(path, 40, soft=True)
    canvas = editor.canvas
    cursor_at(canvas, 600, 330)

    def alt_hint(painter):
        painter.resetTransform()
        painter.setPen(QPen(QColor("#dce7f4")))
        painter.setBrush(QColor(22, 40, 63, 230))
        painter.drawRoundedRect(14, 14, 250, 34, 8, 8)
        painter.drawText(26, 36, "Alt + колесо: 40 px")
    with_overlay(canvas, alt_hint)
    save(dialog, "02-alt-wheel-soft-40-1120x780.png")

    save(soft_table(), "03-soft-brush-edge-1120x780.png")

    # Shift line: first click done, Shift held -> dashed guide to the cursor.
    dialog, editor = editor_window(path, 12)
    canvas = editor.canvas
    a, b = (230, 180), (610, 560)

    def guide(painter):
        pen = QPen(QColor("#ffffff"), 1.5, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QPointF(*a), QPointF(*b))
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(*a), 3, 3)
    with_overlay(canvas, guide)
    cursor_at(canvas, *b)
    save(dialog, "04-shift-line-guide-1120x780.png")

    # Result: real remove stroke along the straight line.
    dialog, editor = editor_window(path, 12)
    canvas = editor.canvas
    document = canvas.document
    steps = 80
    points = [(a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps) for i in range(steps + 1)]
    document.begin_stroke()
    document.extend_stroke(tuple(points), radius=6, action="remove", hardness=100)
    document.end_stroke()
    canvas.refresh_image()
    cursor_at(canvas, *b)
    save(dialog, "05-shift-line-result-1120x780.png")


if __name__ == "__main__":
    main()
