import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import main
import provider_clients
from PyQt6.QtWidgets import QApplication
from provider_clients import check_kie_balance, parse_kie_balance_response
from v3_api_settings import (
    ApiSettingsDialog,
    _fal_platform_request,
    check_fal_balance,
    estimate_fal_cost,
    fetch_fal_pricing,
    PROVIDER_CONCURRENCY_CHOICES,
    check_photoroom_balance,
    load_credentials,
    save_credentials,
)
from network_security import HttpsOnlyRedirectHandler, NetworkSecurityError


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


def test_fal_balance_and_pricing_use_platform_api(monkeypatch):
    calls = []

    def fake_request(api_key, path, **kwargs):
        calls.append((api_key, path, kwargs))
        if path == "account/billing":
            return {"credits": {"current_balance": 12.5, "currency": "USD"}}
        if path == "models/pricing":
            return {"prices": [{"endpoint_id": "fal-ai/birefnet/v2", "unit_price": 0.01}]}
        return {"total_cost": 0.25, "currency": "USD"}

    monkeypatch.setattr("v3_api_settings._fal_platform_request", fake_request)
    assert check_fal_balance("secret") == "Баланс Fal.ai: 12.5 USD"
    assert fetch_fal_pricing("secret", ["fal-ai/birefnet/v2"])[0]["unit_price"] == 0.01
    assert estimate_fal_cost("secret", {"fal-ai/birefnet/v2": 5}) == (0.25, "USD")
    assert calls[2][2]["payload"]["estimate_type"] == "historical_api_price"


def test_fal_zero_historical_estimate_uses_complete_flat_rates(monkeypatch):
    calls = []

    def fake_request(api_key, path, **kwargs):
        calls.append(path)
        if path == "models/pricing/estimate":
            return {"total_cost": 0, "currency": "USD"}
        return {
            "prices": [
                {"endpoint_id": "fal-ai/one", "unit_price": 0.01, "unit": "image", "currency": "USD"},
                {"endpoint_id": "fal-ai/two", "unit_price": 0.02, "unit": "request", "currency": "USD"},
            ]
        }

    monkeypatch.setattr("v3_api_settings._fal_platform_request", fake_request)

    assert estimate_fal_cost("secret", {"fal-ai/one": 2, "fal-ai/two": 3}) == (0.08, "USD")
    assert calls == ["models/pricing/estimate", "models/pricing"]


def test_fal_zero_historical_estimate_rejects_megapixel_rate(monkeypatch):
    def fake_request(api_key, path, **kwargs):
        if path == "models/pricing/estimate":
            return {"total_cost": 0, "currency": "USD"}
        return {
            "prices": [
                {"endpoint_id": "fal-ai/upscale", "unit_price": 0.01, "unit": "megapixel", "currency": "USD"}
            ]
        }

    monkeypatch.setattr("v3_api_settings._fal_platform_request", fake_request)

    with pytest.raises(RuntimeError, match="Оценка пока недоступна"):
        estimate_fal_cost("secret", {"fal-ai/upscale": 1})


def test_fal_zero_historical_estimate_allows_genuine_zero_flat_rates(monkeypatch):
    def fake_request(api_key, path, **kwargs):
        if path == "models/pricing/estimate":
            return {"total_cost": 0, "currency": "USD"}
        return {
            "prices": [
                {"endpoint_id": "fal-ai/free", "unit_price": 0, "unit": "image", "currency": "USD"}
            ]
        }

    monkeypatch.setattr("v3_api_settings._fal_platform_request", fake_request)

    assert estimate_fal_cost("secret", {"fal-ai/free": 1}) == (0.0, "USD")


@pytest.mark.parametrize("total_cost", (-0.01, float("nan"), float("inf"), float("-inf")))
def test_fal_estimate_rejects_invalid_total_cost(monkeypatch, total_cost):
    monkeypatch.setattr(
        "v3_api_settings._fal_platform_request",
        lambda *args, **kwargs: {"total_cost": total_cost, "currency": "USD"},
    )

    with pytest.raises(RuntimeError, match="неподдерживаемом формате"):
        estimate_fal_cost("secret", {"fal-ai/test": 1})


@pytest.mark.parametrize("currency", ("US", "USDD", "12$"))
def test_fal_estimate_rejects_non_iso_currency(monkeypatch, currency):
    monkeypatch.setattr(
        "v3_api_settings._fal_platform_request",
        lambda *args, **kwargs: {"total_cost": 0.01, "currency": currency},
    )

    with pytest.raises(RuntimeError, match="неподдерживаемом формате"):
        estimate_fal_cost("secret", {"fal-ai/test": 1})


def test_fal_zero_historical_estimate_rejects_missing_rates(monkeypatch):
    def fake_request(api_key, path, **kwargs):
        if path == "models/pricing/estimate":
            return {"total_cost": 0, "currency": "USD"}
        return {
            "prices": [
                {"endpoint_id": "fal-ai/one", "unit_price": 0.01, "unit": "image", "currency": "USD"}
            ]
        }

    monkeypatch.setattr("v3_api_settings._fal_platform_request", fake_request)

    with pytest.raises(RuntimeError, match="Оценка пока недоступна"):
        estimate_fal_cost("secret", {"fal-ai/one": 1, "fal-ai/two": 1})


def test_fal_zero_historical_estimate_rejects_inconsistent_rate_currency(monkeypatch):
    def fake_request(api_key, path, **kwargs):
        if path == "models/pricing/estimate":
            return {"total_cost": 0, "currency": "USD"}
        return {
            "prices": [
                {"endpoint_id": "fal-ai/one", "unit_price": 0.01, "unit": "image", "currency": "EUR"}
            ]
        }

    monkeypatch.setattr("v3_api_settings._fal_platform_request", fake_request)

    with pytest.raises(RuntimeError, match="Оценка пока недоступна"):
        estimate_fal_cost("secret", {"fal-ai/one": 1})


@pytest.mark.parametrize("quantity", (0, -1, True, 1.0, "1"))
def test_fal_estimate_requires_strictly_positive_integer_quantities(quantity):
    with pytest.raises(ValueError, match="положительным целым"):
        estimate_fal_cost("secret", {"fal-ai/test": quantity})


@pytest.mark.parametrize(
    "redirect_url",
    (
        "https://attacker.example/v1/account/billing",
        "http://api.fal.ai/v1/account/billing",
    ),
)
def test_fal_platform_api_blocks_redirect_without_forwarding_authorization(
    monkeypatch, redirect_url
):
    observed = {}

    class RedirectingOpener:
        def __init__(self, handler):
            self.handler = handler

        def open(self, request, timeout):
            observed["headers"] = dict(request.headers)
            observed["unredirected_headers"] = dict(request.unredirected_hdrs)
            return self.handler.redirect_request(
                request,
                None,
                302,
                "redirect",
                {},
                redirect_url,
            )

    def build_opener(*handlers):
        redirect_handler = next(
            handler
            for handler in handlers
            if isinstance(handler, HttpsOnlyRedirectHandler)
        )
        return RedirectingOpener(redirect_handler)

    monkeypatch.setattr("v3_api_settings.urllib.request.build_opener", build_opener)

    with pytest.raises(NetworkSecurityError):
        _fal_platform_request("fal-secret", "account/billing")

    assert "Authorization" not in observed["headers"]
    assert observed["unredirected_headers"]["Authorization"] == "Key fal-secret"


def test_api_dialog_exposes_only_supported_provider_concurrency_values(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr("v3_api_settings.load_credentials", lambda: {})
    dialog = ApiSettingsDialog(
        initial={
            "kie_concurrency": 10,
            "photoroom_concurrency": 5,
            "fal_concurrency": 35,
        }
    )

    assert PROVIDER_CONCURRENCY_CHOICES == (1, 2, 3)
    assert [
        int(dialog.kie_concurrency_combo.itemData(index))
        for index in range(dialog.kie_concurrency_combo.count())
    ] == [1, 2, 3]
    assert [
        int(dialog.photoroom_concurrency_combo.itemData(index))
        for index in range(dialog.photoroom_concurrency_combo.count())
    ] == [1, 2, 3]
    assert [
        int(dialog.fal_concurrency_combo.itemData(index))
        for index in range(dialog.fal_concurrency_combo.count())
    ] == [1, 2, 3]
    assert dialog.kie_concurrency_combo.currentData() == 3
    assert dialog.photoroom_concurrency_combo.currentData() == 3
    assert dialog.fal_concurrency_combo.currentData() == 3
    dialog.close()
    app.processEvents()


def test_api_dialog_returns_provider_concurrency_but_never_writes_it_as_credential(monkeypatch):
    app = QApplication.instance() or QApplication([])
    saved = []
    monkeypatch.setattr("v3_api_settings.load_credentials", lambda: {})
    monkeypatch.setattr("v3_api_settings.save_credentials", lambda values: saved.append(dict(values)))
    dialog = ApiSettingsDialog(
        initial={
            "kie_concurrency": 3,
            "photoroom_concurrency": 3,
            "fal_concurrency": 3,
        }
    )
    dialog.kie_concurrency_combo.setCurrentIndex(
        dialog.kie_concurrency_combo.findData(1)
    )
    dialog.photoroom_concurrency_combo.setCurrentIndex(
        dialog.photoroom_concurrency_combo.findData(2)
    )
    dialog.fal_concurrency_combo.setCurrentIndex(
        dialog.fal_concurrency_combo.findData(3)
    )

    dialog._save()

    assert dialog.settings["kie_concurrency"] == 1
    assert dialog.settings["photoroom_concurrency"] == 2
    assert dialog.settings["fal_concurrency"] == 3
    assert "kie_concurrency" not in saved[0]
    assert "photoroom_concurrency" not in saved[0]
    assert "fal_concurrency" not in saved[0]
    dialog.close()
    app.processEvents()
