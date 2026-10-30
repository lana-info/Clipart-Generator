"""Макет: меню «Переделать выбранные» с новым пунктом «Апскейл заново» и подсказками (владелец 2026-10-30).

Рисуется в визуальном языке приложения (тёмная тема), 1120×780, как требует правило проекта.
Запуск: python render.py <out-папка>
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

W, H = 1120, 780
BG = QColor("#0f1725")
PANEL = QColor("#172131")
PANEL_LINE = QColor("#354154")
ACCENT = QColor("#24cabb")
INK = QColor("#e4edf6")
MUTED = QColor("#a6b5c8")
TIP_BG = QColor("#223045")

ITEMS = [
    ("Перегенерировать", False,
     "Новая генерация картинки, затем весь путь обработки: удаление фона → апскейл → очистка края → "
     "резкость → обрезка → сохранение PNG.\nПрежняя картинка станет версией."),
    ("Удалить фон заново", False,
     "Повторное вырезание из сгенерированной картинки, затем апскейл → очистка края → резкость → "
     "обрезка → сохранение PNG."),
    ("Апскейл заново", True,
     "Повторный апскейл вырезанной картинки, затем очистка края → резкость → обрезка → "
     "сохранение PNG."),
]


def rounded(painter, rect, colour, radius=8, line=None):
    painter.setPen(QPen(line, 1) if line else Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    painter.drawPath(path)


def measure(painter, text, width, size=12, bold=False):
    font = QFont(painter.font())
    font.setPixelSize(size)
    font.setBold(bold)
    metrics = QFontMetrics(font)
    height = 0
    for paragraph in text.split("\n"):
        box = metrics.boundingRect(QRect(0, 0, width, 10000), int(Qt.TextFlag.TextWordWrap), paragraph)
        height += box.height() + 4
    return height


def wrapped(painter, text, x, y, width, colour=INK, size=12, bold=False):
    """Рисует текст с переносом; возвращает нижнюю границу."""
    font = QFont(painter.font())
    font.setPixelSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(colour)
    metrics = QFontMetrics(font)
    for paragraph in text.split("\n"):
        box = metrics.boundingRect(QRect(0, 0, width, 10000), int(Qt.TextFlag.TextWordWrap), paragraph)
        painter.drawText(QRect(x, y, width, box.height()), int(Qt.TextFlag.TextWordWrap), paragraph)
        y += box.height() + 4
    return y


canvas_pixmap = None
image = None
from PyQt6.QtGui import QPixmap

pixmap = QPixmap(W, H)
pixmap.fill(BG)
painter = QPainter(pixmap)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

wrapped(painter, "Меню «Переделать выбранные»: три варианта обработки, путь — в подсказке",
        32, 46, W - 64, INK, 18, True)
wrapped(painter, "Жирным — новое. Подсказка появляется при наведении на пункт меню.",
        32, 74, W - 64, MUTED, 12)

menu_x, menu_y, menu_w, row_h = 32, 110, 360, 40
rounded(painter, QRect(menu_x, menu_y, menu_w, row_h * len(ITEMS) + 16),
        PANEL, 10, PANEL_LINE)
for index, (label, is_new, _tip) in enumerate(ITEMS):
    y = menu_y + 8 + index * row_h
    if index == 2:
        rounded(painter, QRect(menu_x + 6, y, menu_w - 12, row_h - 4),
                QColor("#1d3a40"), 6)
    wrapped(painter, label, menu_x + 20, y + 18, menu_w - 40, INK if not is_new else ACCENT, 13, is_new)

tip_x, tip_w = 430, W - 430 - 32
tip_y = menu_y
for label, is_new, tip in ITEMS:
    title = f"Наведение на «{label}»"
    text_height = measure(painter, tip, tip_w - 36, 12)
    height = 46 + 24 + text_height
    rounded(painter, QRect(tip_x, tip_y, tip_w, height), TIP_BG, 10, PANEL_LINE)
    wrapped(painter, title, tip_x + 18, tip_y + 30, tip_w - 36, ACCENT, 12, True)
    wrapped(painter, tip, tip_x + 18, tip_y + 56, tip_w - 36, INK, 12)
    tip_y += height + 14

panel_y = 640
wrapped(painter, "Панель «Оценка» под картинкой: тот же третий вариант отдельной кнопкой",
        32, panel_y - 16, W - 64, MUTED, 12)
rounded(painter, QRect(32, panel_y, W - 64, 76), PANEL, 10, PANEL_LINE)
buttons = [("Перегенерировать", False), ("Убрать фон", False), ("Апскейл заново", True)]
button_x = 52
for label, is_new in buttons:
    width = 210
    rounded(painter, QRect(button_x, panel_y + 22, width, 34),
            QColor("#1d3a40") if is_new else QColor("#263548"), 6, ACCENT if is_new else PANEL_LINE)
    wrapped(painter, label, button_x + 18, panel_y + 44, width - 36, ACCENT if is_new else INK, 13, is_new)
    button_x += width + 14

painter.end()
path = OUT / "меню-переделать-выбранные-20261030.png"
pixmap.save(str(path))
print(path)
