"""Dependency-free Fal.ai queue adapter.

The adapter deliberately exposes lifecycle primitives rather than hiding a
paid request behind a blocking helper. Higher layers can add provider/model
selection, cost estimates and user confirmation later.
"""

from __future__ import annotations

import json
import base64
import mimetypes
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote

from network_security import HttpsOnlyRedirectHandler, NetworkSecurityError
from provider_contract import MAX_PROVIDER_PAYLOAD_BYTES, ProviderTaskRequest


MAX_FAL_RESPONSE_BYTES = 2 * 1024 * 1024


class FalProviderError(RuntimeError):
    pass


_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")


@dataclass(frozen=True, slots=True)
class FalConfig:
    api_key: str = field(repr=False)
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
    allowed_data_uri = value.startswith(
        ("data:image/png;base64,", "data:image/jpeg;base64,", "data:image/webp;base64,")
    )
    if (not value.startswith("https://") and not allowed_data_uri) or "\n" in value or "\r" in value:
        raise FalProviderError("Fal.ai принимает изображение только по HTTPS URL")
    return {"image_url": value}


def fal_image_data_uri(path: str, *, max_bytes: int = 8 * 1024 * 1024) -> str:
    """Encode a bounded local image for Fal file inputs without uploading silently."""

    source = str(path or "").strip()
    if not source:
        raise FalProviderError("Не указан локальный файл для Fal.ai")
    try:
        size = __import__("os").path.getsize(source)
        if size > max_bytes:
            raise FalProviderError("Локальное изображение слишком велико для Fal.ai")
        with open(source, "rb") as handle:
            data = handle.read(max_bytes + 1)
    except OSError as error:
        raise FalProviderError("Не удалось прочитать локальное изображение для Fal.ai") from error
    if len(data) > max_bytes:
        raise FalProviderError("Локальное изображение слишком велико для Fal.ai")
    content_type = mimetypes.guess_type(source)[0] or "image/png"
    if content_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise FalProviderError("Fal.ai поддерживает для этой операции PNG, JPEG или WebP")
    return f"data:{content_type};base64,{base64.b64encode(data).decode('ascii')}"


def fal_image_url(payload: Mapping[str, Any] | None) -> str:
    """Extract one HTTPS image result without accepting arbitrary payload URLs."""

    source = payload if isinstance(payload, Mapping) else {}
    candidates: list[Any] = []
    image = source.get("image")
    if isinstance(image, Mapping):
        candidates.append(image.get("url"))
    images = source.get("images")
    if isinstance(images, list):
        candidates.extend(
            item.get("url") for item in images[:16] if isinstance(item, Mapping)
        )
    candidates.append(source.get("image_url"))
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value.startswith("https://") and "\n" not in value and "\r" not in value:
            return value
    raise FalProviderError("Fal.ai не вернул HTTPS URL изображения")


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
        accepted_http_errors: tuple[int, ...] = (),
    ) -> dict[str, Any]:
        body = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
        if body is not None and len(body) > MAX_PROVIDER_PAYLOAD_BYTES:
            raise FalProviderError("Fal.ai payload слишком большой")
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
                raw = response.read(MAX_FAL_RESPONSE_BYTES + 1)
            if len(raw) > MAX_FAL_RESPONSE_BYTES:
                raise FalProviderError("Fal.ai response слишком большой")
        except urllib.error.HTTPError as error:
            if error.code in accepted_http_errors:
                try:
                    result = json.loads(error.read(256 * 1024).decode("utf-8", "replace"))
                except (OSError, UnicodeError, ValueError) as parse_error:
                    raise FalProviderError("Fal.ai вернул некорректный ответ отмены") from parse_error
                if isinstance(result, dict):
                    return result
            raise FalProviderError("Fal.ai HTTP request failed") from error
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
        result = self._request(self._request_url(), method="POST", payload=arguments)
        if not str(result.get("request_id") or "").strip():
            raise FalProviderError("Fal.ai не вернул request_id")
        return result

    def submit_task(self, request: ProviderTaskRequest) -> dict[str, Any]:
        """Submit through the shared contract, without creating a new fallback."""

        if not isinstance(request, ProviderTaskRequest):
            raise TypeError("request должен быть ProviderTaskRequest")
        request.validate()
        if request.provider_id != "fal" or request.model_id != self.model_id:
            raise FalProviderError("Provider task не соответствует Fal.ai client")
        return self.submit(request.input_payload)

    def run_image_operation(
        self,
        operation: str,
        image_url: str,
        *,
        scale: int = 2,
    ) -> dict[str, Any]:
        model_by_operation = {
            "remove_background": "fal-ai/bria/background/remove",
            "upscale": "fal-ai/esrgan",
        }
        try:
            model_id = model_by_operation[operation]
        except KeyError as error:
            raise FalProviderError(f"Fal.ai operation не поддерживается: {operation}") from error
        if self.model_id != model_id:
            raise FalProviderError("Fal.ai client model не соответствует операции")
        arguments = fal_image_input(image_url)
        if operation == "upscale":
            arguments["scale"] = str(max(2, min(int(scale), 4)))
            arguments["output_format"] = "png"
        request = ProviderTaskRequest(
            provider_id="fal",
            operation=operation,
            model_id=model_id,
            input_payload=arguments,
        )
        submitted = self.submit_task(request)
        request_id = str(submitted["request_id"])
        return self.wait_for_result(
            request_id,
            timeout_seconds=300.0,
            poll_interval_seconds=2.0,
        )

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
            accepted_http_errors=(400, 404),
        )

    def wait_for_result(
        self,
        request_id: str,
        *,
        timeout_seconds: float = 300.0,
        poll_interval_seconds: float = 2.0,
        sleep=time.sleep,
    ) -> dict[str, Any]:
        """Poll one already-submitted request and fetch its final result.

        The caller owns the worker thread and cancellation policy. No retry or
        new submit is performed here, so a timeout can safely be resumed by
        request ID later.
        """

        if timeout_seconds <= 0 or poll_interval_seconds < 0:
            raise ValueError("timeout and poll interval must be non-negative")
        started = time.monotonic()
        while True:
            status = self.status(request_id)
            kind = fal_status_kind(status)
            if kind == "completed":
                result = self.result(request_id)
                return {
                    "request_id": str(request_id),
                    "status": kind,
                    "result": result,
                }
            if kind in {"unknown", "not_found"}:
                raise FalProviderError(f"Fal.ai request завершён с состоянием {kind}")
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError("Превышено время ожидания результата Fal.ai")
            sleep(min(poll_interval_seconds, max(0.0, timeout_seconds)))


__all__ = [
    "MAX_FAL_RESPONSE_BYTES",
    "FalClient",
    "FalConfig",
    "FalProviderError",
    "fal_image_input",
    "fal_image_data_uri",
    "fal_image_url",
    "fal_status_kind",
]
