"""Offline Patterns approval mockups. No production widgets, files or API calls.

The shell (header card, "Шаги" panel on the left, Назад / Далее footer) copies
the real Vibix module windows (Auto Clipart, Image Processing).  Preview images
come from the real local engine (studio_patterns*) on dummy motifs drawn here.
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
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

from studio_patterns import AssetRef, PatternScene, RepeatMode, render_supertile
from studio_patterns_tools import layout_scene, make_seamless, seam_report, tile_preview

STEPS = ("Источник", "Настройки", "Предпросмотр", "Набор", "Экспорт")
GOOD, WARN, BAD, FLAT = ui.ACCENT, "#f0c38a", "#ef8a8a", "#738296"
PALETTE = ((217, 100, 112), (240, 190, 120), (110, 160, 130), (130, 150, 200))
CW, CH = 814, 568


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
    factor = size / 420
    scene = PatternScene(size, size, assets, (), mode, seed=seed, background=(250, 244, 232, 255))
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


def pix(image, width, height):
    image = image.convert("RGBA")
    qimage = QImage(image.tobytes(), image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage).scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)


def picture(parent, x, y, w, h, image, border=ui.LINE):
    frame = ui.box(parent, x, y, w, h, "#0d1522", border)
    holder = QLabel(frame)
    holder.setGeometry(1, 1, w - 2, h - 2)
    holder.setAlignment(Qt.AlignmentFlag.AlignCenter)
    holder.setPixmap(pix(image, w - 2, h - 2))
    holder.setStyleSheet("border:none; background:transparent;")
    return frame


# --- the Vibix module shell -------------------------------------------------

def shell(window, step, title, subtitle, *, note="Платных запросов нет.", next_text="Далее", next_disabled=False):
    """Header card, left step panel and bottom bar exactly as in the other modules."""
    ui.box(window, 24, 24, 1072, 66)
    ui.label(window, 41, 40, 420, 34, "Patterns · Весенний сад", 15, bold=True)
    home = ui.button(window, 658, 37, 139, "Главная Studio")
    home.setStyleSheet(f"background:{ui.BG}; color:{ui.INK}; border:2px solid #5aa0ff; border-radius:8px;")
    ui.label(window, 826, 40, 120, 34, "Настройки API", 10, ui.INK, True)
    ui.label(window, 973, 40, 110, 34, "Диагностика", 10, ui.INK, True)

    ui.box(window, 24, 106, 240, 568)
    ui.label(window, 41, 120, 200, 32, "Шаги", 16, bold=True)
    for index, name in enumerate(STEPS, start=1):
        mark = "✓" if index < step else ("●" if index == step else "○")
        ui.label(window, 41, 158 + (index - 1) * 26, 215, 24, f"{mark} {index}. {name}", 11,
                 ui.ACCENT if index <= step else ui.MUTED, index <= step)
    ui.label(window, 41, 560, 205, 90, "МАКЕТ ДЛЯ СОГЛАСОВАНИЯ\n1120 × 780 · демо-данные", 9, ui.MUTED)

    ui.box(window, 24, 690, 1072, 66)
    ui.label(window, 41, 700, 640, 46, note, 10, ui.MUTED)
    next_width = 78 if len(next_text) <= 6 else 150
    next_x = 1079 - next_width
    ui.button(window, next_x - 12 - 77, 702, 77, "Назад", disabled=step == 1)
    ui.button(window, next_x, 702, next_width, next_text, primary=True, disabled=next_disabled)

    content = QWidget(window)
    content.setGeometry(282, 106, CW, CH)
    content.setStyleSheet("background:transparent;")
    ui.label(content, 0, 0, CW, 36, title, 18, bold=True)
    ui.label(content, 0, 36, CW, 30, subtitle, 11, ui.MUTED)
    return content


def chip(parent, x, y, w, text, selected=False, disabled=False):
    ui.box(parent, x, y, w, 34, "#153b40" if selected else "#182232", ui.ACCENT if selected else ui.LINE)
    color = ui.ACCENT if selected else (FLAT if disabled else ui.INK)
    ui.label(parent, x + 10, y + 4, w - 18, 25, text, 11, color, selected)


def slider(parent, x, y, w, name, value_text, fraction):
    ui.label(parent, x, y, w - 100, 24, name, 11, ui.INK)
    ui.label(parent, x + w - 100, y, 100, 24, value_text, 11, ui.ACCENT, True)
    ui.box(parent, x, y + 32, w, 8, "#182232", ui.LINE)
    ui.box(parent, x, y + 32, max(10, int(w * fraction)), 8, ui.ACCENT, ui.ACCENT)
    ui.box(parent, x + int(w * fraction) - 8, y + 26, 18, 18, ui.INK, ui.INK)


def status(parent, x, y, text, kind):
    color = {"ready": GOOD, "review": WARN, "fail": BAD}[kind]
    ui.box(parent, x, y, 150, 30, "#182232", color)
    ui.label(parent, x + 10, y + 3, 132, 24, text, 11, color, True)


def mode_cards(c, selected_pngs):
    for x, name, text, on in ((0, "Из ваших PNG", "Раскладываем рисунки на листе. Шов бесшовный по построению.", selected_pngs),
                              (410, "Из готовой плитки", "Загрузите плитку: мы сделаем шов незаметным и проверим его.", not selected_pngs)):
        ui.box(c, x, 76, 404, 92, "#153b40" if on else "#182232", ui.ACCENT if on else ui.LINE)
        ui.label(c, x + 16, 84, 372, 28, name, 14, ui.ACCENT if on else ui.INK, True)
        ui.label(c, x + 16, 114, 372, 46, text, 10, ui.MUTED)


# --- screens ----------------------------------------------------------------

def source_empty(window, ctx):
    c = shell(window, 1, "Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Ваши файлы не изменяются.",
              next_disabled=True)
    mode_cards(c, True)
    ui.box(c, 0, 184, CW, 190, "#0d1522", ui.LINE)
    ui.label(c, 24, 232, 700, 34, "Пока нет файлов", 18, bold=True)
    ui.label(c, 24, 276, 700, 50, "Добавьте PNG с прозрачным фоном: цветы, листья, любые элементы.", 12, ui.MUTED)
    ui.button(c, 0, 388, 190, "Добавить PNG")
    ui.button(c, 202, 388, 190, "Добавить папку")
    ui.box(c, 0, 444, CW, 110)
    ui.label(c, 16, 452, 760, 90, "Здесь появится проверка файлов: размер, прозрачность, формат.\nЧтобы продолжить, добавьте хотя бы один файл.", 11, ui.MUTED)


def source_filled(window, ctx):
    c = shell(window, 1, "Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Ваши файлы не изменяются.")
    mode_cards(c, True)
    ui.label(c, 0, 178, 500, 26, "Ваши PNG: 8 файлов", 13, bold=True)
    ui.box(c, 0, 208, CW, 166, "#0d1522", ui.LINE)
    for index in range(8):
        picture(c, 14 + (index % 4) * 198, 218 + (index // 4) * 74, 186, 66, ctx["motif_strips"][index % 4])
    ui.button(c, 0, 388, 190, "Добавить PNG")
    ui.button(c, 202, 388, 190, "Добавить папку")
    for index, (text, color) in enumerate((("8 файлов с прозрачным фоном", GOOD), ("Размер каждого до 8192 px", GOOD),
                                           ("1 файл без прозрачности: останется с фоном", WARN))):
        ui.box(c, index * 274, 444, 266, 110, "#182232", color)
        ui.label(c, index * 274 + 14, 456, 240, 86, text, 11, color, True)


def source_tile(window, ctx):
    c = shell(window, 1, "Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Ваши файлы не изменяются.")
    mode_cards(c, False)
    ui.label(c, 0, 178, 500, 26, "Готовая плитка", 13, bold=True)
    picture(c, 0, 208, 250, 190, ctx["cut"])
    ui.label(c, 270, 214, 540, 28, "tile-spring.png", 13, bold=True)
    ui.label(c, 270, 248, 540, 80, "1024 × 1024 px\nПрозрачность: нет\nШов ещё не проверялся", 11, ui.MUTED)
    ui.button(c, 270, 350, 190, "Выбрать другую")
    ui.box(c, 0, 444, CW, 110, "#342c23", WARN)
    ui.label(c, 16, 454, 780, 90, "Шов заметен.\nНа следующем шаге его можно сделать незаметным. Результат всегда проверяется и получает оценку.", 11, WARN)


def settings_pngs(window, ctx):
    c = shell(window, 2, "Настройте узор", "Измените параметры и пересоберите лист. Результат воспроизводим по seed.")
    ui.box(c, 0, 76, 396, 478)
    ui.label(c, 16, 84, 360, 28, "Раскладка", 14, bold=True)
    for index, (name, on) in enumerate((("Обычная", True), ("Half-drop", False), ("Brick", False), ("Зеркало", False))):
        chip(c, 16 + (index % 2) * 182, 118 + (index // 2) * 42, 174, name, on)
    ui.label(c, 16, 206, 366, 48, "Half-drop и Brick сдвигают соседние ряды на половину листа, как кирпичная кладка.", 10, ui.MUTED)
    ui.label(c, 16, 262, 360, 28, "Размер листа (дюймы)", 14, bold=True)
    for index, (name, on) in enumerate((("12 × 12", True), ("8 × 8", False), ("6 × 6", False), ("Свой", False))):
        chip(c, 16 + (index % 2) * 182, 296 + (index // 2) * 42, 174, name, on)
    ui.label(c, 16, 384, 366, 24, "12 × 12 = 3600 × 3600 px при 300 DPI", 10, ui.MUTED)
    ui.label(c, 16, 420, 360, 28, "Фон", 14, bold=True)
    ui.box(c, 16, 456, 44, 34, "#faf4e8", ui.LINE)
    ui.label(c, 72, 458, 150, 30, "Тёплый белый", 11)
    chip(c, 226, 456, 154, "Прозрачный", False)
    ui.box(c, 410, 76, 404, 478)
    ui.label(c, 426, 84, 360, 28, "Расстановка", 14, bold=True)
    slider(c, 426, 126, 370, "Количество элементов", "14", 0.45)
    slider(c, 426, 186, 370, "Зазор между элементами", "12 px", 0.25)
    slider(c, 426, 246, 370, "Размер элементов", "75–125 %", 0.55)
    slider(c, 426, 306, 370, "Поворот", "±30°", 0.35)
    ui.label(c, 426, 372, 230, 30, "Seed (воспроизводимость)", 11)
    ui.box(c, 676, 370, 120, 34, "#182232", ui.LINE)
    ui.label(c, 690, 374, 100, 26, "4", 12, ui.INK, True)
    ui.button(c, 426, 424, 178, "Закрепить")
    ui.button(c, 616, 424, 180, "Пересобрать")
    ui.label(c, 426, 474, 370, 64, "Если места не хватает, покажем, сколько элементов поставлено из запрошенных.", 10, ui.MUTED)


def settings_tile(window, ctx):
    c = shell(window, 2, "Сделайте плитку бесшовной", "Мы смешаем края со сдвинутой копией и проверим шов. Исходный файл не изменится.")
    ui.box(c, 0, 76, 396, 478)
    ui.label(c, 16, 84, 360, 28, "Раскладка", 14, bold=True)
    for index, (name, on, off) in enumerate((("Обычная", True, False), ("Зеркало", False, False),
                                             ("Half-drop", False, True), ("Brick", False, True))):
        chip(c, 16 + (index % 2) * 182, 118 + (index // 2) * 42, 174, name, on, off)
    ui.label(c, 16, 206, 366, 64, "Half-drop и Brick недоступны для готовой плитки. Они есть в режиме «Из ваших PNG».", 10, ui.MUTED)
    ui.label(c, 16, 282, 360, 28, "Размер листа (дюймы)", 14, bold=True)
    for index, (name, on) in enumerate((("12 × 12", True), ("8 × 8", False), ("6 × 6", False), ("Свой", False))):
        chip(c, 16 + (index % 2) * 182, 316 + (index // 2) * 42, 174, name, on)
    ui.label(c, 16, 404, 366, 40, "Плитка масштабируется так, чтобы шов не появился.", 10, ui.MUTED)
    ui.box(c, 410, 76, 404, 478)
    ui.label(c, 426, 84, 360, 28, "Сглаживание шва", 14, bold=True)
    slider(c, 426, 126, 370, "Ширина полосы смешивания", "20 %", 0.4)
    ui.label(c, 426, 184, 370, 80, "Шире полоса: шов мягче, но на детальном рисунке возможно двоение. Уже полоса: детали сохраняются.", 10, ui.MUTED)
    ui.button(c, 426, 286, 370, "Применить и проверить шов", primary=True)
    ui.label(c, 426, 346, 370, 80, "Результат получит оценку Ready, Review или Fail. Идеальный шов для любого рисунка мы не обещаем.", 10, ui.MUTED)


def preview(window, ctx, ok):
    c = shell(window, 3, "Проверьте повтор" if ok else "Шов заметен",
              "Узор показан 3 × 3. Стык листов находится в центре картинки." if ok else "Шов виден при повторе. Исправьте его или оставьте как есть.",
              note="Оценка проверяет сам файл и не заменяет взгляд человека.")
    picture(c, 0, 76, 440, 440, ctx["preview_ok"] if ok else ctx["preview_bad"], ui.ACCENT if ok else BAD)
    ui.button(c, 0, 524, 160, "Увеличить шов")
    ui.label(c, 172, 526, 270, 30, "Линии границ: выключены", 10, ui.MUTED)
    ui.box(c, 460, 76, 354, 478)
    ui.label(c, 476, 84, 320, 28, "Оценка шва", 14, bold=True)
    status(c, 476, 122, "Ready" if ok else "Fail", "ready" if ok else "fail")
    rows = (("По горизонтали", "0.10" if ok else "8.2"), ("По вертикали", "0.15" if ok else "6.9"), ("Порог Ready", "1.5"))
    for index, (name, value) in enumerate(rows):
        ui.label(c, 476, 170 + index * 32, 200, 26, name, 11, ui.MUTED)
        ui.label(c, 706, 170 + index * 32, 90, 26, value, 12, GOOD if ok else BAD, True)
    ui.label(c, 476, 276, 320, 100, ("Оценка: скачок на стыке относительно обычных переходов внутри рисунка. Меньше — лучше." if ok
             else "Скачок на стыке в несколько раз больше обычных переходов. Такой лист нельзя считать бесшовным."), 10, ui.MUTED)
    if ok:
        ui.button(c, 476, 400, 322, "Добавить лист в набор", primary=True)
        ui.button(c, 476, 452, 322, "Пересобрать с другим seed")
    else:
        ui.button(c, 476, 400, 322, "Сделать бесшовной", primary=True)
        ui.button(c, 476, 452, 322, "Оставить как есть (Review)")


def preview_ok(window, ctx):
    preview(window, ctx, True)


def preview_bad(window, ctx):
    preview(window, ctx, False)


def collection(window, ctx):
    c = shell(window, 4, "Соберите набор листов", "Каждый лист — отдельный файл. Статус показывает, можно ли продавать его как бесшовный.",
              note="Лист со статусом Review можно исправить и выпустить позже отдельной версией.")
    ui.box(c, 0, 76, 560, 478)
    for index in range(6):
        x, y = 14 + (index % 3) * 180, 90 + (index // 3) * 226
        picture(c, x, y, 166, 166, ctx["sheets"][index])
        ui.label(c, x, y + 170, 70, 24, f"Лист {index + 1}", 10, bold=True)
        review = index == 4
        ui.label(c, x + 80, y + 170, 86, 24, "Review" if review else "Ready", 10, WARN if review else GOOD, True)
    ui.box(c, 576, 76, 238, 478)
    ui.label(c, 592, 84, 210, 28, "Параметры набора", 14, bold=True)
    slider(c, 592, 126, 206, "Листов", "6", 0.4)
    chip(c, 592, 190, 206, "Разные seed", True)
    chip(c, 592, 232, 206, "Разные раскладки", False)
    ui.label(c, 592, 290, 206, 110, "5 листов Ready.\n1 лист Review: шов слабо заметен. По умолчанию в экспорт не входит.", 10, ui.MUTED)
    ui.button(c, 592, 440, 206, "Пересобрать выбранный")


def export(window, ctx, folder=True):
    c = shell(window, 5, "Экспортируйте листы", "Выберите папку: файлы появятся в ней. Существующие файлы не перезаписываются молча.",
              note="Платных запросов нет. Сохранение начнётся после нажатия кнопки.",
              next_text="Экспортировать", next_disabled=not folder)
    ui.box(c, 0, 76, 520, 478)
    ui.label(c, 16, 84, 480, 28, "Формат и размер", 14, bold=True)
    for index, (name, on) in enumerate((("PNG", True), ("JPG", False))):
        chip(c, 16 + index * 130, 118, 122, name, on)
    for index, (name, on) in enumerate((("12 × 12", True), ("8 × 8", False), ("6 × 6", False), ("Свой", False))):
        chip(c, 16 + index * 124, 164, 116, name, on)
    ui.label(c, 16, 206, 488, 44, "12 × 12 дюймов = 3600 × 3600 px, 300 DPI, профиль sRGB. DPI — метаданные, деталей не добавляет.", 10, ui.MUTED)
    ui.label(c, 16, 262, 480, 28, "Папка для сохранения", 14, bold=True)
    ui.box(c, 16, 298, 488, 40, "#182232", ui.LINE if folder else WARN)
    ui.label(c, 28, 304, 464, 28, "D:\\Vibix\\Patterns\\Весенний сад" if folder else "Папка не выбрана",
             11, ui.INK if folder else WARN)
    ui.button(c, 16, 350, 200, "Выбрать папку…", primary=not folder)
    ui.label(c, 16, 404, 480, 28, "Имя набора", 14, bold=True)
    ui.box(c, 16, 440, 488, 40, "#182232", ui.LINE)
    ui.label(c, 28, 446, 464, 28, "Весенний сад", 11, ui.INK)
    ui.label(c, 16, 492, 488, 48, "Файлы: Весенний сад 01.png … 05.png. JPG не хранит прозрачность: прозрачные места зальются цветом фона.", 10, ui.MUTED)
    ui.box(c, 536, 76, 278, 478)
    ui.label(c, 552, 84, 250, 28, "Что будет сохранено", 14, bold=True)
    for index, (name, value) in enumerate((("Листов", "5"), ("Размер каждого", "3600 × 3600"),
                                           ("Примерный вес", "≈ 18 МБ"), ("Не входят", "1 лист Review"))):
        ui.label(c, 552, 126 + index * 40, 120, 28, name, 10, ui.MUTED)
        ui.label(c, 672, 126 + index * 40, 130, 28, value, 10, ui.INK, True)
    if not folder:
        ui.box(c, 552, 312, 246, 96, "#342c23", WARN)
        ui.label(c, 564, 320, 224, 80, "Выберите папку, чтобы включить экспорт.", 10, WARN)


def export_no_folder(window, ctx):
    export(window, ctx, folder=False)


SCREENS = (
    ("01-source-empty", source_empty), ("02-source-pngs", source_filled), ("03-source-tile", source_tile),
    ("04-settings-pngs", settings_pngs), ("05-settings-tile", settings_tile),
    ("06-preview-ready", preview_ok), ("07-preview-fail", preview_bad),
    ("08-collection", collection), ("09-export", export), ("10-export-no-folder", export_no_folder),
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
            "motif_strips": [Image.open(a.path).convert("RGBA") for a in assets],
            "cut": cut, "preview_ok": good.resize((438, 438), Image.Resampling.LANCZOS),
            "preview_bad": bad.resize((438, 438), Image.Resampling.LANCZOS),
            "sheets": [make_sheet(assets, RepeatMode.STRAIGHT, seed, 200, 12) for seed in range(6)],
        }
        for name, draw in SCREENS:
            render(app, name, draw, ctx)
    print("Rendered ten offline Patterns mockups; no runtime edits or API calls.")
