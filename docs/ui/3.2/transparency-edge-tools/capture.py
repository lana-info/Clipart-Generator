"""Before/after screens of the transparency window for docs/PRD_TRANSPARENCY_EDGE_TOOLS.ru.md.

Real ClipartTransparencyEditorPage, a flower with a 6 px semi-transparent edge, real mouse and key events.
A widget grab has no system cursor, so the cursor shape the window set is drawn on top (cross or arrow).
Run once per code state, then compose:
  python capture.py shoot <repo root> <before|after> <item> <out dir>
  python capture.py compose <out dir> <item> <target dir>
  python capture.py mockups <out dir> <item> <target dir>   (after render_mockups.py)
"""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
W, H = 1120, 780
BACKGROUNDS = (("white", "Белый"), ("dark", "Чёрный"), ("checker", "Шахматный"))


def flower(path):
    from PIL import Image, ImageDraw, ImageFilter
    alpha = Image.new("L", (800, 800), 0)
    d = ImageDraw.Draw(alpha)
    for k in range(8):
        a = k * math.pi / 4
        x, y = 400 + 190 * math.cos(a), 400 + 190 * math.sin(a)
        d.ellipse((x - 120, y - 120, x + 120, y + 120), fill=255)
    d.ellipse((260, 260, 540, 540), fill=255)
    alpha = alpha.filter(ImageFilter.GaussianBlur(2.2))   # about 6 px soft edge, like a real clipart
    im = Image.new("RGBA", alpha.size, (236, 150, 172, 255))
    ImageDraw.Draw(im).ellipse((300, 300, 500, 500), fill=(248, 206, 92, 255))
    im.putalpha(alpha)
    im.save(path)


def shoot(root, label, item, out):
    sys.path.insert(0, str(root))
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QColor, QPainter, QPen, QPolygonF
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout
    app = QApplication.instance() or QApplication([])
    from studio_contour import BezierNode, BezierPath
    from v3_components import apply_v3_theme
    from v3_clipart_flow import ClipartTransparencyEditorPage

    out.mkdir(parents=True, exist_ok=True)
    picture = Path(tempfile.mkdtemp()) / "01_flower_ready.png"
    flower(picture)

    def window(background):
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

    def view_point(canvas, x, y):
        return canvas.mapFromScene(canvas._item.mapToScene(QPointF(x, y)))

    def hover(canvas, x, y):
        QTest.mouseMove(canvas.viewport(), view_point(canvas, x, y))
        canvas._brush_scene_point = canvas._item.mapToScene(QPointF(x, y))
        canvas.viewport().update()
        return view_point(canvas, x, y)

    def save(dialog, editor, name, cursor_at=None):
        for _ in range(4):
            app.processEvents()
        image = dialog.grab().toImage()
        if cursor_at is not None:
            canvas = editor.canvas
            p = QPointF(canvas.viewport().mapTo(dialog, cursor_at))
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            if canvas.cursor().shape() == Qt.CursorShape.CrossCursor:
                for color, width in (("#000000", 3), ("#ffffff", 1)):
                    painter.setPen(QPen(QColor(color), width))
                    painter.drawLine(p + QPointF(-11, 0), p + QPointF(11, 0))
                    painter.drawLine(p + QPointF(0, -11), p + QPointF(0, 11))
            else:
                arrow = QPolygonF([p + QPointF(*xy) for xy in ((0, 0), (0, 17), (4, 13), (7, 20), (10, 19), (7, 12), (12, 12))])
                painter.setPen(QPen(QColor("#000000"), 1))
                painter.setBrush(QColor("#ffffff"))
                painter.drawPolygon(arrow)
            painter.end()
        image.save(str(out / f"{label}-{name}.png"))
        dialog.hide()

    def flower_contour(editor):
        nodes = tuple(BezierNode((400 + 330 * math.cos(k * math.pi / 8), 400 + 330 * math.sin(k * math.pi / 8)))
                      for k in range(16))
        path = BezierPath(nodes, 255, (800, 800))
        editor._set_tool("pen")
        editor.canvas.contour.paths = [path]
        editor.canvas.contour.original = [path]
        editor._refresh_history_buttons()

    def lasso(canvas, points):
        mapped = [view_point(canvas, *p) for p in points]
        QTest.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mapped[0])
        for point in mapped[1:-1]:
            QTest.mouseMove(canvas.viewport(), point, 2)
        QTest.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, mapped[-1])

    top = [(40, 20), (760, 20), (760, 200), (40, 200), (40, 20)]
    for key, background in BACKGROUNDS:
        if item == 1:
            # Pen -> lasso -> brush: the cursor that is left over the picture.
            dialog, editor = window(background)
            flower_contour(editor)
            editor.lasso_button.click()
            lasso(editor.canvas, top)
            editor._set_tool("brush")
            save(dialog, editor, f"1a-brush-after-lasso-{key}", hover(editor.canvas, 620, 600))
            # Lasso selection in focus mode, then one Esc.
            dialog, editor = window(background)
            flower_contour(editor)
            editor.lasso_button.click()
            lasso(editor.canvas, top)
            editor.toggle_focus_mode()
            QTest.keyClick(editor.canvas, Qt.Key.Key_Escape)
            save(dialog, editor, f"1b-esc-with-selection-{key}")
        if item == 3:
            # Right panel per tool; Lasso: an area drawn over the top of the flower with the contour on.
            for tool in ("brush", "pen", "lasso"):
                dialog, editor = window(background)
                if tool != "brush":
                    flower_contour(editor)
                if tool == "lasso":
                    if "lasso" in editor.tool_buttons:
                        editor._set_tool("lasso")
                    else:
                        editor.lasso_button.click()       # before: lasso was a pen mode
                    lasso(editor.canvas, [(120, 60), (420, 30), (700, 120), (720, 300), (560, 260),
                                          (400, 200), (230, 240), (90, 250), (120, 60)])
                save(dialog, editor, f"3-panel-{tool}-{key}")
        if item == 4:
            # Lasso around the right petal; then each edge button once, at 300 % on the petal edge.
            petal = [(560, 250), (800, 250), (800, 560), (560, 560), (560, 250)]
            dialog, editor = window(background)
            editor._set_tool("lasso")
            lasso(editor.canvas, petal)
            save(dialog, editor, f"4a-panel-area-{key}")
            for operation in ("harder", "softer", "shrink", "grow"):
                dialog, editor = window(background)
                editor._set_tool("lasso")
                lasso(editor.canvas, petal)
                if hasattr(editor, "edge_buttons"):
                    editor._edge_operation(operation)
                    for _ in range(300):
                        if not editor.canvas.contour_busy:
                            break
                        QTest.qWait(10)
                editor._set_zoom(300)
                editor.canvas.centerOn(editor.canvas._item.mapToScene(QPointF(770, 400)))
                save(dialog, editor, f"4b-{operation}-x3-{key}")
        if item == 2:
            # The brush ring at the petal edge, 200 %, hard 16 px and soft 40 px.
            for hard, size in ((True, 16), (False, 40)):
                dialog, editor = window(background)
                editor._set_zoom(200)
                editor._set_diameter(size)
                editor._hardness_changed(100 if hard else 0)
                editor.canvas.centerOn(editor.canvas._item.mapToScene(QPointF(640, 560)))
                hover(editor.canvas, 664, 590)
                save(dialog, editor, f"2-cursor-{'hard16' if hard else 'soft40'}-{key}")


def compose(out, item, target, left="before", right="after",
            titles=("ДО (develop/3.2)", "ПОСЛЕ (эта ветка)")):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    target.mkdir(parents=True, exist_ok=True)
    for before in sorted(out.glob(f"{left}-{item}*.png")):
        name = before.name[len(left) + 1:]
        after = out / f"{right}-{name}"
        old, new = Image.open(before).convert("RGB"), Image.open(after).convert("RGB")
        board = Image.new("RGB", (old.width + new.width + 12, old.height + 34), (11, 22, 38))
        board.paste(old, (0, 34))
        board.paste(new, (old.width + 12, 34))
        d = ImageDraw.Draw(board)
        d.text((12, 10), titles[0], fill=(232, 238, 246), font=font)
        d.text((old.width + 24, 10), titles[1], fill=(36, 216, 197), font=font)
        board.save(target / name)


if __name__ == "__main__":
    if sys.argv[1] == "shoot":
        shoot(Path(sys.argv[2]), sys.argv[3], int(sys.argv[4]), Path(sys.argv[5]))
    elif sys.argv[1] == "mockups":
        compose(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), "current", "proposed",
                ("СЕЙЧАС (develop/3.2)", "МАКЕТ (предложение)"))
    else:
        compose(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]))
