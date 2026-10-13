from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request
import json
import math
from pathlib import Path
from typing import Any, Mapping

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from v3_components import ButtonVariant, V3Button
from api_credentials import ALL_PROVIDER_CREDENTIAL_KEYS, ProviderCredentialStore
from provider_clients import check_kie_balance, check_photoroom_balance
from app_identity import APP_NAME, APP_STORAGE_NAME
from network_security import HttpsOnlyRedirectHandler
from runtime_settings import API_CONCURRENCY_CHOICES, normalize_api_concurrency
from provider_balance import check_provider_balance


def check_openrouter_balance(api_key: str, timeout: float = 15.0) -> str:
    import requests
    from decimal import Decimal, InvalidOperation
    key = str(api_key or '').strip()
    if not key:
        raise ValueError('Введите OpenRouter API Key')
    def read(endpoint):
        with requests.get('https://openrouter.ai/api/v1/' + endpoint,
                          headers={'Authorization': f'Bearer {key}'},
                          timeout=timeout, allow_redirects=False, stream=True) as response:
            if response.status_code == 403 and endpoint == 'credits':
                return None
            if response.status_code in (401, 403):
                raise ValueError('OpenRouter отклонил ключ или у ключа недостаточно прав')
            if response.status_code != 200:
                raise ValueError('OpenRouter не вернул баланс. Повторите проверку позже')
            raw = bytearray()
            for chunk in response.iter_content(8192):
                raw.extend(chunk)
                if len(raw) > 65536:
                    raise ValueError('Ответ OpenRouter слишком большой')
            data = json.loads(raw)['data']
            if not isinstance(data, dict):
                raise ValueError('OpenRouter вернул неподдерживаемый формат баланса')
            return data
    try:
        data = read('credits')
        if data is None:
            data = read('key')
            remaining = data.get('limit_remaining')
            if remaining is None:
                return 'Ключ OpenRouter действителен. Лимит ключа не задан; баланс аккаунта доступен в кабинете OpenRouter.'
            balance = Decimal(str(remaining))
            if not balance.is_finite():
                raise ValueError('Некорректный лимит OpenRouter')
            return f'Остаток лимита ключа OpenRouter: {balance:.2f} USD (не баланс аккаунта)'
        else:
            balance = Decimal(str(data['total_credits'])) - Decimal(str(data['total_usage']))
            if not balance.is_finite():
                raise ValueError('Некорректный баланс OpenRouter')
        return f'Баланс OpenRouter: {balance:.2f} USD'
    except requests.RequestException:
        raise RuntimeError('Не удалось обратиться к OpenRouter') from None
    except (KeyError, TypeError, InvalidOperation, json.JSONDecodeError):
        raise RuntimeError('OpenRouter вернул неподдерживаемый формат баланса') from None


def _fal_platform_request(
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    params: Mapping[str, str] | None = None,
    payload: Mapping[str, Any] | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Введите Fal.ai API Key")
    url = f"https://api.fal.ai/v1/{path.lstrip('/')}"
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode(params)
    body = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Key {key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    authorization = request.get_header("Authorization")
    if authorization:
        request.remove_header("Authorization")
        request.add_unredirected_header("Authorization", authorization)
    try:
        opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(512 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            raise RuntimeError("Fal.ai отклонил ключ или у ключа недостаточно прав") from error
        if error.code == 429:
            raise RuntimeError("Fal.ai временно ограничил частоту запросов") from error
        raise RuntimeError(f"Fal.ai не вернул данные ({error.code})") from error
    except (urllib.error.URLError, OSError) as error:
        raise RuntimeError("Не удалось обратиться к Fal.ai") from error
    try:
        result = json.loads(raw)
    except (UnicodeError, ValueError) as error:
        raise RuntimeError("Fal.ai вернул неподдерживаемый ответ") from error
    if not isinstance(result, dict):
        raise RuntimeError("Fal.ai вернул неожиданный формат ответа")
    return result


def check_fal_balance(api_key: str, timeout: float = 15.0) -> str:
    payload = _fal_platform_request(
        api_key,
        "account/billing",
        params={"expand": "credits"},
        timeout=timeout,
    )
    credits = payload.get("credits")
    if not isinstance(credits, Mapping) or "current_balance" not in credits:
        raise RuntimeError("Fal.ai вернул баланс в неподдерживаемом формате")
    currency = str(credits.get("currency") or "USD").upper()
    return f"Баланс Fal.ai: {credits['current_balance']} {currency}"


def fetch_fal_pricing(
    api_key: str,
    endpoint_ids: str | list[str] | tuple[str, ...],
    timeout: float = 15.0,
) -> tuple[dict[str, Any], ...]:
    if isinstance(endpoint_ids, str):
        endpoint_ids = (endpoint_ids,)
    normalized = tuple(str(endpoint).strip() for endpoint in endpoint_ids if str(endpoint).strip())
    if not normalized or len(normalized) > 50:
        raise ValueError("Укажите от 1 до 50 Fal.ai endpoint ID")
    payload = _fal_platform_request(
        api_key,
        "models/pricing",
        params={"endpoint_id": ",".join(normalized)},
        timeout=timeout,
    )
    prices = payload.get("prices")
    if not isinstance(prices, list):
        raise RuntimeError("Fal.ai вернул цены в неподдерживаемом формате")
    return tuple(item for item in prices if isinstance(item, dict))


def estimate_fal_cost(
    api_key: str,
    endpoint_quantities: Mapping[str, int],
    timeout: float = 15.0,
) -> tuple[float, str]:
    quantities: dict[str, int] = {}
    for endpoint, quantity in endpoint_quantities.items():
        endpoint_id = str(endpoint).strip()
        if not endpoint_id:
            raise ValueError("Укажите Fal.ai endpoint ID")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Количество Fal.ai вызовов должно быть положительным целым числом")
        quantities[endpoint_id] = quantity
    if not quantities:
        raise ValueError("Укажите количество Fal.ai вызовов")
    payload = _fal_platform_request(
        api_key,
        "models/pricing/estimate",
        method="POST",
        payload={
            "estimate_type": "historical_api_price",
            "endpoints": {endpoint: {"call_quantity": quantity} for endpoint, quantity in quantities.items()},
        },
        timeout=timeout,
    )
    try:
        total_cost = float(payload["total_cost"])
        currency = _normalize_fal_currency(payload["currency"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("Fal.ai вернул оценку стоимости в неподдерживаемом формате") from error
    if not math.isfinite(total_cost) or total_cost < 0:
        raise RuntimeError("Fal.ai вернул оценку стоимости в неподдерживаемом формате")
    if total_cost > 0:
        return total_cost, currency

    return _estimate_zero_historical_fal_cost(
        api_key,
        quantities,
        historical_currency=currency,
        timeout=timeout,
    )


def _normalize_fal_currency(value: Any) -> str:
    currency = str(value).upper()
    if len(currency) != 3 or not currency.isalpha():
        raise ValueError("currency must be an ISO 4217 code")
    return currency


def _estimate_zero_historical_fal_cost(
    api_key: str,
    quantities: Mapping[str, int],
    *,
    historical_currency: str,
    timeout: float,
) -> tuple[float, str]:
    prices = fetch_fal_pricing(api_key, list(quantities), timeout=timeout)
    by_endpoint: dict[str, dict[str, Any]] = {}
    for price in prices:
        endpoint_id = str(price.get("endpoint_id") or "").strip()
        if endpoint_id not in quantities or endpoint_id in by_endpoint:
            raise RuntimeError("Оценка пока недоступна: Fal.ai не вернул однозначные тарифы для выбранных операций")
        by_endpoint[endpoint_id] = price

    if set(by_endpoint) != set(quantities):
        raise RuntimeError("Оценка пока недоступна: Fal.ai не вернул тарифы для всех выбранных операций")

    total_cost = 0.0
    for endpoint_id, quantity in quantities.items():
        price = by_endpoint[endpoint_id]
        unit = str(price.get("unit") or "").strip().lower()
        if unit not in {"image", "request"}:
            raise RuntimeError(
                "Оценка пока недоступна: для Fal.ai нужны размеры или длительность, "
                "а тариф операции не является фиксированным за image/request"
            )
        try:
            unit_price = float(price["unit_price"])
            price_currency = _normalize_fal_currency(price["currency"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError("Оценка пока недоступна: Fal.ai вернул неполный тариф операции") from error
        if not math.isfinite(unit_price) or unit_price < 0:
            raise RuntimeError("Оценка пока недоступна: Fal.ai вернул недопустимый тариф операции")
        if price_currency != historical_currency:
            raise RuntimeError("Оценка пока недоступна: Fal.ai вернул тарифы в разных валютах")
        total_cost += unit_price * quantity
        if not math.isfinite(total_cost):
            raise RuntimeError("Оценка пока недоступна: Fal.ai вернул недопустимый тариф операции")

    return total_cost, historical_currency


def user_env_path() -> Path:
    if sys.platform == "darwin":
        directory = Path.home() / "Library" / "Application Support" / APP_STORAGE_NAME
    else:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        directory = Path(base) / APP_STORAGE_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory / ".env"


def user_fal_key_path() -> Path:
    return user_env_path().with_name("fal_api_key.bin")


def load_credentials(path: Path | None = None) -> dict[str, str]:
    env_path = path or user_env_path()
    return ProviderCredentialStore(
        env_path,
        env_path.with_name("fal_api_key.bin"),
    ).load()


def save_credentials(values: Mapping[str, str], path: Path | None = None) -> Path:
    destination = path or user_env_path()
    ProviderCredentialStore(
        destination,
        destination.with_name("fal_api_key.bin"),
    ).save(
        {
            key: str(values.get(key) or "").strip()
            for key in ALL_PROVIDER_CREDENTIAL_KEYS
        }
    )
    return destination


def _legacy_check_kie_balance(api_key: str, timeout: float = 15.0) -> str:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Введите KIE API Key")
    request = urllib.request.Request(
        "https://api.kie.ai/api/v1/chat/credit",
        headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(256 * 1024).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as error:
        raise RuntimeError("Не удалось проверить баланс KIE") from error
    try:
        import json

        payload: Any = json.loads(raw)
    except ValueError as error:
        raise RuntimeError("KIE вернул неподдерживаемый ответ") from error
    if isinstance(payload, dict):
        data = payload.get("data", payload)
        if isinstance(data, dict):
            for name in ("credit", "credits", "balance", "amount"):
                if name in data:
                    return f"Баланс KIE: {data[name]}"
    return "Баланс KIE получен, формат ответа требует уточнения."


class ApiSettingsDialog(QDialog):
    def __init__(self, initial: Mapping[str, Any] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Настройки API")
        self.setMinimumWidth(560)
        values = dict(load_credentials())
        values.update(initial or {})
        layout = QVBoxLayout(self)
        credentials_help = QLabel(
            "Ключи KIE/OpenRouter/PhotoRoom/AtlasCloud/PiAPI хранятся локально в пользовательском .env; "
            "Fal.ai сохраняется в защищённом хранилище Windows и не показывается в логах."
        )
        credentials_help.setWordWrap(True)
        layout.addWidget(credentials_help)
        provider_help = QLabel(
            '<b>Пополнение и управление:</b> '
            '<a href="https://kie.ai/billing">KIE Billing</a> · '
            '<a href="https://kie.ai/api-key">KIE API Key</a> · '
            '<a href="https://www.photoroom.com/api">PhotoRoom API</a> · '
            '<a href="https://docs.photoroom.com/getting-started/pricing">PhotoRoom тарифы и кредиты</a>'
        )
        provider_help.setOpenExternalLinks(True)
        provider_help.setWordWrap(True)
        layout.addWidget(provider_help)
        form = QFormLayout()
        self.kie_edit = QLineEdit(values.get("kie_api_key", ""))
        self.openrouter_edit = QLineEdit(values.get("openrouter_api_key", ""))
        self.photo_edit = QLineEdit(values.get("photoroom_api_key", ""))
        self.fal_edit = QLineEdit(values.get("fal_api_key", ""))
        self.atlascloud_edit = QLineEdit(values.get("atlascloud_api_key", ""))
        self.piapi_edit = QLineEdit(values.get("piapi_api_key", ""))
        self.runpod_key_edit = QLineEdit(values.get("runpod_api_key", ""), self)
        self.runpod_endpoint_edit = QLineEdit(values.get("runpod_endpoint_id", ""), self)
        # Keep stored values when saving other keys; RunPod is not exposed yet.
        self.runpod_key_edit.hide()
        self.runpod_endpoint_edit.hide()
        for edit in (self.kie_edit, self.openrouter_edit, self.photo_edit, self.fal_edit, self.atlascloud_edit, self.piapi_edit, self.runpod_key_edit):
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        kie_row = QHBoxLayout()
        kie_row.addWidget(self.kie_edit)
        self.balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.balance_button.clicked.connect(self._check_balance)
        kie_row.addWidget(self.balance_button)
        form.addRow("KIE API Key", kie_row)
        openrouter_row = QHBoxLayout()
        openrouter_row.addWidget(self.openrouter_edit)
        self.openrouter_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.openrouter_balance_button.clicked.connect(self._check_openrouter_balance)
        openrouter_row.addWidget(self.openrouter_balance_button)
        form.addRow("OpenRouter API Key", openrouter_row)
        photo_row = QHBoxLayout()
        photo_row.addWidget(self.photo_edit)
        self.photo_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.photo_balance_button.clicked.connect(self._check_photoroom_balance)
        photo_row.addWidget(self.photo_balance_button)
        form.addRow("PhotoRoom API Key", photo_row)
        fal_row = QHBoxLayout()
        fal_row.addWidget(self.fal_edit)
        self.fal_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.fal_balance_button.clicked.connect(self._check_fal_balance)
        fal_row.addWidget(self.fal_balance_button)
        form.addRow("Fal.ai API Key", fal_row)
        atlas_row = QHBoxLayout()
        atlas_row.addWidget(self.atlascloud_edit)
        self.atlascloud_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.atlascloud_balance_button.clicked.connect(
            lambda: self._check_external_balance("atlascloud", self.atlascloud_edit.text())
        )
        atlas_row.addWidget(self.atlascloud_balance_button)
        form.addRow("AtlasCloud API Key", atlas_row)
        piapi_row = QHBoxLayout()
        piapi_row.addWidget(self.piapi_edit)
        self.piapi_balance_button = V3Button("Проверить баланс", ButtonVariant.SECONDARY)
        self.piapi_balance_button.clicked.connect(
            lambda: self._check_external_balance("piapi", self.piapi_edit.text())
        )
        piapi_row.addWidget(self.piapi_balance_button)
        form.addRow("PiAPI API Key", piapi_row)
        self.api_concurrency_combo = QComboBox()
        for concurrency in API_CONCURRENCY_CHOICES:
            self.api_concurrency_combo.addItem(str(concurrency), concurrency)
        selected = normalize_api_concurrency(
            values.get("api_concurrency"),
            legacy_value=values.get("kie_concurrency", values.get("generation_concurrency")),
        )
        self.api_concurrency_combo.setCurrentIndex(
            self.api_concurrency_combo.findData(selected)
        )
        self.api_concurrency_combo.setToolTip(
            "Один общий лимит одновременно выполняемых задач для всех API. "
            "Ограничения провайдеров продолжают действовать."
        )
        form.addRow("Одновременных задач (все API)", self.api_concurrency_combo)
        layout.addLayout(form)
        actions = QVBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        actions.addWidget(self.status)
        layout.addLayout(actions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.settings: dict[str, Any] = {}

    def _check_balance(self) -> None:
        try:
            self.status.setText(check_kie_balance(self.kie_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _check_openrouter_balance(self) -> None:
        try:
            self.status.setText(check_openrouter_balance(self.openrouter_edit.text()))
        except (ValueError, RuntimeError) as error:
            self.status.setText(str(error))

    def _check_photoroom_balance(self) -> None:
        try:
            self.status.setText(check_photoroom_balance(self.photo_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _check_fal_balance(self) -> None:
        try:
            self.status.setText(check_fal_balance(self.fal_edit.text()))
        except (RuntimeError, ValueError) as error:
            self.status.setText(str(error))

    def _check_external_balance(self, provider: str, key: str) -> None:
        # Read-only endpoint; never show raw HTTP errors containing credentials.
        button = (
            self.atlascloud_balance_button if provider == "atlascloud"
            else self.piapi_balance_button
        )
        button.setEnabled(False)
        self.status.setText("Проверяем баланс…")
        try:
            self.status.setText(check_provider_balance(provider, key))
        except (RuntimeError, ValueError):
            self.status.setText(
                f"{provider}: проверить баланс не удалось. "
                "Проверьте API-ключ и права доступа."
            )
        finally:
            button.setEnabled(True)

    def _save(self) -> None:
        self.settings = {
            "kie_api_key": self.kie_edit.text().strip(),
            "openrouter_api_key": self.openrouter_edit.text().strip(),
            "photoroom_api_key": self.photo_edit.text().strip(),
            "fal_api_key": self.fal_edit.text().strip(),
            "atlascloud_api_key": self.atlascloud_edit.text().strip(),
            "piapi_api_key": self.piapi_edit.text().strip(),
            "runpod_api_key": self.runpod_key_edit.text().strip(),
            "runpod_endpoint_id": self.runpod_endpoint_edit.text().strip(),
            "api_concurrency": normalize_api_concurrency(
                self.api_concurrency_combo.currentData()
            ),
        }
        try:
            save_credentials(
                {
                    key: value
                    for key, value in self.settings.items()
                    if key in ALL_PROVIDER_CREDENTIAL_KEYS
                }
            )
        except (OSError, RuntimeError, ValueError):
            self.status.setText('Не удалось сохранить ключи. Проверьте формат и доступ к хранилищу.')
            return
        self.accept()
