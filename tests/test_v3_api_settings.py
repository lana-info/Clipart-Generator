from pathlib import Path

from v3_api_settings import check_kie_balance, load_credentials, save_credentials


def test_credentials_round_trip(tmp_path: Path):
    path = tmp_path / ".env"
    save_credentials({"kie_api_key": "kie-test", "photoroom_api_key": "photo-test", "ignored": "x"}, path)
    assert load_credentials(path) == {"kie_api_key": "kie-test", "photoroom_api_key": "photo-test"}


def test_balance_parser(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, _limit): return b'{"data":{"credits":12.5}}'
    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    assert "12.5" in check_kie_balance("secret")
