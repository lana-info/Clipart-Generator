"""Local reference selection, roles and editable observations."""
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                             QListWidget, QLabel, QCheckBox, QPlainTextEdit, QFileDialog)
from studio_clipart_references import (
    REFERENCE_ROLES, validate_references, reference_thumbnail, extract_palette,
)


class ReferenceEditor(QWidget):
    palette_selected = pyqtSignal(str)

    def __init__(self, references, parent=None):
        super().__init__(parent)
        self.references = validate_references(references)
        self.selected = -1
        self.loading = False
        root = QHBoxLayout(self)
        left, right = QVBoxLayout(), QVBoxLayout()
        root.addLayout(left, 1)
        root.addLayout(right, 2)
        self.files = QListWidget()
        self.files.setAccessibleName("Референсы набора")
        left.addWidget(self.files)
        add = QPushButton("Добавить изображения")
        add.clicked.connect(self._choose)
        left.addWidget(add)
        remove = QPushButton("Удалить из набора")
        remove.clicked.connect(self._remove)
        left.addWidget(remove)
        self.preview = QLabel("Добавьте референс или продолжите без него")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(200)
        right.addWidget(self.preview)
        right.addWidget(QLabel("Что использовать из этого изображения?"))
        self.roles = {}
        for key, title in REFERENCE_ROLES.items():
            check = QCheckBox(title)
            check.toggled.connect(self._store)
            self.roles[key] = check
            right.addWidget(check)
        self.notes = QPlainTextEdit()
        self.notes.setAccessibleName("Признаки референса")
        self.notes.setPlaceholderText("Опишите нужные признаки: например, вышивка, улыбка, поза сидя. Автоанализ пока не подключён.")
        self.notes.setMaximumHeight(100)
        self.notes.textChanged.connect(self._store)
        right.addWidget(self.notes)
        self.palette = QPushButton("Взять палитру из изображения")
        self.palette.clicked.connect(self._palette)
        right.addWidget(self.palette)
        self.status = QLabel()
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        self.files.currentRowChanged.connect(self._select)
        for item in self.references:
            self.files.addItem(Path(item['path']).name)
        self.files.setCurrentRow(0)
        if not self.references:
            self._select(-1)

    def _choose(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Референсы", "", "Изображения (*.png *.jpg *.jpeg *.webp)")
        for path in paths:
            try:
                self.add_reference(path)
            except (OSError, ValueError) as error:
                self.status.setText(str(error))
                break

    def add_reference(self, path):
        if len(self.references) >= 20:
            raise ValueError("Можно добавить до 20 референсов")
        path = str(Path(path).resolve())
        reference_thumbnail(path)
        item = {"path": path, "roles": [], "notes": ""}
        validate_references([item])
        self.references.append(item)
        self.files.addItem(Path(path).name)
        self.files.setCurrentRow(len(self.references) - 1)

    def _store(self):
        if self.loading or self.selected < 0:
            return
        item = self.references[self.selected]
        item['roles'] = [key for key, check in self.roles.items() if check.isChecked()]
        item['notes'] = self.notes.toPlainText()

    def _select(self, index):
        self.loading = True
        self.selected = index
        valid = 0 <= index < len(self.references)
        item = self.references[index] if valid else {"roles": [], "notes": ""}
        for key, check in self.roles.items():
            check.setEnabled(valid)
            check.setChecked(key in item['roles'])
        self.notes.setEnabled(valid)
        self.notes.setPlainText(item['notes'])
        self.palette.setEnabled(valid)
        self.preview.clear()
        self.status.clear()
        if valid:
            try:
                image = reference_thumbnail(item['path'])
                data = image.tobytes()
                qimage = QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()
                self.preview.setPixmap(QPixmap.fromImage(qimage))
            except (OSError, ValueError) as error:
                self.preview.setText("Референс недоступен")
                self.status.setText(str(error))
                self.palette.setEnabled(False)
        else:
            self.preview.setText("Можно продолжить без референсов")
        self.loading = False

    def _remove(self):
        if self.selected < 0:
            return
        index = self.selected
        self.files.blockSignals(True)
        self.references.pop(index)
        self.files.takeItem(index)
        self.files.blockSignals(False)
        self._select(self.files.currentRow())

    def _palette(self):
        if self.selected < 0:
            return
        try:
            colors = extract_palette(self.references[self.selected]['path'])
            self.roles['palette'].setChecked(True)
            self.palette_selected.emit(' '.join(colors))
            self.status.setText("Палитра применена. Оттенки можно исправить на экране стиля.")
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def value(self):
        self._store()
        return validate_references(self.references)
