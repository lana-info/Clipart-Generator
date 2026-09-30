import threading
import time
import pytest
from PyQt6.QtWidgets import QApplication
from studio_prompt_composer_host import PromptComposerHost
from prompt_composer.model import new_draft


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def pump(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def host(tmp_path, **kw):
    return PromptComposerHost(tmp_path, settings_provider=lambda: {'openrouter_api_key': 'dummy-secret'}, authorize=lambda: True,
                              tariff=lambda *_: {'prompt': .2, 'completion': .4}, **kw)


def test_quote_then_one_use_submit_gui_delivery(tmp_path, app):
    calls, quoted, results, errors = [], [], [], []
    gui = threading.get_ident()
    def transport(*args, **kwargs):
        assert threading.get_ident() != gui
        calls.append(kwargs)
        return {'ok': True}
    service = host(tmp_path, transport=transport)
    service.quote_ai(new_draft(), quoted.append, errors.append, provider='openrouter', model='openai/gpt-5-mini')
    pump(app, lambda: bool(quoted))
    assert not calls and 'api_key' not in quoted[0]
    def done(value):
        assert threading.get_ident() == gui
        results.append(value)
    service.submit_ai(quoted[0], done, errors.append)
    pump(app, lambda: bool(results))
    with pytest.raises(ValueError, match='устарело'):
        service.submit_ai(quoted[0], done, errors.append)
    assert len(calls) == 1 and not errors


def test_close_suppresses_late_result_and_releases_lease_after_delivery(tmp_path, app):
    entered, release = threading.Event(), threading.Event()
    class Lease:
        closed = 0
        def close(self):
            self.closed += 1
    class Runtime:
        leases = []
        def acquire_job_lease(self, _):
            lease = Lease()
            self.leases.append(lease)
            return lease
    runtime = Runtime()
    def transport(*args, **kwargs):
        entered.set()
        release.wait(2)
        return {'late': True}
    service = host(tmp_path, transport=transport, runtime=runtime)
    quotes, results, errors = [], [], []
    service.quote_ai(new_draft(), quotes.append, errors.append, provider='openrouter', model='openai/gpt-5-mini')
    pump(app, lambda: bool(quotes))
    service.submit_ai(quotes[0], results.append, errors.append)
    assert entered.wait(1)
    service.close()
    release.set()
    pump(app, lambda: not service._jobs)
    assert not results and not errors
    assert [lease.closed for lease in runtime.leases] == [1, 1]


def test_revoked_access_denies_existing_host(tmp_path, app):
    allowed = True
    service = PromptComposerHost(tmp_path, settings_provider=lambda: {}, authorize=lambda: allowed)
    record = service.save(new_draft(), {'name': 'A'})
    allowed = False
    for operation in (lambda: service.generate(new_draft()), lambda: service.load(record['id']),
                      lambda: service.save(new_draft(), {'name': 'B'}), lambda: service.delete(record['id'], 1),
                      service.list_entries, service.ai_options):
        with pytest.raises(ValueError, match='доступа'):
            operation()


def test_ai_is_not_limited_to_local_choice_axes(tmp_path, app):
    service = host(tmp_path)
    draft = new_draft()
    draft['locks'] = ['style', 'lighting', 'time', 'camera', 'shot', 'angle']
    result = []
    service.quote_ai(draft, result.append, pytest.fail, provider='openrouter', model='openai/gpt-5-mini')
    pump(app, lambda: bool(result))
    service.close()


def test_fresh_authorization_denies_paid_request_after_quote(tmp_path, app):
    quoted, errors, sent = [], [], []
    service = host(tmp_path, authorize_request=lambda: False,
                   transport=lambda *a, **kw: sent.append(kw))
    service.quote_ai(new_draft(), quoted.append, errors.append,
                     provider='openrouter', model='openai/gpt-5-mini')
    pump(app, lambda: bool(quoted))
    service.submit_ai(quoted[0], lambda result: pytest.fail('unexpected result'), errors.append)
    pump(app, lambda: bool(errors))
    assert not sent
    with pytest.raises(ValueError, match='устарело'):
        service.submit_ai(quoted[0], lambda result: None, errors.append)
    service.close()
