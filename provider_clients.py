"""Provider API clients kept independent from Qt UI code."""

from __future__ import annotations

import urllib.error
from dataclasses import dataclass
from typing import Any

from network_security import NetworkSecurityError, secure_json_request


@dataclass(frozen=True)
class KieBalance:
    value: str
    currency: str = ""

    @property
    def label(self) -> str:
        suffix = f" {self.currency}" if self.currency else ""
        return f"Баланс KIE: {self.value}{suffix}"


def parse_kie_balance_response(payload: Any) -> KieBalance:
    data = payload.get("data", payload) if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("KIE вернул неизвестный формат баланса")
    for name in ("credit", "credits", "balance", "amount", "available"):
        if name not in data:
            continue
        raw = data[name]
        if isinstance(raw, (int, float)) and not isinstance(raw, bool):
            value = str(raw)
        elif isinstance(raw, str) and raw.strip():
            value = raw.strip()
        else:
            continue
        currency = str(data.get("currency", data.get("unit", "")) or "").strip()
        return KieBalance(value=value, currency=currency)
    raise ValueError("KIE вернул неизвестный формат баланса")


def check_photoroom_balance(api_key: str, timeout: float = 15.0) -> str:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Введите PhotoRoom API Key")
    try:
        payload = secure_json_request("https://image-api.photoroom.com/v2/account", headers={"x-api-key": key, "Accept": "application/json"}, timeout=timeout)
    except (NetworkSecurityError, urllib.error.URLError, OSError) as error:
        raise RuntimeError("Не удалось проверить баланс PhotoRoom") from error
    images = payload.get("images", {}) if isinstance(payload, dict) else {}
    if isinstance(images, dict) and "available" in images:
        return f"Баланс PhotoRoom: {images['available']} из {images.get('subscription', '?')} изображений"
    return "Баланс PhotoRoom получен, формат ответа требует уточнения."


def check_kie_balance(api_key: str, timeout: float = 15.0) -> str:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("Введите KIE API Key")
    try:
        payload: Any = secure_json_request("https://api.kie.ai/api/v1/chat/credit", headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}, timeout=timeout)
    except (NetworkSecurityError, urllib.error.URLError, OSError) as error:
        raise RuntimeError("Не удалось проверить баланс KIE") from error
    try:
        return parse_kie_balance_response(payload).label
    except ValueError as error:
        raise RuntimeError(str(error)) from error


__all__ = ["KieBalance", "check_kie_balance", "check_photoroom_balance", "parse_kie_balance_response"]
