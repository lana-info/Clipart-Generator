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
ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
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


from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QColor, QPainter, QPen
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget, QMessageBox,
                             QDialog, QGridLayout)
from PIL import ImageFont
from studio_patterns_page import _card, _text, _status, _qpixmap
from v3_components import ButtonVariant, V3Button, apply_v3_theme

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
HOME = Path(sys.argv[1]) / "docs/ui/3.2/patterns-module-proposal/actual/11-studio-home-1120x780.png"


def grab(widget):
    app.processEvents(); app.processEvents()
    path = OUT / "_tmp.png"
    widget.grab().save(str(path))
    return Image.open(path).convert("RGB")


def with_header(page_img, title, plaque=True):
    """Studio window = Studio header (real screenshot) + the module page under it."""
    header = Image.open(HOME).convert("RGB").crop((0, 0, 1120, 100))
    d = ImageDraw.Draw(header)
    d.rectangle((430, 38, 700, 76), fill=(31, 42, 56))
    w = d.textlength(title, font=ImageFont.truetype(BOLD, 19))
    d.text((560 - w / 2, 45), title, font=ImageFont.truetype(BOLD, 19), fill=(228, 237, 246))
    body = page_img if plaque else page_img
    out = Image.new("RGB", (1120, 100 + body.height - 8), (14, 22, 36))
    out.paste(header, (0, 0)); out.paste(body.crop((0, 8, 1120, body.height)), (0, 100))
    return out


def label(img, text, colour=(45, 212, 191)):
    out = Image.new("RGB", (img.width, img.height + 40), (8, 12, 20))
    out.paste(img, (0, 40))
    ImageDraw.Draw(out).text((14, 9), text, font=ImageFont.truetype(BOLD, 18), fill=colour)
    return out


def pair(a, b, name, left="СЕЙЧАС", right="ПРЕДЛАГАЮ"):
    a, b = label(a, left, (240, 180, 90)), label(b, right)
    out = Image.new("RGB", (a.width + b.width + 24, max(a.height, b.height)), (8, 12, 20))
    out.paste(a, (0, 0)); out.paste(b, (a.width + 24, 0))
    out.save(OUT / name)


with tempfile.TemporaryDirectory(prefix="vibix-patterns-mock-") as temp:
    folder = Path(temp)
    page = new_page(folder, "pngs")
    apply_v3_theme(page)
    top_card = page.title.parentWidget()

    # ---- П1 + П2: step 1, current (plaque + wrong header) vs proposed (no plaque, «Паттерны»)
    page._add_assets(motifs(folder))
    cur = with_header(grab(page), "Автоматический клипарт")
    top_card.hide()
    page.add_folder.hide()   # owner 2026-10-23: only «Добавить PNG» (the dialog takes many files at once)
    prop = with_header(grab(page), "Паттерны")
    pair(cur, prop, "P1-P2-header-and-plaque.png")

    # ---- П3 + П5 + П6: step 2 with a live preview
    page._go_next()
    top_card.show(); cur = with_header(grab(page), "Автоматический клипарт"); top_card.hide()
    settings_page = page.stack.currentWidget()
    columns = settings_page.layout().itemAt(2).layout()
    left_card = columns.itemAt(0).widget(); right_card = columns.itemAt(1).widget()
    columns.removeWidget(left_card); columns.removeWidget(right_card)
    holder = QWidget(); hl = QVBoxLayout(holder); hl.setContentsMargins(0, 0, 0, 0); hl.setSpacing(12)
    hl.addWidget(right_card); hl.addWidget(left_card)
    scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(holder); scroll.setFixedWidth(380)
    columns.addWidget(scroll)
    # Background row: clickable colour swatch + note that the background goes into the file (П6)
    page.background_name.setText("Тёплый белый · нажмите на образец, чтобы выбрать цвет")
    page.background_swatch.setStyleSheet("background:#fbf3e6;border:2px solid #2dd4bf;border-radius:4px")
    left_card.layout().insertWidget(left_card.layout().count() - 1,
                                    _text("Фон попадёт в итоговый файл. «Прозрачный» — только для PNG.", "v3Small"))
    # Live preview card (П3)
    preview, pl = _card("Предпросмотр листа")
    shown = page.host.preview_image(page.host.render(page._scene()) if hasattr(page.host, "render") else None, 1, 600000) \
        if False else None
    pic = QLabel(); pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
    pl.addWidget(pic, 1)
    pl.addWidget(_status("Поставлено 14 из 14 элементов.", "ok"))
    pl.addWidget(_text("Обновляется сам через полсекунды после изменения ползунка. Шов проверим на шаге 3.", "v3Small"))
    columns.addWidget(preview, 1)
    page._go_next(); pump(lambda: page._current is not None)
    sheet = page._current["image"]
    page._go_back()
    pic.setPixmap(_qpixmap(sheet, 330, 330))
    page.background_name.setText("Тёплый белый — нажмите на образец, чтобы выбрать цвет")
    page.background_swatch.setStyleSheet("background:#fbf3e6;border:2px solid #2dd4bf;border-radius:4px")
    prop = with_header(grab(page), "Паттерны")
    pair(cur, prop, "P3-P5-P6-settings-live-preview.png")
    # П5: not enough room — the same screen, Russian message with the reason and what to do
    pl.itemAt(2).widget().setText("Поставлено 8 из 27 элементов: при зазоре 120 px на листе нет места.\n"
                                  "Уменьшите зазор или размер элементов, либо количество.")
    from studio_patterns_page import _set_state
    _set_state(pl.itemAt(2).widget(), "warning")
    with_header(grab(page), "Паттерны").save(OUT / "P5-settings-not-enough-room.png")
    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
    with_header(grab(page), "Паттерны").save(OUT / "P6-settings-background-scrolled.png")
    scroll.verticalScrollBar().setValue(0)

    # ---- П7: manual placement on step 3
    page._go_next(); pump(lambda: page._current is not None)
    top_card.show(); cur = with_header(grab(page), "Автоматический клипарт"); top_card.hide()
    prev_card = page.preview_picture.parentWidget()
    bar = QHBoxLayout()
    for text, variant in (("Двигать", ButtonVariant.PRIMARY), ("Поворот", ButtonVariant.SECONDARY),
                          ("Размер", ButtonVariant.SECONDARY), ("Убрать", ButtonVariant.SECONDARY)):
        bar.addWidget(V3Button(text, variant))
    prev_card.layout().insertLayout(0, bar)
    back_auto = V3Button("Вернуть автоматическую расстановку", ButtonVariant.GHOST)
    prev_card.layout().insertWidget(1, back_auto)
    prev_card.layout().addWidget(_text("Щелчок по элементу — выбрать; тянуть — двигать; угол рамки — размер, "
                                       "кружок сверху — поворот. Элемент у края появится и с другой стороны листа.", "v3Small"))
    app.processEvents()
    img = grab(page)
    d = ImageDraw.Draw(img)
    pr = page.preview_picture
    origin = pr.mapTo(page, pr.rect().topLeft())
    pm = pr.pixmap(); ox = origin.x() + (pr.width() - pm.width()) // 2; oy = origin.y() + (pr.height() - pm.height()) // 2
    cx, cy, r = ox + pm.width() // 2 + 30, oy + pm.height() // 2 - 20, 26
    d.rectangle((cx - r, cy - r, cx + r, cy + r), outline=(45, 212, 191), width=2)
    for hx, hy in ((cx - r, cy - r), (cx + r, cy - r), (cx - r, cy + r), (cx + r, cy + r)):
        d.rectangle((hx - 4, hy - 4, hx + 4, hy + 4), fill=(45, 212, 191))
    d.line((cx, cy - r, cx, cy - r - 16), fill=(45, 212, 191), width=2)
    d.ellipse((cx - 5, cy - r - 22, cx + 5, cy - r - 12), outline=(45, 212, 191), width=2)
    prop = with_header(img, "Паттерны")
    pair(cur, prop, "P7-manual-placement.png")
    page.host.close()

    # ---- П4: tile mode, step 1
    tile_page = new_page(folder, "tile"); apply_v3_theme(tile_page)
    tile_page._set_mode("tile")
    tile_page._tile = {**tile_page.host.import_png(cut_picture(folder)), "name": "tile.png"}
    tile_page._refresh()
    t_top = tile_page.title.parentWidget()
    cur = with_header(grab(tile_page), "Автоматический клипарт")
    t_top.hide()
    for i in range(tile_page.checks.count()):
        w = tile_page.checks.itemAt(i).widget()
        if w is not None and "прозрачным" in w.text():
            w.setText("Плитка 600 × 600 px. Прозрачный фон для готовой плитки не нужен.")
            _set_state(w, "ok")
    prop = with_header(grab(tile_page), "Паттерны")
    pair(cur, prop, "P4-tile-source-texts.png")
    tile_page.host.close()

    # ---- П8: too-large PNG message
    box = QDialog(); apply_v3_theme(box); box.setWindowTitle("Паттерны")
    bl = QVBoxLayout(box); bl.setContentsMargins(20, 18, 20, 18); bl.setSpacing(10)
    bl.addWidget(_text("Файл слишком большой для узора", "v3Title"))
    bl.addWidget(_text("rough_03_upscaled-after.png — 12 288 × 12 288 px (151 млн пикселей).\n"
                       "Для узора нужен PNG до 8192 px по стороне и до 16 млн пикселей.", None))
    bl.addWidget(_text("Можно добавить уменьшенную копию 4000 × 4000 px — её хватит для листа 12 × 12 дюймов при 300 DPI. "
                       "Исходный файл не меняется.", "v3Small"))
    row = QHBoxLayout(); row.addStretch()
    row.addWidget(V3Button("Пропустить файл", ButtonVariant.SECONDARY)); row.addWidget(V3Button("Добавить уменьшенную копию", ButtonVariant.PRIMARY))
    bl.addLayout(row); box.resize(620, 240); box.show()
    old = Image.new("RGB", (620, 240), (31, 42, 56)); od = ImageDraw.Draw(old)
    od.text((20, 20), "Patterns", font=ImageFont.truetype(BOLD, 16), fill=(228, 237, 246))
    od.text((20, 60), "Не удалось добавить файлы: rough_03_upscaled-after.png\nНужен PNG не больше 8192 px.",
            font=ImageFont.truetype(FONT, 15), fill=(228, 237, 246))
    pair(old, grab(box), "P8-too-large-png.png")
(OUT / "_tmp.png").unlink(missing_ok=True)
print("ok")
