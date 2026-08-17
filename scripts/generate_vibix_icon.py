"""Rasterize the approved Vibix Images SVG into a Windows multi-size ICO."""

from __future__ import annotations

import argparse
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(svg_path: Path, png_path: Path, size: int) -> None:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise ValueError(f"Invalid SVG: {svg_path}")
    image = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    if not image.save(str(png_path), "PNG"):
        raise OSError(f"Could not write PNG: {png_path}")


def generate_icon(svg_path: Path, ico_path: Path) -> None:
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vibix-icon-") as temp_dir:
        png_path = Path(temp_dir) / "vibix-256.png"
        render_png(svg_path, png_path, 256)
        image = Image.open(png_path).convert("RGBA")
        image.save(ico_path, format="ICO", sizes=[(size, size) for size in ICON_SIZES])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    app = QGuiApplication.instance() or QGuiApplication([])
    try:
        generate_icon(args.source.resolve(), args.output.resolve())
    finally:
        app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
