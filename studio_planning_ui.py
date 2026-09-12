"""Explicit asynchronous planning with tariff confirmation and discard-on-cancel."""
from threading import Event
from pathlib import Path
import copy
import json

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QPushButton, QLabel, QMessageBox

from studio_text_models import text_models_for
from studio_text_client import generate_plan, TextGenerationError
from studio_text_pricing import fetch_text_model_info
from studio_clipart_planner import planning_request, apply_suggestions


class WorkerSignals(QObject):
    completed = pyqtSignal(object, object)


class PlanningWorker(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = WorkerSignals()

    def run(self):
        try:
            value, error = self.work(), None
        except (TextGenerationError, ValueError) as exc:
            value, error = None, str(exc)
        except Exception:
            value, error = None, 'Ошибка текстового помощника. Автоповтора нет.'
        self.signals.completed.emit(value, error)


class PlanningPanel(QWidget):
    def __init__(self, snapshot, editor, selection=None, parent=None, reference_images=None, clear_reference_images=None):
        super().__init__(parent)
        self.snapshot, self.editor = snapshot, editor
        self.reference_images = reference_images or (lambda: ())
        self.clear_reference_images = clear_reference_images or (lambda: None)
        self.pending = None
        self.worker = None
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.provider = QComboBox()
        for title, key in [('KIE', 'kie'), ('OpenRouter', 'openrouter')]:
            self.provider.addItem(title, key)
        self.model = QComboBox()
        row.addWidget(self.provider)
        row.addWidget(self.model, 1)
        root.addLayout(row)
        self.provider.currentIndexChanged.connect(self._models)
        self._models()
        self.provider.setCurrentIndex(1)
        if selection:
            self.provider.setCurrentIndex(self.provider.findData(selection['provider']))
            self.model.setCurrentIndex(self.model.findData(selection['model']))
        actions = QHBoxLayout()
        self.all_button = QPushButton('Подобрать незакреплённые')
        self.one_button = QPushButton('Заменить выбранную идею')
        self.cancel_button = QPushButton('Отменить ожидание')
        self.cancel_button.setEnabled(False)
        for button in (self.all_button, self.one_button, self.cancel_button):
            actions.addWidget(button)
        root.addLayout(actions)
        self.status = QLabel('Подбор запускается только после подтверждения. По умолчанию изображения референсов не отправляются; передача возможна только по явному выбору пользователя.')
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.all_button.clicked.connect(lambda: self.start(False))
        self.one_button.clicked.connect(lambda: self.start(True))
        self.cancel_button.clicked.connect(self.cancel)

    def _models(self):
        self.model.clear()
        for route in text_models_for(self.provider.currentData()):
            self.model.addItem(route.label + (' · Experimental' if route.experimental else ''), route.model)

    def selection(self):
        return dict(provider=self.provider.currentData(), model=self.model.currentData())

    def _busy(self, busy):
        for widget in (self.provider, self.model, self.all_button, self.one_button):
            widget.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)

    def cancel(self):
        if self.pending:
            self.pending.set()
        self.pending = None
        self._busy(False)
        self.status.setText('Результат отменён. Уже отправленный запрос может быть оплачен.')

    def _run(self, work, callback):
        self.worker = PlanningWorker(work)
        self.worker.signals.completed.connect(callback)
        QThreadPool.globalInstance().start(self.worker)

    def start(self, single):
        if self.pending is not None:
            return
        selection = self.selection()
        if selection['provider'] == 'kie':
            self.status.setText('KIE выбран. Платный подбор пока недоступен: тариф и ограничение расходов ещё не подтверждены.')
            return
        try:
            recipe, palette = self.snapshot()
            ids = None
            if single:
                if self.editor.selected < 0:
                    raise ValueError('Выберите идею для замены')
                ids = [self.editor.items[self.editor.selected]['id']]
            request = planning_request(recipe, palette, ids)
            if len(request['targets']) > 80:
                raise ValueError('За один подбор допускается до 80 незакреплённых идей')
            image_paths = tuple(str(Path(path).resolve()) for path in self.reference_images())
            if len(image_paths) > 4:
                raise ValueError('Для одного AI-подбора можно передать до 4 изображений-референсов')
            reference_hashes = {}
            if image_paths:
                if len(set(image_paths)) != len(image_paths):
                    raise ValueError('Выберите разные изображения-референсы')
                from studio_clipart_references import reference_image_upload_info
                total_reference_bytes = 0
                for path in image_paths:
                    info = reference_image_upload_info(path)
                    total_reference_bytes += info['size']
                    reference_hashes[path] = info['sha256']
                if total_reference_bytes > 20 * 1024 * 1024:
                    raise ValueError('Общий размер изображений-референсов превышает 20 МБ')
            reference_snapshot = copy.deepcopy(recipe.references) if image_paths else None
            from v3_api_settings import load_credentials
            key = load_credentials().get('openrouter_api_key', '').strip()
            if not key:
                raise ValueError('Добавьте ключ OpenRouter в настройках API')
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        token = Event()
        self.pending = token
        self._busy(True)
        self.status.setText('Проверяю текущий тариф. Генерация ещё не запущена.')

        def quoted(tariff, error):
            if token.is_set():
                return
            if error:
                self._finish(error)
                return
            if image_paths and 'image' not in tuple(tariff.get('input_modalities', ())):
                self._finish('Выбранная модель не подтверждает поддержку изображений. Оставьте текстовые признаки или выберите vision-модель.')
                return
            try:
                current, current_palette = self.snapshot()
                if reference_snapshot is not None and current.references != reference_snapshot:
                    raise ValueError('Референсы изменились. Запустите подбор заново.')
                if planning_request(current, current_palette, ids) != request:
                    raise ValueError('Настройки изменились. Запустите подбор заново.')
            except ValueError as exc:
                self._finish(str(exc))
                return
            # Approximation, explicitly not a hard token or monetary cap.
            input_estimate = len(json.dumps(request, ensure_ascii=False).encode()) + 2048
            estimate = (input_estimate * tariff['prompt'] + 16000 * tariff['completion']) / 1_000_000
            text = (f"{self.model.currentText()} · OpenRouter\nИдей: {len(request['targets'])}\n"
                    f"Тариф за 1 млн токенов: вход ${tariff['prompt']:g}, выход ${tariff['completion']:g}.\n"
                    f"Ориентир с резервом на ответ: ${estimate:.4f}. Это оценка, не денежный лимит; комиссия не включена.\n"
                    + ((f'Будут переданы изображения ({len(image_paths)}): ' +
                        ', '.join(__import__('pathlib').Path(path).name for path in image_paths) +
                        '. Разрешение действует только для этого запуска. Стоимость изображений может увеличить итог.\n')
                       if image_paths else
                       'Передаются текст задания и ручные наблюдения референсов. Изображения не передаются.\n')
                    + 'Запрос может быть оплачен даже при ошибке ответа. Запустить?')
            decision = QMessageBox.question(
                self, 'Платный подбор', text,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if image_paths:
                self.clear_reference_images()
            if decision != QMessageBox.StandardButton.Yes:
                self.cancel()
                return
            if token.is_set():
                return
            try:
                current, current_palette = self.snapshot()
                if reference_snapshot is not None and current.references != reference_snapshot:
                    raise ValueError('Референсы изменились. Запустите подбор заново.')
                if planning_request(current, current_palette, ids) != request:
                    raise ValueError('Настройки изменились. Запустите подбор заново.')
            except ValueError as exc:
                self._finish(str(exc))
                return
            self.status.setText('Подбираю идеи. Можно отменить ожидание; автоповтора нет.')

            def work():
                if token.is_set():
                    return None
                return generate_plan(recipe, palette=palette, replace_ids=ids, **selection,
                                     api_key=key, approved=True, max_price={key: tariff[key] for key in ('prompt','completion','request')},
                                     reference_images=image_paths,
                                     reference_images_approved=bool(image_paths),
                                     reference_image_hashes=reference_hashes,
                                     input_modalities=tuple(tariff.get('input_modalities', ())))

            def completed(result, error):
                if token.is_set():
                    return
                if error:
                    self._finish(error)
                    return
                try:
                    current, current_palette = self.snapshot()
                    items = apply_suggestions(current, result['request'], result['suggestions'], palette=current_palette)
                    self.editor.items = items
                    self.editor.refresh()
                    self._finish('Идеи предложены. Проверьте набор и сохраните настройки.')
                except ValueError as exc:
                    self._finish(str(exc))
            self._run(work, completed)
        self._run(lambda: fetch_text_model_info(selection['model'], key), quoted)

    def _finish(self, text):
        self.pending = None
        self._busy(False)
        self.status.setText(text)
