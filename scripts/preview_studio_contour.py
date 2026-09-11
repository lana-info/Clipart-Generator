"""Render the real Qt editor with a synthetic QA cup, never user artwork."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image, ImageDraw
from PyQt6.QtWidgets import QApplication
from studio_contour_editor import ContourEditorDialog


def main():
    app = QApplication.instance() or QApplication([])
    output = ROOT / "docs/ui/3.2/contour-editor-proof"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "qa-cup.png"
        image = Image.new("RGBA", (512, 512), (22, 170, 175, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((270, 165, 435, 330), fill=(22, 170, 175, 255))
        draw.ellipse((305, 198, 403, 300), fill=(22, 170, 175, 0))
        draw.rounded_rectangle((105, 160, 330, 370), radius=45, fill=(22, 170, 175, 255))
        draw.ellipse((105, 125, 330, 200), fill=(124, 227, 222, 255))
        draw.ellipse((120, 138, 315, 183), fill=(129, 80, 49, 255))
        draw.ellipse((180, 215, 255, 290), fill=(255, 227, 156, 255))
        image.save(path)
        dialog = ContourEditorDialog(path)
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(output / "default-1120x780.png"))
        dialog.canvas.auto_contour()
        app.processEvents()
        dialog.grab().save(str(output / "contour-1120x780.png"))
        dialog.resize(980, 700)
        app.processEvents()
        dialog.grab().save(str(output / "narrow.png"))
        dialog.close()
        missing = ContourEditorDialog(Path(folder) / "absent.png")
        missing.show()
        app.processEvents()
        missing.grab().save(str(output / "missing-1120x780.png"))
        missing.close()
    print(output)


if __name__ == "__main__":
    main()
