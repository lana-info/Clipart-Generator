"""Offline paid-call error contracts and actual Qt/journal delivery."""
import json
import threading
import time
from copy import deepcopy

import pytest
import requests
from PyQt6.QtWidgets import QApplication
from diagnostics import DiagnosticJournal
from prompt_composer.model import new_draft, FIELD_KEYS
from prompt_composer.engine import generate_variants
from studio_prompt_composer_ai import perform_request, MAX_OUTPUT_TOKENS
from studio_prompt_composer_host import PromptComposerHost, ComposerJob
from studio_text_errors import ComposerAIError

KEY = 'PRIVATE_TEST_KEY'
PROVIDER = 'kie'
MODEL = 'gemini-3-8-flash-openai'


def envelope(content='{}', finish='stop'):
    return {'choices':[{'finish_reason':finish,'message':{'content':content}}]}


class Response:
    def __init__(self, value, status=200):
        self.status_code = status
        self.raw = value if isinstance(value, bytes) else json.dumps(value).encode()
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def iter_content(self,*args): yield self.raw


def request(monkeypatch, value, status=200, draft=None):
    calls = []
    def post(*args, **kwargs):
        calls.append(kwargs)
        return Response(value,status)
    monkeypatch.setattr('studio_prompt_composer_ai.requests.post',post)
    try:
        return perform_request(draft or new_draft(),provider=PROVIDER,model=MODEL,api_key=KEY)
    finally:
        assert len(calls) == 1
        assert calls[0]['allow_redirects'] is False
        assert calls[0]['json']['max_tokens'] == MAX_OUTPUT_TOKENS == 12000


@pytest.mark.parametrize('status,payload,code', [
    (401,{},'auth'), (402,{},'payment'), (429,{},'rate_limit'), (503,{},'service'),
    (400,{},'http'), (200,{'code':402,'msg':KEY},'payment'),
    (200,{'code':500,'msg':KEY},'service'),
    (200,{'code':'unknown-'+KEY,'msg':KEY},'provider_error'),
    (200,envelope(finish='length'),'truncated'),
    (200,{'candidates':[{'finishReason':'MAX_TOKENS'}]},'truncated'),
    (200,envelope(finish='content_filter'),'refused'),
    (200,{'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{'name':KEY}}]}}]},'refused'),
    (200,envelope('not JSON '+KEY),'json'), (200,b'invalid '+KEY.encode(),'json'),
    (200,b'\xff','json'), (200,[],'json'), (200,envelope(),'invalid_contract'),
])
def test_failure_categories_survive_job_without_secrets_or_retry(monkeypatch,status,payload,code):
    snapshot = new_draft()
    before = deepcopy(snapshot)
    with pytest.raises(ComposerAIError) as failure:
        request(monkeypatch,payload,status,snapshot)
    assert failure.value.code == code
    assert KEY not in str(failure.value)
    output = []
    def work(_): raise failure.value
    job = ComposerJob(work,lambda _:None,output.append,lambda _:None)
    job._run()
    assert output == [str(failure.value)]
    assert snapshot == before


@pytest.mark.parametrize('error,code', [(requests.Timeout(KEY),'timeout'),(requests.ConnectionError(KEY),'network')])
def test_network_failure_not_repeated(monkeypatch,error,code):
    calls=[]
    def fail(*args,**kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr('studio_prompt_composer_ai.requests.post',fail)
    with pytest.raises(ComposerAIError) as failure:
        perform_request(new_draft(),provider=PROVIDER,model=MODEL,api_key=KEY)
    assert failure.value.code == code and KEY not in str(failure.value)
    assert calls == [1]


def valid_reply(draft):
    variants = generate_variants(draft)['variants']
    return {'status':'complete','reason':'','variants':[
        {'label':v['label'],'en':v['en'],'ru':v['ru'],
         'fields':{key:v['draft']['fields'].get(key,{'ru':'','en':''}) for key in FIELD_KEYS}}
        for v in variants]}


def test_success_and_locked_identity_still_strict(monkeypatch):
    draft = new_draft()
    draft['locks'] = ['subject']
    value = valid_reply(draft)
    data = envelope(json.dumps(value))
    data['code'] = 200
    assert len(request(monkeypatch,data,draft=draft)['variants']) == 7
    value['variants'][0]['fields']['subject'] = {'ru':'другой','en':'other'}
    with pytest.raises(ComposerAIError) as failure:
        request(monkeypatch,envelope(json.dumps(value)),draft=draft)
    assert failure.value.code == 'invalid_contract'


def pump(app,predicate):
    until = time.monotonic()+3
    while not predicate() and time.monotonic()<until:
        app.processEvents(); time.sleep(.005)
    assert predicate()


@pytest.mark.parametrize('mode', ['success','typed_failure','unexpected','cancel'])
def test_real_host_records_safe_lifecycle_and_suppresses_cancel(tmp_path,mode):
    app = QApplication.instance() or QApplication([])
    journal = DiagnosticJournal(tmp_path/'logs',app_version='test')
    calls,quotes,results,errors=[],[],[],[]
    entered,release = threading.Event(),threading.Event()
    def transport(*args,**kwargs):
        calls.append(1)
        entered.set()
        if mode == 'cancel': release.wait(2)
        if mode == 'typed_failure': raise ComposerAIError('truncated',http_status=200)
        if mode == 'unexpected': raise RuntimeError(KEY+' PRIVATE_PROMPT')
        return {'ok':True}
    host = PromptComposerHost(tmp_path/'library',settings_provider=lambda:{'kie_api_key':KEY},
        authorize=lambda:True,transport=transport,diagnostic_journal=journal)
    draft = new_draft()
    draft['fields']['subject'] = {'ru':'PRIVATE_PROMPT','en':'PRIVATE_PROMPT'}
    host.quote_ai(draft,quotes.append,errors.append,provider=PROVIDER,model=MODEL)
    pump(app,lambda:bool(quotes))
    host.submit_ai(quotes[0],results.append,errors.append)
    assert entered.wait(1)
    if mode == 'cancel': host.close(); release.set()
    pump(app,lambda:not host._jobs)
    events = sorted(journal.read_events(), key=lambda event: event["sequence"])
    assert [event['event'] for event in events] == [
        'composer_ai_started', 'composer_ai_failed' if mode in ('typed_failure','unexpected') else 'composer_ai_finished']
    encoded = json.dumps(events)
    assert KEY not in encoded and 'PRIVATE_PROMPT' not in encoded
    assert events[0]['operation_id'] == events[1]['operation_id']
    if mode == 'cancel': assert not results and not errors
    elif mode == 'success': assert results == [{'ok':True}] and not errors
    else:
        assert len(errors) == 1 and KEY not in errors[0]
        assert events[-1]['details']['error_code'] == ('truncated' if mode == 'typed_failure' else 'unexpected')
        if mode == 'typed_failure': assert 'обрезан' in errors[0]
    assert calls == [1]
    host.close(); journal.close()
