"""Editable brief, visual direction and recipe, using the existing draft store."""
from pathlib import Path
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QTabWidget, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QAbstractSpinBox, QStackedWidget,
    QVBoxLayout, QWidget, QFrame, QSizePolicy,
)
from studio_clipart_recipe import ClipartRecipe, ROLES
from v3_project_state import ClipartModeData
from v3_components import apply_v3_theme

ROLE_LABELS = ("Главные объекты", "Композиции", "Венки", "Бордюры и рамки", "Мелкий декор")
from studio_palette_library import all_palette_presets, palette_categories, recommended_palette_presets
from studio_style_profiles import (
    all_style_profiles, all_style_modifiers, style_categories,
    get_style_profile, style_modifier_keys, style_prompt_text,
)

PALETTES = tuple((preset.title, ' '.join(preset.colors)) for preset in all_palette_presets())


def style_preview_path(key):
    local = Path(__file__).resolve().parent / 'assets' / 'style_previews' / f'{key}.jpg'
    if local.is_file():
        return local
    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return root / 'assets' / 'style_previews' / f'{key}.jpg'


class PalettePreview(QWidget):
    """A small, repeatable motif shows the five colors together beyond swatches."""
    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = tuple(QColor(color) for color in colors)
        self.setFixedSize(104, 48)
        self.setAccessibleName('Пример сочетания цветов: ' + ', '.join(colors))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.colors[4])
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 5, 5)
        painter.setBrush(self.colors[1])
        painter.drawEllipse(20, 25, 25, 12)
        painter.setBrush(self.colors[2])
        painter.drawEllipse(59, 27, 25, 11)
        painter.setBrush(self.colors[0])
        for x, y in ((38, 7), (51, 7), (32, 18), (57, 18), (43, 27)):
            painter.drawEllipse(x, y, 17, 15)
        painter.setBrush(self.colors[3])
        painter.drawEllipse(46, 17, 15, 15)
        painter.end()


class PlainNumberSpinBox(QSpinBox):
    """Editable integer field with no arrows or accidental wheel changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        event.ignore()


def combo(values):
    widget = QComboBox()
    widget.setEditable(True)
    widget.addItems(values)
    widget.lineEdit().setMaxLength(4000)
    return widget


class ClipartBuilderDialog(QDialog):
    """Changes remain local until Apply; cancellation preserves the project."""
    def __init__(self, data: ClipartModeData, parent=None):
        if not isinstance(data, ClipartModeData):
            raise TypeError("ClipartBuilderDialog requires ClipartModeData")
        super().__init__(parent)
        self.data = data
        self._reference_palette_cache = {}
        self._card_columns = 3
        self.recipe = (ClipartRecipe.from_dict(data.recipe)
                       if data.recipe is not None else ClipartRecipe())
        self.setWindowTitle("Clipart · Настройка набора")
        self.resize(1080, 720)
        self.setMinimumSize(760, 560)
        apply_v3_theme(self)
        self.setStyleSheet(self.styleSheet() + "\nQPushButton {background:#1f2937;color:#eef3f7;border:1px solid #405363;border-radius:4px;min-height:30px;padding:3px 8px;} QPushButton:checked {background:#20c9b7;color:#071d1a;border:1px solid #20c9b7;} QPushButton:disabled {color:#718496;} QComboBox::drop-down {width:24px;}")
        layout = QVBoxLayout(self)
        self.heading = QLabel()
        self.heading.setStyleSheet("font-size:24px;font-weight:600")
        layout.addWidget(self.heading)
        self.pages = QStackedWidget()
        layout.addWidget(self.pages, 1)
        self._idea()
        self._style()
        self._references()
        self._structure()
        self._objects()
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        footer = QHBoxLayout()
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        footer.addStretch()
        self.back = QPushButton("Назад")
        self.next = QPushButton("Далее")
        self.back.clicked.connect(lambda: self._navigate(-1))
        self.next.clicked.connect(lambda: self._navigate(1))
        footer.addWidget(self.back)
        footer.addWidget(self.next)
        layout.addLayout(footer)
        self._update_navigation()
        self.finished.connect(lambda: self.planning.cancel())

    def _page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(16)
        scroll.setWidget(content)
        self.pages.addWidget(scroll)
        return layout

    def _idea(self):
        layout = self._page()
        form = QFormLayout()
        self.theme = QLineEdit(self.recipe.theme)
        self.theme.setMaxLength(4000)
        self.theme.setPlaceholderText("Например, мишки Тедди")
        self.context = combo(["", "Зима", "Весна", "Лето", "Осень", "Рождество",
                              "Пасха", "Хэллоуин", "Baby Shower", "Свадьба",
                              "День рождения ребёнка", "Первый день рождения", "Выпускной"])
        self.context.setCurrentText(self.recipe.context)
        self.context.lineEdit().setPlaceholderText("Выберите повод или напишите свой")
        self.motifs = QLineEdit(", ".join(self.recipe.motifs))
        self.motifs.setMaxLength(4000)
        self.motifs.setPlaceholderText("Машинки, самолёты, поезда")
        self.total = PlainNumberSpinBox()
        self.total.setRange(1, 1000)
        self.total.setMaximumWidth(120)
        self.total.setValue(self.recipe.total)
        for label, field in (("Основная тема", self.theme), ("Контекст", self.context),
                             ("Дополнительные мотивы", self.motifs),
                             ("Изображений в наборе", self.total)):
            field.setAccessibleName(label)
            form.addRow(label, field)
        layout.addLayout(form)
        layout.addWidget(QLabel("Распределение по ролям будет предложено автоматически. Его можно изменить."))
        layout.addStretch()

    def _style(self):
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)
        self.style_tabs = QTabWidget()
        style_layout = self._tab_layout(self.style_tabs, "Стиль")
        palette_layout = self._tab_layout(self.style_tabs, "Палитра")
        fine_layout = self._tab_layout(self.style_tabs, "Тонкая настройка")
        page_layout.addWidget(self.style_tabs, 1)
        self.style_summary = QLabel()
        self.style_summary.setProperty('v3Summary', True)
        self.style_summary.setWordWrap(True)
        self.style_summary.setAccessibleName("Сводка выбора")
        page_layout.addWidget(self.style_summary)
        self.pages.addWidget(page)
        generator = self.data.prompt_generator
        self.technique = combo(["", *(profile.title for profile in all_style_profiles())])
        self.technique.setCurrentText(generator.style)
        self.mood = combo(["", "Уютное", "Весёлое", "Сказочное", "Нежное", "Спокойное", "Праздничное"])
        self.line = combo(["", "Без художественной обводки", "Тонкая обводка", "Рисованная неровная линия"])
        self.detail = combo(["", "Минималистично", "Умеренная детализация", "Много мелких деталей"])
        self.visual_fields = dict(zip(("technique", "mood", "line", "detail"),
                                      (self.technique, self.mood, self.line, self.detail)))
        for key, value in self.recipe.visual.items():
            if key == 'material':
                continue
            self.visual_fields[key].setCurrentText(value)
        for field in (self.line, self.detail):
            saved_value = field.currentText()
            if saved_value and field.findText(saved_value) < 0:
                field.addItem(saved_value)
            field.setEditable(False)
            field.setCurrentText(saved_value)
            field.setPlaceholderText("Не выбрано")
            if not field.currentText():
                field.setCurrentIndex(-1)

        style_library_group = self._section("Библиотека базовых стилей")
        style_library_layout = QVBoxLayout(style_library_group.body)
        style_library_layout.setContentsMargins(0, 0, 0, 0)
        self.style_category = QComboBox()
        self.style_category.addItems(["Все", *style_categories()])
        self.style_category.currentTextChanged.connect(self._refresh_style_library)
        style_library_layout.addWidget(self.style_category)
        self.style_library_host = QWidget()
        self.style_library_grid = QGridLayout(self.style_library_host)
        style_library_layout.addWidget(self.style_library_host)
        style_layout.addWidget(style_library_group)

        modifier_group = self._section("Характер стиля", "До двух характеристик")
        modifier_layout = QGridLayout(modifier_group.body)
        modifier_layout.setContentsMargins(0, 0, 0, 0)
        self.style_modifier_buttons = {}
        for index, modifier in enumerate(all_style_modifiers()):
            button = QPushButton(modifier.title)
            button.setCheckable(True)
            button.setProperty('v3Chip', True)
            button.setAccessibleName(f"Характер стиля: {modifier.title}")
            button.toggled.connect(self._sync_style_modifiers)
            self.style_modifier_buttons[modifier.key] = button
            modifier_layout.addWidget(button, index // 4, index % 4)
        style_layout.addWidget(modifier_group)

        custom_style = QHBoxLayout()
        custom_style.addWidget(QLabel("Свой стиль"))
        self.technique.setAccessibleName("Свой стиль")
        self.technique.lineEdit().setPlaceholderText("Например: линогравюра с зернистой фактурой")
        custom_style.addWidget(self.technique, 1)
        fine_layout.addLayout(custom_style)
        custom_style_hint = QLabel("Если готовый стиль не подходит, опишите технику своими словами.")
        custom_style_hint.setProperty('v3Small', True)
        custom_style_hint.setWordWrap(True)
        fine_layout.addWidget(custom_style_hint)
        self.mood.hide()

        extra = self._section("Дополнительные параметры")
        extra_form = QFormLayout(extra.body)
        extra_form.setContentsMargins(0, 0, 0, 0)
        for label, field in (("Художественная линия", self.line),
                             ("Детализация", self.detail)):
            field.setAccessibleName(label)
            extra_form.addRow(label, field)
        fine_layout.addWidget(extra)

        self.palette = QLineEdit(generator.palette)
        self.palette.setMaxLength(4000)
        self.palette.setAccessibleName("Своя палитра")
        self.palette.setPlaceholderText("HEX-коды или выберите палитру выше")

        recommended_title = QLabel("Рекомендуем палитру для вашей темы")
        recommended_title.setStyleSheet("font-size:16px;font-weight:600")
        palette_layout.addWidget(recommended_title)
        palette_hint = QLabel("Подбор по словам в теме и поводе. Измените их на шаге 1, чтобы увидеть другие варианты.")
        palette_hint.setWordWrap(True)
        palette_hint.setProperty('v3Small', True)
        palette_layout.addWidget(palette_hint)
        recommended_group = QFrame()
        recommended_group.setProperty('v3Card', True)
        self.recommended_palette_grid = QGridLayout(recommended_group)
        palette_layout.addWidget(recommended_group)

        library_group = self._section("Библиотека палитр")
        library_layout = QVBoxLayout(library_group.body)
        library_layout.setContentsMargins(0, 0, 0, 0)
        self.palette_category = QComboBox()
        self.palette_category.addItems(["Все", *palette_categories()])
        self.palette_category.currentTextChanged.connect(self._refresh_palette_library)
        library_layout.addWidget(self.palette_category)
        self.palette_library_host = QWidget()
        self.palette_library_grid = QGridLayout(self.palette_library_host)
        library_layout.addWidget(self.palette_library_host)
        palette_layout.addWidget(library_group)

        custom = QHBoxLayout()
        custom.addWidget(QLabel("Своя палитра"))
        custom.addWidget(self.palette, 1)
        self.palette_reference_button = QPushButton("Взять из референса")
        self.palette_reference_button.clicked.connect(self._go_to_references)
        custom.addWidget(self.palette_reference_button)
        palette_layout.addLayout(custom)

        self.style_cards = []
        self.technique.currentTextChanged.connect(self._refresh_style_card_checks)
        self.recommended_palette_cards = []
        self.palette_cards = []
        self.palette.textChanged.connect(self._refresh_palette_checks)
        reset_palette = QPushButton("Сбросить палитру")
        reset_palette.clicked.connect(self.palette.clear)
        custom.addWidget(reset_palette)
        self.theme.textChanged.connect(self._refresh_palette_recommendations)
        self.context.currentTextChanged.connect(self._refresh_palette_recommendations)
        self._restore_style_modifier_buttons()
        for button in self.style_modifier_buttons.values():
            button.setEnabled(button.isChecked() or sum(b.isChecked() for b in self.style_modifier_buttons.values()) < 2)
        self._refresh_style_library()
        self._refresh_palette_recommendations()
        self._refresh_palette_library()
        for tab_layout in (style_layout, palette_layout, fine_layout):
            tab_layout.addStretch()
        for field in (self.technique, self.line, self.detail):
            field.currentTextChanged.connect(self._refresh_style_summary)
        self.palette.textChanged.connect(self._refresh_style_summary)
        self._refresh_style_summary()

    def _tab_layout(self, tabs, title):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.setSpacing(16)
        scroll.setWidget(content)
        tabs.addTab(scroll, title)
        return layout

    def _refresh_style_summary(self, *_):
        if not hasattr(self, 'style_summary') or not hasattr(self, 'style_modifier_buttons'):
            return
        parts = [f"Стиль: {self.technique.currentText().strip() or 'не выбран'}"]
        characters = [button.text() for button in self.style_modifier_buttons.values() if button.isChecked()]
        if characters:
            parts.append("Характер: " + ", ".join(characters))
        colors = self.palette.text().strip()
        preset = next((item for item in all_palette_presets()
                       if ' '.join(item.colors).casefold() == colors.casefold()), None)
        parts.append("Палитра: " + (preset.title if preset else "своя" if colors else "не выбрана"))
        for label, field in (("Линия", self.line), ("Детализация", self.detail)):
            if field.currentText().strip():
                parts.append(f"{label}: {field.currentText().strip()}")
        self.style_summary.setText("  ·  ".join(parts))

    @staticmethod
    def _section(title, hint=""):
        """Plain heading + body instead of a framed group box; the body is accessible by its title."""
        box = QWidget()
        outer = QVBoxLayout(box)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        head = QHBoxLayout()
        label = QLabel(title)
        label.setProperty('v3Section', True)
        head.addWidget(label)
        if hint:
            note = QLabel(hint)
            note.setProperty('v3Small', True)
            head.addWidget(note)
        head.addStretch()
        outer.addLayout(head)
        box.body = QWidget()
        box.body.setAccessibleName(title)
        outer.addWidget(box.body)
        return box

    def _style_card(self, profile, grid, index, target):
        button = QPushButton()
        button.setCheckable(True)
        button.setProperty('v3StyleCard', True)
        button.setAccessibleName(profile.title)
        button.setToolTip(profile.title)
        button.setFixedHeight(104)
        content = QHBoxLayout(button)
        content.setContentsMargins(10, 10, 14, 10)
        content.setSpacing(12)
        preview = QLabel()
        preview.setProperty('v3StylePreview', True)
        preview.setFixedSize(84, 84)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        pixmap = QPixmap(str(style_preview_path(profile.key)))
        if not pixmap.isNull():
            preview.setPixmap(pixmap.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio,
                                            Qt.TransformationMode.SmoothTransformation))
        content.addWidget(preview)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addStretch()
        title = QLabel(profile.title)
        title.setProperty('v3CardTitle', True)
        title.setWordWrap(True)
        detail = QLabel(" · ".join(profile.best_for[:3]))
        detail.setProperty('v3Small', True)
        detail.setWordWrap(True)
        for label in (title, detail):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            text.addWidget(label)
        text.addStretch()
        content.addLayout(text, 1)
        button.clicked.connect(lambda checked=False, key=profile.key: self._select_style_profile(key))
        grid.addWidget(button, index // self._card_columns, index % self._card_columns)
        target.append(dict(key=profile.key, title=profile.title, category=profile.category,
                           best_for=list(profile.best_for), button=button, preview=preview, widget=button))

    def _refresh_style_library(self, *_):
        if not hasattr(self, 'style_library_grid'):
            return
        self._clear_layout(self.style_library_grid)
        self.style_cards = []
        category = self.style_category.currentText() if hasattr(self, 'style_category') else 'Все'
        profiles = (list(all_style_profiles()) if category == 'Все' else
                    [profile for profile in all_style_profiles() if profile.category == category])
        for index, profile in enumerate(profiles):
            self._style_card(profile, self.style_library_grid, index, self.style_cards)
        self._refresh_style_card_checks()

    def _refresh_style_card_checks(self):
        profile = get_style_profile(self.technique.currentText()) if hasattr(self, 'technique') else None
        selected = profile.key if profile is not None else None
        for card in getattr(self, 'style_cards', []):
            card['button'].setChecked(card['key'] == selected)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.width() < 950 else 3
        if columns == self._card_columns:
            return
        self._card_columns = columns
        for cards, grid in (
                (getattr(self, 'style_cards', []), getattr(self, 'style_library_grid', None)),
                (getattr(self, 'recommended_palette_cards', []), getattr(self, 'recommended_palette_grid', None)),
                (getattr(self, 'palette_cards', []), getattr(self, 'palette_library_grid', None))):
            if grid is None:
                continue
            for index, card in enumerate(cards):
                grid.removeWidget(card['widget'])
                grid.addWidget(card['widget'], index // columns, index % columns)

    def _select_style_profile(self, key):
        profile = get_style_profile(key)
        if profile is None:
            raise ValueError('Неизвестный стиль')
        self.technique.setCurrentText(profile.title)
        if not self.mood.currentText().strip():
            self._set_style_modifiers(profile.default_modifiers)
        self._refresh_style_card_checks()

    def _set_style_modifiers(self, keys):
        selected = set(keys)
        for key, button in self.style_modifier_buttons.items():
            previous = button.blockSignals(True)
            button.setChecked(key in selected)
            button.blockSignals(previous)
        self._sync_style_modifiers()

    def _restore_style_modifier_buttons(self):
        selected = set(style_modifier_keys(self.mood.currentText()))
        for key, button in self.style_modifier_buttons.items():
            previous = button.blockSignals(True)
            button.setChecked(key in selected)
            button.blockSignals(previous)

    def _sync_style_modifiers(self, *_):
        selected = [modifier for modifier in all_style_modifiers()
                    if self.style_modifier_buttons[modifier.key].isChecked()]
        self.mood.setCurrentText(', '.join(modifier.title for modifier in selected))
        for button in self.style_modifier_buttons.values():
            button.setEnabled(button.isChecked() or len(selected) < 2)
        self._refresh_style_summary()

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

    def _select_palette(self, colors):
        self.palette.setText(' '.join(colors))
        self._refresh_palette_checks()

    def _refresh_palette_checks(self, *_):
        current = self.palette.text().strip().casefold()
        for card in self.recommended_palette_cards + self.palette_cards:
            card['button'].setChecked(current == ' '.join(card['colors']).casefold())

    def _palette_card(self, preset, grid, index, target):
        card = QFrame()
        card.setProperty('v3Card', True)
        card_layout = QVBoxLayout(card)
        top = QVBoxLayout()
        button = QPushButton(preset.title)
        button.setCheckable(True)
        button.setMinimumHeight(42)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        title = QLabel(preset.title, button)
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        button.setText("")
        button_layout = QVBoxLayout(button)
        button_layout.setContentsMargins(4, 2, 4, 2)
        button_layout.addWidget(title)
        button.setAccessibleName(preset.title)
        button.setToolTip(preset.title)
        button.clicked.connect(lambda checked=False, colors=preset.colors: self._select_palette(colors))
        top.addWidget(button, 1)
        character = QLabel(preset.character)
        character.setProperty('v3Small', True)
        character.setWordWrap(True)
        character.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        character.setToolTip(preset.character)
        top.addWidget(character, 1)
        card_layout.addLayout(top)
        swatches = QHBoxLayout()
        for color in preset.colors:
            swatch = QLabel()
            swatch.setFixedHeight(26)
            swatch.setMinimumWidth(34)
            swatch.setToolTip(color)
            swatch.setStyleSheet(f'background:{color};border-radius:4px')
            swatches.addWidget(swatch, 1)
        card_layout.addLayout(swatches)
        example = QHBoxLayout()
        example.addWidget(QLabel("Пример сочетания"))
        example.addStretch()
        example.addWidget(PalettePreview(preset.colors))
        card_layout.addLayout(example)
        grid.addWidget(card, index // self._card_columns, index % self._card_columns)
        target.append(dict(key=preset.key, title=preset.title, category=preset.category,
                           character=preset.character, colors=list(preset.colors), widget=card, button=button))
        button.setChecked(self.palette.text().strip().casefold() == ' '.join(preset.colors).casefold())

    def _refresh_palette_recommendations(self, *_):
        if not hasattr(self, 'recommended_palette_grid'):
            return
        self._clear_layout(self.recommended_palette_grid)
        self.recommended_palette_cards = []
        for index, preset in enumerate(recommended_palette_presets(
                self.theme.text().strip(), self.context.currentText().strip())):
            self._palette_card(preset, self.recommended_palette_grid, index,
                               self.recommended_palette_cards)

    def _refresh_palette_library(self, *_):
        if not hasattr(self, 'palette_library_grid'):
            return
        self._clear_layout(self.palette_library_grid)
        self.palette_cards = []
        category = self.palette_category.currentText() if hasattr(self, 'palette_category') else 'Все'
        presets = [preset for preset in all_palette_presets()
                   if category == 'Все' or preset.category == category]
        for index, preset in enumerate(presets):
            self._palette_card(preset, self.palette_library_grid, index, self.palette_cards)

    def _go_to_references(self):
        self.pages.setCurrentIndex(2)
        self.error.clear()
        self._update_navigation()

    def _references(self):
        from studio_reference_editor import ReferenceEditor
        layout = self._page()
        self.reference_editor = ReferenceEditor(
            self.recipe.references,
            selected_style=lambda: self.technique.currentText(),
            selected_palette=self._selected_palette_name,
        )
        self.reference_editor.palette_selected.connect(self.palette.setText)
        self.technique.currentTextChanged.connect(self.reference_editor.refresh_source_labels)
        self.palette.textChanged.connect(self.reference_editor.refresh_source_labels)
        layout.addWidget(self.reference_editor)

    def _selected_palette_name(self):
        value = self.palette.text().strip().casefold()
        if not value:
            return ''
        for preset in all_palette_presets():
            if value == ' '.join(preset.colors).casefold():
                return preset.title
        return 'Своя палитра'

    def _effective_visual(self, references):
        from studio_clipart_references import active_references, reference_source
        active = active_references(references)
        if len(active) > 5:
            raise ValueError('Для генерации можно выбрать не более 5 референсов')
        style_source = reference_source(references, 'technique')
        palette_source = reference_source(references, 'palette')
        if style_source:
            number = active.index(style_source) + 1
            style = f'Use the illustration technique and visual style of reference image {number}.'
        else:
            base = style_prompt_text(self.technique.currentText(), self.mood.currentText())
            style = '; '.join(part for part in
                              (base, self.line.currentText().strip(),
                               self._visual_values()['material'], self.detail.currentText().strip())
                              if part)
        palette = (' '.join(self._reference_palette(palette_source['path'])) if palette_source
                   else self.palette.text().strip())
        return style, palette

    def _reference_palette(self, path):
        from studio_clipart_references import extract_palette
        source = Path(path)
        stat = source.stat()
        key = (str(source), stat.st_mtime_ns, stat.st_size)
        if key not in self._reference_palette_cache:
            self._reference_palette_cache.clear()
            self._reference_palette_cache[key] = extract_palette(path)
        return self._reference_palette_cache[key]

    def _structure(self):
        layout = self._page()
        self.presets = QComboBox()
        for title, key in (("Сбалансированный", "balanced"), ("Больше персонажей", "characters"),
                           ("Больше оформления", "decorative")):
            self.presets.addItem(title, key)
        self.presets.setAccessibleName("Рецепт распределения")
        self.presets.setMaximumWidth(280)
        layout.addWidget(self.presets, alignment=Qt.AlignmentFlag.AlignLeft)
        suggest = QPushButton("Предложить распределение")
        suggest.setMaximumWidth(280)
        suggest.clicked.connect(self._suggest)
        layout.addWidget(suggest, alignment=Qt.AlignmentFlag.AlignLeft)
        form_widget = QWidget()
        form_widget.setMaximumWidth(540)
        form = QFormLayout(form_widget)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
        form.setSpacing(12)
        self.counts = {}
        for key, label in zip(ROLES, ROLE_LABELS):
            spin = PlainNumberSpinBox()
            spin.setRange(0, 1000)
            spin.setFixedWidth(104)
            spin.setAlignment(Qt.AlignmentFlag.AlignLeft)
            spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            spin.setValue(self.recipe.counts[key])
            spin.setAccessibleName(label)
            spin.valueChanged.connect(self._show_total)
            self.counts[key] = spin
            form.addRow(label, spin)
        layout.addWidget(form_widget, alignment=Qt.AlignmentFlag.AlignLeft)
        self.sum_label = QLabel()
        layout.addWidget(self.sum_label)
        self._show_total()
        note = QLabel("Сохранение добавляет настройки в проект. Конкретные объекты и промпты остаются на следующем этапе работы.")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()

    def _show_total(self):
        if hasattr(self, "sum_label"):
            self.sum_label.setText(f"Всего изображений: {sum(s.value() for s in self.counts.values())}")

    def _objects(self):
        from studio_object_editor import ObjectEditor
        from studio_planning_ui import PlanningPanel
        layout = self._page()
        self.object_editor = ObjectEditor(self.recipe.objects)
        self.planning = PlanningPanel(
            self._planning_snapshot, self.object_editor, self.recipe.assistant,
            reference_images=self.reference_editor.selected_ai_image_paths,
            clear_reference_images=self.reference_editor.clear_ai_image_paths,
        )
        layout.addWidget(self.planning)
        layout.addWidget(self.object_editor)
        from PyQt6.QtWidgets import QCheckBox
        self.make_prompts = QCheckBox('Добавить промпты этих объектов к существующему списку при сохранении')
        layout.addWidget(self.make_prompts)

    def _visual_values(self):
        values = {key: widget.currentText().strip() for key, widget in self.visual_fields.items()}
        values['material'] = ''  # Legacy project field; no longer a collection-wide choice.
        return values

    def _planning_snapshot(self):
        from copy import deepcopy
        if len(style_modifier_keys(self.mood.currentText())) > 2:
            raise ValueError('Оставьте не более двух характеристик стиля')
        recipe = deepcopy(self.recipe)
        recipe.theme = self.theme.text().strip()
        if not recipe.theme:
            raise ValueError('Укажите основную тему набора')
        recipe.context = self.context.currentText().strip()
        recipe.motifs = [s.strip() for s in self.motifs.text().split(',') if s.strip()]
        recipe.visual = self._visual_values()
        recipe.references = self.reference_editor.value()
        recipe.objects = self.object_editor.value()
        recipe.edit_counts({role: sum(item['role'] == role for item in recipe.objects) for role in ROLES})
        if recipe.objects:
            from studio_bundle_planner import propose_bundle_plan
            recipe.bundle_plan = propose_bundle_plan(recipe.objects, existing=recipe.bundle_plan)
        recipe.assistant = self.planning.selection()
        recipe.validate()
        _, palette = self._effective_visual(recipe.references)
        return recipe, palette

    def _suggest(self):
        self.recipe.select(self.total.value(), self.presets.currentData())
        for key, spin in self.counts.items():
            spin.setValue(self.recipe.counts[key])

    def _navigate(self, direction):
        index = self.pages.currentIndex()
        if direction < 0 and index == 4:
            items = self.object_editor.value()
            for role, spin in self.counts.items():
                spin.setValue(sum(item['role'] == role for item in items))
            if items:
                self.total.setValue(len(items))
                self.recipe.edit_counts({role: spin.value() for role, spin in self.counts.items()})
        if direction > 0 and index == 0:
            if not self.theme.text().strip():
                self.error.setText("Укажите основную тему набора")
                return
            if self.total.value() != self.recipe.total:
                self._suggest()
        if direction > 0 and index == 3:
            from studio_clipart_objects import fill_recipe
            try:
                counts = {key: spin.value() for key, spin in self.counts.items()}
                self.recipe.edit_counts(counts)
                items = fill_recipe(self.object_editor.value(), counts)
                self.object_editor.items = items
                self.object_editor.refresh()
                self.object_editor.status.setText('Заполните названия. При уменьшении рецепта уже созданные строки сохраняются; лишние можно удалить здесь.')
            except ValueError as error:
                self.error.setText(str(error))
                return
        if direction > 0 and index == 4:
            self._apply()
            return
        self.pages.setCurrentIndex(index + direction)
        self.error.clear()
        self._update_navigation()

    def _update_navigation(self):
        index = self.pages.currentIndex()
        self.heading.setText(("Идея набора", "Визуальное направление", "Референсы", "Структура набора", "Предложенный набор")[index])
        self.back.setEnabled(index > 0)
        self.next.setText("Сохранить настройки" if index == 4 else "Далее")

    def _apply(self):
        try:
            self.recipe.theme = self.theme.text().strip()
            if not self.recipe.theme:
                raise ValueError("Укажите основную тему набора")
            self.recipe.context = self.context.currentText().strip()
            self.recipe.motifs = [s.strip() for s in self.motifs.text().split(",") if s.strip()]
            self.recipe.edit_counts({key: spin.value() for key, spin in self.counts.items()})
            self.recipe.visual = self._visual_values()
            self.recipe.references = self.reference_editor.value()
            self.recipe.assistant = self.planning.selection()
            self.recipe.objects = self.object_editor.value()
            if self.recipe.objects:
                self.recipe.edit_counts({role: sum(item['role'] == role for item in self.recipe.objects) for role in ROLES})
                from studio_bundle_planner import propose_bundle_plan
                self.recipe.bundle_plan = propose_bundle_plan(
                    self.recipe.objects, existing=self.recipe.bundle_plan)
            value = self.recipe.to_dict()
        except (ValueError, OSError) as error:
            self.error.setText(str(error))
            return
        try:
            style, palette = self._effective_visual(self.recipe.references)
        except (ValueError, OSError) as error:
            self.error.setText(str(error))
            return
        if len(style) > 4000:
            self.error.setText("Сократите описание стиля до 4000 символов")
            return
        from v3_project_state import PromptGeneratorData, MAX_PROMPT_ENTRIES
        generator = PromptGeneratorData.from_dict(self.data.prompt_generator.to_dict())
        generator.style = style
        generator.palette = palette
        prompts = []
        if self.make_prompts.isChecked():
            from studio_clipart_objects import compile_objects
            try:
                prompts = compile_objects(self.recipe, generator)
                from studio_clipart_references import active_references
                from studio_clipart_objects import attach_reference_guidance
                prompts = attach_reference_guidance(prompts, active_references(self.recipe.references))
                if len(self.data.prompts) + len(prompts) > MAX_PROMPT_ENTRIES:
                    raise ValueError('Общий список промптов превышает допустимый размер')
            except ValueError as error:
                self.error.setText(str(error))
                return
        self.data.recipe = value
        self.data.prompt_generator.style = style
        self.data.prompt_generator.palette = palette
        self.data.prompts.extend(prompts)
        self.accept()
