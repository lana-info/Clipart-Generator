"""Opt-in RunPod Serverless client for the experimental GPU cleanup backend."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


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
    def __init__(self, config: RunPodConfig) -> None:
        config.validate()
        self.config = config
        self.base_url = f"https://api.runpod.ai/v2/{config.endpoint_id.strip()}"

    def _request(self, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            headers={
                "Authorization": self.config.api_key.strip(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST" if body is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                raw = response.read(2 * 1024 * 1024)
        except (urllib.error.URLError, OSError) as error:
            raise CloudGpuError("Не удалось обратиться к RunPod") from error
        try:
            result = json.loads(raw.decode("utf-8", "replace"))
        except (UnicodeDecodeError, ValueError) as error:
            raise CloudGpuError("RunPod вернул некорректный ответ") from error
        if not isinstance(result, dict):
            raise CloudGpuError("RunPod вернул неожиданный формат ответа")
        return result

    def submit(self, worker_input: Mapping[str, Any], *, allow_upload: bool = False) -> dict[str, Any]:
        if not allow_upload:
            raise CloudGpuError("Передача файла в RunPod не подтверждена")
        if not isinstance(worker_input, Mapping):
            raise TypeError("worker_input должен быть объектом")
        return self._request("run", {"input": dict(worker_input)})

    def status(self, job_id: str) -> dict[str, Any]:
        if not job_id or len(job_id) > 256:
            raise CloudGpuError("Некорректный RunPod job ID")
        return self._request(f"status/{job_id}")
