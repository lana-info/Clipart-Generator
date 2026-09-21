"""Local reference selection, roles and editable observations."""
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                             QListWidget, QLabel, QCheckBox, QPlainTextEdit, QFileDialog, QRadioButton, QButtonGroup)
from studio_clipart_references import (
    REFERENCE_ROLES, validate_references, reference_thumbnail, extract_palette,
    reference_file_info,
    reference_image_upload_info,
)


class ReferenceEditor(QWidget):
    palette_selected = pyqtSignal(str)

    @staticmethod
    def generation_reference_snapshot(paths):
        return {path: reference_image_upload_info(path)['sha256'] for path in paths}

    def __init__(self, references, parent=None):
        super().__init__(parent)
        self.references = validate_references(references)
        self.selected = -1
        self.loading = False
        self._ai_image_paths = set()
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
        self.reference_info = QLabel("")
        self.reference_info.setProperty('v3Small', True)
        right.addWidget(self.reference_info)
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
        right.addWidget(QLabel("Использование в AI-подборе"))
        self.ai_usage_group = QButtonGroup(self)
        self.text_only_radio = QRadioButton("Только текстовые признаки — изображение не отправляется")
        self.send_image_radio = QRadioButton("Передать изображение модели — только для следующего AI-подбора")
        self.ai_usage_group.addButton(self.text_only_radio)
        self.ai_usage_group.addButton(self.send_image_radio)
        self.text_only_radio.setChecked(True)
        self.send_image_radio.toggled.connect(self._store_ai_choice)
        right.addWidget(self.text_only_radio)
        right.addWidget(self.send_image_radio)
        self.ai_privacy_note = QLabel("Перед запуском будет отдельное подтверждение. Разрешение не сохраняется в проекте.")
        self.ai_privacy_note.setWordWrap(True)
        self.ai_privacy_note.setProperty('v3Small', True)
        right.addWidget(self.ai_privacy_note)
        self.ai_preflight_note = QLabel("Перед отправкой проверим поддержку изображения выбранной моделью, формат и размер файла.")
        self.ai_preflight_note.setWordWrap(True)
        self.ai_preflight_note.setProperty('v3Small', True)
        right.addWidget(self.ai_preflight_note)
        self.ai_selection_count = QLabel("Выбрано для передачи сейчас: 0 · максимум 4")
        self.ai_selection_count.setProperty('v3Small', True)
        right.addWidget(self.ai_selection_count)
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

    def set_compact_mode(self):
        self.setAcceptDrops(True)
        self.files.setAcceptDrops(False)
        self.files.setMinimumHeight(180)
        self.files.setMaximumHeight(340)
        self.files.setIconSize(QSize(64, 64))
        right = self.layout().itemAt(1).layout()
        for index in range(right.count()):
            widget = right.itemAt(index).widget()
            if widget is not None and widget not in (self.preview, self.reference_info, self.status):
                widget.hide()
        self.preview.setMaximumHeight(300)
        for index, item in enumerate(self.references):
            self.files.item(index).setIcon(QIcon(item['path']))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            try:
                self.add_reference(url.toLocalFile())
            except (OSError, ValueError) as error:
                self.status.setText(str(error))
                break
        event.acceptProposedAction()

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
        self.files.item(self.files.count() - 1).setIcon(QIcon(path))
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
        self.text_only_radio.setEnabled(valid)
        self.send_image_radio.setEnabled(valid)
        send_image = bool(valid and item.get('path') in self._ai_image_paths)
        self.send_image_radio.setChecked(send_image)
        self.text_only_radio.setChecked(not send_image)
        self.palette.setEnabled(valid)
        self.preview.clear()
        self.reference_info.clear()
        self.status.clear()
        if valid:
            try:
                info = reference_file_info(item['path'])
                label = {'image/png': 'PNG', 'image/jpeg': 'JPEG', 'image/webp': 'WebP'}[info['mime_type']]
                size_mb = info['size'] / (1024 * 1024)
                self.reference_info.setText(f"{label} · {info['width']}×{info['height']} · {size_mb:.1f} МБ")
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

    def _store_ai_choice(self, checked):
        if self.loading or self.selected < 0 or self.selected >= len(self.references):
            return
        path = self.references[self.selected]['path']
        if checked:
            self._ai_image_paths.add(path)
        else:
            self._ai_image_paths.discard(path)
        self._update_ai_selection_count()

    def _update_ai_selection_count(self):
        self.ai_selection_count.setText(
            f"Выбрано для передачи сейчас: {len(self.selected_ai_image_paths())} · максимум 4"
        )

    def selected_ai_image_paths(self):
        return tuple(item['path'] for item in self.references if item['path'] in self._ai_image_paths)

    def clear_ai_image_paths(self):
        self._ai_image_paths.clear()
        if self.selected >= 0:
            previous = self.loading
            self.loading = True
            self.send_image_radio.setChecked(False)
            self.text_only_radio.setChecked(True)
            self.loading = previous
        self._update_ai_selection_count()

    def consume_ai_image_paths(self):
        paths = self.selected_ai_image_paths()
        self.clear_ai_image_paths()
        return paths

    def _remove(self):
        if self.selected < 0:
            return
        index = self.selected
        removed_path = self.references[index]['path']
        self._ai_image_paths.discard(removed_path)
        self._update_ai_selection_count()
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
