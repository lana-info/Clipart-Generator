"""Local reference selection, roles and editable observations."""
from pathlib import Path
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap, QIcon
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QPushButton,
                             QListWidget, QLabel, QCheckBox, QPlainTextEdit, QFileDialog, QRadioButton, QButtonGroup)
from studio_clipart_references import (
    REFERENCE_ROLES, validate_references, reference_thumbnail, extract_palette,
    reference_file_info, active_references,
    reference_image_upload_info,
)


class ReferenceEditor(QWidget):
    palette_selected = pyqtSignal(str)

    @staticmethod
    def generation_reference_snapshot(paths):
        return {path: reference_image_upload_info(path)['sha256'] for path in paths}

    def __init__(self, references, parent=None, selected_style=None, selected_palette=None):
        super().__init__(parent)
        self.references = validate_references(references)
        self.selected_style = selected_style or (lambda: '')
        self.selected_palette = selected_palette or (lambda: '')
        self.selected = -1
        self.loading = False
        self._compact = False
        self._ai_image_paths = set()
        root = QHBoxLayout(self)
        left, right = QVBoxLayout(), QVBoxLayout()
        root.addLayout(left, 1)
        self.right_panel = QWidget()
        self.right_panel.setLayout(right)
        root.addWidget(self.right_panel, 2)
        self.empty_panel = QLabel('Референсов пока нет. Добавьте изображение или пропустите этот шаг.')
        self.empty_panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_panel.setWordWrap(True)
        root.addWidget(self.empty_panel, 2)
        self.files = QListWidget()
        self.files.setAccessibleName("Референсы набора")
        left.addWidget(self.files)
        add = QPushButton("Добавить изображения")
        add.clicked.connect(self._choose)
        left.addWidget(add)
        self.remove_button = QPushButton("Удалить из набора")
        self.remove_button.clicked.connect(self._remove)
        left.addWidget(self.remove_button)
        self.preview = QLabel("Добавьте референс или продолжите без него")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(200)
        right.addWidget(self.preview)
        self.reference_info = QLabel("")
        self.reference_info.setProperty('v3Small', True)
        right.addWidget(self.reference_info)
        self.use_for_generation = QCheckBox("Использовать этот референс для выбранных признаков")
        self.use_for_generation.toggled.connect(self._store)
        right.addWidget(self.use_for_generation)
        right.addWidget(QLabel("Источник стиля · выберите одно"))
        self.style_source_group = QButtonGroup(self)
        self.style_from_selected = QRadioButton()
        self.style_from_reference = QRadioButton("Стиль этого референса")
        self.style_source_group.addButton(self.style_from_selected)
        self.style_source_group.addButton(self.style_from_reference)
        self.style_from_reference.toggled.connect(self._store)
        right.addWidget(self.style_from_selected)
        right.addWidget(self.style_from_reference)
        right.addWidget(QLabel("Источник палитры · выберите одно"))
        self.palette_source_group = QButtonGroup(self)
        self.palette_from_selected = QRadioButton()
        self.palette_from_reference = QRadioButton("Цвета этого референса")
        self.palette_source_group.addButton(self.palette_from_selected)
        self.palette_source_group.addButton(self.palette_from_reference)
        self.palette_from_reference.toggled.connect(self._store)
        right.addWidget(self.palette_from_selected)
        right.addWidget(self.palette_from_reference)
        right.addWidget(QLabel("Дополнительно взять из изображения"))
        role_grid = QGridLayout()
        self.roles = {}
        for key, title in REFERENCE_ROLES.items():
            if key in ('technique', 'palette'):
                self.roles[key] = (self.style_from_reference if key == 'technique'
                                   else self.palette_from_reference)
                continue
            check = QCheckBox(title)
            check.toggled.connect(self._store)
            self.roles[key] = check
            position = role_grid.count()
            role_grid.addWidget(check, position // 2, position % 2)
        right.addLayout(role_grid)
        self.notes = QPlainTextEdit()
        self.notes.setAccessibleName("Признаки референса")
        self.notes.setPlaceholderText("Опишите нужные признаки: например, вышивка, улыбка, поза сидя. Автоанализ пока не подключён.")
        self.notes.setMaximumHeight(100)
        self.notes.textChanged.connect(self._store)
        right.addWidget(self.notes)
        self.ai_usage_title = QLabel("Использование в AI-подборе")
        right.addWidget(self.ai_usage_title)
        self.generation_note = QLabel(
            "При создании изображений модель увидит включённый референс. "
            "При подборе идей учитываются только ваши заметки.")
        self.generation_note.setWordWrap(True)
        self.generation_note.setProperty('v3Small', True)
        right.addWidget(self.generation_note)
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
        self.refresh_source_labels()
        for item in self.references:
            self.files.addItem(Path(item['path']).name)
        self.files.setCurrentRow(0)
        if not self.references:
            self._select(-1)

    def set_compact_mode(self):
        self._compact = True
        self.setAcceptDrops(True)
        self.files.setAcceptDrops(False)
        self.files.setMinimumHeight(180)
        self.files.setMaximumHeight(240)
        self.files.setIconSize(QSize(64, 64))
        for widget in (self.text_only_radio, self.send_image_radio, self.ai_privacy_note,
                       self.ai_preflight_note, self.ai_selection_count, self.ai_usage_title,
                       self.palette):
            widget.hide()
        self.preview.setFixedHeight(150)
        self.notes.setMaximumHeight(64)
        for index, item in enumerate(self.references):
            self.files.item(index).setIcon(QIcon(item['path']))
        self._select(self.selected)

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
        enabled = len(active_references(self.references)) < 5
        # New references have one visible, editable purpose instead of an implicit
        # subject-only fallback in the generated prompt.
        item = {"path": path, "roles": ["subject"], "notes": "", "enabled": enabled}
        validate_references([item])
        self.references.append(item)
        self.files.addItem(Path(path).name)
        self.files.item(self.files.count() - 1).setIcon(QIcon(path))
        self.files.setCurrentRow(len(self.references) - 1)
        if not enabled:
            self.status.setText('Можно добавить до 20 изображений, но для генерации выбрать не более 5. Новый референс пока выключен.')

    def _store(self):
        if self.loading or self.selected < 0:
            return
        item = self.references[self.selected]
        if self.use_for_generation.isChecked() and sum(
                other.get('enabled', True) for index, other in enumerate(self.references)
                if index != self.selected) >= 5:
            self.loading = True
            self.use_for_generation.setChecked(False)
            self.loading = False
            self.status.setText('Для генерации можно выбрать не более 5 референсов.')
            return
        item['enabled'] = self.use_for_generation.isChecked()
        item['roles'] = [key for key, check in self.roles.items() if check.isChecked()]
        item['notes'] = self.notes.toPlainText()
        for role in ('technique', 'palette'):
            if role in item['roles']:
                for index, other in enumerate(self.references):
                    if index != self.selected and role in other['roles']:
                        other['roles'].remove(role)
        self._update_reference_controls()

    def refresh_source_labels(self):
        self.style_from_selected.setText('Выбранный стиль: ' + (self.selected_style().strip() or 'не выбран'))
        self.palette_from_selected.setText('Выбранная палитра: ' + (self.selected_palette().strip() or 'не выбрана'))

    def _update_reference_controls(self):
        active = self.selected >= 0 and self.use_for_generation.isChecked()
        for widget in (*self.roles.values(), self.style_from_selected, self.palette_from_selected,
                       self.notes):
            widget.setEnabled(active)

    def active_generation_paths(self):
        return tuple(item['path'] for item in active_references(self.value()))

    def active_references(self):
        return active_references(self.value())

    def disable_all(self):
        self._store()
        for item in self.references:
            item['enabled'] = False
        if self.selected >= 0:
            self.loading = True
            self.use_for_generation.setChecked(False)
            self.loading = False
            self._update_reference_controls()
        self.clear_ai_image_paths()

    def _select(self, index):
        self.loading = True
        self.selected = index
        valid = 0 <= index < len(self.references)
        self.remove_button.setEnabled(valid)
        self.right_panel.setVisible(valid)
        self.empty_panel.setVisible(not valid)
        item = self.references[index] if valid else {"roles": [], "notes": "", "enabled": False}
        self.use_for_generation.setEnabled(valid)
        self.use_for_generation.setChecked(bool(valid and item.get('enabled', True)))
        for key, check in self.roles.items():
            check.setChecked(key in item['roles'])
        self.style_from_selected.setChecked('technique' not in item['roles'])
        self.palette_from_selected.setChecked('palette' not in item['roles'])
        self.refresh_source_labels()
        self._update_reference_controls()
        self.notes.setPlainText(item['notes'])
        self.text_only_radio.setEnabled(valid and item.get('enabled', True))
        self.send_image_radio.setEnabled(valid and item.get('enabled', True))
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
                preview_size = QSize(300, 150 if self._compact else 200)
                self.preview.setPixmap(QPixmap.fromImage(qimage).scaled(
                    preview_size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation))
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
        return tuple(item['path'] for item in self.references
                     if item.get('enabled', True) and item['path'] in self._ai_image_paths)

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
            for item in self.references:
                if 'palette' in item['roles']:
                    item['roles'].remove('palette')
            self.loading = True
            self.palette_from_selected.setChecked(True)
            self.loading = False
            self.palette_selected.emit(' '.join(colors))
            self.status.setText("Палитра применена. Оттенки можно исправить на экране стиля.")
        except (OSError, ValueError) as error:
            self.status.setText(str(error))

    def value(self):
        self._store()
        return validate_references(self.references)
