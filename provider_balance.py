"""Read-only provider balances, without Qt or billable requests."""

from __future__ import annotations

import urllib.error
import time
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from security_redaction import SECRET_KEY_PATTERN
from app_identity import APP_USER_AGENT
from network_security import NetworkSecurityError, secure_json_request


class ProviderBalanceError(RuntimeError):
    """A provider error message that is safe to show without its response body."""


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


_SCHEMA_FIELDS = frozenset({"data", "wallet", "balance", "available", "value", "currency", "equivalent_in_usd", "point_remain", "code", "status", "error", "message", "detail", "account", "accounts", "account_id", "account_name", "credits", "remaining", "success", "result", "output"})

def balance_response_schema(payload: Any) -> str:
    """Bounded field/type summary; never include scalar values or unknown field names."""
    entries = []
    def walk(value, path, depth):
        if len(entries) >= 32:
            return
        kind = ("object" if isinstance(value, Mapping) else "array" if isinstance(value, list)
                else "null" if value is None else "boolean" if isinstance(value, bool)
                else "number" if isinstance(value, (int, float, Decimal))
                else "string" if isinstance(value, str) else "other")
        entries.append(f"{path}:{kind}")
        if depth >= 4:
            return
        if isinstance(value, Mapping):
            unknown = 0
            for name, item in value.items():
                if len(entries) >= 32:
                    break
                if isinstance(name, str) and name in _SCHEMA_FIELDS and not SECRET_KEY_PATTERN.search(name):
                    walk(item, path + "." + name, depth + 1)
                else:
                    unknown += 1
            if unknown and len(entries) < 32:
                entries.append(f"{path}.<other-fields>:{unknown}")
        elif isinstance(value, list) and value:
            walk(value[0], path + "[]", depth + 1)
    walk(payload, "$", 0)
    return "; ".join(entries)[:480]

def _balance_parse_reason(provider, payload):
    if not isinstance(payload, Mapping):
        return "response_not_object", "ответ не является объектом JSON"
    if provider == "piapi":
        data = payload.get("data", payload)
        if isinstance(data, list):
            if len(data) != 1:
                return "ambiguous_account_records", "API вернул пустой список или несколько записей аккаунта"
            data = data[0]
        if not isinstance(data, Mapping):
            return "account_not_object", "запись аккаунта не является объектом JSON"
        if "equivalent_in_usd" not in data:
            return "usd_field_missing", "в поддерживаемой структуре нет поля equivalent_in_usd"
        return "usd_value_invalid", "поле equivalent_in_usd имеет недопустимое значение"
    return "usd_balance_invalid", "структура долларового баланса не соответствует ожидаемой"

def check_provider_balance(provider: str, api_key: str, timeout: float = 12.0, *, diagnostic=None) -> str:
    key = str(api_key or "").strip()
    if not key or "\r" in key or "\n" in key:
        raise ValueError("Введите корректный API Key")
    if provider == "piapi":
        url = "https://api.piapi.ai/account/info"
        headers = {"X-API-KEY": key, "Accept": "application/json", "User-Agent": APP_USER_AGENT}
    elif provider == "atlascloud":
        url = "https://api.atlascloud.ai/public/v1/balance"
        headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    else:
        raise ValueError("Неизвестный провайдер")
    started = time.monotonic()
    correlation = uuid.uuid4().hex
    metadata = {}
    def emit(event, *, stage, outcome, reason="", payload=None):
        if diagnostic is None:
            return
        details = {"provider": provider, "operation_type": "balance_check",
                   "stage": stage, "reason": reason, "correlation_id": correlation,
                   "elapsed_ms": round((time.monotonic() - started) * 1000),
                   "retry_risk": "no_generation_submitted",
                   "expected_field": "equivalent_in_usd" if provider == "piapi" else "available.value (USD)"}
        details.update(metadata)
        if stage == "parse_response":
            details["response_schema"] = balance_response_schema(payload)
        try:
            diagnostic({"event": event, "outcome": outcome, "details": details})
        except Exception:
            pass
    emit("provider_balance_started", stage="request", outcome="started")
    try:
        options = {}
        if diagnostic is not None:
            options["on_response"] = lambda status: metadata.update(http_status=status)
        payload = secure_json_request(url, headers=headers, timeout=timeout, max_bytes=65536, **options)
    except urllib.error.HTTPError as exc:
        metadata["http_status"] = exc.code
        emit("provider_balance_failed", stage="http_response", outcome="failed", reason="http_error")
        if exc.code in (401, 403):
            raise ProviderBalanceError(f"{provider}: ключ отклонён или нет прав на баланс") from None
        if exc.code == 429:
            raise ProviderBalanceError(f"{provider}: слишком частые запросы") from None
        raise ProviderBalanceError(f"{provider}: баланс сейчас недоступен (HTTP {exc.code})") from None
    except NetworkSecurityError as exc:
        known = {"API returned malformed JSON": ("invalid_json", "API вернул некорректный JSON"),
                 "API response exceeds size limit": ("response_too_large", "ответ API превышает разрешённый размер"),
                 "cross-host redirect blocked": ("redirect_blocked", "заблокировано перенаправление на другой сервер"),
                 "HTTPS-only redirect blocked": ("redirect_blocked", "заблокировано небезопасное перенаправление"),
                 "redirect credentials blocked": ("redirect_blocked", "заблокировано перенаправление с учётными данными")}
        reason, message = known.get(str(exc), ("transport_security_error", "запрос отклонён проверкой безопасности"))
        emit("provider_balance_failed", stage="transport", outcome="failed", reason=reason)
        raise ProviderBalanceError(f"{provider}: {message}") from None
    except (urllib.error.URLError, OSError, ValueError):
        emit("provider_balance_failed", stage="transport", outcome="failed", reason="network_or_request_error")
        raise ProviderBalanceError(f"{provider}: сеть или параметры запроса не позволили получить баланс") from None
    try:
        result = parse_balance(provider, payload)
    except ValueError:
        reason, message = _balance_parse_reason(provider, payload)
        emit("provider_balance_failed", stage="parse_response", outcome="failed", reason=reason, payload=payload)
        raise ProviderBalanceError(f"{provider}: баланс не прочитан: {message}") from None
    emit("provider_balance_succeeded", stage="parse_response", outcome="succeeded", payload=payload)
    return result
