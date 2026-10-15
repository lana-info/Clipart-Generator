"""Balance transport, real Qt worker, journal and ZIP export; offline only."""
import json
import zipfile
import pytest
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QApplication
from diagnostics import DiagnosticJournal
from v3_api_settings import _BalanceCheck, ApiSettingsDialog

@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])

def test_real_transport_failure_survives_journal_and_zip(tmp_path, monkeypatch, app):
    secret = "fixture-private-key-not-for-logs"
    body = {"data": {"wallet": {"point_remain": 700}, "api_key": secret,
                     "account_name": "Private Fixture Person", "email": "fixture@example.org"}}
    class Response:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return json.dumps(body).encode()
    monkeypatch.setattr("network_security.urllib.request.OpenerDirector.open", lambda *a, **k: Response())
    journal = DiagnosticJournal(tmp_path, app_version="test-balance-diagnostics")
    worker = _BalanceCheck("piapi", secret, diagnostic_journal=journal)
    messages = []
    worker.signals.completed.connect(messages.append)
    worker.run()
    assert worker.key == ""
    assert len(messages) == 1 and "equivalent_in_usd" in messages[0]
    events = journal.read_events()
    failed = next(e for e in events if e["event"] == "provider_balance_failed")
    assert failed["details"]["http_status"] == 200
    assert failed["details"]["stage"] == "parse_response"
    assert failed["details"]["reason"] == "usd_field_missing"
    assert "$.data.wallet:object" in failed["details"]["response_schema"]
    assert failed["operation_id"] == failed["details"]["correlation_id"]
    archive_path = journal.export_zip(tmp_path / "diagnostics.zip")
    with zipfile.ZipFile(archive_path) as archive:
        exported = json.loads(archive.read("diagnostics.json"))
        assert any(e["event"] == "provider_balance_failed" for e in exported["events"])
        text = "\n".join(archive.read(n).decode() for n in archive.namelist())
    for private in (secret, "Private Fixture Person", "fixture@example.org"):
        assert private not in text
    journal.close()

def test_actual_transport_status_is_not_invented(tmp_path, monkeypatch, app):
    class Response:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b'{"equivalent_in_usd":"3.25"}'
    monkeypatch.setattr("network_security.urllib.request.OpenerDirector.open", lambda *a, **k: Response())
    journal = DiagnosticJournal(tmp_path, app_version="test")
    worker = _BalanceCheck("piapi", "fixture-only-key", diagnostic_journal=journal)
    worker.run()
    event = next(e for e in journal.read_events() if e["event"] == "provider_balance_succeeded")
    assert event["details"]["http_status"] == 201
    journal.close()

def test_settings_button_connects_balance_worker_to_journal(tmp_path, monkeypatch, app):
    monkeypatch.setattr("v3_api_settings.load_credentials", lambda: {})
    def request(*a, on_response, **kw):
        on_response(200)
        return {"data": {"wallet": {"point_remain": 9}}}
    monkeypatch.setattr("provider_balance.secure_json_request", request)
    journal = DiagnosticJournal(tmp_path, app_version="test")
    dialog = ApiSettingsDialog({"piapi_api_key": "fixture-only-key"}, diagnostic_journal=journal)
    try:
        dialog.piapi_balance_button.click()
        assert QThreadPool.globalInstance().waitForDone(3000)
        app.processEvents()
        assert dialog.piapi_balance_button.isEnabled()
        assert "equivalent_in_usd" in dialog.status.text()
        assert any(e["event"] == "provider_balance_failed" for e in journal.read_events())
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()
        journal.close()
