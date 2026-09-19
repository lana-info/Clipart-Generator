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
    busy_changed = pyqtSignal()
    def __init__(self, snapshot, editor, selection=None, parent=None, reference_images=None, clear_reference_images=None):
        super().__init__(parent)
        self.snapshot, self.editor = snapshot, editor
        self.authorize = None
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
        self.busy_changed.emit()

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
            target_ids = [target['id'] for target in request['targets']]
            batches = [target_ids[index:index + 80]
                       for index in range(0, len(target_ids), 80)]
            batch_requests = [planning_request(recipe, palette, list(batch)) for batch in batches]
            if any(len(json.dumps(batch_request, ensure_ascii=False).encode()) > 200_000
                   for batch_request in batch_requests):
                raise ValueError('Сократите описание набора перед подбором')
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

        def current_matches_request():
            current, current_palette = self.snapshot()
            if reference_snapshot is not None and current.references != reference_snapshot:
                raise ValueError('Референсы изменились. Запустите подбор заново.')
            if planning_request(current, current_palette, ids) != request:
                raise ValueError('Настройки изменились. Запустите подбор заново.')
            return current, current_palette

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
                current_matches_request()
            except ValueError as exc:
                self._finish(str(exc))
                return
            # Estimate: each batch reserves its own response budget; it is not a monetary ceiling.
            input_estimate = sum(
                len(json.dumps(batch_request, ensure_ascii=False).encode()) + 2048
                for batch_request in batch_requests
            )
            estimate = (
                input_estimate * tariff['prompt']
                + 16000 * len(batches) * tariff['completion']
            ) / 1_000_000
            image_note = 'Передаются текст задания и ручные наблюдения референсов. Изображения не передаются.\n'
            if image_paths:
                image_note = (
                    f'Будут переданы изображения ({len(image_paths)}): '
                    + ', '.join(Path(path).name for path in image_paths)
                    + '. Разрешение действует только для этого запуска. '
                    + ('Изображения будут переданы в каждом запросе этого подбора. '
                       if len(batches) > 1 else '')
                    + 'Стоимость изображений может увеличить итог.\n'
                )
            text = (
                f"{self.model.currentText()} · OpenRouter\n"
                f"Идей: {len(request['targets'])}\n"
                f"Запросов: {len(batches)} (не более 80 идей в каждом)\n"
                f"Тариф за 1 млн токенов: вход ${tariff['prompt']:g}, выход ${tariff['completion']:g}.\n"
                f"Ориентир с резервом на все ответы: ${estimate:.4f}. Это оценка, не денежный лимит; комиссия не включена.\n"
                + image_note
                + 'Запросы выполняются последовательно без автоповторов. Уже отправленный запрос может быть оплачен даже при ошибке. Запустить?'
            )
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
                current_matches_request()
            except ValueError as exc:
                self._finish(str(exc))
                return

            collected = []
            working_recipe = copy.deepcopy(recipe)

            def run_batch(batch_index):
                if token.is_set():
                    return
                if batch_index >= len(batches):
                    try:
                        current, current_palette = current_matches_request()
                        items = apply_suggestions(
                            current, request, collected, palette=current_palette
                        )
                        self.editor.items = items
                        self.editor.refresh()
                        self._finish('Идеи предложены. Проверьте набор и сохраните настройки.')
                    except ValueError as exc:
                        self._finish(f'{exc} Набор не изменён.')
                    return

                batch = list(batches[batch_index])
                batch_recipe = copy.deepcopy(working_recipe)
                expected_request = planning_request(batch_recipe, palette, batch)
                self.status.setText(
                    f'Подбираю идеи: запрос {batch_index + 1} из {len(batches)}. '
                    'Можно отменить ожидание; автоповтора нет.'
                )

                def work():
                    if token.is_set():
                        return None
                    if self.authorize is not None:
                        self.authorize()
                    if token.is_set():
                        return None
                    return generate_plan(
                        batch_recipe, palette=palette, replace_ids=batch, **selection,
                        api_key=key, approved=True,
                        max_price={name: tariff[name] for name in ('prompt', 'completion', 'request')},
                        reference_images=image_paths,
                        reference_images_approved=bool(image_paths),
                        reference_image_hashes=reference_hashes,
                        input_modalities=tuple(tariff.get('input_modalities', ())),
                    )

                def completed(result, error):
                    if token.is_set():
                        return
                    if error:
                        self._finish(
                            f'{error} Набор не изменён. Уже завершённые запросы могли быть оплачены.'
                        )
                        return
                    try:
                        if not isinstance(result, dict):
                            raise ValueError('Текстовый помощник вернул неверный результат')
                        result_request = result.get('request')
                        suggestions = result.get('suggestions')
                        if result_request != expected_request:
                            raise ValueError('Ответ относится к другому батчу')
                        # Keep previous batch suggestions only in a private working copy.
                        # The editor/project is changed atomically only after every batch succeeds.
                        next_objects = apply_suggestions(
                            working_recipe, result_request, suggestions, palette=palette
                        )
                        current_matches_request()
                        working_recipe.objects = next_objects
                        collected.extend(suggestions)
                    except (TypeError, ValueError) as exc:
                        self._finish(f'{exc} Набор не изменён.')
                        return
                    run_batch(batch_index + 1)

                self._run(work, completed)

            run_batch(0)

        self._run(lambda: fetch_text_model_info(selection['model'], key), quoted)

    def _finish(self, text):
        self.pending = None
        self._busy(False)
        self.status.setText(text)
