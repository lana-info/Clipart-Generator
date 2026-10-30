"""Макет: страница наборов — кнопки сверху, карандаш и стрелки сортировки в заголовках (владелец 2026-10-30).

Запуск: python render.py <out-папка>
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)

from PyQt6.QtCore import QRect, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

W, H = 1120, 780
BG = QColor("#0f1725")
PANEL = QColor("#172131")
LINE = QColor("#354154")
ACCENT = QColor("#24cabb")
INK = QColor("#e4edf6")
MUTED = QColor("#a6b5c8")
ROW = QColor("#1b2636")
HEAD = QColor("#223045")


def rounded(painter, rect, colour, radius=8, line=None):
    painter.setPen(QPen(line, 1) if line else Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    path = QPainterPath()
    path.addRoundedRect(QRectF(rect), radius, radius)
    painter.drawPath(path)


def text(painter, value, x, y, width, colour=INK, size=13, bold=False, align=Qt.AlignmentFlag.AlignLeft):
    font = QFont(painter.font())
    font.setPixelSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(colour)
    painter.drawText(QRect(x, y, width, size + 10), int(align | Qt.TextFlag.TextSingleLine), value)


def button(painter, x, y, width, label, primary=False):
    rounded(painter, QRect(x, y, width, 32), QColor("#1d3a40") if primary else QColor("#263548"), 6,
            ACCENT if primary else LINE)
    text(painter, label, x + 12, y + 9, width - 24, ACCENT if primary else INK, 13, primary,
         Qt.AlignmentFlag.AlignCenter)


def table(painter, x, y, width, headers, rows, hide_actions=True):
    """headers: (title, glyphs); rows: (name, [ticks])."""
    column = [200] + [max(150, (width - 200) // max(1, len(headers) - 1))] * (len(headers) - 1)
    rounded(painter, QRect(x, y, width, 40), HEAD, 6, LINE)
    cursor = x
    state = {1: True, 2: False, 3: True, 4: False}
    for index, (title, glyphs) in enumerate(headers):
        gap = 10 + 20 * len(glyphs)
        text(painter, title, cursor + 10, y + 12, column[index] - gap, INK if index else MUTED, 13, bool(index))
        marks_x = cursor + column[index] - 10 - 20 * len(glyphs)
        colours = {"✓": ACCENT if state.get(index) else MUTED, "✎": ACCENT, "⇅": ACCENT}
        for glyph in glyphs:
            text(painter, glyph, marks_x, y + 12, 18, colours[glyph], 14, False, Qt.AlignmentFlag.AlignCenter)
            marks_x += 20
        cursor += column[index]
    for position, (name, ticks) in enumerate(rows):
        top = y + 44 + position * 40
        rounded(painter, QRect(x, top, width, 40), ROW, 6)
        text(painter, name, x + 10, top + 12, column[0] - 20, INK, 13)
        cursor = x + column[0]
        for index in range(len(headers) - 1):
            box = QRect(cursor + 10, top + 12, 16, 16)
            painter.setPen(QPen(ACCENT if ticks[index] else LINE, 1))
            painter.setBrush(QColor("#1d3a40") if ticks[index] else Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
            if ticks[index]:
                painter.drawText(box, int(Qt.AlignmentFlag.AlignCenter), "✓")
            cursor += column[index + 1]


def scene(proposed: bool):
    pixmap = QPixmap(W, H)
    pixmap.fill(BG)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    text(painter, "Экспорт наборов", 32, 40, 500, INK, 20, True)
    text(painter, "6 изображений · 4 набора", 32, 78, 400, INK, 13)
    if proposed:
        button(painter, W - 32 - 160 - 12 - 200 - 12 - 170, 68, 170, "+ Добавить набор")
        button(painter, W - 32 - 160 - 12 - 200, 68, 200, "Переименовать набор")
        button(painter, W - 32 - 160, 68, 160, "Удалить набор")
        text(painter, "Кнопки столбцов — вверху справа, в одной горизонтали", 32, 96, 500, MUTED, 11)
    else:
        button(painter, W - 32 - 150, 68, 150, "+ Добавить набор")
        text(painter, "Переименовать и удалить столбец — кнопками под таблицей; "
                      "столбец выбирается нажатием на его заголовок (и не видно, выбран ли)", 32, 96, 700, MUTED, 11)

    headers = [("PNG", [])]
    for title in ("Мини", "Стандарт", "Макси", "Полный"):
        headers.append((title, ["✓", "✎", "⇅"] if proposed else []))
    rows = [("gusenok_01_ready.png", [True, True, False, False]),
            ("gusenok_02_ready.png", [True, False, True, False]),
            ("venok_03_ready.png", [False, True, False, True]),
            ("ramka_04_ready.png", [True, True, True, True])]
    table(painter, 32, 124 if proposed else 120, W - 64, headers, rows)

    if proposed:
        text(painter, "✓ — отметить или снять весь столбец (значок показывает состояние); название столбца ничего не делает",
             32, 380, 900, MUTED, 11)
        text(painter, "✎ — переименовать или удалить этот столбец;  ⇅ — сортировка по отметкам этого столбца",
             32, 398, 900, MUTED, 11)
        # всплывающее меню карандаша
        rounded(painter, QRect(360, 420, 300, 96), PANEL, 8, LINE)
        text(painter, "Переименовать набор…", 376, 436, 260, INK, 13)
        text(painter, "Удалить набор…", 376, 468, 260, INK, 13)
        text(painter, "Меню карандаша в заголовке — то же, что обе кнопки сверху", 360, 528, 340, MUTED, 11)
        # стрелки
        rounded(painter, QRect(700, 420, 388, 96), PANEL, 8, LINE)
        text(painter, "⇅ Отмеченные сверху", 716, 436, 360, ACCENT, 13, True)
        text(painter, "⇅ Неотмеченные сверху", 716, 468, 360, INK, 13)
        text(painter, "Порядок переключается тем же значком", 700, 528, 380, MUTED, 11)
    else:
        text(painter, "Кнопки «Переименовать набор», «Удалить набор» и «⇅ Отметки наверх» — под таблицей",
             32, 380, 900, MUTED, 11)
        for index, label in enumerate(("Переименовать набор", "Удалить набор", "⇅ Отметки наверх")):
            button(painter, 32 + index * 190, 400, 180, label)
        text(painter, "Нажатие на заголовок столбца отмечает весь столбец галочками (случайное нажатие "
                      "ставит галочки везде); что столбец выбран — не видно", 32, 450, 900, MUTED, 11)
    painter.end()
    return pixmap


before = scene(False)
before.save(str(OUT / "наборы-таблица-было.png"))
after = scene(True)
after.save(str(OUT / "наборы-таблица-стало.png"))
print(OUT / "наборы-таблица-стало.png")
