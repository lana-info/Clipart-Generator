"""Offline Patterns approval mockups. No production widgets, files or API calls.

Preview images are produced by the real local engine (studio_patterns*) from
dummy motifs drawn here, so the mockups show what the engine can really do.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(__file__).parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location(
    "mockup_primitives", OUT.parent / "result-kind-proposal/render_mockups.py"
)
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from studio_patterns import AssetRef, PatternScene, RepeatMode, render_supertile
from studio_patterns_tools import layout_scene, make_seamless, seam_report, tile_preview

STEPS = ("1  Источник", "2  Настройки", "3  Предпросмотр", "4  Набор", "5  Экспорт")
GOOD, WARN, BAD = ui.ACCENT, "#f0c38a", "#ef8a8a"
PALETTE = ((217, 100, 112), (240, 190, 120), (110, 160, 130), (130, 150, 200))


# --- dummy engine content ---------------------------------------------------

def make_motifs(folder):
    refs = []
    for index, color in enumerate(PALETTE):
        image = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if index % 2 == 0:  # flower
            for angle in range(0, 360, 60):
                dx, dy = int(55 * np.cos(np.radians(angle))), int(55 * np.sin(np.radians(angle)))
                draw.ellipse((120 + dx - 38, 120 + dy - 38, 120 + dx + 38, 120 + dy + 38), fill=color + (255,))
            draw.ellipse((90, 90, 150, 150), fill=(250, 235, 190, 255))
        else:  # leaf
            draw.ellipse((40, 85, 200, 155), fill=color + (255,))
            draw.line((50, 120, 190, 120), fill=(240, 240, 230, 255), width=4)
        path = Path(folder) / f"motif{index}.png"
        image.filter(ImageFilter.GaussianBlur(0.8)).save(path)
        refs.append(AssetRef(f"motif{index}", str(path)))
    return tuple(refs)


def make_sheet(assets, mode=RepeatMode.STRAIGHT, seed=4, size=420, count=14):
    scene = PatternScene(size, size, assets, (), mode, seed=seed, background=(250, 244, 232, 255))
    factor = size / 420
    scene, _ = layout_scene(scene, count=count, min_gap=10 * factor, scale_range=(0.3 * factor, 0.5 * factor))
    return render_supertile(scene)


def make_cut_picture(size=420):
    """A picture that is NOT periodic: its left/right and top/bottom edges differ."""
    y, x = np.mgrid[0:size, 0:size].astype(np.float32)
    data = np.stack([60 + 150 * x / size, 90 + 100 * y / size, 140 + 80 * (x + y) / (2 * size)], axis=-1)
    image = Image.fromarray(data.astype(np.uint8), "RGB")
    draw = ImageDraw.Draw(image)
    for cx, cy, r, c in ((90, 100, 55, (240, 200, 120)), (300, 260, 70, (217, 100, 112)), (210, 340, 45, (250, 235, 190))):
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=c)
    return image.filter(ImageFilter.GaussianBlur(1.2))


def pix(image, width, height=None):
    image = image.convert("RGBA")
    qimage = QImage(image.tobytes(), image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
    pixmap = QPixmap.fromImage(qimage)
    return pixmap.scaled(width, height or width)


def picture(parent, x, y, w, h, image, border=ui.LINE):
    frame = ui.box(parent, x, y, w, h, "#0d1522", border)
    holder = QLabel(frame)
    holder.setGeometry(1, 1, w - 2, h - 2)
    holder.setPixmap(pix(image, w - 2, h - 2))
    holder.setStyleSheet("border:none; background:transparent;")
    return frame


# --- shared widgets ---------------------------------------------------------

def header(window, step, title, subtitle):
    ui.box(window, 0, 0, 1120, 62, "#111b2a", "#111b2a")
    ui.label(window, 24, 12, 166, 36, "VIBIX  Studio", 14, bold=True)
    ui.label(window, 205, 12, 490, 36, "Модуль Patterns  /  Весенний сад", 13, ui.ACCENT)
    ui.button(window, 812, 11, 129, "Каталог Studio")
    ui.button(window, 953, 11, 143, "Настройки API")
    ui.label(window, 24, 72, 1068, 20, "МАКЕТ ДЛЯ СОГЛАСОВАНИЯ · 1120 × 780 · демо-данные, без запуска генерации", 10, ui.MUTED)
    ui.label(window, 24, 104, 1068, 37, title, 24, bold=True)
    ui.label(window, 24, 147, 1068, 30, subtitle, 12, ui.MUTED)
    for index, name in enumerate(STEPS, start=1):
        x, active = 24 + (index - 1) * 218, index == step
        ui.box(window, x, 187, 200, 34, "#153b40" if active else "#182232", ui.ACCENT if active else ui.LINE)
        ui.label(window, x + 12, 192, 176, 22, name, 11, ui.ACCENT if active else ui.MUTED, active)


def footer(window, note, secondary, primary, disabled=False):
    ui.label(window, 24, 724, 645, 34, note, 10, ui.MUTED)
    ui.button(window, 680, 721, 183, secondary)
    ui.button(window, 878, 721, 218, primary, primary=True, disabled=disabled)


def chip(parent, x, y, w, text, selected=False, disabled=False):
    border = ui.ACCENT if selected else ui.LINE
    ui.box(parent, x, y, w, 34, "#153b40" if selected else "#182232", border)
    color = ui.ACCENT if selected else ("#738296" if disabled else ui.INK)
    ui.label(parent, x + 10, y + 4, w - 18, 25, text, 11, color, selected)


def slider(parent, x, y, w, name, value_text, fraction):
    ui.label(parent, x, y, w - 110, 24, name, 11, ui.INK)
    ui.label(parent, x + w - 110, y, 110, 24, value_text, 11, ui.ACCENT, True)
    ui.box(parent, x, y + 32, w, 8, "#182232", ui.LINE)
    ui.box(parent, x, y + 32, max(10, int(w * fraction)), 8, ui.ACCENT, ui.ACCENT)
    ui.box(parent, x + int(w * fraction) - 8, y + 26, 18, 18, ui.INK, ui.INK)


def status(parent, x, y, text, kind):
    color = {"ready": GOOD, "review": WARN, "fail": BAD}[kind]
    ui.box(parent, x, y, 150, 30, "#182232", color)
    ui.label(parent, x + 10, y + 3, 132, 24, text, 11, color, True)


# --- screens ----------------------------------------------------------------

def source_empty(window, ctx):
    header(window, 1, "Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Файлы не изменяются.")
    left, right = ui.box(window, 24, 242, 682, 470), ui.box(window, 724, 242, 372, 470)
    ui.label(left, 20, 16, 640, 31, "Режим", 16, bold=True)
    for x, name, text, on in ((20, "Из ваших PNG", "Раскладываем рисунки на листе. Шов бесшовный по построению.", True),
                              (344, "Из готовой плитки", "Загрузите плитку, мы сделаем шов незаметным и проверим его.", False)):
        ui.box(left, x, 56, 318, 108, "#153b40" if on else "#182232", ui.ACCENT if on else ui.LINE)
        ui.label(left, x + 16, 64, 288, 28, name, 14, ui.ACCENT if on else ui.INK, True)
        ui.label(left, x + 16, 96, 288, 60, text, 10, ui.MUTED)
    ui.label(left, 20, 186, 640, 28, "Ваши PNG", 14, bold=True)
    ui.box(left, 20, 224, 642, 180, "#0d1522", ui.LINE)
    ui.label(left, 40, 262, 600, 36, "Пока нет файлов", 18, bold=True)
    ui.label(left, 40, 306, 600, 48, "Добавьте PNG с прозрачным фоном: цветы, листья, любые элементы.", 12, ui.MUTED)
    ui.button(left, 20, 420, 190, "Добавить PNG")
    ui.button(left, 222, 420, 190, "Добавить папку")
    ui.label(right, 20, 16, 330, 31, "Проверка файлов", 16, bold=True)
    ui.label(right, 20, 62, 330, 60, "Здесь появится результат проверки: размер, прозрачность, формат.", 11, ui.MUTED)
    footer(window, "Черновик проекта сохранён локально. Платных запросов нет.", "К каталогу", "К настройкам", disabled=True)


def source_filled(window, ctx):
    header(window, 1, "Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Файлы не изменяются.")
    left, right = ui.box(window, 24, 242, 682, 470), ui.box(window, 724, 242, 372, 470)
    ui.label(left, 20, 16, 640, 31, "Режим", 16, bold=True)
    for x, name, text, on in ((20, "Из ваших PNG", "Раскладываем рисунки на листе. Шов бесшовный по построению.", True),
                              (344, "Из готовой плитки", "Загрузите плитку, мы сделаем шов незаметным и проверим его.", False)):
        ui.box(left, x, 56, 318, 108, "#153b40" if on else "#182232", ui.ACCENT if on else ui.LINE)
        ui.label(left, x + 16, 64, 288, 28, name, 14, ui.ACCENT if on else ui.INK, True)
        ui.label(left, x + 16, 96, 288, 60, text, 10, ui.MUTED)
    ui.label(left, 20, 186, 640, 28, "Ваши PNG: 8 файлов", 14, bold=True)
    ui.box(left, 20, 224, 642, 180, "#0d1522", ui.LINE)
    for index in range(8):
        picture(left, 34 + (index % 4) * 154, 236 + (index // 4) * 80, 144, 72, ctx["motif_strips"][index % 4])
    ui.button(left, 20, 420, 190, "Добавить PNG")
    ui.button(left, 222, 420, 190, "Добавить папку")
    ui.label(right, 20, 16, 330, 31, "Проверка файлов", 16, bold=True)
    for index, (text, color) in enumerate((("8 файлов с прозрачным фоном", GOOD), ("Размер каждого не больше 8192 px", GOOD),
                                           ("1 файл без прозрачности: останется с фоном", WARN))):
        ui.box(right, 20, 62 + index * 82, 332, 70, "#182232", color)
        ui.label(right, 34, 72 + index * 82, 306, 50, text, 11, color, True)
    footer(window, "Черновик проекта сохранён локально. Платных запросов нет.", "К каталогу", "К настройкам")


def source_tile(window, ctx):
    header(window, 1, "Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Файлы не изменяются.")
    left, right = ui.box(window, 24, 242, 682, 470), ui.box(window, 724, 242, 372, 470)
    ui.label(left, 20, 16, 640, 31, "Режим", 16, bold=True)
    for x, name, text, on in ((20, "Из ваших PNG", "Раскладываем рисунки на листе. Шов бесшовный по построению.", False),
                              (344, "Из готовой плитки", "Загрузите плитку, мы сделаем шов незаметным и проверим его.", True)):
        ui.box(left, x, 56, 318, 108, "#153b40" if on else "#182232", ui.ACCENT if on else ui.LINE)
        ui.label(left, x + 16, 64, 288, 28, name, 14, ui.ACCENT if on else ui.INK, True)
        ui.label(left, x + 16, 96, 288, 60, text, 10, ui.MUTED)
    ui.label(left, 20, 186, 640, 28, "Готовая плитка", 14, bold=True)
    picture(left, 20, 224, 240, 180, ctx["cut"])
    ui.label(left, 280, 232, 380, 28, "tile-spring.png", 13, bold=True)
    ui.label(left, 280, 266, 380, 90, "1024 × 1024 px\nПрозрачность: нет\nШов пока не проверялся", 11, ui.MUTED)
    ui.button(left, 20, 420, 190, "Выбрать другую")
    ui.label(right, 20, 16, 330, 31, "Проверка шва", 16, bold=True)
    ui.box(right, 20, 62, 332, 120, "#342c23", WARN)
    ui.label(right, 34, 70, 306, 104, "Шов заметен.\nМожно сделать его незаметным на следующем шаге. Результат всегда проверяется.", 11, WARN)
    footer(window, "Исходный файл не изменяется: результат сохраняется отдельно.", "К каталогу", "К настройкам")


def settings_pngs(window, ctx):
    header(window, 2, "Настройте узор", "Измените параметры и пересоберите лист. Результат всегда воспроизводим по seed.")
    left, right = ui.box(window, 24, 242, 560, 470), ui.box(window, 602, 242, 494, 470)
    ui.label(left, 20, 14, 520, 30, "Раскладка", 16, bold=True)
    for index, (name, on) in enumerate((("Обычная", True), ("Half-drop", False), ("Brick", False), ("Зеркало", False))):
        chip(left, 20 + index * 132, 54, 124, name, on)
    ui.label(left, 20, 98, 520, 44, "Обычная: узор повторяется по сетке. Half-drop и Brick сдвигают соседние ряды на половину.", 10, ui.MUTED)
    ui.label(left, 20, 152, 520, 30, "Размер листа", 16, bold=True)
    for index, (name, on) in enumerate((("12 × 12", True), ("8 × 8", False), ("6 × 6", False), ("Свой", False))):
        chip(left, 20 + index * 132, 192, 124, name, on)
    ui.label(left, 20, 236, 520, 24, "Размеры в дюймах. 12 × 12 = 3600 × 3600 px при 300 DPI", 10, ui.MUTED)
    ui.label(left, 20, 276, 520, 30, "Фон", 16, bold=True)
    ui.box(left, 20, 316, 44, 34, "#faf4e8", ui.LINE)
    ui.label(left, 76, 318, 300, 30, "Тёплый белый", 12, ui.INK)
    chip(left, 380, 316, 160, "Прозрачный", False)
    ui.label(left, 20, 372, 520, 30, "Элементы", 16, bold=True)
    ui.button(left, 20, 412, 250, "Закрепить выбранные")
    ui.button(left, 282, 412, 258, "Пересобрать остальные")
    ui.label(right, 20, 14, 450, 30, "Расстановка", 16, bold=True)
    slider(right, 20, 62, 454, "Количество элементов", "14", 0.45)
    slider(right, 20, 122, 454, "Зазор между элементами", "12 px", 0.25)
    slider(right, 20, 182, 454, "Размер элементов", "75–125 %", 0.55)
    slider(right, 20, 242, 454, "Поворот", "±30°", 0.35)
    ui.label(right, 20, 306, 300, 30, "Seed (воспроизводимость)", 11)
    ui.box(right, 330, 304, 144, 34, "#182232", ui.LINE)
    ui.label(right, 344, 308, 120, 26, "4", 12, ui.INK, True)
    ui.box(right, 20, 360, 454, 90, "#182232", ui.LINE)
    ui.label(right, 34, 368, 428, 74, "Если места не хватает, будет показано, сколько элементов поставлено из запрошенных. Расстановка не зависает.", 10, ui.MUTED)
    footer(window, "Любое изменение сохраняется в проекте. Платных запросов нет.", "К источнику", "К предпросмотру")


def settings_tile(window, ctx):
    header(window, 2, "Сделайте плитку бесшовной", "Мы смешаем края со сдвинутой копией и проверим шов. Исходный файл не изменится.")
    left, right = ui.box(window, 24, 242, 560, 470), ui.box(window, 602, 242, 494, 470)
    ui.label(left, 20, 14, 520, 30, "Раскладка", 16, bold=True)
    for index, (name, on, off) in enumerate((("Обычная", True, False), ("Зеркало", False, False), ("Half-drop", False, True), ("Brick", False, True))):
        chip(left, 20 + index * 132, 54, 124, name, on, off)
    ui.box(left, 20, 100, 520, 70, "#182232", ui.LINE)
    ui.label(left, 34, 106, 492, 58, "Half-drop и Brick недоступны для готовой плитки. Они есть в режиме «Из ваших PNG».", 10, ui.MUTED)
    ui.label(left, 20, 196, 520, 30, "Размер листа", 16, bold=True)
    for index, (name, on) in enumerate((("12 × 12", True), ("8 × 8", False), ("6 × 6", False), ("Свой", False))):
        chip(left, 20 + index * 132, 236, 124, name, on)
    ui.label(left, 20, 280, 520, 24, "Плитка масштабируется без появления шва.", 10, ui.MUTED)
    ui.label(right, 20, 14, 450, 30, "Сглаживание шва", 16, bold=True)
    slider(right, 20, 62, 454, "Ширина полосы смешивания", "20 %", 0.4)
    ui.label(right, 20, 124, 454, 70, "Шире полоса: шов мягче, но на детальном рисунке возможно двоение. Узкая полоса сохраняет детали.", 10, ui.MUTED)
    ui.button(right, 20, 210, 454, "Применить и проверить шов", primary=True)
    ui.box(right, 20, 274, 454, 90, "#182232", ui.LINE)
    ui.label(right, 34, 282, 428, 74, "Результат получит оценку Ready, Review или Fail. Мы не обещаем идеальный шов для любого рисунка.", 10, ui.MUTED)
    footer(window, "Исходный файл не изменяется: результат сохраняется отдельно.", "К источнику", "К предпросмотру")


def preview(window, ctx, ok=True):
    header(window, 3, "Проверьте повтор" if ok else "Шов заметен", "Узор показан 3 × 3. Стык листов находится в центре картинки." if ok else "Шов виден при повторе. Исправьте или оставьте как есть.")
    left, right = ui.box(window, 24, 242, 622, 470), ui.box(window, 664, 242, 432, 470)
    picture(left, 20, 20, 430, 430, ctx["preview_ok"] if ok else ctx["preview_bad"], ui.ACCENT if ok else BAD)
    ui.button(left, 466, 20, 140, "Увеличить шов")
    ui.label(left, 466, 70, 140, 120, "Линии границ\nвыключены", 10, ui.MUTED)
    ui.label(right, 20, 16, 392, 31, "Оценка шва", 16, bold=True)
    status(right, 20, 60, "Ready" if ok else "Fail", "ready" if ok else "fail")
    rows = (("По горизонтали", "0.10" if ok else "8.2"), ("По вертикали", "0.15" if ok else "6.9"), ("Порог Ready", "1.5"))
    for index, (name, value) in enumerate(rows):
        ui.label(right, 20, 112 + index * 34, 260, 28, name, 11, ui.MUTED)
        ui.label(right, 300, 112 + index * 34, 110, 28, value, 12, GOOD if ok else BAD, True)
    note = ("Оценка — отношение скачка на стыке к обычным переходам внутри рисунка. Меньше — лучше." if ok
            else "Скачок на стыке в несколько раз больше обычных переходов. Такой лист нельзя считать бесшовным.")
    ui.box(right, 20, 226, 392, 110, "#182232", ui.LINE)
    ui.label(right, 34, 234, 366, 94, note, 10, ui.MUTED)
    if ok:
        ui.button(right, 20, 358, 392, "Добавить лист в набор", primary=True)
        ui.button(right, 20, 408, 392, "Пересобрать с другим seed")
    else:
        ui.button(right, 20, 358, 392, "Сделать бесшовной", primary=True)
        ui.button(right, 20, 408, 392, "Оставить как есть (Review)")
    footer(window, "Оценка проверяет сам файл. Она не заменяет взгляд человека.", "К настройкам", "К набору")


def preview_ok(window, ctx):
    preview(window, ctx, True)


def preview_bad(window, ctx):
    preview(window, ctx, False)


def collection(window, ctx):
    header(window, 4, "Соберите набор листов", "Каждый лист — отдельный файл. Статус показывает, можно ли его продавать как бесшовный.")
    left, right = ui.box(window, 24, 242, 728, 470), ui.box(window, 770, 242, 326, 470)
    for index in range(6):
        x, y = 20 + (index % 3) * 236, 16 + (index // 3) * 226
        picture(left, x, y, 214, 170, ctx["sheets"][index], ui.LINE)
        ui.label(left, x, y + 174, 90, 24, f"Лист {index + 1}", 11, ui.INK, True)
        kind = "review" if index == 4 else "ready"
        color = WARN if kind == "review" else GOOD
        ui.label(left, x + 100, y + 174, 114, 24, "Review" if kind == "review" else "Ready", 11, color, True)
    ui.label(right, 20, 16, 290, 31, "Параметры набора", 16, bold=True)
    slider(right, 20, 62, 286, "Количество листов", "6", 0.4)
    chip(right, 20, 122, 286, "Разные seed", True)
    chip(right, 20, 164, 286, "Разные раскладки", False)
    ui.box(right, 20, 226, 286, 120, "#182232", ui.LINE)
    ui.label(right, 34, 234, 258, 104, "5 листов Ready.\n1 лист Review: шов слабо заметен. В экспорт по умолчанию не входит.", 10, ui.MUTED)
    ui.button(right, 20, 372, 286, "Пересобрать выбранный")
    footer(window, "Review можно исправить и выпустить позже отдельной версией.", "К предпросмотру", "К экспорту")


def export(window, ctx):
    header(window, 5, "Экспортируйте листы", "Файлы сохраняются в выбранную папку. Файлы уже существующих листов не перезаписываются молча.")
    left, right = ui.box(window, 24, 242, 640, 470), ui.box(window, 682, 242, 414, 470)
    ui.label(left, 20, 14, 600, 30, "Формат и размер", 16, bold=True)
    for index, (name, on) in enumerate((("PNG", True), ("JPG", False))):
        chip(left, 20 + index * 132, 54, 124, name, on)
    for index, (name, on) in enumerate((("12 × 12", True), ("8 × 8", False), ("6 × 6", False), ("Свой", False))):
        chip(left, 20 + index * 132, 100, 124, name, on)
    ui.label(left, 20, 144, 600, 48, "3600 × 3600 px, 300 DPI, цветовой профиль sRGB. DPI — метаданные и детали не добавляет.", 10, ui.MUTED)
    ui.label(left, 20, 206, 600, 30, "Папка и имена", 16, bold=True)
    ui.box(left, 20, 246, 600, 40, "#182232", ui.LINE)
    ui.label(left, 34, 252, 570, 28, "Google Drive / Patterns / Весенний сад", 12, ui.INK)
    ui.box(left, 20, 298, 600, 40, "#182232", ui.LINE)
    ui.label(left, 34, 304, 570, 28, "spring-garden-01.png … spring-garden-05.png", 12, ui.MUTED)
    ui.box(left, 20, 366, 600, 80, "#182232", ui.LINE)
    ui.label(left, 34, 372, 572, 68, "JPG не хранит прозрачность: прозрачные места будут залиты выбранным цветом фона.", 10, ui.MUTED)
    ui.label(right, 20, 14, 380, 30, "Что будет сохранено", 16, bold=True)
    for index, (name, value) in enumerate((("Листов", "5"), ("Размер каждого", "3600 × 3600"), ("Примерный вес", "≈ 18 МБ"), ("В экспорт не входят", "1 лист Review"))):
        ui.label(right, 20, 62 + index * 38, 210, 28, name, 11, ui.MUTED)
        ui.label(right, 230, 62 + index * 38, 164, 28, value, 11, ui.INK, True)
    ui.box(right, 20, 232, 374, 130, "#153b40", ui.ACCENT)
    ui.label(right, 34, 240, 346, 114, "Каждый файл можно повторять без шва: при изменении размера край учитывается по периоду.", 11, ui.ACCENT)
    footer(window, "Платных запросов нет. Сохранение начнётся после нажатия кнопки.", "К набору", "Экспортировать")


SCREENS = (
    ("01-source-empty", source_empty), ("02-source-pngs", source_filled), ("03-source-tile", source_tile),
    ("04-settings-pngs", settings_pngs), ("05-settings-tile", settings_tile),
    ("06-preview-ready", preview_ok), ("07-preview-fail", preview_bad),
    ("08-collection", collection), ("09-export", export),
)


def render(app, name, draw, ctx):
    window = QWidget()
    window.setFixedSize(1120, 780)
    window.setStyleSheet(f"background:{ui.BG};")
    draw(window, ctx)
    window.show()
    app.processEvents()
    assert window.grab().save(str(OUT / f"{name}-1120x780.png"))
    window.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="vibix-patterns-") as folder:
        os.environ["LOCALAPPDATA"] = folder
        app = QApplication.instance() or QApplication([])
        assets = make_motifs(folder)
        sheet = make_sheet(assets)
        cut = make_cut_picture()
        good = tile_preview(sheet.resize((140, 140), Image.Resampling.LANCZOS), 3)
        bad = tile_preview(cut.resize((140, 140)), 3)
        print("seam of generated sheet:", seam_report(sheet).status.value,
              "| cut picture:", seam_report(cut).status.value,
              "| after make_seamless:", seam_report(make_seamless(cut)).status.value)
        ctx = {
            "motif_strips": [Image.open(a.path).convert("RGBA").resize((72, 72)).crop((0, 0, 72, 72)) for a in assets],
            "cut": cut, "preview_ok": good.resize((428, 428), Image.Resampling.LANCZOS),
            "preview_bad": bad.resize((428, 428), Image.Resampling.LANCZOS),
            "sheets": [make_sheet(assets, RepeatMode.STRAIGHT, seed, 200, 12) for seed in range(6)],
        }
        for name, draw in SCREENS:
            render(app, name, draw, ctx)
    print("Rendered nine offline Patterns mockups; no runtime edits or API calls.")
