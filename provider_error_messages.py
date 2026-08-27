from __future__ import annotations

import re
from typing import Any


_CODE_402 = re.compile(r"(?:errorCode|error_code|code)\s*[=:]\s*402\b", re.I)
_CODE_401 = re.compile(r"(?:errorCode|error_code|code)\s*[=:]\s*401\b", re.I)
_CODE_413 = re.compile(r"(?:errorCode|error_code|code)\s*[=:]\s*413\b", re.I)
_CODE_429 = re.compile(r"(?:errorCode|error_code|code)\s*[=:]\s*429\b", re.I)


def friendly_provider_error(message: Any) -> tuple[str, str] | None:
    """Return a stable Russian category/message for known provider failures."""
    text = str(message or "").strip()
    lowered = text.casefold()
    is_fal = "fal.ai" in lowered or "fal ai" in lowered

    if is_fal and any(marker in lowered for marker in (
        "402", "insufficient credit", "insufficient balance",
        "not enough credit", "credit balance is insufficient",
    )):
        return (
            "insufficient_credits",
            "Недостаточно средств на балансе Fal.ai. Пополните баланс и повторите запуск.",
        )

    if is_fal and any(marker in lowered for marker in (
        "401", "unauthorized", "invalid api key", "invalid key",
    )):
        return (
            "authentication",
            "Fal.ai отклонил API-ключ. Проверьте ключ и его область доступа в настройках API.",
        )

    if is_fal and any(marker in lowered for marker in (
        "403", "forbidden", "insufficient permission", "scope",
    )):
        return (
            "authorization",
            "У ключа Fal.ai недостаточно прав для этой операции. Проверьте область доступа ключа.",
        )

    if is_fal and any(marker in lowered for marker in (
        "429", "rate limit", "too many requests",
    )):
        return (
            "rate_limit",
            "Fal.ai временно ограничил частоту запросов. Подождите и повторите запуск.",
        )

    if is_fal and any(marker in lowered for marker in (
        "400", "bad request", "invalid input", "validation",
    )):
        return (
            "invalid_request",
            "Fal.ai не принял параметры изображения или выбранной модели. Проверьте файл и настройки операции.",
        )

    if is_fal and any(marker in lowered for marker in (
        "500", "502", "503", "504", "service unavailable", "server error",
    )):
        return (
            "provider_unavailable",
            "Fal.ai временно недоступен. Попробуйте повторить позже.",
        )

    if _CODE_402.search(text) or any(
        marker in lowered
        for marker in (
            "insufficient credit",
            "insufficient balance",
            "not enough credit",
            "credit balance is insufficient",
        )
    ):
        return (
            "insufficient_credits",
            "Недостаточно средств на балансе KIE. Пополните баланс KIE и повторите запуск.",
        )

    reference_marker = any(
        marker in lowered
        for marker in ("reference", "референс", "input image", "image input")
    )
    size_marker = _CODE_413.search(text) or any(
        marker in lowered
        for marker in (
            "exceeds 10mb",
            "exceeds 10 mb",
            "too large",
            "size limit",
            "payload too large",
        )
    )
    if reference_marker and size_marker:
        return (
            "reference_too_large",
            "Референс превышает допустимый размер 10 МБ. Уменьшите файл и повторите запуск.",
        )

    if _CODE_401.search(text) or any(
        marker in lowered
        for marker in ("unauthorized", "access permissions", "invalid api key")
    ):
        return (
            "authentication",
            "KIE отклонил API-ключ. Проверьте ключ в настройках API.",
        )

    if (
        _CODE_429.search(text)
        or "rate limit" in lowered
        or "too many requests" in lowered
    ):
        return (
            "rate_limit",
            "KIE временно ограничил частоту запросов. Подождите и повторите запуск.",
        )

    if "timeout" in lowered or "timed out" in lowered or "превышено время" in lowered:
        return (
            "timeout",
            "KIE не ответил вовремя. Проверьте соединение и повторите запуск.",
        )

    return None


__all__ = ["friendly_provider_error"]
