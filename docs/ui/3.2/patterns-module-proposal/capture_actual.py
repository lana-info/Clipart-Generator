"""Capture the real Patterns page offscreen in the approved states (dummy data only).

Run from the repository root: python docs/ui/3.2/patterns-module-proposal/capture_actual.py
Images go to ./actual/ and are compared by eye with the approved mockups next to them.
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent / "actual"
OUT.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtWidgets import QApplication

import studio_patterns
import studio_patterns_tools
from studio_patterns_host import PatternsHost
from studio_patterns_page import PatternsPage

app = QApplication.instance() or QApplication([])
kernel = SimpleNamespace(
    ALGORITHM_VERSION=1,
    **{n: getattr(studio_patterns, n) for n in (
        "MAX_DIMENSION", "MAX_ASSET_PIXELS", "MAX_JSON_BYTES", "AssetRef", "PatternElement", "PatternScene",
        "PatternValidationError", "RepeatMode", "render_supertile", "render_preview", "supertile_size", "rebuild_layout")},
    **{n: getattr(studio_patterns_tools, n) for n in (
        "SeamStatus", "layout_scene", "wrap_resize", "seam_report", "make_seamless", "mirror_tile",
        "tile_preview", "export_tile", "inches_to_px", "cm_to_px", "encoded_size_hint")})


def pump(predicate, seconds=60):
    end = time.monotonic() + seconds
    while not predicate() and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()


def motifs(folder):
    paths = []
    for index, color in enumerate(((217, 100, 112), (240, 190, 120), (110, 160, 130), (130, 150, 200))):
        image = Image.new("RGBA", (500, 500), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if index % 2 == 0:
            for angle in range(0, 360, 60):
                dx, dy = int(120 * np.cos(np.radians(angle))), int(120 * np.sin(np.radians(angle)))
                draw.ellipse((250 + dx - 80, 250 + dy - 80, 250 + dx + 80, 250 + dy + 80), fill=color + (255,))
            draw.ellipse((190, 190, 310, 310), fill=(250, 235, 190, 255))
        else:
            draw.ellipse((60, 170, 440, 330), fill=color + (255,))
        path = folder / f"motif{index}.png"
        image.save(path)
        paths.append(str(path))
    return paths


def cut_picture(folder, size=600):
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    data = np.stack([60 + 150 * x / size, 90 + 100 * y / size, 140 + 80 * (x + y) / (2 * size)], axis=-1)
    image = Image.fromarray(data.astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(image)
    for cx, cy, r, c in ((130, 150, 80, (240, 200, 120)), (440, 380, 100, (217, 100, 112)), (300, 500, 65, (250, 235, 190))):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)
    path = folder / "tile.png"
    image.filter(ImageFilter.GaussianBlur(1.5)).save(path)
    return str(path)


def new_page(folder, name):
    host = PatternsHost(folder / name, authorize=lambda: True, kernel=kernel)
    page = PatternsPage(host)
    page.resize(1120, 780)
    page.show()
    return page


def shot(page, name):
    app.processEvents()
    page.grab().save(str(OUT / f"{name}-1120x780.png"))


with tempfile.TemporaryDirectory(prefix="vibix-patterns-actual-") as temp:
    folder = Path(temp)
    page = new_page(folder, "pngs")
    shot(page, "01-source-empty")
    page._add_assets(motifs(folder))
    shot(page, "02-source-pngs")
    page._go_next()
    shot(page, "04-settings-pngs")
    page._go_next()
    pump(lambda: page._current is not None)
    shot(page, "06-preview-ready")
    page._go_next()
    pump(lambda: len(page._sheets) >= page._settings["sheet_count"] and not page._busy)
    shot(page, "08-collection")
    page._go_next()
    shot(page, "10-export-no-folder")
    page._export_folder = str(folder)
    page._refresh()
    shot(page, "09-export")
    page.host.close()

    tile_page = new_page(folder, "tile")
    tile_page._set_mode("tile")
    tile_page._tile = {**tile_page.host.import_png(cut_picture(folder)), "name": "tile.png"}
    tile_page._refresh()
    shot(tile_page, "03-source-tile")
    tile_page._go_next()
    shot(tile_page, "05-settings-tile")
    tile_page._settings["band"] = 5
    tile_page._go_next()
    pump(lambda: tile_page._current is not None)
    shot(tile_page, "06b-preview-tile-ready")
    # A real Fail: the engine's own verdict for the unprocessed, visibly cut picture.
    cut = Image.open(cut_picture(folder)).convert("RGB")
    tile_page._current = {"image": cut, "seam": tile_page.host._seam(cut)}
    print("seam status of the unprocessed picture:", tile_page._current["seam"]["status"])
    tile_page._refresh()
    shot(tile_page, "07-preview-fail")
print("Captured real Patterns screens into", OUT)
