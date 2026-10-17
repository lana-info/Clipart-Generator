"""Opt-in RunPod Serverless client for the experimental GPU cleanup backend."""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from provider_diagnostics import build_provider_event, count_provider_results


class CloudGpuError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunPodConfig:
    api_key: str
    endpoint_id: str
    timeout_seconds: float = 30.0

    def validate(self) -> None:
        if not self.api_key.strip():
            raise CloudGpuError("Не указан RunPod API key")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", self.endpoint_id.strip()):
            raise CloudGpuError("Не указан корректный RunPod endpoint ID")
        if not 1 <= self.timeout_seconds <= 120:
            raise CloudGpuError("Недопустимый timeout RunPod")


class RunPodClient:
    def __init__(
        self,
        config: RunPodConfig,
        diagnostic_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        config.validate()
        self.config = config
        self.base_url = f"https://api.runpod.ai/v2/{config.endpoint_id.strip()}"
        self._diagnostic_callback = diagnostic_callback
        self._last_http_status: int | None = None

    def _emit(self, event: str, **values: object) -> None:
        if self._diagnostic_callback is None:
            return
        try:
            self._diagnostic_callback(
                build_provider_event(event, provider="runpod", **values)
            )
        except Exception:
            return

    def _request(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        started = time.monotonic()
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            headers={
                "Authorization": self.config.api_key.strip() if self.config.api_key.strip().lower().startswith("bearer ") else "Bearer " + self.config.api_key.strip(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                self._last_http_status = int(getattr(response, "status", None) or 200)
                raw = response.read(2 * 1024 * 1024)
        except urllib.error.HTTPError as error:
            self._last_http_status = int(error.code)
            self._emit(
                "provider_task_failed",
                http_status=error.code,
                error_code=f"http_{error.code}",
                error_message="RunPod HTTP request failed",
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise CloudGpuError("Не удалось обратиться к RunPod") from error
        except (urllib.error.URLError, OSError) as error:
            self._emit(
                "provider_task_failed",
                error_code="network_error",
                error_message="RunPod network request failed",
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise CloudGpuError("Не удалось обратиться к RunPod") from error
        try:
            result = json.loads(raw.decode("utf-8", "replace"))
        except (UnicodeDecodeError, ValueError) as error:
            self._emit(
                "provider_task_failed",
                http_status=self._last_http_status,
                error_code="invalid_json",
                error_message="RunPod returned invalid JSON",
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise CloudGpuError("RunPod вернул некорректный ответ") from error
        if not isinstance(result, dict):
            self._emit(
                "provider_task_failed",
                http_status=self._last_http_status,
                error_code="invalid_response",
                error_message="RunPod returned unexpected response shape",
                elapsed_ms=round((time.monotonic() - started) * 1000),
            )
            raise CloudGpuError("RunPod вернул неожиданный формат ответа")
        return result

    def submit(self, worker_input: Mapping[str, Any], *, allow_upload: bool = True) -> dict[str, Any]:
        """Submit after the user explicitly starts cloud processing.

        ``allow_upload`` remains accepted for backwards compatibility; the
        UI no longer shows a redundant second consent control.
        """
        if not isinstance(worker_input, Mapping):
            raise TypeError("worker_input должен быть объектом")
        started = time.monotonic()
        result = self._request("run", {"input": dict(worker_input)})
        task_id = str(result.get("id") or "")
        self._emit(
            "provider_task_submitted",
            task=task_id,
            provider_state=str(result.get("status") or "submitted"),
            http_status=self._last_http_status,
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        return result

    def status(self, job_id: str) -> dict[str, Any]:
        if not job_id or len(job_id) > 256:
            raise CloudGpuError("Некорректный RunPod job ID")
        started = time.monotonic()
        result = self._request(f"status/{job_id}")
        self._emit(
            "provider_task_polled",
            task=job_id,
            provider_state=str(result.get("status") or "unknown"),
            http_status=self._last_http_status,
            result_count=count_provider_results(result.get("output")),
            elapsed_ms=round((time.monotonic() - started) * 1000),
        )
        return result
