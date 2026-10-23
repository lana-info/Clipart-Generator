"""Patterns module page: five steps (source, settings, preview, set, export).

The page only draws widgets and holds the user's choices.  Files, projects,
background rendering and writing to disk all go through the Core ``host``; the
engine is never imported here.  Layout follows docs/ui/3.2/patterns-module-proposal.
"""
from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QMessageBox, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)
from v3_components import ButtonVariant, DEFAULT_TOKENS, V3Button, apply_v3_theme

STEPS = ("Источник", "Настройки", "Предпросмотр", "Набор", "Экспорт")
LAYOUTS = (("Обычная", "straight"), ("Half-drop", "half_column"), ("Brick", "half_row"), ("Зеркало", "mirror"))
SIZES = (("12 × 12", 12.0), ("8 × 8", 8.0), ("6 × 6", 6.0), ("Свой", None))
DPI = 300
MAX_FOLDER_FILES = 200
MAX_SHEETS = 12
STATUS_TEXT = {"ready": "Ready", "review": "Review", "fail": "Fail"}
DEFAULTS = {
    "layout": "straight", "inches": 12.0, "background": [250, 244, 232, 255], "transparent": False,
    "count": 14, "gap": 40, "size_percent": 12, "angle": 30, "seed": 4, "band": 20,
    "sheet_count": 6, "vary": "seed", "format": "png", "set_name": "Новый набор",
}


def _qpixmap(image, width, height):
    image = image.convert("RGBA")
    qimage = QImage(image.tobytes(), image.width, image.height, image.width * 4,
                    QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage).scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation)


def _restyle(widget):
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _clear(layout):
    """Remove widgets at once; deleteLater alone leaves ghosts until the event loop runs."""
    while layout.count():
        widget = layout.takeAt(0).widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _text(value, prop=None, wrap=True):
    label = QLabel(str(value))
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(wrap)
    if prop:
        label.setProperty(prop, True)
    return label


def _card(title=None):
    frame = QFrame()
    frame.setProperty("v3Card", True)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(DEFAULT_TOKENS.space_4, DEFAULT_TOKENS.space_4, DEFAULT_TOKENS.space_4, DEFAULT_TOKENS.space_4)
    layout.setSpacing(DEFAULT_TOKENS.space_3)
    if title:
        layout.addWidget(_text(title, "v3Title"))
    return frame, layout


def _status(text, state):
    label = _text(text, "v3Status", wrap=True)
    _set_state(label, state)
    return label


def _set_state(label, state):
    """warning/error come from the v3 theme; "ok" is drawn here with the accent colours."""
    label.setProperty("state", state)
    tokens = DEFAULT_TOKENS
    label.setStyleSheet(f"color:{tokens.accent}; background:{tokens.accent_soft}; border:1px solid {tokens.accent};"
                        if state == "ok" else "")
    _restyle(label)


class Chips(QWidget):
    """A row or grid of mutually exclusive choices; selected = filled, disabled = grey."""

    changed = pyqtSignal(str)

    def __init__(self, options, columns=4, parent=None):
        super().__init__(parent)
        self._buttons = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(DEFAULT_TOKENS.space_2)
        for index, (label, key) in enumerate(options):
            button = V3Button(label, ButtonVariant.SECONDARY)
            button.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            self._buttons[key] = button
            grid.addWidget(button, index // columns, index % columns)

    def set_value(self, key):
        for name, button in self._buttons.items():
            button.set_variant(ButtonVariant.PRIMARY if name == key else ButtonVariant.SECONDARY)

    def set_enabled_keys(self, enabled):
        for key, button in self._buttons.items():
            button.setEnabled(key in enabled)


class SheetTile(QFrame):
    clicked = pyqtSignal(int)

    def __init__(self, index, sheet):
        super().__init__()
        self.index = index
        self.setProperty("v3Card", True)
        layout = QVBoxLayout(self)
        layout.setSpacing(DEFAULT_TOKENS.space_2)
        picture = QLabel()
        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        picture.setPixmap(_qpixmap(sheet["thumb"], 150, 150))
        layout.addWidget(picture)
        row = QHBoxLayout()
        row.addWidget(_text(f"Лист {index + 1}", "v3Small"))
        state = {"ready": None, "review": "warning", "fail": "error"}[sheet["status"]]
        mark = _text(STATUS_TEXT[sheet["status"]] + ("" if sheet["included"] else " · не входит"), "v3Small")
        if state:
            mark.setProperty("v3Status", True)
            mark.setProperty("state", state)
        row.addWidget(mark)
        layout.addLayout(row)

    def mousePressEvent(self, event):
        self.clicked.emit(self.index)
        super().mousePressEvent(event)


class PatternsPage(QWidget):
    back_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    diagnostics_requested = pyqtSignal()

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.tokens = DEFAULT_TOKENS
        self.setObjectName("patternsPage")
        self.setMinimumSize(980, 700)
        apply_v3_theme(self, self.tokens)
        self._mode = "pngs"
        self._assets, self._tile = [], None
        self._settings = dict(DEFAULTS)
        self._elements = []
        self._sheets = []
        self._selected = None
        self._current = None
        self._render_key = None
        self._layout_dirty = True
        self._busy = False
        self._export_folder = None
        self._project_id = self._revision = None
        self._step = 0
        self._generation = 0
        self._build()
        self._restore()
        self._refresh()

    # ------------------------------------------------------------- building

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(*(self.tokens.space_6,) * 4)
        root.setSpacing(self.tokens.space_4)
        # П1 (owner 2026-10-23): no plaque with «Главная Studio / Настройки API / Диагностика» — the Studio header
        # already has them. The set name stays available to the code, but is not shown here.
        self.title = _text("Patterns", "v3Title", wrap=False)
        self.title.setParent(self)
        self.title.hide()
        body = QHBoxLayout()
        body.setSpacing(self.tokens.space_4)
        side, side_layout = _card("Шаги")
        side.setFixedWidth(240)
        self.step_labels = []
        for _ in STEPS:
            label = _text("")
            self.step_labels.append(label)
            side_layout.addWidget(label)
        side_layout.addStretch()
        body.addWidget(side)
        self.stack = QStackedWidget()
        for builder in (self._build_source, self._build_settings, self._build_preview,
                        self._build_set, self._build_export):
            self.stack.addWidget(builder())
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)
        foot, foot_layout = _card()
        row = QHBoxLayout()
        self.note = _text("Платных запросов нет.", "v3Small")
        row.addWidget(self.note, 1)
        self.back_button = V3Button("Назад", ButtonVariant.SECONDARY)
        self.back_button.clicked.connect(self._go_back)
        self.next_button = V3Button("Далее", ButtonVariant.PRIMARY)
        self.next_button.clicked.connect(self._go_next)
        row.addWidget(self.back_button)
        row.addWidget(self.next_button)
        foot_layout.addLayout(row)
        root.addWidget(foot)

    def _page(self, title, subtitle):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(self.tokens.space_3)
        layout.addWidget(_text(title, "v3Title"))
        layout.addWidget(_text(subtitle, "v3Description"))
        return page, layout

    def _slider(self, key, low, high, name, formatter):
        label_row = QHBoxLayout()
        name_label = _text(name)
        value_label = _text("", "v3Selection", wrap=False)
        label_row.addWidget(name_label, 1)
        label_row.addWidget(value_label)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(low, high)
        slider.setValue(self._settings[key])

        def changed(value):
            self._settings[key] = value
            value_label.setText(formatter(value))
            self._invalidate(layout=key in ("count", "gap", "size_percent", "angle"))
        slider.valueChanged.connect(changed)
        value_label.setText(formatter(self._settings[key]))
        box = QVBoxLayout()
        box.setSpacing(self.tokens.space_1)
        box.addLayout(label_row)
        box.addWidget(slider)
        return box, slider

    # ------------------------------------------------------------ step 1

    def _build_source(self):
        page, layout = self._page("Откуда берём рисунок", "Выберите, из чего собрать бесшовный узор. Ваши файлы не изменяются.")
        cards = QHBoxLayout()
        self.mode_cards = {}
        for key, name, text in (("pngs", "Из ваших PNG", "Раскладываем рисунки на листе. Шов бесшовный по построению."),
                                ("tile", "Из готовой плитки", "Загрузите плитку: мы сделаем шов незаметным и проверим его.")):
            card, card_layout = _card()
            card_layout.addWidget(_text(name, "v3Title"))
            card_layout.addWidget(_text(text, "v3Small"))
            card.mousePressEvent = lambda _event, k=key: self._set_mode(k)
            self.mode_cards[key] = card
            cards.addWidget(card)
        layout.addLayout(cards)
        self.source_title = _text("", "v3Title")
        layout.addWidget(self.source_title)
        self.source_list, source_layout = _card()
        self.source_grid = QGridLayout()
        self.source_grid.setSpacing(self.tokens.space_2)
        source_layout.addLayout(self.source_grid)
        self.source_empty = _text("Пока нет файлов. Добавьте PNG с прозрачным фоном: цветы, листья, любые элементы.", "v3Description")
        source_layout.addWidget(self.source_empty)
        layout.addWidget(self.source_list, 1)
        row = QHBoxLayout()
        self.add_files = V3Button("Добавить PNG", ButtonVariant.SECONDARY)
        self.add_files.clicked.connect(self._pick_files)
        self.add_folder = V3Button("Добавить папку", ButtonVariant.SECONDARY)
        self.add_folder.clicked.connect(self._pick_folder)
        self.pick_tile = V3Button("Выбрать файл", ButtonVariant.SECONDARY)
        self.pick_tile.clicked.connect(self._pick_tile)
        for button in (self.add_files, self.add_folder, self.pick_tile):
            row.addWidget(button)
        row.addStretch()
        layout.addLayout(row)
        self.checks = QVBoxLayout()
        layout.addLayout(self.checks)
        return page

    def _set_mode(self, mode):
        if mode != self._mode:
            self._mode = mode
            self._sheets, self._selected, self._current = [], None, None
            self._invalidate(layout=True)
            self._refresh()

    def _import(self, paths):
        records, problems = [], []
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for path in paths:
                try:
                    records.append({**self.host.import_png(path), "name": Path(path).name})
                except (ValueError, OSError) as error:
                    if hasattr(error, "width") and self._offer_smaller_copy(path, error):
                        try:
                            records.append({**self.host.import_png_downscaled(path), "name": Path(path).name})
                            continue
                        except (ValueError, OSError) as second:
                            error = second
                    elif hasattr(error, "width"):
                        continue  # the user chose to skip it
                    problems.append(f"{Path(path).name} — {error}")
        finally:
            QApplication.restoreOverrideCursor()
        if problems:
            QMessageBox.warning(self, "Паттерны", "Не удалось добавить файлы:\n" + "\n".join(problems[:5])
                                + ("\n…" if len(problems) > 5 else ""))
        return records

    def _offer_smaller_copy(self, path, error):
        """П8: the PNG is too large — show its size and offer a smaller copy (the source file is not changed)."""
        if not hasattr(self.host, "import_png_downscaled"):
            return False  # an older Studio without the smaller-copy import
        QApplication.restoreOverrideCursor()
        try:
            box = QMessageBox(self)
            box.setWindowTitle("Паттерны")
            box.setText("Файл слишком большой для узора")
            box.setInformativeText(f"{Path(path).name} — {error.width} × {error.height} px.\n{error}.\n\n"
                                   "Можно добавить уменьшенную копию — её хватит для листа 12 × 12 дюймов при 300 DPI. "
                                   "Исходный файл не меняется.")
            add = box.addButton("Добавить уменьшенную копию", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Пропустить файл", QMessageBox.ButtonRole.RejectRole)
            box.exec()
            return box.clickedButton() is add
        finally:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

    def _pick_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Добавить PNG", "", "PNG (*.png)")
        self._add_assets(paths)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Папка с PNG")
        if folder:
            paths = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() == ".png" and p.is_file() and not p.is_symlink())
            self._add_assets([str(p) for p in paths[:MAX_FOLDER_FILES]])

    def _add_assets(self, paths):
        known = {a["handle"]["asset_id"] for a in self._assets}
        for record in self._import(paths):
            if record["handle"]["asset_id"] not in known:
                known.add(record["handle"]["asset_id"])
                self._assets.append(record)
        self._invalidate(layout=True)
        self._refresh()

    def _pick_tile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Готовая плитка", "", "PNG (*.png)")
        if path:
            records = self._import([path])
            if records:
                self._tile = records[0]
                self._current = None
                self._invalidate()
                self._refresh()

    # ------------------------------------------------------------ step 2

    def _build_settings(self):
        page, layout = self._page("Настройте узор", "Измените параметры и пересоберите лист. Результат воспроизводим по seed.")
        columns = QHBoxLayout()
        left, left_layout = _card()
        left_layout.addWidget(_text("Раскладка", "v3Title"))
        self.layout_chips = Chips(LAYOUTS, columns=2)
        self.layout_chips.changed.connect(self._set_layout)
        left_layout.addWidget(self.layout_chips)
        self.layout_hint = _text("Half-drop и Brick сдвигают соседние ряды на половину листа, как кирпичная кладка.", "v3Small")
        left_layout.addWidget(self.layout_hint)
        left_layout.addWidget(_text("Размер листа (дюймы)", "v3Title"))
        self.size_chips = Chips([(label, label) for label, _ in SIZES], columns=2)
        self.size_chips.changed.connect(self._set_size)
        left_layout.addWidget(self.size_chips)
        self.size_hint = _text("", "v3Small")
        left_layout.addWidget(self.size_hint)
        left_layout.addWidget(_text("Фон", "v3Title"))
        row = QHBoxLayout()
        self.background_swatch = QLabel()
        self.background_swatch.setFixedSize(44, 34)
        self.background_swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.background_swatch.setToolTip("Выбрать цвет фона")
        self.background_swatch.mousePressEvent = lambda _event: self._pick_background()
        row.addWidget(self.background_swatch)
        self.background_name = _text("Тёплый белый")
        row.addWidget(self.background_name, 1)
        self.transparent_button = V3Button("Прозрачный", ButtonVariant.SECONDARY)
        self.transparent_button.clicked.connect(self._toggle_transparent)
        row.addWidget(self.transparent_button)
        left_layout.addLayout(row)
        left_layout.addWidget(_text("Фон попадёт в итоговый файл. «Прозрачный» — только для PNG.", "v3Small"))
        left_layout.addStretch()
        columns.addWidget(left, 1)
        right, right_layout = _card()
        self.right_title = _text("Расстановка", "v3Title")
        right_layout.addWidget(self.right_title)
        self.png_controls = QWidget()
        pc = QVBoxLayout(self.png_controls)
        pc.setContentsMargins(0, 0, 0, 0)
        for key, low, high, name, fmt in (
                ("count", 1, 60, "Количество элементов", lambda v: str(v)),
                ("gap", 0, 300, "Зазор между элементами", lambda v: f"{v} px"),
                ("size_percent", 3, 40, "Размер элементов", lambda v: f"{v} % листа"),
                ("angle", 0, 180, "Поворот", lambda v: f"±{v}°")):
            box, _ = self._slider(key, low, high, name, fmt)
            pc.addLayout(box)
        seed_row = QHBoxLayout()
        seed_row.addWidget(_text("Seed (воспроизводимость)"), 1)
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(self._settings["seed"])
        self.seed_spin.valueChanged.connect(lambda v: (self._settings.__setitem__("seed", v), self._invalidate(layout=True)))
        seed_row.addWidget(self.seed_spin)
        pc.addLayout(seed_row)
        buttons = QHBoxLayout()
        self.pin_button = V3Button("Закрепить", ButtonVariant.SECONDARY)
        self.pin_button.clicked.connect(self._toggle_pin)
        self.reroll_button = V3Button("Пересобрать", ButtonVariant.SECONDARY)
        self.reroll_button.clicked.connect(self._reroll)
        buttons.addWidget(self.pin_button)
        buttons.addWidget(self.reroll_button)
        pc.addLayout(buttons)
        self.layout_note = _text("Если места не хватает, покажем, сколько элементов поставлено из запрошенных.", "v3Small")
        pc.addWidget(self.layout_note)
        right_layout.addWidget(self.png_controls)
        self.tile_controls = QWidget()
        tc = QVBoxLayout(self.tile_controls)
        tc.setContentsMargins(0, 0, 0, 0)
        box, self.band_slider = self._slider("band", 5, 50, "Ширина полосы смешивания", lambda v: f"{v} %")
        tc.addLayout(box)
        tc.addWidget(_text("Шире полоса: шов мягче, но на детальном рисунке возможно двоение. Уже полоса: детали сохраняются.", "v3Small"))
        self.apply_button = V3Button("Применить и проверить шов", ButtonVariant.PRIMARY)
        self.apply_button.clicked.connect(self._go_next)
        tc.addWidget(self.apply_button)
        tc.addWidget(_text("Результат получит оценку Ready, Review или Fail. Идеальный шов для любого рисунка мы не обещаем.", "v3Small"))
        right_layout.addWidget(self.tile_controls)
        right_layout.addStretch()
        columns.addWidget(right, 1)
        layout.addLayout(columns, 1)
        return page

    def _set_layout(self, key):
        self._settings["layout"] = key
        self._invalidate(layout=True)
        self._refresh()

    def _set_size(self, label):
        inches = dict(SIZES)[label]
        if inches is None:
            value, ok = QInputDialog.getDouble(self, "Свой размер", "Сторона листа, дюймы:", self._settings["inches"], 1.0, 27.0, 1)
            if not ok:
                return
            inches = value
        old = self._settings["inches"]
        self._settings["inches"] = float(inches)
        if self._mode == "pngs":
            ratio = inches / old
            self._elements = [{**e, "x": e["x"] * ratio, "y": e["y"] * ratio, "scale": e["scale"] * ratio}
                              for e in self._elements]
        self._invalidate(layout=True)
        self._refresh()

    def _pick_background(self):
        from PyQt6.QtGui import QColor
        from PyQt6.QtWidgets import QColorDialog
        colour = QColorDialog.getColor(QColor(*self._settings["background"][:3]), self, "Цвет фона")
        if colour.isValid():
            self._settings["background"] = [colour.red(), colour.green(), colour.blue(), 255]
            self._settings["transparent"] = False
            self._invalidate()
            self._refresh()

    def _toggle_transparent(self):
        self._settings["transparent"] = not self._settings["transparent"]
        self._invalidate()
        self._refresh()

    def _toggle_pin(self):
        locked = not all(e.get("locked") for e in self._elements)
        self._elements = [{**e, "locked": locked} for e in self._elements]
        self._invalidate()
        self._refresh()

    def _reroll(self):
        self._settings["seed"] = (self._settings["seed"] + 1) % 1_000_000
        self.seed_spin.setValue(self._settings["seed"])
        self._invalidate(layout=True)

    # ------------------------------------------------------------ step 3

    def _build_preview(self):
        page, layout = self._page("Проверьте повтор", "Узор показан 3 × 3. Стык листов находится в центре картинки.")
        self.preview_title, self.preview_subtitle = layout.itemAt(0).widget(), layout.itemAt(1).widget()
        columns = QHBoxLayout()
        left, left_layout = _card()
        self.preview_picture = QLabel()
        self.preview_picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_picture.setMinimumSize(380, 380)
        left_layout.addWidget(self.preview_picture, 1)
        row = QHBoxLayout()
        self.zoom_button = V3Button("Увеличить шов", ButtonVariant.SECONDARY)
        self.zoom_button.clicked.connect(self._zoom_seam)
        row.addWidget(self.zoom_button)
        row.addWidget(_text("Линии границ: выключены", "v3Small"), 1)
        left_layout.addLayout(row)
        columns.addWidget(left, 3)
        right, right_layout = _card("Оценка шва")
        self.seam_status = _status("", "warning")
        right_layout.addWidget(self.seam_status)
        self.seam_numbers = _text("")
        right_layout.addWidget(self.seam_numbers)
        right_layout.addWidget(_text("Оценка: скачок на стыке относительно обычных переходов внутри рисунка. Меньше — лучше.", "v3Small"))
        right_layout.addStretch()
        self.primary_action = V3Button("Добавить лист в набор", ButtonVariant.PRIMARY)
        self.primary_action.clicked.connect(self._primary)
        self.secondary_action = V3Button("Пересобрать с другим seed", ButtonVariant.SECONDARY)
        self.secondary_action.clicked.connect(self._secondary)
        right_layout.addWidget(self.primary_action)
        right_layout.addWidget(self.secondary_action)
        columns.addWidget(right, 2)
        layout.addLayout(columns, 1)
        return page

    def _zoom_seam(self):
        if self._current is None:
            return
        picture = self.host.preview_image(self._current["image"], 3, 2_000_000)
        half = min(picture.width, picture.height) // 6
        centre = picture.crop((picture.width // 2 - half, picture.height // 2 - half,
                               picture.width // 2 + half, picture.height // 2 + half))
        dialog = QDialog(self)
        dialog.setWindowTitle("Шов в центре, увеличено")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        label.setPixmap(_qpixmap(centre, 560, 560))
        layout.addWidget(label)
        dialog.exec()

    def _primary(self):
        status = self._current["seam"]["status"] if self._current else None
        if status == "fail":
            if self._mode == "tile":
                if self._settings["band"] >= 50:
                    QMessageBox.information(self, "Patterns", "Ширина полосы уже максимальная. Оставьте как есть или выберите другую плитку.")
                    return
                self._settings["band"] = min(50, self._settings["band"] + 10)
                self.band_slider.setValue(self._settings["band"])
                self._render_current()
            else:
                self._reroll()
                self._render_current()
        else:
            self._add_current()

    def _secondary(self):
        if self._current and self._current["seam"]["status"] == "fail":
            self._add_current(forced=True)  # «Оставить как есть (Review)»
        else:
            self._reroll()
            self._render_current()

    def _add_current(self, forced=False):
        if self._current is None:
            return
        self._sheets.append(self._sheet_from(self._current, forced=forced))
        self._selected = len(self._sheets) - 1
        self._goto(3)

    def _sheet_from(self, result, forced=False, auto=False):
        """A set entry.  A Review sheet is exported only when the user chose it (not when auto-generated);
        a sheet kept as is despite Fail counts as Review."""
        thumb = result["image"].copy()
        thumb.thumbnail((200, 200))
        status = result["seam"]["status"]
        if forced and status == "fail":
            status = "review"
        return {"image": result["image"], "seam": result["seam"], "status": status, "thumb": thumb,
                "included": status == "ready" or (not auto and status == "review"), "seed": self._settings["seed"], "elements": list(self._elements)}

    # ------------------------------------------------------------ step 4

    def _build_set(self):
        page, layout = self._page("Соберите набор листов", "Каждый лист — отдельный файл. Статус показывает, можно ли продавать его как бесшовный.")
        columns = QHBoxLayout()
        left, left_layout = _card()
        self.set_grid = QGridLayout()
        self.set_grid.setSpacing(self.tokens.space_3)
        left_layout.addLayout(self.set_grid)
        left_layout.addStretch()
        columns.addWidget(left, 3)
        right, right_layout = _card("Параметры набора")
        self.count_box, self.count_slider = self._slider("sheet_count", 1, MAX_SHEETS, "Листов", lambda v: str(v))
        right_layout.addLayout(self.count_box)
        self.vary_chips = Chips([("Разные seed", "seed"), ("Разные раскладки", "layout")], columns=1)
        self.vary_chips.changed.connect(self._set_vary)
        right_layout.addWidget(self.vary_chips)
        self.set_note = _text("", "v3Small")
        right_layout.addWidget(self.set_note)
        right_layout.addStretch()
        self.reroll_sheet = V3Button("Пересобрать выбранный", ButtonVariant.SECONDARY)
        self.reroll_sheet.clicked.connect(self._reroll_selected)
        right_layout.addWidget(self.reroll_sheet)
        columns.addWidget(right, 2)
        layout.addLayout(columns, 1)
        return page

    def _set_vary(self, key):
        self._settings["vary"] = key
        self._refresh()

    def _select_sheet(self, index):
        self._selected = index
        self._refresh()

    def _variant(self, index):
        """Settings for sheet ``index`` of a generated set (the first is the user's own)."""
        layouts = [key for _, key in LAYOUTS]
        base = layouts.index(self._settings["layout"])
        layout = layouts[(base + index) % len(layouts)] if self._settings["vary"] == "layout" else self._settings["layout"]
        return layout, (self._settings["seed"] + index) % 1_000_000

    def _fill_sheets(self):
        """Render missing sheets one after another until the set has the requested size."""
        if self._busy or self._mode == "tile" or not self._sheets:
            return
        target, token = self._settings["sheet_count"], self._generation
        if len(self._sheets) >= target:
            return
        index = len(self._sheets)
        layout, seed = self._variant(index)
        self._busy = True
        self._refresh()
        try:
            elements = self._relayout(layout=layout, seed=seed)
            payload = self._payload(layout=layout, seed=seed, elements=elements)
        except ValueError as error:
            self._busy = False
            self._show_error(str(error))
            return

        def done(result):
            if token != self._generation:
                return
            self._busy = False
            self._sheets.append({**self._sheet_from(result, auto=True), "seed": seed, "elements": elements})
            self._refresh()
            self._fill_sheets()

        def failed(message):
            if token == self._generation:
                self._busy = False
                self._show_error(message)
                self._refresh()
        self.host.render_sheet(payload, done, failed)

    def _reroll_selected(self):
        if self._selected is None or self._busy or self._mode == "tile":
            return
        index, token = self._selected, self._generation
        seed = (max(s["seed"] for s in self._sheets) + 1) % 1_000_000
        layout = self._settings["layout"]
        self._busy = True
        self._refresh()
        try:
            elements = self._relayout(layout=layout, seed=seed)
            payload = self._payload(layout=layout, seed=seed, elements=elements)
        except ValueError as error:
            self._busy = False
            self._show_error(str(error))
            return

        def done(result):
            if token == self._generation and index < len(self._sheets):
                self._sheets[index] = {**self._sheet_from(result, auto=True), "seed": seed, "elements": elements}
            self._busy = False
            self._refresh()

        def failed(message):
            self._busy = False
            self._show_error(message)
            self._refresh()
        self.host.render_sheet(payload, done, failed)

    # ------------------------------------------------------------ step 5

    def _build_export(self):
        page, layout = self._page("Экспортируйте листы", "Выберите папку: файлы появятся в ней. Существующие файлы не перезаписываются молча.")
        columns = QHBoxLayout()
        left, left_layout = _card()
        left_layout.addWidget(_text("Формат и размер", "v3Title"))
        self.format_chips = Chips([("PNG", "png"), ("JPG", "jpg")], columns=2)
        self.format_chips.changed.connect(self._set_format)
        left_layout.addWidget(self.format_chips)
        self.export_size_chips = Chips([(label, label) for label, _ in SIZES], columns=4)
        self.export_size_chips.changed.connect(self._set_size)
        left_layout.addWidget(self.export_size_chips)
        self.export_hint = _text("", "v3Small")
        left_layout.addWidget(self.export_hint)
        left_layout.addWidget(_text("Папка для сохранения", "v3Title"))
        self.folder_label = _status("Папка не выбрана", "warning")
        left_layout.addWidget(self.folder_label)
        self.folder_button = V3Button("Выбрать папку…", ButtonVariant.PRIMARY)
        self.folder_button.clicked.connect(self._pick_export_folder)
        left_layout.addWidget(self.folder_button)
        left_layout.addWidget(_text("Имя набора", "v3Title"))
        self.name_edit = QLineEdit(self._settings["set_name"])
        self.name_edit.setMaxLength(100)
        self.name_edit.textChanged.connect(lambda t: (self._settings.__setitem__("set_name", t), self._refresh_export()))
        left_layout.addWidget(self.name_edit)
        self.name_hint = _text("", "v3Small")
        left_layout.addWidget(self.name_hint)
        left_layout.addStretch()
        columns.addWidget(left, 3)
        right, right_layout = _card("Что будет сохранено")
        self.summary = _text("")
        right_layout.addWidget(self.summary)
        self.export_warning = _status("", "warning")
        right_layout.addWidget(self.export_warning)
        right_layout.addStretch()
        columns.addWidget(right, 2)
        layout.addLayout(columns, 1)
        return page

    def _set_format(self, key):
        self._settings["format"] = key
        self._refresh_export()

    def _pick_export_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Папка для сохранения")
        if folder:
            self._export_folder = folder
            self._refresh_export()

    def _exportable(self):
        return [s for s in self._sheets if s["included"]]

    def _export(self):
        sheets = self._exportable()
        s = self._settings
        try:
            plan = self.host.plan_export(self._export_folder, s["set_name"], len(sheets), s["format"])
            if plan["conflicts"]:
                raise ValueError("Файлы уже существуют: " + ", ".join(plan["conflicts"][:3]) + ". Измените имя набора или папку.")
            background = (255, 255, 255) if s["transparent"] else tuple(s["background"][:3])
            self._busy = True
            self._refresh()
            self.host.export_sheets([x["image"] for x in sheets], self._export_folder, s["set_name"], s["format"],
                                    s["inches"], DPI, background, self._exported, self._export_failed, self._export_progress)
        except ValueError as error:
            self._busy = False
            self._show_error(str(error))
            self._refresh()

    def _export_progress(self, done, total):
        self.note.setText(f"Сохранено {done} из {total}…")

    def _exported(self, result):
        self._busy = False
        self._save()
        QMessageBox.information(self, "Patterns", f"Сохранено файлов: {len(result['written'])}.")
        self._refresh()

    def _export_failed(self, message):
        self._busy = False
        self._show_error(message)
        self._refresh()

    # ------------------------------------------------------------ engine glue

    def _canvas(self):
        return round(self._settings["inches"] * DPI)

    def _reference_side(self):
        sides = [max(a["width"], a["height"]) for a in self._assets]
        return max(1, sum(sides) // len(sides)) if sides else 1

    def _payload(self, *, layout=None, seed=None, elements=None):
        s = self._settings
        payload = {
            "schema_version": 1, "algorithm_version": self.host.algorithm_version, "mode": self._mode,
            "assets": [a["handle"] for a in (self._assets if self._mode == "pngs" else [self._tile] if self._tile else [])],
            "ui": {key: s[key] for key in s},
        }
        if self._mode == "tile":
            payload["tile"] = {"asset": self._tile["handle"] if self._tile else None, "band": s["band"] / 100,
                               "layout": "mirror" if s["layout"] == "mirror" else "straight"}
        else:
            size = self._canvas()
            payload["scene"] = {
                "width": size, "height": size, "repeat_mode": layout or s["layout"],
                "seed": s["seed"] if seed is None else seed,
                "background": [0, 0, 0, 0] if s["transparent"] else list(s["background"]),
                "elements": list(self._elements if elements is None else elements),
            }
        return payload

    def _relayout(self, *, layout=None, seed=None):
        """New element positions for the current settings; locked ones stay."""
        s, size = self._settings, self._canvas()
        reference = self._reference_side()
        centre = s["size_percent"] / 100 * size / reference
        payload = self._payload(layout=layout, seed=seed, elements=[e for e in self._elements if e.get("locked")])
        elements, warnings = self.host.layout_elements(
            payload, count=s["count"], min_gap=float(s["gap"]), scale_range=(centre * 0.75, centre * 1.25),
            angle_range=(-float(s["angle"]), float(s["angle"])), seed=payload["scene"]["seed"])
        self._layout_warnings = warnings
        placed = len(elements) - len(payload["scene"]["elements"])
        self._layout_shortage = (placed, s["count"]) if warnings and placed < s["count"] else None
        return elements

    def _invalidate(self, layout=False):
        self._render_key = None
        self._current = None
        if layout:
            self._layout_dirty = True
            self._layout_shortage = None  # П5: a message about the previous slider values must not stay
        self._generation += 1
        if hasattr(self, "stack"):
            self._refresh_light()

    def _render_current(self):
        """Lay out (pngs mode) and render the current sheet in the background."""
        if self._busy:
            return
        try:
            if self._mode == "pngs" and (self._layout_dirty or not self._elements):
                self._elements = self._relayout()
                self._layout_dirty = False
            payload = self._payload()
        except ValueError as error:
            self._show_error(str(error))
            return
        token = self._generation
        self._busy = True
        self._refresh()

        def done(result):
            if token != self._generation:
                return
            self._busy = False
            self._current = result
            self._render_key = json.dumps(payload["ui"], sort_keys=True)
            self._refresh()

        def failed(message):
            self._busy = False
            self._show_error(message)
            self._refresh()
        self.host.render_sheet(payload, done, failed)

    # ------------------------------------------------------------ navigation

    def _go_back(self):
        if self._busy:
            return
        self._goto(max(0, self._step - 1))

    def _can_leave(self):
        if self._step == 0:
            ready = bool(self._assets) if self._mode == "pngs" else self._tile is not None
            if not ready:
                self._show_error("Добавьте хотя бы один файл.")
            return ready
        if self._step == 2 and self._current is None:
            return False
        if self._step == 3 and not self._exportable():
            self._show_error("В наборе нет листов, которые можно экспортировать. Оставьте как есть лист со статусом Review или пересоберите.")
            return False
        return True

    def _go_next(self):
        if self._busy:
            return
        if self._step == 4:
            if self._export_folder is not None and self._exportable():
                self._export()
            return
        if not self._can_leave():
            return
        if self._step == 2:
            self._add_current()
            return
        self._goto(self._step + 1)

    def _goto(self, step):
        self._step = step
        self._save()
        if step == 2 and self._current is None:
            self._render_current()
        if step == 3:
            self._fill_sheets()
        self._refresh()

    # ------------------------------------------------------------ rendering UI

    def _show_error(self, message):
        QMessageBox.warning(self, "Patterns", message)

    def _refresh_light(self):
        self._update_buttons()

    def _refresh(self):
        s = self._settings
        self.title.setText("Patterns · " + (s["set_name"] or "Новый набор"))
        self.stack.setCurrentIndex(self._step)
        for index, label in enumerate(self.step_labels):
            marker = "✓" if index < self._step else ("●" if index == self._step else "○")
            label.setText(f"{marker} {index + 1}. {STEPS[index]}")
            label.setProperty("v3Selection", index <= self._step)
            label.setProperty("v3Description", index > self._step)
            _restyle(label)
        for key, card in self.mode_cards.items():
            card.setProperty("selected", key == self._mode)
            _restyle(card)
        self._refresh_source()
        self._refresh_settings()
        self._refresh_preview()
        self._refresh_set()
        self._refresh_export()
        self._update_buttons()

    def _refresh_source(self):
        _clear(self.source_grid)
        pngs = self._mode == "pngs"
        records = self._assets if pngs else ([self._tile] if self._tile else [])
        self.source_title.setText((f"Ваши PNG: {len(records)}" if pngs else "Готовая плитка"))
        self.source_empty.setVisible(not records)
        self.add_files.setVisible(pngs)
        self.add_folder.setVisible(False)  # owner 2026-10-23: the file dialog takes many PNG at once
        self.pick_tile.setVisible(not pngs)
        self.pick_tile.setText("Выбрать другой файл" if self._tile else "Выбрать файл")
        self.source_empty.setText(
            "Пока нет файлов. Добавьте PNG с прозрачным фоном: цветы, листья, любые элементы." if pngs else
            "Файл ещё не выбран. Выберите картинку, которую нужно сделать бесшовной плиткой.")
        for index, record in enumerate(records[:24]):
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setToolTip(record["name"])
            try:
                thumb.setPixmap(_qpixmap(self.host.thumbnail(record["handle"], 84), 84, 84))
            except (ValueError, OSError):
                thumb.setText("?")
            self.source_grid.addWidget(thumb, index // 8, index % 8)
        _clear(self.checks)
        if records and pngs:
            transparent = sum(1 for r in records if r["has_alpha"])
            self.checks.addWidget(_status(f"{transparent} из {len(records)} файлов с прозрачным фоном", "warning" if transparent < len(records) else "ok"))
        elif records:
            # A ready tile is a whole picture: transparency is not expected, the size is information only.
            self.checks.addWidget(_status("Прозрачный фон для готовой плитки не нужен.", "ok"))
            self.checks.addWidget(_text(f"Выбран файл {records[0]['name']} · {records[0]['width']} × {records[0]['height']} px. "
                                        "Подойдёт файл до 8192 px по стороне; шов проверим на следующем шаге.", "v3Small"))

    def _refresh_settings(self):
        s, tile = self._settings, self._mode == "tile"
        self.png_controls.setVisible(not tile)
        self.tile_controls.setVisible(tile)
        self.right_title.setText("Сглаживание шва" if tile else "Расстановка")
        self.layout_chips.set_value(s["layout"] if not tile or s["layout"] == "mirror" else "straight")
        self.layout_chips.set_enabled_keys({"straight", "mirror"} if tile else {key for _, key in LAYOUTS})
        self.layout_hint.setText("Half-drop и Brick недоступны для готовой плитки. Они есть в режиме «Из ваших PNG»." if tile
                                 else "Half-drop и Brick сдвигают соседние ряды на половину листа, как кирпичная кладка.")
        label = next((l for l, v in SIZES if v == s["inches"]), "Свой")
        self.size_chips.set_value(label)
        self.size_hint.setText(f"12 × 12 = 3600 × 3600 px при {DPI} DPI. Сейчас: {self._canvas()} × {self._canvas()} px")
        color = "transparent" if s["transparent"] else "rgb({},{},{})".format(*s["background"][:3])
        self.background_swatch.setStyleSheet(f"background:{color}; border:1px solid {self.tokens.border};")
        default = list(s["background"][:3]) == list(DEFAULTS["background"][:3])
        name = "Тёплый белый" if default else "Свой цвет #{:02X}{:02X}{:02X}".format(*s["background"][:3])
        self.background_name.setText("Прозрачный" if s["transparent"] else f"{name} — нажмите на образец, чтобы выбрать цвет")
        self.transparent_button.set_variant(ButtonVariant.PRIMARY if s["transparent"] else ButtonVariant.SECONDARY)
        locked = sum(1 for e in self._elements if e.get("locked"))
        shortage = getattr(self, "_layout_shortage", None)
        if shortage:
            placed, requested = shortage
            text = (f"Поставлено {placed} из {requested} элементов: при зазоре {s['gap']} px на листе нет места. "
                    "Уменьшите зазор или размер элементов, либо количество.")
        else:
            text = "Если места не хватает, покажем, сколько элементов поставлено из запрошенных."
        self.layout_note.setText(text + (f" Закреплено: {locked}." if locked else ""))
        self.layout_note.setStyleSheet("color:#f5b45a;font-weight:bold" if shortage else "")

    def _refresh_preview(self):
        result = self._current
        busy = self._busy and self._step == 2
        if result is None:
            self.preview_picture.setPixmap(QPixmap())
            self.preview_picture.setText("Идёт расчёт…" if busy else "Нет результата")
            self.seam_status.setText("")
            self.seam_numbers.setText("")
            self.primary_action.setEnabled(False)
            self.secondary_action.setEnabled(False)
            self.zoom_button.setEnabled(False)
            return
        seam, status = result["seam"], result["seam"]["status"]
        picture = self.host.preview_image(result["image"], 3, 4_000_000)
        size = min(self.preview_picture.width(), self.preview_picture.height(), 520)
        self.preview_picture.setPixmap(_qpixmap(picture, max(size, 380), max(size, 380)))
        ready = status == "ready"
        self.preview_title.setText("Проверьте повтор" if ready else "Шов заметен" if status == "fail" else "Шов слабо заметен")
        self.preview_subtitle.setText("Узор показан 3 × 3. Стык листов находится в центре картинки." if ready
                                      else "Шов виден при повторе. Исправьте его или оставьте как есть." if status == "fail"
                                      else "Шов слабо виден при повторе. Можно добавить лист или попробовать ещё раз.")
        self.seam_status.setText(STATUS_TEXT[status])
        _set_state(self.seam_status, {"ready": "ok", "review": "warning", "fail": "error"}[status])
        self.seam_numbers.setText(f"По горизонтали: {seam['horizontal']:.2f}\nПо вертикали: {seam['vertical']:.2f}\nПорог Ready: 1.5")
        tile = self._mode == "tile"
        if status == "fail":
            self.primary_action.setText("Сделать бесшовной" if tile else "Пересобрать с другим seed")
            self.secondary_action.setText("Оставить как есть (Review)")
            self.secondary_action.setVisible(True)
        else:
            self.primary_action.setText("Добавить лист в набор")
            self.secondary_action.setText("Пересобрать с другим seed")
            self.secondary_action.setVisible(not tile)
        self.primary_action.setEnabled(not self._busy)
        self.secondary_action.setEnabled(not self._busy)
        self.zoom_button.setEnabled(True)

    def _refresh_set(self):
        _clear(self.set_grid)
        for index, sheet in enumerate(self._sheets):
            tile = SheetTile(index, sheet)
            tile.setProperty("selected", index == self._selected)
            tile.clicked.connect(self._select_sheet)
            self.set_grid.addWidget(tile, index // 3, index % 3)
        tile_mode = self._mode == "tile"
        self.count_slider.setEnabled(not tile_mode)
        self.vary_chips.set_value(self._settings["vary"])
        self.vary_chips.setEnabled(not tile_mode)
        self.reroll_sheet.setEnabled(self._selected is not None and not self._busy and not tile_mode)
        excluded = [i + 1 for i, s in enumerate(self._sheets) if not s["included"]]
        ready = sum(1 for s in self._sheets if s["status"] == "ready")
        text = f"Листов в наборе: {len(self._sheets)}. Ready: {ready}."
        if excluded:
            text += " В экспорт не входят: " + ", ".join(map(str, excluded)) + "."
        if tile_mode:
            text += " Для готовой плитки набор состоит из одного листа."
        self.set_note.setText(text + (" Идёт расчёт…" if self._busy else ""))

    def _refresh_export(self):
        s = self._settings
        self.format_chips.set_value(s["format"])
        self.export_size_chips.set_value(next((l for l, v in SIZES if v == s["inches"]), "Свой"))
        self.export_hint.setText(f"{self._canvas()} × {self._canvas()} px, {DPI} DPI, профиль sRGB. DPI — метаданные, деталей не добавляет.")
        has_folder = self._export_folder is not None
        self.folder_label.setText(self._export_folder or "Папка не выбрана")
        _set_state(self.folder_label, "ok" if has_folder else "warning")
        self.folder_button.set_variant(ButtonVariant.SECONDARY if has_folder else ButtonVariant.PRIMARY)
        count = len(self._exportable())
        self.name_hint.setText(f"Файлы: {s['set_name'] or '…'} 01.{s['format']} … {s['set_name'] or '…'} {count:02d}.{s['format']}"
                               + (". JPG не хранит прозрачность: прозрачные места зальются фоном." if s["format"] == "jpg" else ""))
        skipped = len(self._sheets) - count
        self.summary.setText(f"Листов: {count}\nРазмер каждого: {self._canvas()} × {self._canvas()} px\nНе входят: {skipped}")
        self.export_warning.setVisible(not has_folder)
        self.export_warning.setText("Выберите папку, чтобы включить экспорт.")

    def _update_buttons(self):
        last = self._step == 4
        self.back_button.setEnabled(self._step > 0 and not self._busy)
        self.next_button.setText("Экспортировать" if last else "Далее")
        enabled = not self._busy
        if last:
            enabled = enabled and self._export_folder is not None and bool(self._exportable())
        elif self._step == 0:
            enabled = enabled and (bool(self._assets) if self._mode == "pngs" else self._tile is not None)
        elif self._step == 2:
            enabled = enabled and self._current is not None and self._current["seam"]["status"] != "fail"
        self.next_button.setEnabled(enabled)
        if not self._busy:
            self.note.setText("Платных запросов нет." + (" Сохранение начнётся после нажатия кнопки." if last else ""))
        else:
            self.note.setText("Идёт расчёт, подождите…")

    # ------------------------------------------------------------ persistence

    def _save(self):
        payload = self._payload()
        if self._mode == "tile" and not self._tile:
            return
        try:
            record = self.host.save_project(payload, self._settings["set_name"] or "Новый набор",
                                            self._project_id, self._revision)
        except ValueError:
            self._project_id = self._revision = None
            return
        self._project_id, self._revision = record["id"], record["revision"]

    def _restore(self):
        try:
            projects = self.host.list_projects()
            if not projects:
                return
            record = self.host.load_project(projects[0]["id"])
            payload = record["payload"]
            if payload.get("algorithm_version") != self.host.algorithm_version or "ui" not in payload:
                return
            handles = payload.get("assets", [])
            if not all(self.host.asset_available(h) for h in handles):
                return
            self._settings.update({k: v for k, v in payload["ui"].items() if k in DEFAULTS})
            self._mode = payload["mode"]
            infos = [{"handle": h, "name": h["filename"], **self.host.asset_info(h)} for h in handles]
            if self._mode == "pngs":
                self._assets = infos
                self._elements = list(payload.get("scene", {}).get("elements", []))
                self._layout_dirty = not self._elements
            elif infos:
                self._tile = infos[0]
            self._project_id, self._revision = record["id"], record["revision"]
        except (ValueError, OSError, KeyError):
            self._project_id = self._revision = None

    def confirm_close(self):
        """Work is saved at every step; only a running job needs the user's word."""
        if not self._busy:
            return True
        answer = QMessageBox.question(self, "Patterns", "Идёт расчёт или сохранение. Остановить и выйти?")
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self._generation += 1
        return True
