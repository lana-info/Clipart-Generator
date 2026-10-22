"""Real screens of the brush slider, Alt+wheel and Shift line for comparison with the mockups.

Real ClipartTransparencyEditorPage, dummy picture, real wheel and click events; the held
Shift key for the guide is simulated. Run: python docs/ui/3.2/transparency-brush-slider/capture_actual.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).parent
OUT = HERE / "actual"
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout

from render_mockups import W, H, app, cursor_at, flower  # noqa: E402  (shares the QApplication)
from v3_components import apply_v3_theme  # noqa: E402
from v3_clipart_flow import ClipartTransparencyEditorPage  # noqa: E402


def window(path):
    dialog = QDialog()
    dialog.setWindowTitle("Проверка PNG")
    apply_v3_theme(dialog)
    editor = ClipartTransparencyEditorPage()
    QVBoxLayout(dialog).addWidget(editor)
    editor.set_files([path], selected_index=0)
    dialog.resize(W, H)
    dialog.show()
    for _ in range(4):
        app.processEvents()
    return dialog, editor


def save(dialog, name):
    for _ in range(4):
        app.processEvents()
    dialog.grab().save(str(OUT / name))
    dialog.hide()


def view_point(canvas, x, y):
    return canvas.mapFromScene(canvas._item.mapToScene(QPointF(x, y)))


def main():
    OUT.mkdir(exist_ok=True)
    path = Path(tempfile.mkdtemp()) / "01_flower_ready.png"
    flower(path)

    dialog, editor = window(path)
    cursor_at(editor.canvas, 600, 330)
    save(dialog, "01-slider-hard-16.png")

    dialog, editor = window(path)
    canvas = editor.canvas
    editor._hardness_changed(0)
    editor._set_diameter(32)   # two wheel notches: 32 -> 36 -> 40
    centre = QPointF(canvas.viewport().rect().center())
    canvas.wheelEvent(QWheelEvent(centre, canvas.viewport().mapToGlobal(centre), QPoint(), QPoint(0, 240),
                                  Qt.MouseButton.NoButton, Qt.KeyboardModifier.AltModifier,
                                  Qt.ScrollPhase.NoScrollPhase, False))
    cursor_at(canvas, 600, 330)
    save(dialog, "02-alt-wheel-soft-40.png")

    a, b = (230, 180), (610, 560)
    dialog, editor = window(path)
    canvas = editor.canvas
    editor._set_diameter(12)
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
                     view_point(canvas, *a))
    original = QApplication.keyboardModifiers
    QApplication.keyboardModifiers = staticmethod(lambda: Qt.KeyboardModifier.ShiftModifier)
    cursor_at(canvas, *b)
    save(dialog, "04-shift-line-guide.png")
    QApplication.keyboardModifiers = original

    dialog.show()
    QTest.mouseClick(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier,
                     view_point(canvas, *b))
    cursor_at(canvas, *b)
    save(dialog, "05-shift-line-result.png")


def soft_strokes():
    """Real soft-brush strokes (production background_mask) at several sizes, 1:1 and x2."""
    from PIL import Image, ImageDraw
    from background_mask import diameter_radius, paint_mask_path
    sizes = (4, 8, 16, 30, 48, 64)
    mask = Image.new("L", (560, 120 * len(sizes)), 255)
    for row, size in enumerate(sizes):
        y = 60 + row * 120
        paint_mask_path(mask, [(200, y), (500, y)], radius=diameter_radius(size), action="remove", hardness=0)
    pink = Image.new("RGBA", mask.size, (236, 150, 172, 255))
    pink.putalpha(mask)
    board = Image.new("RGBA", mask.size, (255, 255, 255, 255))
    d = ImageDraw.Draw(board)
    for y in range(0, board.height, 8):
        for x in range(0, board.width, 8):
            if (x // 8 + y // 8) % 2:
                d.rectangle((x, y, x + 7, y + 7), fill=(214, 220, 228, 255))
    board.alpha_composite(pink)
    d = ImageDraw.Draw(board)
    for row, size in enumerate(sizes):
        d.rectangle((0, row * 120, 120, row * 120 + 119), fill=(11, 22, 38, 255))
        d.text((14, row * 120 + 52), f"{size} px", fill=(232, 238, 246, 255))
    board.resize((board.width * 2, board.height * 2), Image.Resampling.NEAREST).save(OUT / "03-soft-edge-real-x2.png")


if __name__ == "__main__":
    main()
    soft_strokes()
