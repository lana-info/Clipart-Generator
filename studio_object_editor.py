"""Master/detail editing for concrete clipart objects."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QListWidget, QFormLayout, QLineEdit, QComboBox, QPushButton, QLabel, QCheckBox
from studio_clipart_objects import validate_objects, new_object, OBJECT_ROLES, TEXT_FIELDS


class ObjectEditor(QWidget):
    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = validate_objects(items)
        self.selected = -1
        self.loading = False
        root = QHBoxLayout(self)
        left, right = QVBoxLayout(), QVBoxLayout()
        root.addLayout(left, 1)
        root.addLayout(right, 2)
        self.left = left
        self.buttons = []
        self.list = QListWidget()
        self.list.setAccessibleName('Объекты набора')
        left.addWidget(self.list)
        for text, handler in (('Добавить', self.add), ('Дублировать', self.duplicate), ('Удалить', self.remove)):
            button = QPushButton(text)
            button.clicked.connect(handler)
            left.addWidget(button)
            self.buttons.append(button)
        form = QFormLayout()
        self.form = form
        self.role = QComboBox()
        for key, title in zip(OBJECT_ROLES, ('Главный объект', 'Композиция', 'Венок', 'Бордюр / рамка', 'Декор')):
            self.role.addItem(title, key)
        form.addRow('Роль', self.role)
        self.fields = {}
        for key, title in zip(TEXT_FIELDS, ('Название', 'Действие / поза', 'Дополнительные предметы', 'Форма / расположение', 'Другие детали')):
            edit = QLineEdit()
            edit.setMaxLength(2000)
            edit.setAccessibleName(title)
            edit.textChanged.connect(self._store)
            self.fields[key] = edit
            form.addRow(title, edit)
        right.addLayout(form)
        self.pinned = QCheckBox('Сохранить эту идею при повторном подборе')
        self.pinned.toggled.connect(self._store)
        right.addWidget(self.pinned)
        self.right = right
        self.extra_actions = QHBoxLayout()
        right.addLayout(self.extra_actions)
        self.role.currentIndexChanged.connect(self._store)
        self.status = QLabel('Заполните названия. Поля действий и деталей необязательны.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        right.addStretch()
        self.list.currentRowChanged.connect(self._select)
        self.refresh()

    def set_compact_mode(self):
        """Fit one screen: the three list buttons in one row, tighter spacing."""
        from v3_components import make_icon_button
        row = QHBoxLayout()
        row.setSpacing(6)
        for button, kind in zip(self.buttons, ("plus", "copy", "trash")):
            self.left.removeWidget(button)
            make_icon_button(button, kind, button.text())  # icon only; text kept as tooltip/name
            row.addWidget(button)
        row.addStretch(1)
        self.tool_row = row
        self.left.addLayout(row)
        self.form.setVerticalSpacing(6)
        self.right.setSpacing(6)
        self.list.setMinimumHeight(120)
        # "Keep on re-pick" checkbox and the extra action button share one row.
        self.right.removeWidget(self.pinned)
        self.right.removeItem(self.extra_actions)
        self.right.insertWidget(1, self.pinned)
        self.status.hide()  # the hint under the fields is redundant on the compact page

    def add_action(self, widget):
        """Add an extra action (e.g. 'replace this idea') to the icon row under the list."""
        if hasattr(self, "tool_row"):
            self.tool_row.insertWidget(self.tool_row.count() - 1, widget)
        else:
            self.extra_actions.addWidget(widget)

    def refresh(self):
        index = min(max(self.selected, 0), len(self.items) - 1)
        self.list.blockSignals(True)
        self.list.clear()
        for item in self.items:
            self.list.addItem(self._title(item))
        self.list.setCurrentRow(index)
        self.list.blockSignals(False)
        self._select(index)

    @staticmethod
    def _title(item):
        return f"{item['ordinal']:03d} · {item['name'] or 'Укажите объект'}"

    def _select(self, index):
        self.loading = True
        self.selected = index
        valid = 0 <= index < len(self.items)
        self.role.setEnabled(valid)
        self.pinned.setEnabled(valid)
        self.pinned.setChecked(self.items[index].get('pinned', False) if valid else False)
        if valid:
            self.role.setCurrentIndex(self.role.findData(self.items[index]['role']))
        for key, edit in self.fields.items():
            edit.setEnabled(valid)
            edit.setText(self.items[index][key] if valid else '')
        self.loading = False

    def _store(self):
        if self.loading or self.selected < 0:
            return
        item = self.items[self.selected]
        item.update({key: edit.text() for key, edit in self.fields.items()})
        item['role'] = self.role.currentData()
        item['pinned'] = self.pinned.isChecked()
        self.list.item(self.selected).setText(self._title(item))

    def add(self):
        if len(self.items) >= 1000:
            self.status.setText('Достигнут предел: 1000 объектов')
            return
        number = max((item['ordinal'] for item in self.items), default=0) + 1
        self.items.append(new_object('hero', number))
        self.selected = len(self.items) - 1
        self.refresh()

    def duplicate(self):
        if self.selected < 0 or len(self.items) >= 1000:
            return
        original = dict(self.items[self.selected])
        self.add()
        self.items[self.selected].update({key: original[key] for key in (*TEXT_FIELDS, 'role')})
        self.refresh()

    def remove(self):
        if self.selected < 0:
            return
        self.items.pop(self.selected)
        self.refresh()

    def value(self):
        self._store()
        return validate_objects(self.items)
