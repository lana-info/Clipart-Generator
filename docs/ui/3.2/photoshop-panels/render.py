"""Mockup: Photoshop-like panels in the transparency window («Файлы», «Инструменты»).

Real ClipartTransparencyEditorPage widgets moved into QDockWidget panels of a QMainWindow.
Run: python render.py <repo root> <out dir>
"""
import math, os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QApplication, QDockWidget, QHBoxLayout, QLabel, QMainWindow, QMenu, QToolButton,
                             QVBoxLayout, QWidget, QFrame)
app = QApplication.instance() or QApplication([])
from v3_components import ButtonVariant, V3Button, apply_v3_theme
from v3_clipart_flow import ClipartTransparencyEditorPage


def flower(path):
    alpha = Image.new("L", (800, 800), 0); d = ImageDraw.Draw(alpha)
    for k in range(8):
        a = k * math.pi / 4; x, y = 400 + 190 * math.cos(a), 400 + 190 * math.sin(a)
        d.ellipse((x - 120, y - 120, x + 120, y + 120), fill=255)
    d.ellipse((260, 260, 540, 540), fill=255)
    im = Image.new("RGBA", alpha.size, (236, 150, 172, 255))
    ImageDraw.Draw(im).ellipse((300, 300, 500, 500), fill=(248, 206, 92, 255))
    im.putalpha(alpha.filter(ImageFilter.GaussianBlur(2.2))); im.save(path)


tmp = Path(tempfile.mkdtemp())
files = []
for n in ("01_flower_ready.png", "02_rose_ready.png", "03_leaf_ready.png"):
    flower(tmp / n); files.append(tmp / n)


def title_bar(text, dock):
    bar = QFrame(); bar.setStyleSheet("QFrame{background:#1b2636;border-bottom:1px solid #2b3a4e}")
    row = QHBoxLayout(bar); row.setContentsMargins(10, 4, 4, 4)
    grip = QLabel("⋮⋮"); grip.setStyleSheet("color:#5d6f84"); row.addWidget(grip)
    label = QLabel(text); label.setStyleSheet("color:#e4edf6;font-weight:bold"); row.addWidget(label, 1)
    for sign, tip in (("▾", "Свернуть"), ("⧉", "Открепить окном"), ("✕", "Убрать (вернуть: «Панели»)")):
        b = QToolButton(); b.setText(sign); b.setToolTip(tip); b.setAutoRaise(True)
        b.setStyleSheet("QToolButton{color:#a6b5c8;padding:2px 6px}"); row.addWidget(b)
    return bar


def window():
    editor = ClipartTransparencyEditorPage()
    editor.set_files(files, selected_index=0)
    win = QMainWindow(); apply_v3_theme(win)
    top = QWidget(); tl = QHBoxLayout(top); tl.setContentsMargins(12, 8, 12, 4)
    t = QLabel("Проверка и корректировка прозрачности"); t.setStyleSheet("font-size:17px;font-weight:bold;color:#e4edf6")
    tl.addWidget(t, 1)
    panels = V3Button("Панели ▾", ButtonVariant.GHOST); tl.addWidget(panels)
    tl.addWidget(V3Button("Сбросить расположение", ButtonVariant.GHOST))
    central = QWidget(); cl = QVBoxLayout(central); cl.setContentsMargins(8, 0, 4, 8)
    cl.addWidget(top); cl.addWidget(editor.canvas.parentWidget(), 1)
    win.setCentralWidget(central)
    docks = {}
    for key, title, widget in (("files", "Файлы", editor.files_frame), ("tools", "Инструменты", editor.tools_scroll)):
        dock = QDockWidget(title); dock.setObjectName(key)
        dock.setTitleBarWidget(title_bar(title, dock)); dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetFloatable
                         | QDockWidget.DockWidgetFeature.DockWidgetClosable)
        win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock); docks[key] = dock
    win.resize(1120, 780); win.show(); app.processEvents()
    return win, editor, docks, panels


def save(win, name):
    for _ in range(6): app.processEvents()
    win.grab().save(str(OUT / name))


# 1. Default: both panels docked on the right, as today, but each has a title bar with ▾ ⧉ ✕ and a grip.
win, editor, docks, panels = window()
win.resizeDocks([docks["files"], docks["tools"]], [200, 520], Qt.Orientation.Vertical)
win.resizeDocks([docks["tools"]], [290], Qt.Orientation.Horizontal)
save(win, "01-default-docked-right.png")
# 2. «Файлы» dragged to the left edge, «Инструменты» widened.
win.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, docks["files"])
win.resizeDocks([docks["files"], docks["tools"]], [210, 360], Qt.Orientation.Horizontal)
save(win, "02-files-left-tools-wide.png")
# 3. «Файлы» removed, «Инструменты» floating over the picture; the «Панели» menu brings panels back.
docks["files"].hide()
docks["tools"].setFloating(True); docks["tools"].resize(300, 520)
docks["tools"].move(win.mapToGlobal(win.rect().topLeft()).x() + 760, win.mapToGlobal(win.rect().topLeft()).y() + 120)
save(win, "_base3.png")
base = Image.open(OUT / "_base3.png").convert("RGB")
tools = docks["tools"].grab(); tools.save(str(OUT / "_tools.png"))
tool_img = Image.open(OUT / "_tools.png").convert("RGB")
base.paste(tool_img, (790, 110))
d = ImageDraw.Draw(base)
d.rectangle((788, 108, 790 + tool_img.width + 1, 110 + tool_img.height + 1), outline=(45, 212, 191), width=2)
menu = Image.new("RGB", (230, 92), (27, 38, 54)); md = ImageDraw.Draw(menu)
from PIL import ImageFont
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
md.rectangle((0, 0, 229, 91), outline=(43, 58, 78))
md.text((12, 10), "☐  Файлы", font=f, fill=(228, 237, 246))
md.text((12, 36), "☑  Инструменты", font=f, fill=(228, 237, 246))
md.text((12, 62), "Сбросить расположение", font=f, fill=(166, 181, 200))
pb = panels.mapTo(win, panels.rect().bottomLeft())
base.paste(menu, (pb.x(), pb.y() + 2))
base.save(OUT / "03-files-hidden-tools-floating.png")
for n in ("_base3.png", "_tools.png"):
    (OUT / n).unlink()
os._exit(0)
