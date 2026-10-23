"""Offline approval mockups for Auto Clipart image marks. No production changes,
no provider requests, no user files.

The transparency check window is the real ClipartTransparencyEditorPage built on
dummy PNGs; the proposed controls are added around it only inside this script.
The results page reuses the shell of the real step 7 screen.
Run: python docs/ui/3.2/autoclipart-image-marks/render_mockups.py
"""
import math
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
OUT = Path(__file__).parent
ROOT = OUT.parents[3]
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFilter
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QVBoxLayout, QWidget,
)

app = QApplication([])
from v3_components import ButtonVariant, V3Button, apply_v3_theme  # noqa: E402
from v3_clipart_flow import ClipartTransparencyEditorPage  # noqa: E402

W, H = 1120, 780
OK, GEN, CUT, DEL = "#24cabb", "#f0c38a", "#b9a3f5", "#8a97a8"
MARKS = (("ok", "Ок", OK), ("gen", "Брак генерации", GEN),
         ("cut", "Брак вырезания", CUT), ("del", "Удалить", DEL))
MARK_TEXT = {key: text for key, text, _ in MARKS}
LIST_TEXT = dict(MARK_TEXT, **{"del": "Удалено"})
MARK_COLOR = {key: color for key, _, color in MARKS}

FILES = (
    ("01_teddy-gifts_ready.png", "ok", ""),
    ("02_goose-flowers_ready.png", "gen", "лишняя лапа, кривой клюв"),
    ("03_garden-basket_ready.png", "cut", "синяя кайма по краю"),
    ("04_christmas-wreath_ready.png", "ok", ""),
    ("05_tea-cup-bow_ready.png", "del", "не подходит к набору"),
)


# --- dummy pictures -----------------------------------------------------------

def _canvas():
    return Image.new("RGBA", (800, 800), (0, 0, 0, 0))


def teddy():
    im = _canvas(); d = ImageDraw.Draw(im)
    brown, light = (176, 118, 72, 255), (232, 196, 150, 255)
    for x in (250, 550):
        d.ellipse((x - 70, 140, x + 70, 280), fill=brown)
    d.ellipse((240, 450, 560, 740), fill=brown)
    d.ellipse((220, 170, 580, 500), fill=brown)
    d.ellipse((330, 330, 470, 450), fill=light)
    d.ellipse((310, 270, 345, 305), fill=(40, 30, 25, 255))
    d.ellipse((455, 270, 490, 305), fill=(40, 30, 25, 255))
    d.ellipse((380, 345, 420, 375), fill=(60, 40, 30, 255))
    d.rectangle((330, 470, 470, 520), fill=(214, 92, 104, 255))
    return im


def goose(defect=True):
    im = _canvas(); d = ImageDraw.Draw(im)
    white, orange = (246, 244, 238, 255), (240, 160, 70, 255)
    d.ellipse((200, 380, 640, 660), fill=white)
    d.line((560, 470, 600, 220), fill=white, width=70)
    d.ellipse((540, 150, 660, 270), fill=white)
    d.polygon(((650, 200), (745, 195 if not defect else 250), (650, 235)), fill=orange)
    d.ellipse((600, 185, 620, 205), fill=(30, 30, 30, 255))
    for x in (360, 470) + ((560,) if defect else ()):
        d.line((x, 640, x, 730), fill=orange, width=16)
        d.polygon(((x - 30, 735), (x + 40, 735), (x, 715)), fill=orange)
    for cx, cy, c in ((190, 560, (230, 110, 130)), (150, 500, (250, 200, 90)), (680, 600, (230, 110, 130))):
        for a in range(0, 360, 72):
            px, py = cx + 26 * math.cos(math.radians(a)), cy + 26 * math.sin(math.radians(a))
            d.ellipse((px - 20, py - 20, px + 20, py + 20), fill=c + (255,))
        d.ellipse((cx - 14, cy - 14, cx + 14, cy + 14), fill=(255, 240, 200, 255))
    return im


def basket(fringe=True):
    im = _canvas(); d = ImageDraw.Draw(im)
    shape = Image.new("L", (800, 800), 0); s = ImageDraw.Draw(shape)
    s.polygon(((170, 400), (630, 400), (570, 690), (230, 690)), fill=255)
    s.arc((230, 170, 570, 560), 180, 360, fill=255, width=34)
    for cx, cy in ((290, 380), (400, 340), (510, 380)):
        s.ellipse((cx - 75, cy - 75, cx + 75, cy + 75), fill=255)
    if fringe:
        halo = shape.filter(ImageFilter.MaxFilter(13))
        blue = Image.new("RGBA", (800, 800), (40, 90, 230, 210))
        im.paste(blue, (0, 0), halo)
    d.polygon(((170, 400), (630, 400), (570, 690), (230, 690)), fill=(176, 122, 70, 255))
    for y in range(430, 690, 34):
        d.line((180, y, 620, y), fill=(140, 92, 50, 255), width=6)
    d.arc((230, 170, 570, 560), 180, 360, fill=(160, 108, 62, 255), width=34)
    for cx, cy, c in ((290, 380, (230, 110, 130)), (400, 340, (250, 200, 90)), (510, 380, (200, 120, 200))):
        d.ellipse((cx - 75, cy - 75, cx + 75, cy + 75), fill=c + (255,))
        d.ellipse((cx - 25, cy - 25, cx + 25, cy + 25), fill=(255, 240, 200, 255))
    if fringe:
        for x, y in ((120, 300), (690, 520), (660, 260), (140, 640)):
            d.ellipse((x, y, x + 14, y + 14), fill=(40, 90, 230, 230))
    return im


def wreath():
    im = _canvas(); d = ImageDraw.Draw(im)
    d.ellipse((140, 140, 660, 660), fill=(52, 128, 78, 255))
    d.ellipse((270, 270, 530, 530), fill=(0, 0, 0, 0))
    for a in range(0, 360, 30):
        x, y = 400 + 195 * math.cos(math.radians(a)), 400 + 195 * math.sin(math.radians(a))
        d.ellipse((x - 18, y - 18, x + 18, y + 18), fill=(208, 50, 60, 255))
    d.polygon(((340, 600), (460, 600), (400, 660)), fill=(208, 50, 60, 255))
    return im


def cup():
    im = _canvas(); d = ImageDraw.Draw(im)
    d.ellipse((150, 600, 650, 700), fill=(236, 176, 190, 255))
    d.rounded_rectangle((220, 330, 560, 640), 60, fill=(240, 150, 170, 255))
    d.arc((500, 380, 680, 560), 270, 90, fill=(240, 150, 170, 255), width=34)
    d.polygon(((330, 300), (400, 340), (330, 380)), fill=(214, 92, 104, 255))
    d.polygon(((470, 300), (400, 340), (470, 380)), fill=(214, 92, 104, 255))
    return im


def make_files(folder):
    makers = (teddy, goose, basket, wreath, cup)
    paths = []
    for (name, _, _), make in zip(FILES, makers):
        path = Path(folder) / name
        make().save(path)
        paths.append(path)
    fixed = Path(folder) / "fixed" / FILES[2][0]
    fixed.parent.mkdir()
    basket(fringe=False).save(fixed)
    good_goose = Path(folder) / "v2" / FILES[1][0]
    good_goose.parent.mkdir()
    goose(defect=False).save(good_goose)
    return paths, fixed, good_goose


# --- small helpers ------------------------------------------------------------

def dot_icon(color, size=14):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color)); painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, size - 2, size - 2)
    painter.end()
    return QIcon(pix)


def thumb(path, size):
    pix = QPixmap(str(path)).scaled(size, size, Qt.AspectRatioMode.KeepAspectRatio,
                                    Qt.TransformationMode.SmoothTransformation)
    label = QLabel()
    label.setFixedSize(size, size)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("background: #e9edf2; border-radius: 6px;")
    label.setPixmap(pix)
    return label


def small(text, color="#a6b5c8", bold=False, size=10):
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color:{color}; background:transparent;")
    font = QFont("DejaVu Sans", size)
    font.setBold(bold)
    label.setFont(font)
    return label


def mark_button(text, color, checked):
    button = QPushButton(text)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setMinimumHeight(30)
    border = color if checked else "#3b4b60"
    background = "#1d3a40" if checked and color == OK else ("#3a3326" if checked and color == GEN else
                 ("#2e2a45" if checked and color == CUT else ("#2b3340" if checked else "#263548")))
    button.setStyleSheet(
        f"QPushButton {{border:1px solid {border}; border-radius:6px; background:{background};"
        f" color:{color if checked else '#e4edf6'}; padding:0 10px; font-weight:{'bold' if checked else 'normal'};}}")
    return button


def save(widget, name):
    widget.resize(W, H)
    widget.show()
    for _ in range(4):
        app.processEvents()
    widget.grab().save(str(OUT / name))
    widget.hide()


# --- transparency window with proposed controls ---------------------------------

def editor_window(paths, selected, *, filter_text="Все (5)", overrides=None, only=None):
    dialog = QDialog()
    dialog.setWindowTitle("Проверка PNG")
    apply_v3_theme(dialog)
    layout = QVBoxLayout(dialog)
    editor = ClipartTransparencyEditorPage()
    layout.addWidget(editor)
    editor.set_files(paths, selected_index=selected)

    # File list: mark dot + second line with the mark and a note sign.
    files = editor.files_frame.layout()
    combo = QComboBox()
    combo.addItems([filter_text])
    combo.setToolTip("Все · Помеченные · Удалённые")
    files.insertWidget(1, combo)
    marks = dict(overrides or {})
    editor.file_list.setSpacing(1)
    for row, (name, mark, note) in enumerate(FILES):
        mark = marks.get(row, mark)
        item = editor.file_list.item(row)
        second = LIST_TEXT[mark] + (" · ✎ заметка" if note and mark != "ok" else "")
        item.setText(f"{name}\n   {second}")
        item.setIcon(dot_icon(MARK_COLOR[mark]))
        if mark == "del":
            item.setForeground(QColor("#738296"))
        item.setHidden(only is not None and mark != only)
    return dialog, editor


def mark_strip(editor, mark, note, actions, status=""):
    strip = QFrame()
    strip.setStyleSheet("QFrame#strip {background:#172131; border-top:1px solid #354154;}")
    strip.setObjectName("strip")
    box = QVBoxLayout(strip)
    box.setContentsMargins(12, 10, 12, 10)
    box.setSpacing(8)
    row = QHBoxLayout(); row.setSpacing(6)
    row.addWidget(small("Оценка", "#e4edf6", bold=True))
    for key, text, color in MARKS:
        row.addWidget(mark_button(text, color, key == mark))
    row.addStretch(1)
    history = QPushButton("История версий (1)" if mark != "gen" else "История версий (2)")
    history.setStyleSheet("QPushButton {border:none; color:#24cabb; background:transparent; text-decoration:underline;}")
    row.addWidget(history)
    box.addLayout(row)
    field = QLineEdit(note)
    field.setPlaceholderText("Заметка: что не так (необязательно)")
    box.addWidget(field)
    if actions or status:
        bottom = QHBoxLayout(); bottom.setSpacing(8)
        if status:
            bottom.addWidget(small(status), 1)
        for widget in actions:
            bottom.addWidget(widget)
        box.addLayout(bottom)
    grid = editor.canvas.parentWidget().layout()
    grid.addWidget(strip, 2, 0)
    return strip


def button(text, variant=ButtonVariant.SECONDARY, width=None):
    item = V3Button(text, variant)
    if width:
        item.setFixedWidth(width)
    return item


def overlay(editor, text, sub):
    grid = editor.canvas.parentWidget().layout()
    shade = QFrame()
    shade.setStyleSheet("QFrame#shade {background: rgba(16,24,39,190);}")
    shade.setObjectName("shade")
    inner = QVBoxLayout(shade)
    inner.addStretch(1)
    title = small(text, "#e4edf6", bold=True, size=15)
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    note = small(sub, "#a6b5c8", size=11)
    note.setAlignment(Qt.AlignmentFlag.AlignCenter)
    inner.addWidget(title); inner.addWidget(note)
    inner.addStretch(1)
    grid.addWidget(shade, 0, 0)


def state_default(paths):
    dialog, editor = editor_window(paths, 0)
    mark_strip(editor, "ok", "", [], "Картинка в порядке. Поставьте метку, если что-то не так — менять ничего не нужно.")
    save(dialog, "01-editor-ok-1120x780.png")


def state_bad_generation(paths):
    dialog, editor = editor_window(paths, 1)
    mark_strip(editor, "gen", "лишняя лапа, кривой клюв",
               [button("Изменить промпт…")],
               "Будет создана заново кнопкой «Пересоздать помеченные» на странице результатов. "
               "Текущая картинка сохранится как версия 1.")
    save(dialog, "02-editor-bad-generation-1120x780.png")


def state_prompt_dialog(paths):
    dialog = QDialog(); apply_v3_theme(dialog)
    dialog.setWindowTitle("Изменить промпт")
    root = QVBoxLayout(dialog); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(12)
    root.addWidget(small("Изменить промпт картинки", "#e4edf6", bold=True, size=15))
    top = QHBoxLayout(); top.setSpacing(16)
    top.addWidget(thumb(paths[1], 220), 0, Qt.AlignmentFlag.AlignTop)
    side = QVBoxLayout(); side.setSpacing(6)
    side.addWidget(small("02_goose-flowers_ready.png · Брак генерации", "#f0c38a", bold=True))
    side.addWidget(small("Заметка: лишняя лапа, кривой клюв"))
    side.addWidget(small("Было", "#e4edf6", bold=True))
    was = QPlainTextEdit("A cute white goose standing among pink and yellow flowers, watercolor clipart, "
                         "soft pastel colors, isolated on solid blue background")
    was.setReadOnly(True); was.setFixedHeight(80)
    side.addWidget(was)
    side.addWidget(small("Новый промпт", "#e4edf6", bold=True))
    new = QPlainTextEdit("A cute white goose with exactly two orange legs and a short straight beak, standing among "
                         "pink and yellow flowers, watercolor clipart, soft pastel colors, isolated on solid blue background")
    new.setFixedHeight(96)
    side.addWidget(new)
    top.addLayout(side, 1)
    root.addLayout(top)
    root.addWidget(small("Промпт сохранится в объекте набора. Генерация не запускается здесь: картинка будет создана "
                         "заново по кнопке «Пересоздать помеченные», с ценой и подтверждением.", size=11))
    root.addStretch(1)
    row = QHBoxLayout(); row.addStretch(1)
    row.addWidget(button("Вернуть исходный", ButtonVariant.GHOST))
    row.addWidget(button("Отмена"))
    row.addWidget(button("Сохранить промпт", ButtonVariant.PRIMARY))
    root.addLayout(row)
    dialog.resize(760, 520)
    holder = backdrop(dialog)
    save(holder, "03-dialog-change-prompt-1120x780.png")


def cutout_controls(trying=False):
    method = QComboBox()
    method.addItems(["Хромакей, бережный режим — бесплатно"])
    method.setMinimumWidth(300)
    method.setToolTip("Хромакей, бережный режим · ИИ на компьютере: мягкий / обычный / резкий край — бесплатно · "
                      "ИИ онлайн (KIE, fal) — платно")
    return [small("Способ:", "#e4edf6"), method,
            button("Попробовать", ButtonVariant.PRIMARY, 140)] if not trying else []


def state_bad_cutout(paths):
    dialog, editor = editor_window(paths, 2)
    editor.canvas.set_background("Белый") if hasattr(editor.canvas, "set_background") else None
    mark_strip(editor, "cut", "синяя кайма по краю", cutout_controls(),
               "Вырезать заново из исходной картинки, без новой генерации.")
    save(dialog, "04-editor-bad-cutout-1120x780.png")


def state_cutout_preview(paths, fixed):
    preview_paths = list(paths)
    preview_paths[2] = fixed
    dialog, editor = editor_window(preview_paths, 2)
    editor.file_list.item(2).setText(f"{FILES[2][0]}\n   Брак вырезания · ✎ заметка")
    mark_strip(editor, "cut", "синяя кайма по краю",
               [button("Отменить"), button("Сравнить с прежним"), button("Оставить новый вариант", ButtonVariant.PRIMARY)],
               "Новый вариант: хромакей, бережный режим. Прежний сохранится как версия 1.")
    title = editor.title_label
    title.setText("Проверка и корректировка прозрачности · предпросмотр нового вырезания")
    save(dialog, "05-editor-cutout-preview-1120x780.png")


def state_cutout_unavailable(paths):
    dialog, editor = editor_window(paths, 2)
    mark_strip(editor, "cut", "синяя кайма по краю",
               [button("Исправить кистью"), button("Отметить как брак генерации", ButtonVariant.PRIMARY)],
               "⚠ Исходная картинка до вырезания уже удалена очисткой рабочих файлов. Вырезать заново не из чего: "
               "исправьте край кистью или пересоздайте картинку.")
    save(dialog, "06-editor-cutout-unavailable-1120x780.png")


def state_deleted(paths):
    dialog, editor = editor_window(paths, 4, filter_text="Удалённые (1)", only="del")
    overlay(editor, "Удалено из набора", "Не попадёт в обзорный лист, PDF и ZIP. Файл не стёрт — можно восстановить.")
    mark_strip(editor, "del", "не подходит к набору", [button("Восстановить", ButtonVariant.PRIMARY, 180)], "Удалено из набора.")
    save(dialog, "07-editor-deleted-1120x780.png")


def state_versions(paths, good_goose):
    dialog = QDialog(); apply_v3_theme(dialog)
    root = QVBoxLayout(dialog); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(12)
    root.addWidget(small("История версий · 02_goose-flowers_ready.png", "#e4edf6", bold=True, size=15))
    root.addWidget(small("В наборы и экспорт идёт только текущая версия. Старые лежат в папке версий набора."))
    cards = QHBoxLayout(); cards.setSpacing(16)
    for path, title, lines, current in (
        (paths[1], "Версия 1", ("Брак генерации", "«лишняя лапа, кривой клюв»", "Промпт: исходный", "22.10 14:05"), False),
        (good_goose, "Версия 2 · текущая", ("Ок", "Промпт: изменён", "22.10 14:31"), True),
    ):
        card = QFrame(); card.setProperty("v3Card", True)
        card.setStyleSheet(f"QFrame {{border:{2 if current else 1}px solid {'#24cabb' if current else '#354154'};"
                           " border-radius:12px; background:#1f2937;} QLabel {border:none;}")
        inner = QVBoxLayout(card); inner.setSpacing(6)
        inner.addWidget(thumb(path, 230), 0, Qt.AlignmentFlag.AlignHCenter)
        inner.addWidget(small(title, "#e4edf6", bold=True, size=12))
        for line in lines:
            inner.addWidget(small(line, GEN if line == "Брак генерации" else "#a6b5c8"))
        if not current:
            inner.addWidget(button("Сделать текущей"))
        else:
            inner.addWidget(small("Используется в наборе", OK, bold=True))
        cards.addWidget(card)
    cards.addStretch(1)
    root.addLayout(cards)
    root.addStretch(1)
    row = QHBoxLayout(); row.addStretch(1)
    row.addWidget(button("Закрыть", ButtonVariant.PRIMARY))
    root.addLayout(row)
    dialog.resize(760, 600)
    save(backdrop(dialog), "08-dialog-versions-1120x780.png")


def backdrop(dialog):
    """Show a dialog centred over a dimmed results page, as it appears in the app."""
    holder = QWidget()
    page = results_page(dim=True)
    page.setParent(holder)
    page.setGeometry(0, 0, W, H)
    shade = QFrame(holder)
    shade.setGeometry(0, 0, W, H)
    shade.setStyleSheet("background: rgba(5,10,20,150);")
    frame = QFrame(holder)
    frame.setStyleSheet("QFrame#dlg {border:1px solid #354154; border-radius:12px;}")
    frame.setObjectName("dlg")
    lay = QVBoxLayout(frame); lay.setContentsMargins(0, 0, 0, 0)
    dialog.setParent(frame); dialog.setWindowFlags(Qt.WindowType.Widget)
    lay.addWidget(dialog)
    size = dialog.size()
    frame.setGeometry((W - size.width()) // 2, (H - size.height()) // 2, size.width(), size.height())
    apply_v3_theme(holder)
    return holder


# --- results page (step 7) ------------------------------------------------------

def results_page(dim=False, paths=None):
    page = QWidget(); apply_v3_theme(page)
    page.setStyleSheet(page.styleSheet() + " QWidget#bg {background:#101827;}")
    root = QVBoxLayout(page); root.setContentsMargins(24, 24, 24, 24); root.setSpacing(16)
    header = QFrame(); header.setProperty("v3Card", True)
    hl = QHBoxLayout(header); hl.setContentsMargins(16, 14, 16, 14)
    title = small("Автоматический Clipart", "#eef2f7", bold=True, size=15)
    title.setWordWrap(False)
    hl.addWidget(title); hl.addStretch(1)
    for text in ("Сменить режим", "Настройки API", "Диагностика"):
        ghost = button(text, ButtonVariant.GHOST)
        ghost.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hl.addWidget(ghost)
    root.addWidget(header)
    body = QHBoxLayout(); body.setSpacing(16)
    steps = QFrame(); steps.setProperty("v3Card", True); steps.setFixedWidth(240)
    sl = QVBoxLayout(steps); sl.setContentsMargins(16, 14, 16, 14); sl.setSpacing(6)
    sl.addWidget(small("Шаги", "#eef2f7", bold=True, size=15))
    for text in ("1. Идея", "2. Визуальное направление", "3. Референсы", "4. Структура набора",
                 "5. Объекты", "6. Промпты и запуск"):
        sl.addWidget(small("✓ " + text, OK, bold=True))
    sl.addWidget(small("● 7. Проверка", OK, bold=True))
    sl.addWidget(small("○ 8. Экспорт", "#a6b5c8", size=11))
    sl.addStretch(1)
    body.addWidget(steps)
    main = QFrame(); main.setProperty("v3Card", True)
    ml = QVBoxLayout(main); ml.setContentsMargins(16, 14, 16, 14); ml.setSpacing(10)
    ml.addWidget(small("Выполнение и результаты", "#eef2f7", bold=True, size=15))
    ml.addWidget(small("Обработано: 5 · Ошибки: 0 · Всего: 5. Помечено: брак генерации 1, брак вырезания 1, удалено 1.",
                       "#e4edf6", bold=True))
    filt = QHBoxLayout()
    filt.addWidget(small("Показать:", "#e4edf6"))
    combo = QComboBox(); combo.addItems(["Все (5)"]); combo.setFixedWidth(170)
    filt.addWidget(combo)
    legend = small("● Ок   ● Брак генерации   ● Брак вырезания   ● Удалено", "#a6b5c8")
    legend.setText(f"<span style='color:{OK}'>●</span> Ок &nbsp; <span style='color:{GEN}'>●</span> Брак генерации "
                   f"&nbsp; <span style='color:{CUT}'>●</span> Брак вырезания &nbsp; "
                   f"<span style='color:{DEL}'>●</span> Удалено")
    legend.setTextFormat(Qt.TextFormat.RichText)
    legend.setWordWrap(False)
    filt.addSpacing(12); filt.addWidget(legend); filt.addStretch(1)
    ml.addLayout(filt)
    queue = QListWidget()
    queue.setSpacing(2)
    for index, (name, mark, note) in enumerate(FILES):
        text = f"{index + 1}. {name} — готово · {LIST_TEXT[mark]}"
        if note and mark != "ok":
            text += f" · ✎ {note}"
        if mark == "gen":
            text += " · промпт изменён"
        item = QListWidgetItem(dot_icon(MARK_COLOR[mark]), text)
        if mark == "del":
            item.setForeground(QColor("#738296"))
        queue.addItem(item)
    ml.addWidget(queue, 1)
    ml.addWidget(small("«Пересоздать помеченные»: брак генерации — новая платная генерация (цена в подтверждении); "
                       "брак вырезания без выбранного способа — бесплатное повторное вырезание бережным режимом. "
                       "Прежние картинки сохраняются как версии."))
    actions = QHBoxLayout(); actions.setSpacing(8)
    actions.addWidget(button("Проверить PNG"))
    actions.addWidget(button("Пересоздать помеченные (2)", ButtonVariant.PRIMARY))
    actions.addStretch(1)
    actions.addWidget(button("Корзина (1)"))
    actions.addWidget(button("Открыть папку с результатами"))
    ml.addLayout(actions)
    body.addWidget(main, 1)
    root.addLayout(body, 1)
    footer = QFrame(); footer.setProperty("v3Card", True)
    fl = QHBoxLayout(footer); fl.setContentsMargins(16, 12, 16, 12); fl.addStretch(1)
    fl.addWidget(button("Назад")); fl.addWidget(button("К экспорту", ButtonVariant.PRIMARY))
    root.addWidget(footer)
    page.resize(W, H)
    return page


def state_results():
    save(results_page(), "09-results-marked-1120x780.png")


def confirm_dialog(title, lines, yes, no="Отмена", destructive=False):
    dialog = QDialog(); apply_v3_theme(dialog)
    root = QVBoxLayout(dialog); root.setContentsMargins(24, 20, 24, 20); root.setSpacing(10)
    root.addWidget(small(title, "#e4edf6", bold=True, size=15))
    for line in lines:
        root.addWidget(small(line, "#e4edf6", size=11))
    root.addStretch(1)
    row = QHBoxLayout(); row.addStretch(1)
    row.addWidget(button(no))
    row.addWidget(button(yes, ButtonVariant.DESTRUCTIVE if destructive else ButtonVariant.PRIMARY))
    root.addLayout(row)
    dialog.resize(620, 330)
    return dialog


def state_confirm():
    dialog = confirm_dialog("Пересоздать помеченные: 2?", (
        "• Брак генерации — 1: 02_goose-flowers (промпт изменён). Новая генерация, платно.",
        "  Стоимость: ≈ $0.04 · Модель: как в наборе.",
        "• Брак вырезания — 1: 03_garden-basket. Повторное вырезание бережным режимом, бесплатно.",
        "Текущие картинки не удаляются: они станут версиями и их можно вернуть.",
    ), "Пересоздать")
    save(backdrop(dialog), "10-dialog-regenerate-confirm-1120x780.png")


def state_trash():
    dialog = confirm_dialog("Очистить корзину?", (
        "Будут окончательно стёрты с диска:",
        "• удалённые картинки — 1 (05_tea-cup-bow);",
        "• старые версии — 2 (их нельзя будет вернуть).",
        "Текущие картинки наборов не затрагиваются.",
    ), "Стереть 3 файла", destructive=True)
    save(backdrop(dialog), "11-dialog-empty-trash-1120x780.png")


def main():
    with tempfile.TemporaryDirectory() as folder:
        paths, fixed, good_goose = make_files(folder)
        state_default(paths)
        state_bad_generation(paths)
        state_prompt_dialog(paths)
        state_bad_cutout(paths)
        state_cutout_preview(paths, fixed)
        state_cutout_unavailable(paths)
        state_deleted(paths)
        state_versions(paths, good_goose)
        state_results()
        state_confirm()
        state_trash()


if __name__ == "__main__":
    main()
    os._exit(0)  # offscreen Qt may crash in teardown; files are already written
