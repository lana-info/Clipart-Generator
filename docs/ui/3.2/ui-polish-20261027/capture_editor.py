"""Real transparency editor with the «Размеры» and «Превью» panels. Run from the repo root:
QT_QPA_PLATFORM=offscreen python docs/ui/3.2/ui-polish-20261027/capture_editor.py"""
import os, sys, tempfile
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication
app = QApplication([])
from v3_transparency_preview import ClipartTransparencyEditorPage

tmp = Path(tempfile.mkdtemp())
paths = []
for i in range(8):
    p = tmp / f"gusenok_{i + 1:02d}_ready.png"
    im = Image.new("RGBA", (400, 400), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.ellipse((70, 70, 330, 330), fill=(250, 240, 220, 255)); d.ellipse((250, 110, 300, 160), fill=(245, 170, 80, 255))
    im.save(p); paths.append(p)
editor = ClipartTransparencyEditorPage()
editor.set_files(paths, selected_index=2)
editor.set_file_annotations([("#34d399", "Ок", False, False), ("#34d399", "Ок", False, False), ("#f59e0b", "Брак генерации", False, False),
                             ("#a78bfa", "Брак вырезания", False, False), ("#8ea3b8", "Не проверено", False, False),
                             ("#34d399", "Ок", False, False), ("#8ea3b8", "Не проверено", True, False), ("#34d399", "Ок", False, False)])
editor.resize(1120, 780); editor.show()
for _ in range(8): app.processEvents()
editor.grab().save(str(Path(os.environ.get("SHOT_OUT", str(Path(__file__).with_name("editor-actual.png"))))))
os._exit(0)
