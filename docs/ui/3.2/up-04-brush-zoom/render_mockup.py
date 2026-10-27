"""UP-04 mockup built from the real editor widgets (dummy pictures only). Run from the repo root:
QT_QPA_PLATFORM=offscreen python docs/ui/3.2/up-04-brush-zoom/render_mockup.py
The real source is not changed: the script only moves widgets around the same way the implementation will."""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3]))
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication, QFrame, QVBoxLayout
app = QApplication([])
from v3_transparency_preview import ClipartTransparencyEditorPage

OUTLINE = ("QToolButton, QPushButton {border: 1px solid #3b4b60; border-radius: 6px; padding: 3px 8px;}"
           " QToolButton:hover, QPushButton:hover {border-color: #5b6f88;}")


def editor_with_pictures():
    tmp = Path(tempfile.mkdtemp())
    paths = []
    for i in range(8):
        p = tmp / f"gusenok_{i + 1:02d}_ready.png"
        im = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        d.ellipse((70, 70, 330, 330), fill=(250, 240, 220, 255)); d.ellipse((250, 110, 300, 160), fill=(245, 170, 80, 255))
        im.save(p); paths.append(p)
    editor = ClipartTransparencyEditorPage()
    editor.set_files(paths, selected_index=2)
    editor.set_file_annotations([("#34d399", "Ок", False, False)] * 2 + [("#f59e0b", "Брак генерации", False, False),
                                 ("#a78bfa", "Брак вырезания", False, False), ("#8ea3b8", "Не проверено", False, False),
                                 ("#34d399", "Ок", False, False), ("#8ea3b8", "Не проверено", True, False),
                                 ("#34d399", "Ок", False, False)])
    editor.resize(1120, 780)
    return editor


def propose(editor):
    """Diameter and hardness go back under «Кисть»; «Размеры» becomes the zoom bar with thin outlines."""
    size_layout = editor.size_frame.layout()
    brush_layout = editor.brush_controls.layout()
    label = size_layout.takeAt(0).widget()
    diameter_row = size_layout.takeAt(0).layout()
    style_row = size_layout.takeAt(0).layout()
    hint_at = brush_layout.count() - 1  # the hint stays the last line
    brush_layout.insertWidget(hint_at, label)
    brush_layout.insertLayout(hint_at + 1, diameter_row)
    brush_layout.insertLayout(hint_at + 2, style_row)
    editor.zoom_bar.setParent(editor.size_frame)
    editor.zoom_bar.setStyleSheet(editor.zoom_bar.styleSheet() + OUTLINE)
    size_layout.addWidget(editor.zoom_bar)
    size_layout.addStretch(1)


def shot(editor, name):
    editor.show()
    for _ in range(10): app.processEvents()
    editor.grab().save(str(HERE / name))


proposed = editor_with_pictures(); propose(proposed)
shot(proposed, "02-proposed-1120x780.png")

a = Image.open(HERE / "01-current-1120x780.png").convert("RGB")
b = Image.open(HERE / "02-proposed-1120x780.png").convert("RGB")
canvas = Image.new("RGB", (a.width + b.width + 24, a.height + 44), "#0f1722")
d = ImageDraw.Draw(canvas)
d.text((12, 12), "Сейчас", fill="#e4edf6"); d.text((a.width + 36, 12), "Предлагается", fill="#24cabb")
canvas.paste(a, (0, 44)); canvas.paste(b, (a.width + 24, 44))
canvas.save(str(HERE / "00-comparison.png"))
os._exit(0)
