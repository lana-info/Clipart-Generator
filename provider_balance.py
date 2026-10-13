"""Read-only provider balances, without Qt or billable requests."""

from __future__ import annotations

import urllib.error
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from network_security import NetworkSecurityError, secure_json_request


def _usd(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("Неизвестный формат баланса")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Неизвестный формат баланса") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("Неизвестный формат баланса")
    return f"{result:.2f}"


def parse_balance(provider: str, payload: Any) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("Неизвестный формат баланса")
    if provider == "atlascloud":
        balance = payload.get("available")
        if not isinstance(balance, Mapping) or str(balance.get("currency", "")).casefold() != "usd":
            raise ValueError("Неизвестный формат баланса AtlasCloud")
        return f"Баланс AtlasCloud: {_usd(balance.get('value'))} USD"
    if provider == "piapi":
        data = payload.get("data", payload)
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, Mapping) or "equivalent_in_usd" not in data:
            raise ValueError("Неизвестный формат баланса PiAPI")
        return f"Баланс PiAPI: {_usd(data['equivalent_in_usd'])} USD"
    raise ValueError("Неизвестный провайдер")


def check_provider_balance(provider: str, api_key: str, timeout: float = 12.0) -> str:
    key = str(api_key or "").strip()
    if not key or "\r" in key or "\n" in key:
        raise ValueError("Введите корректный API Key")
    if provider == "piapi":
        url = "https://api.piapi.ai/account/info"
        headers = {"X-API-KEY": key, "Accept": "application/json"}
    elif provider == "atlascloud":
        url = "https://api.atlascloud.ai/public/v1/balance"
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    else:
        raise ValueError("Неизвестный провайдер")
    try:
        payload = secure_json_request(url, headers=headers, timeout=timeout, max_bytes=65536)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise RuntimeError(f"{provider}: ключ отклонён или нет прав на баланс") from None
        if exc.code == 429:
            raise RuntimeError(f"{provider}: слишком частые запросы") from None
        raise RuntimeError(f"{provider}: баланс сейчас недоступен") from None
    except (NetworkSecurityError, urllib.error.URLError, OSError, ValueError):
        raise RuntimeError(f"{provider}: не удалось безопасно получить баланс") from None
    try:
        return parse_balance(provider, payload)
    except ValueError:
        raise RuntimeError(f"{provider}: формат ответа не распознан; проверьте баланс в кабинете") from None
