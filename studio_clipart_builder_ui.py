"""Editable brief, visual direction and recipe, using the existing draft store."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QStackedWidget,
    QVBoxLayout, QWidget,
)
from studio_clipart_recipe import ClipartRecipe, ROLES
from v3_components import apply_v3_theme

ROLE_LABELS = ("Главные объекты", "Композиции", "Венки", "Бордюры и рамки", "Мелкий декор")
PALETTES = (
    ("Розовый сад", "#F8D6DF #E68BA0 #BE5566 #F5E6DB #EDE4D8"),
    ("Зимний лес", "#24483C #587662 #B24A55 #DEC7A3 #F3EBDF"),
    ("Морской", "#24566D #77B9CA #BDDCE0 #D2B390 #F5EEE1"),
    ("Осенняя охра", "#A45C38 #D89050 #DFB666 #80764B #F0E1C4"),
    ("Нежная сирень", "#81769F #B8A3CD #E8D7EA #CEE3DF #F5EEE8"),
    ("Детский праздник", "#EDAFB6 #F3D487 #9BC9CA #B5CFA0 #F7EEE0"),
    ("Винтажная бумага", "#66584D #A68B72 #C8B89F #DED2BD #F3EBDD"),
    ("Ягодный", "#762E46 #B04E6A #DC92A3 #84916C #F4E5D7"),
)


def combo(values):
    widget = QComboBox()
    widget.setEditable(True)
    widget.addItems(values)
    widget.lineEdit().setMaxLength(4000)
    return widget


class ClipartBuilderDialog(QDialog):
    """Changes remain local until Apply; cancellation preserves the project."""
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.recipe = (ClipartRecipe.from_dict(state.clipart.recipe)
                       if state.clipart.recipe is not None else ClipartRecipe())
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
        form = QFormLayout()
        generator = self.state.clipart.prompt_generator
        self.technique = combo(["", "Акварель", "Гуашь", "Карандаш", "Маркер / doodle",
                                "Плоская иллюстрация", "Пастель", "Винтажная иллюстрация"])
        # Preserve an existing custom style verbatim, including previous edits.
        self.technique.setCurrentText(generator.style)
        self.mood = combo(["", "Уютное", "Весёлое", "Сказочное", "Нежное", "Спокойное", "Праздничное"])
        self.line = combo(["", "Без художественной обводки", "Тонкая обводка", "Рисованная неровная линия"])
        self.material = combo(["", "Бумага", "Дерево", "Керамика", "Ткань", "Вышивка", "Вязаная фактура"])
        self.detail = combo(["", "Минималистично", "Умеренная детализация", "Много мелких деталей"])
        self.visual_fields = dict(zip(("technique", "mood", "line", "material", "detail"),
                                      (self.technique, self.mood, self.line, self.material, self.detail)))
        for key, value in self.recipe.visual.items():
            self.visual_fields[key].setCurrentText(value)
        for label, field in (("Техника и стиль", self.technique), ("Настроение", self.mood),
                             ("Художественная линия", self.line), ("Материал / фактура", self.material),
                             ("Детализация", self.detail)):
            field.setAccessibleName(label)
            form.addRow(label, field)
        layout.addLayout(form)
        palette_group = QGroupBox("Готовые палитры · выберите набор оттенков")
        grid = QGridLayout(palette_group)
        for i, (name, colors) in enumerate(PALETTES):
            card = QWidget()
            card_layout = QVBoxLayout(card)
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, value=colors: self.palette.setText(value))
            card_layout.addWidget(button)
            row = QHBoxLayout()
            for color in colors.split():
                swatch = QLabel()
                swatch.setFixedHeight(23)
                swatch.setToolTip(color)
                swatch.setStyleSheet(f"background:{color};border-radius:4px")
                row.addWidget(swatch)
            card_layout.addLayout(row)
            grid.addWidget(card, i // 4, i % 4)
        layout.addWidget(palette_group)
        self.palette = QLineEdit(generator.palette)
        self.palette.setMaxLength(4000)
        self.palette.setAccessibleName("Своя палитра")
        self.palette.setPlaceholderText("Выберите палитру выше или задайте свои цвета")
        layout.addWidget(self.palette)
        layout.addStretch()

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
        self.planning = PlanningPanel(self._planning_snapshot, self.object_editor, self.recipe.assistant)
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
        style = "; ".join(w.currentText().strip() for w in
                          (self.technique, self.mood, self.line, self.material, self.detail)
                          if w.currentText().strip())
        if len(style) > 4000:
            self.error.setText("Сократите описание стиля до 4000 символов")
            return
        from v3_project_state import PromptGeneratorData, MAX_PROMPT_ENTRIES
        generator = PromptGeneratorData.from_dict(self.state.clipart.prompt_generator.to_dict())
        generator.style = style
        generator.palette = self.palette.text().strip()
        prompts = []
        if self.make_prompts.isChecked():
            from studio_clipart_objects import compile_objects
            try:
                prompts = compile_objects(self.recipe, generator)
                if len(self.state.clipart.prompts) + len(prompts) > MAX_PROMPT_ENTRIES:
                    raise ValueError('Общий список промптов превышает допустимый размер')
            except ValueError as error:
                self.error.setText(str(error))
                return
        self.state.clipart.recipe = value
        self.state.clipart.prompt_generator.style = style
        self.state.clipart.prompt_generator.palette = self.palette.text().strip()
        self.state.clipart.prompts.extend(prompts)
        self.accept()
