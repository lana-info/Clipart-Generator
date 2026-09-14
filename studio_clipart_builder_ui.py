"""Editable brief, visual direction and recipe, using the existing draft store."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget, QFrame, QSizePolicy,
)
from studio_clipart_recipe import ClipartRecipe, ROLES
from v3_project_state import ClipartModeData
from v3_components import apply_v3_theme

ROLE_LABELS = ("Главные объекты", "Композиции", "Венки", "Бордюры и рамки", "Мелкий декор")
from studio_palette_library import all_palette_presets, palette_categories, recommended_palette_presets
from studio_style_profiles import (
    all_style_profiles, all_style_modifiers, featured_style_profiles, style_categories,
    recommended_style_profiles, get_style_profile, style_modifier_keys, style_prompt_text,
)

PALETTES = tuple((preset.title, ' '.join(preset.colors)) for preset in all_palette_presets())


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
        self.recipe = (ClipartRecipe.from_dict(data.recipe)
                       if data.recipe is not None else ClipartRecipe())
        self.setWindowTitle("Clipart · Настройка набора")
        self.resize(1080, 720)
        self.setMinimumSize(760, 560)
        apply_v3_theme(self)
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
        self.total = QSpinBox()
        self.total.setRange(1, 1000)
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
        layout = self._page()
        generator = self.data.prompt_generator
        self.technique = combo(["", *(profile.title for profile in all_style_profiles())])
        self.technique.setCurrentText(generator.style)
        self.mood = combo(["", "Уютное", "Весёлое", "Сказочное", "Нежное", "Спокойное", "Праздничное"])
        self.line = combo(["", "Без художественной обводки", "Тонкая обводка", "Рисованная неровная линия"])
        self.material = combo(["", "Бумага", "Дерево", "Керамика", "Ткань", "Вышивка", "Вязаная фактура"])
        self.detail = combo(["", "Минималистично", "Умеренная детализация", "Много мелких деталей"])
        self.visual_fields = dict(zip(("technique", "mood", "line", "material", "detail"),
                                      (self.technique, self.mood, self.line, self.material, self.detail)))
        for key, value in self.recipe.visual.items():
            self.visual_fields[key].setCurrentText(value)

        style_title = QLabel("Рекомендуем стиль для вашей темы")
        style_title.setStyleSheet("font-size:16px;font-weight:600")
        layout.addWidget(style_title)
        style_hint = QLabel("Базовый стиль применяется ко всей коллекции; характер можно дополнить ниже.")
        style_hint.setWordWrap(True)
        style_hint.setProperty('v3Small', True)
        layout.addWidget(style_hint)
        recommended_style_group = QFrame()
        recommended_style_group.setProperty('v3Card', True)
        self.recommended_style_grid = QGridLayout(recommended_style_group)
        layout.addWidget(recommended_style_group)

        style_library_group = QGroupBox("Библиотека стилей")
        style_library_layout = QVBoxLayout(style_library_group)
        self.style_category = QComboBox()
        self.style_category.addItems(["Все", *style_categories()])
        self.style_category.currentTextChanged.connect(self._refresh_style_library)
        style_library_layout.addWidget(self.style_category)
        self.style_library_host = QWidget()
        self.style_library_grid = QGridLayout(self.style_library_host)
        style_library_layout.addWidget(self.style_library_host)
        layout.addWidget(style_library_group)

        modifier_group = QGroupBox("Характер стиля")
        modifier_layout = QGridLayout(modifier_group)
        self.style_modifier_buttons = {}
        for index, modifier in enumerate(all_style_modifiers()):
            button = QPushButton(modifier.title)
            button.setCheckable(True)
            button.setAccessibleName(f"Характер стиля: {modifier.title}")
            button.toggled.connect(self._sync_style_modifiers)
            self.style_modifier_buttons[modifier.key] = button
            modifier_layout.addWidget(button, index // 4, index % 4)
        layout.addWidget(modifier_group)

        custom_style = QHBoxLayout()
        custom_style.addWidget(QLabel("Базовый стиль / своя формулировка"))
        self.technique.setAccessibleName("Базовый стиль / своя формулировка")
        custom_style.addWidget(self.technique, 1)
        layout.addLayout(custom_style)
        self.mood.hide()

        extra = QGroupBox("Дополнительные параметры")
        extra_form = QFormLayout(extra)
        for label, field in (("Художественная линия", self.line),
                             ("Материал / фактура", self.material),
                             ("Детализация", self.detail)):
            field.setAccessibleName(label)
            extra_form.addRow(label, field)
        layout.addWidget(extra)

        self.palette = QLineEdit(generator.palette)
        self.palette.setMaxLength(4000)
        self.palette.setAccessibleName("Своя палитра")
        self.palette.setPlaceholderText("HEX-коды или выберите палитру выше")

        recommended_title = QLabel("Рекомендуем палитру для вашей темы")
        recommended_title.setStyleSheet("font-size:16px;font-weight:600")
        layout.addWidget(recommended_title)
        recommended_group = QFrame()
        recommended_group.setProperty('v3Card', True)
        self.recommended_palette_grid = QGridLayout(recommended_group)
        layout.addWidget(recommended_group)

        library_group = QGroupBox("Библиотека палитр")
        library_layout = QVBoxLayout(library_group)
        self.palette_category = QComboBox()
        self.palette_category.addItems(["Все", *palette_categories()])
        self.palette_category.currentTextChanged.connect(self._refresh_palette_library)
        library_layout.addWidget(self.palette_category)
        self.palette_library_host = QWidget()
        self.palette_library_grid = QGridLayout(self.palette_library_host)
        library_layout.addWidget(self.palette_library_host)
        layout.addWidget(library_group)

        custom = QHBoxLayout()
        custom.addWidget(QLabel("Своя палитра"))
        custom.addWidget(self.palette, 1)
        self.palette_reference_button = QPushButton("Взять из референса")
        self.palette_reference_button.clicked.connect(self._go_to_references)
        custom.addWidget(self.palette_reference_button)
        layout.addLayout(custom)

        self.recommended_style_cards = []
        self.style_cards = []
        self.technique.currentTextChanged.connect(self._refresh_style_card_checks)
        self.recommended_palette_cards = []
        self.palette_cards = []
        self.theme.textChanged.connect(self._refresh_style_recommendations)
        self.context.currentTextChanged.connect(self._refresh_style_recommendations)
        self.theme.textChanged.connect(self._refresh_palette_recommendations)
        self.context.currentTextChanged.connect(self._refresh_palette_recommendations)
        self._restore_style_modifier_buttons()
        self._refresh_style_recommendations()
        self._refresh_style_library()
        self._refresh_palette_recommendations()
        self._refresh_palette_library()
        layout.addStretch()

    def _style_card(self, profile, grid, index, target):
        card = QFrame()
        card.setProperty('v3Card', True)
        card_layout = QVBoxLayout(card)
        button = QPushButton(profile.title)
        button.setCheckable(True)
        button.clicked.connect(lambda checked=False, key=profile.key: self._select_style_profile(key))
        card_layout.addWidget(button)
        detail = QLabel(" · ".join(profile.best_for[:3]))
        detail.setWordWrap(True)
        detail.setProperty('v3Small', True)
        card_layout.addWidget(detail)
        grid.addWidget(card, index // 3, index % 3)
        target.append(dict(key=profile.key, title=profile.title, category=profile.category,
                           best_for=list(profile.best_for), button=button, widget=card))

    def _refresh_style_recommendations(self, *_):
        if not hasattr(self, 'recommended_style_grid'):
            return
        self._clear_layout(self.recommended_style_grid)
        self.recommended_style_cards = []
        for index, profile in enumerate(recommended_style_profiles(
                self.theme.text().strip(), self.context.currentText().strip())):
            self._style_card(profile, self.recommended_style_grid, index, self.recommended_style_cards)
        self._refresh_style_card_checks()

    def _refresh_style_library(self, *_):
        if not hasattr(self, 'style_library_grid'):
            return
        self._clear_layout(self.style_library_grid)
        self.style_cards = []
        category = self.style_category.currentText() if hasattr(self, 'style_category') else 'Все'
        profiles = (list(featured_style_profiles()) if category == 'Все' else
                    [profile for profile in all_style_profiles() if profile.category == category])
        for index, profile in enumerate(profiles):
            self._style_card(profile, self.style_library_grid, index, self.style_cards)
        self._refresh_style_card_checks()

    def _refresh_style_card_checks(self):
        profile = get_style_profile(self.technique.currentText()) if hasattr(self, 'technique') else None
        selected = profile.key if profile is not None else None
        for card in getattr(self, 'recommended_style_cards', []) + getattr(self, 'style_cards', []):
            card['button'].setChecked(card['key'] == selected)

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

    @staticmethod
    def _clear_layout(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _select_palette(self, colors):
        self.palette.setText(' '.join(colors))

    def _palette_card(self, preset, grid, index, target):
        card = QFrame()
        card.setProperty('v3Card', True)
        card_layout = QVBoxLayout(card)
        top = QHBoxLayout()
        button = QPushButton(preset.title)
        button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
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
        grid.addWidget(card, index // 3, index % 3)
        target.append(dict(key=preset.key, title=preset.title, category=preset.category,
                           character=preset.character, colors=list(preset.colors), widget=card))

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
        self.reference_editor = ReferenceEditor(self.recipe.references)
        self.reference_editor.palette_selected.connect(self.palette.setText)
        layout.addWidget(self.reference_editor)

    def _structure(self):
        layout = self._page()
        self.presets = QComboBox()
        for title, key in (("Сбалансированный", "balanced"), ("Больше персонажей", "characters"),
                           ("Больше оформления", "decorative")):
            self.presets.addItem(title, key)
        self.presets.setAccessibleName("Рецепт распределения")
        layout.addWidget(self.presets)
        suggest = QPushButton("Предложить распределение")
        suggest.clicked.connect(self._suggest)
        layout.addWidget(suggest)
        form = QFormLayout()
        self.counts = {}
        for key, label in zip(ROLES, ROLE_LABELS):
            spin = QSpinBox()
            spin.setRange(0, 1000)
            spin.setValue(self.recipe.counts[key])
            spin.setAccessibleName(label)
            spin.valueChanged.connect(self._show_total)
            self.counts[key] = spin
            form.addRow(label, spin)
        layout.addLayout(form)
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

    def _planning_snapshot(self):
        from copy import deepcopy
        recipe = deepcopy(self.recipe)
        recipe.theme = self.theme.text().strip()
        if not recipe.theme:
            raise ValueError('Укажите основную тему набора')
        recipe.context = self.context.currentText().strip()
        recipe.motifs = [s.strip() for s in self.motifs.text().split(',') if s.strip()]
        recipe.visual = {key: widget.currentText().strip() for key, widget in self.visual_fields.items()}
        recipe.references = self.reference_editor.value()
        recipe.objects = self.object_editor.value()
        recipe.edit_counts({role: sum(item['role'] == role for item in recipe.objects) for role in ROLES})
        if recipe.objects:
            from studio_bundle_planner import propose_bundle_plan
            recipe.bundle_plan = propose_bundle_plan(recipe.objects, existing=recipe.bundle_plan)
        recipe.assistant = self.planning.selection()
        recipe.validate()
        return recipe, self.palette.text().strip()

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
            self.recipe.visual = {key: widget.currentText().strip()
                                  for key, widget in self.visual_fields.items()}
            self.recipe.references = self.reference_editor.value()
            self.recipe.assistant = self.planning.selection()
            self.recipe.objects = self.object_editor.value()
            if self.recipe.objects:
                self.recipe.edit_counts({role: sum(item['role'] == role for item in self.recipe.objects) for role in ROLES})
                from studio_bundle_planner import propose_bundle_plan
                self.recipe.bundle_plan = propose_bundle_plan(
                    self.recipe.objects, existing=self.recipe.bundle_plan)
            value = self.recipe.to_dict()
        except ValueError as error:
            self.error.setText(str(error))
            return
        base_style = style_prompt_text(self.technique.currentText(), self.mood.currentText())
        style = "; ".join(part for part in
                          (base_style, self.line.currentText().strip(),
                           self.material.currentText().strip(), self.detail.currentText().strip())
                          if part)
        if len(style) > 4000:
            self.error.setText("Сократите описание стиля до 4000 символов")
            return
        from v3_project_state import PromptGeneratorData, MAX_PROMPT_ENTRIES
        generator = PromptGeneratorData.from_dict(self.data.prompt_generator.to_dict())
        generator.style = style
        generator.palette = self.palette.text().strip()
        prompts = []
        if self.make_prompts.isChecked():
            from studio_clipart_objects import compile_objects
            try:
                prompts = compile_objects(self.recipe, generator)
                if len(self.data.prompts) + len(prompts) > MAX_PROMPT_ENTRIES:
                    raise ValueError('Общий список промптов превышает допустимый размер')
            except ValueError as error:
                self.error.setText(str(error))
                return
        self.data.recipe = value
        self.data.prompt_generator.style = style
        self.data.prompt_generator.palette = self.palette.text().strip()
        self.data.prompts.extend(prompts)
        self.accept()
