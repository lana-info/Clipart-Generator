from pathlib import Path

import provider_clients
from provider_clients import check_kie_balance, parse_kie_balance_response
from v3_api_settings import check_photoroom_balance, load_credentials, save_credentials


def test_credentials_round_trip(tmp_path: Path):
    path = tmp_path / ".env"
    save_credentials({"kie_api_key": "kie-test", "photoroom_api_key": "photo-test", "ignored": "x"}, path)
    assert load_credentials(path) == {"kie_api_key": "kie-test", "photoroom_api_key": "photo-test"}


def test_balance_parser(monkeypatch):
    monkeypatch.setattr(provider_clients, "secure_json_request", lambda *args, **kwargs: {"data": {"credits": 12.5}})
    assert "12.5" in check_kie_balance("secret")


def test_balance_parser_rejects_unknown_schema():
    import pytest

    with pytest.raises(ValueError):
        parse_kie_balance_response({"data": {"unexpected": 12}})


def test_photoroom_balance_parser(monkeypatch):
    monkeypatch.setattr(provider_clients, "secure_json_request", lambda *args, **kwargs: {"images": {"available": 83, "subscription": 100}})
    assert "83" in check_photoroom_balance("secret")
