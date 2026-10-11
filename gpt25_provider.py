"""Documented GPT Image 2.5 image-generation adapters (no HTTP side effects).

AtlasCloud: POST /api/v1/model/generateImage, poll /api/v1/model/prediction/{id}.
PiAPI: POST /api/v1/images/generations/async, poll /api/v1/task/{id}.
Both endpoints are asynchronous, so callers can journal an accepted paid task.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import quote, urlsplit

MODEL_TO_PROVIDER = {
    **{f"atlascloud/gpt-image-2.5-{variant}": "atlascloud" for variant in ("flare", "sunburst")},
    **{f"piapi/{model}": "piapi" for model in ("gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-2.5")},
}
MODEL_ENDPOINT_IDS = {
    model_id: (f"openai/{model_id.split('/', 1)[1]}/text-to-image"
               if provider == "atlascloud" else model_id.split('/', 1)[1])
    for model_id, provider in MODEL_TO_PROVIDER.items()
}
BUDGET_MODEL_ID = "piapi/gpt-image-2.5"
SIZE_BY_RATIO = {
    "1:1": "1024x1024",
    "2:3": "1024x1536",
    "3:2": "1536x1024",
}
_SUBMIT_URLS = {
    "atlascloud": "https://api.atlascloud.ai/api/v1/model/generateImage",
    "piapi": "https://api.piapi.ai/api/v1/images/generations/async",
}
_STATUS_URLS = {
    "atlascloud": "https://api.atlascloud.ai/api/v1/model/prediction/",
    "piapi": "https://api.piapi.ai/api/v1/task/",
}
_TASK_ID = re.compile(r"[A-Za-z0-9_-]{1,256}\Z")


class Gpt25ProviderError(ValueError):
    """Provider response or unsupported request; safe for user-facing errors."""


def provider_for_model(model_id: str) -> str | None:
    return MODEL_TO_PROVIDER.get(str(model_id))


def generation_payload(model_id: str, prompt: str, ratio: str, resolution: str) -> dict:
    provider = provider_for_model(model_id)
    if not provider:
        raise Gpt25ProviderError("Неизвестная модель GPT Image 2.5")
    budget = model_id == BUDGET_MODEL_ID
    if (budget and (ratio != "auto" or resolution != "auto")) or (
        not budget and (resolution != "1K" or ratio not in SIZE_BY_RATIO)
    ):
        raise Gpt25ProviderError(
            "Бюджетный GPT Image 2.5 сам выбирает размер и качество" if budget else
            "Для этой модели пока доступны 1K и форматы 1:1, 2:3, 3:2"
        )
    if not str(prompt or "").strip() or len(prompt) > 32000:
        raise Gpt25ProviderError("Промпт должен содержать от 1 до 32000 символов")
    payload = {
        "model": MODEL_ENDPOINT_IDS[model_id],
        "prompt": prompt,
        "output_format": "png",
    }
    if not budget:
        payload.update({"size": SIZE_BY_RATIO[ratio], "quality": "medium"})
    if provider == "atlascloud":
        payload.update({"enable_sync_mode": False, "enable_base64_output": False})
    else:
        payload.update({"n": 1, "response_format": "url"})
    return payload


def submit_url(provider: str) -> str:
    return _SUBMIT_URLS[provider]


def status_url(provider: str, task_id: str) -> str:
    value = str(task_id or "").strip()
    if not _TASK_ID.fullmatch(value):
        raise Gpt25ProviderError("Некорректный идентификатор задачи провайдера")
    return _STATUS_URLS[provider] + quote(value, safe="")


def request_headers(provider: str, api_key: str) -> dict[str, str]:
    key = str(api_key or "").strip()
    if not key or "\r" in key or "\n" in key:
        raise Gpt25ProviderError("Не указан корректный API-ключ провайдера")
    headers = {"Accept": "application/json"}
    if provider == "atlascloud":
        headers["Authorization"] = f"Bearer {key}"
    elif provider == "piapi":
        headers["X-API-KEY"] = key
    else:
        raise Gpt25ProviderError("Неизвестный провайдер")
    return headers


def submitted_task_id(provider: str, response: object) -> str:
    if not isinstance(response, Mapping):
        raise Gpt25ProviderError("Провайдер не вернул данные о задаче")
    data = response.get("data") if provider == "atlascloud" else response
    if not isinstance(data, Mapping):
        raise Gpt25ProviderError("Провайдер не вернул задачу")
    task_id = str(data.get("id" if provider == "atlascloud" else "task_id") or "")
    if not _TASK_ID.fullmatch(task_id):
        raise Gpt25ProviderError("Провайдер не вернул идентификатор задачи")
    return task_id


def _result_url(value: object) -> str:
    candidate = str(value or "").strip()
    try:
        parsed = urlsplit(candidate)
        valid = (parsed.scheme == "https" and bool(parsed.hostname)
                 and not parsed.username and not parsed.password
                 and parsed.port in (None, 443))
    except ValueError:
        valid = False
    if not valid or "\r" in candidate or "\n" in candidate:
        raise Gpt25ProviderError("Провайдер не вернул безопасную HTTPS-ссылку на изображение")
    return candidate


def task_result(provider: str, response: object) -> tuple[str, str | None]:
    """Return (pending|completed|failed, image-url-if-completed)."""
    if not isinstance(response, Mapping):
        raise Gpt25ProviderError("Провайдер вернул некорректный статус задачи")
    data = response.get("data") if provider == "atlascloud" else response
    if not isinstance(data, Mapping):
        raise Gpt25ProviderError("Провайдер вернул некорректные данные задачи")
    status = str(data.get("status") or "").lower()
    if status in {"failed", "error", "cancelled", "canceled"}:
        return "failed", None
    if status in {"created", "pending", "processing", "running", "queued"}:
        return "pending", None
    if status != "completed":
        raise Gpt25ProviderError("Неизвестный статус задачи у провайдера")
    if provider == "atlascloud":
        urls = data.get("outputs")
        if not isinstance(urls, list) or not urls:
            raise Gpt25ProviderError("AtlasCloud не вернул изображение")
        return "completed", _result_url(urls[0])
    output = data.get("output")
    if not isinstance(output, Mapping):
        raise Gpt25ProviderError("PiAPI не вернул результат изображения")
    images = output.get("data")
    if not isinstance(images, list) or not images or not isinstance(images[0], Mapping):
        raise Gpt25ProviderError("PiAPI не вернул URL изображения")
    return "completed", _result_url(images[0].get("url"))
