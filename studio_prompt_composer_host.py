"""Narrow Core façade for the downloaded composer, including cancellable Qt jobs."""
from dataclasses import dataclass
import json
import threading
import time
import uuid

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot
from studio_prompt_composer_ai import MAX_OUTPUT_TOKENS, perform_request, request_body
from studio_prompt_composer_storage import PromptLibrary
from studio_prompt_composer_api import COMPOSER_TEXT_MODELS, resolve_composer_model
from studio_text_pricing import fetch_text_tariff

MODULE_ID = 'prompt-composer'


class ComposerJob(QObject):
    finished = pyqtSignal(object, object)

    def __init__(self, work, on_done, on_error, cleanup, lease=None):
        super().__init__()
        self._cancelled = threading.Event()
        self._on_done, self._on_error, self._cleanup = on_done, on_error, cleanup
        self._work, self._lease = work, lease
        self.finished.connect(self._deliver)

    def start(self):
        threading.Thread(target=self._run, daemon=True, name='prompt-composer-text').start()
        return self

    def cancel(self):
        self._cancelled.set()

    def _run(self):
        result, error = None, None
        try:
            if not self._cancelled.is_set():
                result = self._work(self._cancelled.is_set)
        except Exception:
            # Provider/network exceptions may embed authorization headers or URLs.
            error = 'Не удалось завершить запрос. Если он был отправлен, возможно списание. Черновик сохранён; автоматического повтора нет.'
        finally:
            self.finished.emit(result, error)

    @pyqtSlot(object, object)
    def _deliver(self, result, error):
        try:
            if not self._cancelled.is_set():
                if error:
                    self._on_error(error)
                else:
                    self._on_done(result)
        finally:
            if self._lease is not None:
                self._lease.close()
            self._cleanup(self)
            self._work = self._on_done = self._on_error = None


@dataclass
class _Quote:
    snapshot: dict
    provider: str
    model: str
    api_key: str
    operation: str
    text: str
    target: str
    expires: float


class PromptComposerHost:
    can_handoff = False

    def __init__(self, root, *, settings_provider, authorize, runtime=None, authorize_request=None, tariff=fetch_text_tariff, transport=None, kernel=None):
        if kernel is None:
            # Local source tests may construct the host without a signed runtime.
            from prompt_composer import catalog, engine, model
            from types import SimpleNamespace
            kernel = SimpleNamespace(catalogue=catalog.catalogue, new_draft=model.new_draft,
                                     validate_draft=model.validate_draft, rendered_text=model.rendered_text,
                                     generate_variants=engine.generate_variants, preflight_ai=engine.preflight_ai,
                                     validate_single_scene=engine.validate_single_scene, FIELD_KEYS=model.FIELD_KEYS)
        self._kernel = kernel
        self._library = PromptLibrary(root, kernel=kernel)
        self._settings_provider = settings_provider
        self._authorize = authorize
        self._authorize_request = authorize_request or authorize
        self._runtime = runtime
        self._tariff = tariff
        self._transport = transport or (lambda *args, **kwargs: perform_request(*args, kernel=self._kernel, **kwargs))
        self._quotes, self._jobs = {}, set()
        self._closed = False

    def _check(self):
        if self._closed:
            raise ValueError('Модуль закрыт')
        if self._authorize() is not True:
            raise ValueError('Нет доступа к модулю')

    def catalogue(self):
        self._check()
        return self._kernel.catalogue()

    def new_draft(self):
        self._check()
        return self._kernel.new_draft()

    def generate(self, draft):
        self._check()
        return self._kernel.generate_variants(draft)

    def list_entries(self, kind='prompt'):
        self._check()
        return self._library.list_entries(kind)

    def load(self, entry_id):
        self._check()
        return self._library.load(entry_id)

    def save(self, draft, metadata, entry_id=None, expected_revision=None):
        self._check()
        return self._library.save(draft, metadata, entry_id, expected_revision)

    def delete(self, entry_id, expected_revision):
        self._check()
        return self._library.delete(entry_id, expected_revision)

    def import_reference(self, path):
        self._check()
        return self._library.import_reference(path)

    def reference_available(self, handle):
        self._check()
        return self._library.reference_available(handle)

    def ai_options(self):
        self._check()
        settings = self._settings_provider()
        return [{'provider': route.provider, 'model': route.model, 'label': route.label + ' · ' + route.provider,
                 'configured': bool(settings.get(route.provider + '_api_key', '').strip())} for route in COMPOSER_TEXT_MODELS]

    def _job(self, work, on_done, on_error):
        self._check()
        lease = self._runtime.acquire_job_lease(MODULE_ID) if self._runtime else None
        def deliver(result):
            try:
                self._check()
            except ValueError:
                on_error('Доступ к модулю изменился. Ответ не применён.')
                return
            on_done(result)
        job = ComposerJob(work, deliver, on_error, self._jobs.discard, lease)
        self._jobs.add(job)
        return job.start()

    def quote_ai(self, draft, on_done, on_error, operation='variants', provider=None, model=None, text='', target='ru'):
        self._check()
        snapshot = self._kernel.validate_draft(draft)
        settings = self._settings_provider()
        provider = provider or 'openrouter'
        model = model or next(route.model for route in COMPOSER_TEXT_MODELS if route.provider == provider)
        route = resolve_composer_model(provider, model)
        key = settings.get(provider + '_api_key', '')
        if not key.strip():
            raise ValueError('Укажите API-ключ в настройках студии')
        body = request_body(snapshot, provider, model, operation, text, target, kernel=self._kernel)
        if operation == 'variants':
            self._kernel.preflight_ai(snapshot)
        identifier = uuid.uuid4().hex
        private = _Quote(snapshot, provider, route.model, key, operation, text, target, time.monotonic() + 300)
        def work(cancelled):
            price = None
            if provider == 'openrouter':
                try:
                    rates = self._tariff(model, key)
                    # Conservative byte-based estimate, not a hard billing cap.
                    inputs = len(json.dumps(body, ensure_ascii=False).encode('utf-8')) + 512
                    price = (inputs * rates['prompt'] + MAX_OUTPUT_TOKENS * rates['completion']) / 1_000_000
                except Exception:
                    price = None
            return {'id': identifier, 'provider': provider, 'model': model, 'configured': True, 'price': price}
        def done(public):
            self._quotes = {k: v for k, v in self._quotes.items() if v.expires > time.monotonic()}
            self._quotes[identifier] = private
            on_done(public)
        return self._job(work, done, on_error)

    def submit_ai(self, quote, on_done, on_error):
        self._check()
        private = self._quotes.pop(quote.get('id'), None)
        if private is None or private.expires <= time.monotonic():
            raise ValueError('Подтверждение устарело; запросите новую оценку')
        if self._authorize() is not True:
            raise ValueError('Нет доступа к модулю')
        def work(cancelled):
            if cancelled():
                return None
            if self._authorize_request() is not True:
                raise ValueError('Нет доступа к модулю')
            if cancelled():
                return None
            return self._transport(private.snapshot, provider=private.provider, model=private.model,
                                   api_key=private.api_key, operation=private.operation, text=private.text,
                                   target=private.target, cancelled=cancelled)
        return self._job(work, on_done, on_error)

    def close(self):
        self._closed = True
        self._quotes.clear()
        for job in tuple(self._jobs):
            job.cancel()
