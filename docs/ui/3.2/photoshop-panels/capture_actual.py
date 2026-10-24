import math, os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, sys.argv[1]); OUT = Path(sys.argv[2]); OUT.mkdir(parents=True, exist_ok=True)
from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QVBoxLayout
app = QApplication.instance() or QApplication([])
from v3_components import apply_v3_theme
from v3_clipart_flow import ClipartTransparencyEditorPage
tmp = Path(tempfile.mkdtemp()); files = []
for n in ("01_flower_ready.png", "02_rose_ready.png", "03_leaf_ready.png"):
    alpha = Image.new("L", (800, 800), 0); d = ImageDraw.Draw(alpha)
    for k in range(8):
        a = k * math.pi / 4; x, y = 400 + 190 * math.cos(a), 400 + 190 * math.sin(a)
        d.ellipse((x - 120, y - 120, x + 120, y + 120), fill=255)
    im = Image.new("RGBA", alpha.size, (236, 150, 172, 255)); ImageDraw.Draw(im).ellipse((300, 300, 500, 500), fill=(248, 206, 92, 255))
    im.putalpha(alpha.filter(ImageFilter.GaussianBlur(2.2))); im.save(tmp / n); files.append(tmp / n)
dialog = QDialog(); apply_v3_theme(dialog); editor = ClipartTransparencyEditorPage(); QVBoxLayout(dialog).addWidget(editor)
editor.set_files(files, selected_index=0); dialog.resize(1120, 780); dialog.show()
def save(name):
    for _ in range(6): app.processEvents()
    dialog.grab().save(str(OUT / name))
save("01-default-actual.png")
host, docks = editor.panel_host, editor.panel_docks
host.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, docks["files"])
host.resizeDocks([docks["files"], docks["tools"]], [240, 300], Qt.Orientation.Horizontal)
save("02-files-left-actual.png")
editor.reset_panels(); docks["files"].hide()
editor.zoom_buttons[150].click()
save("03-files-hidden-zoom150-actual.png")
os._exit(0)
