from pathlib import Path

import main
import provider_clients
from provider_clients import check_kie_balance, parse_kie_balance_response
from v3_api_settings import check_photoroom_balance, load_credentials, save_credentials


def test_credentials_round_trip(tmp_path: Path):
    path = tmp_path / ".env"
    save_credentials({"kie_api_key": "kie-test", "photoroom_api_key": "photo-test", "ignored": "x"}, path)
    assert load_credentials(path) == {"kie_api_key": "kie-test", "photoroom_api_key": "photo-test"}


def test_macos_runtime_reads_credentials_from_application_support(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(main.sys, "platform", "darwin")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Path(main.get_user_data_dir()) == (
        tmp_path / "Library" / "Application Support" / "Vibix Images"
    )


def test_balance_parser(monkeypatch):
    monkeypatch.setattr(provider_clients, "secure_json_request", lambda *args, **kwargs: {"data": {"credits": 12.5}})
    assert "12.5" in check_kie_balance("secret")


def test_balance_parser_accepts_official_scalar_data_response(monkeypatch):
    monkeypatch.setattr(
        provider_clients,
        "secure_json_request",
        lambda *args, **kwargs: {"code": 200, "msg": "success", "data": 100},
    )
    assert check_kie_balance("secret") == "Баланс KIE: 100"


def test_balance_parser_rejects_unknown_schema():
    import pytest

    with pytest.raises(ValueError):
        parse_kie_balance_response({"data": {"unexpected": 12}})


def test_photoroom_balance_parser(monkeypatch):
    monkeypatch.setattr(provider_clients, "secure_json_request", lambda *args, **kwargs: {"images": {"available": 83, "subscription": 100}})
    assert "83" in check_photoroom_balance("secret")
