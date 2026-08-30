"""Dependency-free Fal.ai queue adapter.

The adapter deliberately exposes lifecycle primitives rather than hiding a
paid request behind a blocking helper. Higher layers can add provider/model
selection, cost estimates and user confirmation later.
"""

from __future__ import annotations

import json
import base64
import mimetypes
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path

from network_security import HttpsOnlyRedirectHandler, NetworkSecurityError
from provider_contract import MAX_PROVIDER_PAYLOAD_BYTES, ProviderTaskRequest
from fal_model_catalog import fal_endpoint_profile


MAX_FAL_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TASK_JOURNAL_RECORDS = 1000
_JOURNAL_LOCKS_GUARD = threading.Lock()
_JOURNAL_LOCKS: dict[str, threading.RLock] = {}


def _journal_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve(strict=False)))
    with _JOURNAL_LOCKS_GUARD:
        return _JOURNAL_LOCKS.setdefault(key, threading.RLock())


class FalProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FalTaskRecord:
    """Secret-free metadata needed to resume polling after a restart."""

    request_id: str
    operation: str
    model_id: str
    status: str = "queued"
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not _REQUEST_RE.fullmatch(str(self.request_id or "")):
            raise FalProviderError("Некорректный Fal.ai request ID в журнале")
        if not _MODEL_RE.fullmatch(str(self.model_id or "")):
            raise FalProviderError("Некорректная модель Fal.ai в журнале")
        if not str(self.operation or "").strip():
            raise FalProviderError("Не указана операция Fal.ai в журнале")

    def to_dict(self) -> dict[str, str]:
        return {
            "request_id": self.request_id,
            "operation": self.operation,
            "model_id": self.model_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class FalTaskJournal:
    """Small atomic JSON journal for resumable, non-secret Fal task metadata."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = _journal_lock(self.path)

    @staticmethod
    def _bounded_records(
        records: Mapping[str, FalTaskRecord],
    ) -> dict[str, FalTaskRecord]:
        values = list(records.values())
        pending = [
            record
            for record in values
            if record.status not in _TERMINAL_TASK_STATUSES
        ]
        terminal = [
            record
            for record in values
            if record.status in _TERMINAL_TASK_STATUSES
        ]
        terminal_budget = max(0, MAX_TASK_JOURNAL_RECORDS - len(pending))
        retained = terminal[-terminal_budget:] if terminal_budget else []
        retained.extend(pending)
        return {record.request_id: record for record in retained}

    def _read(self) -> dict[str, FalTaskRecord]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError):
            return {}
        entries = raw.get("tasks", []) if isinstance(raw, Mapping) else []
        result: dict[str, FalTaskRecord] = {}
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, Mapping):
                    continue
                try:
                    record = FalTaskRecord(
                        request_id=str(entry.get("request_id") or ""),
                        operation=str(entry.get("operation") or ""),
                        model_id=str(entry.get("model_id") or ""),
                        status=str(entry.get("status") or "unknown"),
                        created_at=str(entry.get("created_at") or ""),
                        updated_at=str(entry.get("updated_at") or ""),
                    )
                except FalProviderError:
                    continue
                result[record.request_id] = record
        return self._bounded_records(result)

    def _write(self, records: Mapping[str, FalTaskRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        records = self._bounded_records(records)
        payload = json.dumps(
            {"tasks": [record.to_dict() for record in records.values()]},
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        fd, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=str(self.path.parent)
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def upsert(self, request_id: str, operation: str, model_id: str, status: str) -> FalTaskRecord:
        with self._lock:
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            records = self._read()
            previous = records.get(str(request_id))
            record = FalTaskRecord(
                request_id=str(request_id),
                operation=str(operation),
                model_id=str(model_id),
                status=str(status),
                created_at=previous.created_at if previous else now,
                updated_at=now,
            )
            records[record.request_id] = record
            self._write(records)
            return record

    def update_status(self, request_id: str, status: str) -> FalTaskRecord | None:
        with self._lock:
            records = self._read()
            previous = records.get(str(request_id))
            if previous is None:
                return None
            record = FalTaskRecord(
                request_id=previous.request_id,
                operation=previous.operation,
                model_id=previous.model_id,
                status=str(status),
                created_at=previous.created_at,
                updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            records[record.request_id] = record
            self._write(records)
            return record

    def pending(self) -> tuple[FalTaskRecord, ...]:
        with self._lock:
            return tuple(
                record
                for record in self._read().values()
                if record.status not in _TERMINAL_TASK_STATUSES
            )


_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")
_REQUEST_RE = re.compile(r"^[A-Za-z0-9_-]{1,256}$")
_TERMINAL_TASK_STATUSES = frozenset(
    {"completed", "completed_after_cancel", "cancelled", "failed"}
)


@dataclass(frozen=True, slots=True)
class FalConfig:
    api_key: str = field(repr=False)
    model_id: str
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    before_paid_submit: Callable[[], None] | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def validate(self) -> None:
        if not str(self.api_key or "").strip():
            raise FalProviderError("Не указан Fal.ai API key")
        model = str(self.model_id or "").strip()
        if not _MODEL_RE.fullmatch(model) or ".." in model:
            raise FalProviderError("Не указан корректный Fal.ai model ID")
        if not 1 <= float(self.timeout_seconds) <= 120:
            raise FalProviderError("Недопустимый timeout Fal.ai")
        if not 0 <= int(self.max_retries) <= 3:
            raise FalProviderError("Недопустимое число повторов Fal.ai")
        if not 0 <= float(self.retry_backoff_seconds) <= 10:
            raise FalProviderError("Недопустимая задержка повторов Fal.ai")


def fal_status_kind(payload: Mapping[str, Any] | None) -> str:
    status = str((payload or {}).get("status") or "").strip().upper()
    return {
        "IN_QUEUE": "queued",
        "IN_PROGRESS": "running",
        "COMPLETED": "completed",
        "CANCELLATION_REQUESTED": "cancel_requested",
        "ALREADY_COMPLETED": "already_completed",
        "CANCELLED": "cancelled",
        "CANCELED": "cancelled",
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


def validate_fal_image_result(
    payload: Mapping[str, Any] | None,
    *,
    operation: str,
    model_id: str,
) -> str:
    """Validate a provider image result before passing its URL downstream."""
    try:
        profile = fal_endpoint_profile(model_id, operation)
    except KeyError as error:
        raise FalProviderError("Неизвестный Fal.ai профиль результата") from error
    source = payload if isinstance(payload, Mapping) else {}
    image_records: list[Mapping[str, Any]] = []
    image = source.get("image")
    if isinstance(image, Mapping):
        image_records.append(image)
    images = source.get("images")
    if isinstance(images, list):
        image_records.extend(item for item in images[:16] if isinstance(item, Mapping))
    if not image_records:
        raise FalProviderError("Fal.ai не вернул файл изображения")
    for record in image_records:
        content_type = str(record.get("content_type") or "").strip().lower()
        if content_type and not content_type.startswith("image/"):
            raise FalProviderError("Fal.ai вернул результат не в формате изображения")
        if operation == "remove_background" and content_type:
            allowed = {f"image/{fmt}" for fmt in profile.output_formats}
            if content_type not in allowed:
                raise FalProviderError(
                    "Fal.ai вернул неподдерживаемый формат результата удаления фона"
                )
    return fal_image_url(source)


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
        transient_http = {408, 409, 425, 429, 500, 502, 503, 504}
        for attempt in range(int(self.config.max_retries) + 1):
            if (
                request.method.upper() == "POST"
                and self.config.before_paid_submit is not None
            ):
                self.config.before_paid_submit()
            try:
                opener = urllib.request.build_opener(HttpsOnlyRedirectHandler())
                with opener.open(request, timeout=self.config.timeout_seconds) as response:
                    raw = response.read(MAX_FAL_RESPONSE_BYTES + 1)
                if len(raw) > MAX_FAL_RESPONSE_BYTES:
                    raise FalProviderError("Fal.ai response слишком большой")
                break
            except urllib.error.HTTPError as error:
                detail = ""
                try:
                    error_body = error.read(16 * 1024).decode("utf-8", "replace")
                    parsed_body = json.loads(error_body)
                    if isinstance(parsed_body, dict):
                        detail = str(
                            parsed_body.get("message")
                            or parsed_body.get("detail")
                            or parsed_body.get("error")
                            or ""
                        )[:300]
                except (OSError, UnicodeError, ValueError):
                    detail = ""
                if error.code in accepted_http_errors:
                    try:
                        result = json.loads(error.read(256 * 1024).decode("utf-8", "replace"))
                    except (OSError, UnicodeError, ValueError) as parse_error:
                        raise FalProviderError("Fal.ai вернул некорректный ответ отмены") from parse_error
                    if isinstance(result, dict):
                        return result
                retryable_request = request.method.upper() in {"GET", "HEAD"} or (
                    request.method.upper() == "POST" and error.code == 429
                )
                if (
                    not retryable_request
                    or error.code not in transient_http
                    or attempt >= int(self.config.max_retries)
                ):
                    suffix = f": {detail}" if detail else ""
                    raise FalProviderError(f"Fal.ai HTTP {error.code}{suffix}") from error
                time.sleep(float(self.config.retry_backoff_seconds) * (2**attempt))
            except (urllib.error.URLError, OSError, NetworkSecurityError) as error:
                if (
                    request.method.upper() not in {"GET", "HEAD"}
                    or attempt >= int(self.config.max_retries)
                ):
                    raise FalProviderError("Не удалось обратиться к Fal.ai") from error
                time.sleep(float(self.config.retry_backoff_seconds) * (2**attempt))
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
        model_id: str | None = None,
        parameters: dict[str, Any] | None = None,
        is_cancelled: Callable[[], bool] | None = None,
        on_submitted: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        model_by_operation = {
            "remove_background": "fal-ai/bria/background/remove",
            "upscale": "fal-ai/esrgan",
        }
        try:
            selected_model_id = model_id or model_by_operation[operation]
        except KeyError as error:
            raise FalProviderError(f"Fal.ai operation не поддерживается: {operation}") from error
        if self.model_id != selected_model_id:
            raise FalProviderError("Fal.ai client model не соответствует операции")
        try:
            profile = fal_endpoint_profile(selected_model_id, operation)
        except KeyError as error:
            raise FalProviderError(
                f"Неизвестный Fal.ai endpoint profile: {selected_model_id}/{operation}"
            ) from error
        arguments = fal_image_input(image_url)
        if parameters:
            unknown_parameters = set(parameters) - set(profile.parameter_names)
            if unknown_parameters:
                raise FalProviderError(
                    "Параметры не разрешены для выбранного Fal.ai профиля: "
                    + ", ".join(sorted(unknown_parameters))
                )
            arguments.update(parameters)
        if operation == "upscale":
            arguments["scale"] = str(max(2, min(int(scale), 4)))
            arguments["output_format"] = "png"
        request = ProviderTaskRequest(
            provider_id="fal",
            operation=operation,
            model_id=selected_model_id,
            input_payload=arguments,
        )
        submitted = self.submit_task(request)
        request_id = str(submitted["request_id"])
        if on_submitted is not None:
            on_submitted(request_id)
        completed = self.wait_for_result(
            request_id,
            timeout_seconds=300.0,
            poll_interval_seconds=2.0,
            is_cancelled=is_cancelled,
            on_status=on_status,
        )
        validate_fal_image_result(
            completed.get("result"),
            operation=operation,
            model_id=selected_model_id,
        )
        return completed

    def status(self, request_id: str) -> dict[str, Any]:
        request_id = str(request_id or "").strip()
        if not _REQUEST_RE.fullmatch(request_id):
            raise FalProviderError("Некорректный Fal.ai request ID")
        return self._request(self._request_url(f"/requests/{request_id}/status"))

    def result(self, request_id: str) -> dict[str, Any]:
        request_id = str(request_id or "").strip()
        if not _REQUEST_RE.fullmatch(request_id):
            raise FalProviderError("Некорректный Fal.ai request ID")
        return self._request(self._request_url(f"/requests/{request_id}/response"))

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
        is_cancelled: Callable[[], bool] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Poll one already-submitted request and fetch its final result.

        The caller owns the worker thread and cancellation policy. No retry or
        new submit is performed here, so a timeout can safely be resumed by
        request ID later.
        """

        if timeout_seconds <= 0 or poll_interval_seconds < 0:
            raise ValueError("timeout and poll interval must be non-negative")
        started = time.monotonic()
        cancellation_requested = False
        while True:
            if (
                is_cancelled is not None
                and is_cancelled()
                and not cancellation_requested
            ):
                try:
                    cancel_response = self.cancel(request_id)
                except FalProviderError as error:
                    if on_status is not None:
                        on_status("cancel_failed")
                    raise FalProviderError(
                        "Fal.ai cancel_failed; request ID сохранён для проверки статуса"
                    ) from error
                cancel_kind = fal_status_kind(cancel_response)
                if cancel_kind == "already_completed":
                    result = self.result(request_id)
                    if on_status is not None:
                        on_status("completed_after_cancel")
                    return {
                        "request_id": str(request_id),
                        "status": "completed_after_cancel",
                        "result": result,
                    }
                if on_status is not None:
                    on_status(cancel_kind or "cancel_requested")
                cancellation_requested = True
            status = self.status(request_id)
            kind = fal_status_kind(status)
            if kind == "completed":
                result = self.result(request_id)
                if on_status is not None:
                    on_status(
                        "completed_after_cancel"
                        if cancellation_requested
                        else kind
                    )
                return {
                    "request_id": str(request_id),
                    "status": "completed_after_cancel" if cancellation_requested else kind,
                    "result": result,
                }
            if on_status is not None:
                on_status(kind)
            if kind in {
                "cancel_requested",
                "cancelled",
                "already_completed",
                "unknown",
                "not_found",
            }:
                raise FalProviderError(f"Fal.ai request завершён с состоянием {kind}")
            if time.monotonic() - started >= timeout_seconds:
                raise TimeoutError("Превышено время ожидания результата Fal.ai")
            sleep(min(poll_interval_seconds, max(0.0, timeout_seconds)))


__all__ = [
    "MAX_FAL_RESPONSE_BYTES",
    "FalClient",
    "FalConfig",
    "FalProviderError",
    "FalTaskJournal",
    "FalTaskRecord",
    "fal_image_input",
    "fal_image_data_uri",
    "fal_image_url",
    "validate_fal_image_result",
    "fal_status_kind",
]
