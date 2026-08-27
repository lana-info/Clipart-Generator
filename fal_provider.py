"""Dependency-free Fal.ai queue adapter.

The adapter deliberately exposes lifecycle primitives rather than hiding a
paid request behind a blocking helper. Higher layers can add provider/model
selection, cost estimates and user confirmation later.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote

from network_security import HttpsOnlyRedirectHandler, NetworkSecurityError


class FalProviderError(RuntimeError):
    pass


_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


@dataclass(frozen=True, slots=True)
class FalConfig:
    api_key: str
    model_id: str
    timeout_seconds: float = 30.0

    def validate(self) -> None:
        if not str(self.api_key or "").strip():
            raise FalProviderError("Не указан Fal.ai API key")
        model = str(self.model_id or "").strip()
        if not _MODEL_RE.fullmatch(model) or ".." in model:
            raise FalProviderError("Не указан корректный Fal.ai model ID")
        if not 1 <= float(self.timeout_seconds) <= 120:
            raise FalProviderError("Недопустимый timeout Fal.ai")


def fal_status_kind(payload: Mapping[str, Any] | None) -> str:
    status = str((payload or {}).get("status") or "").strip().upper()
    return {
        "IN_QUEUE": "queued",
        "IN_PROGRESS": "running",
        "COMPLETED": "completed",
        "CANCELLATION_REQUESTED": "cancel_requested",
        "ALREADY_COMPLETED": "already_completed",
        "NOT_FOUND": "not_found",
    }.get(status, "unknown")


def fal_image_input(image_url: str) -> dict[str, str]:
    value = str(image_url or "").strip()
    if not value.startswith("https://") or "\n" in value or "\r" in value:
        raise FalProviderError("Fal.ai принимает изображение только по HTTPS URL")
    return {"image_url": value}


class FalClient:
    def __init__(self, config: FalConfig) -> None:
        config.validate()
        self.config = config

    @property
    def model_id(self) -> str:
        return self.config.model_id.strip()

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Key {self.config.api_key.strip()}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method=method,
        )
        try:
            opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
            with opener.open(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(2 * 1024 * 1024)
        except (urllib.error.URLError, OSError, NetworkSecurityError) as error:
            raise FalProviderError("Не удалось обратиться к Fal.ai") from error
        try:
            result = json.loads(raw.decode("utf-8", "replace"))
        except (UnicodeError, ValueError) as error:
            raise FalProviderError("Fal.ai вернул некорректный JSON") from error
        if not isinstance(result, dict):
            raise FalProviderError("Fal.ai вернул неожиданный формат ответа")
        return result

    def _request_url(self, suffix: str = "") -> str:
        return f"https://queue.fal.run/{quote(self.model_id, safe='/.-_')}{suffix}"

    def submit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(arguments, Mapping):
            raise TypeError("arguments должен быть объектом")
        return self._request(self._request_url(), method="POST", payload=arguments)

    def status(self, request_id: str) -> dict[str, Any]:
        request_id = str(request_id or "").strip()
        if not _REQUEST_RE.fullmatch(request_id):
            raise FalProviderError("Некорректный Fal.ai request ID")
        return self._request(self._request_url(f"/requests/{request_id}/status"))

    def result(self, request_id: str) -> dict[str, Any]:
        request_id = str(request_id or "").strip()
        if not _REQUEST_RE.fullmatch(request_id):
            raise FalProviderError("Некорректный Fal.ai request ID")
        return self._request(self._request_url(f"/requests/{request_id}"))

    def cancel(self, request_id: str) -> dict[str, Any]:
        request_id = str(request_id or "").strip()
        if not _REQUEST_RE.fullmatch(request_id):
            raise FalProviderError("Некорректный Fal.ai request ID")
        return self._request(
            self._request_url(f"/requests/{request_id}/cancel"),
            method="PUT",
        )


__all__ = [
    "FalClient",
    "FalConfig",
    "FalProviderError",
    "fal_image_input",
    "fal_status_kind",
]
