"""Documented GPT Image 2.5 image-generation adapters (no HTTP side effects).

AtlasCloud: POST /api/v1/model/generateImage, poll /api/v1/model/prediction/{id}.
PiAPI: POST /api/v1/images/generations/async, poll /api/v1/task/{id}.
Both endpoints are asynchronous, so callers can journal an accepted paid task.
"""
from __future__ import annotations

import base64
import binascii
import re
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any
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
MAX_REFERENCE_BYTES = 10 * 1024 * 1024
MAX_REFERENCE_IMAGES = 16


class Gpt25ProviderError(ValueError):
    """Provider response or unsupported request; safe for user-facing errors."""


def provider_for_model(model_id: str) -> str | None:
    return MODEL_TO_PROVIDER.get(str(model_id))


def prepare_reference_inputs(references: Sequence[str] | None) -> tuple[str, ...]:
    """Encode local references for direct submission to the selected paid provider.

    No KIE upload is involved. The paid provider receives the image bytes.
    This function is reused by the paid-task recovery fingerprint.
    """
    result: list[str] = []
    for reference in references or ():
        value = str(reference or "").strip()
        if not value:
            raise Gpt25ProviderError("Пустой референс изображения")
        if len(result) >= MAX_REFERENCE_IMAGES:
            raise Gpt25ProviderError("Максимум 16 референсов на генерацию")
        if value.lower().startswith("https://"):
            parsed = urlsplit(value)
            if not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
                raise Gpt25ProviderError("Некорректная HTTPS-ссылка на референс")
            result.append(value)
            continue
        if "://" in value or value.lower().startswith("data:"):
            raise Gpt25ProviderError("Референсы по ссылке должны использовать HTTPS")
        path = Path(value).expanduser()
        try:
            with path.open("rb") as stream:
                blob = stream.read(MAX_REFERENCE_BYTES + 1)
        except OSError as error:
            raise Gpt25ProviderError("Референс не найден или недоступен") from error
        if not blob or len(blob) > MAX_REFERENCE_BYTES:
            raise Gpt25ProviderError("Референс пустой или превышает 10 МБ")
        if blob.startswith(b"\x89PNG\r\n\x1a\n"):
            mime = "image/png"
        elif blob.startswith(b"\xff\xd8\xff"):
            mime = "image/jpeg"
        elif blob.startswith(b"RIFF") and blob[8:12] == b"WEBP":
            mime = "image/webp"
        else:
            raise Gpt25ProviderError("Референс должен быть PNG, JPEG или WEBP")
        result.append(f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}")
    return tuple(result)


def generation_payload(
    model_id: str, prompt: str, ratio: str, resolution: str,
    references: Sequence[str] | None = None,
) -> dict:
    provider = provider_for_model(model_id)
    if not provider:
        raise Gpt25ProviderError("Неизвестная модель GPT Image 2.5")
    images = tuple(references or ())
    if len(images) > MAX_REFERENCE_IMAGES:
        raise Gpt25ProviderError("Максимум 16 референсов на генерацию")
    if any(not isinstance(image, str) or not image.strip() for image in images):
        raise Gpt25ProviderError("Некорректный референс изображения")
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
    model = MODEL_ENDPOINT_IDS[model_id]
    if images and provider == "atlascloud":
        model = model.replace("/text-to-image", "/edit")
    payload = {"model": model, "prompt": prompt, "output_format": "png"}
    if not budget:
        payload.update({"size": SIZE_BY_RATIO[ratio], "quality": "medium"})
    if provider == "atlascloud":
        payload.update({"enable_sync_mode": False, "enable_base64_output": False})
        if images:
            payload["images"] = list(images)
    else:
        payload.update({"n": 1, "response_format": "url"})
        if images:
            payload["image"] = list(images) if len(images) > 1 else images[0]
    return payload


def submit_url(provider: str, *, has_references: bool = False) -> str:
    if provider == "piapi" and has_references:
        return "https://api.piapi.ai/api/v1/images/edits/async"
    return _SUBMIT_URLS[provider]


def piapi_edit_multipart_body(payload: Mapping[str, Any]) -> tuple[bytes, str]:
    """Encode PiAPI image edits as multipart with one `image[]` part per reference."""
    raw_images = payload.get("image")
    images = list(raw_images) if isinstance(raw_images, (list, tuple)) else [raw_images]
    if not images or any(not isinstance(image, str) or not image.strip() for image in images):
        raise Gpt25ProviderError("PiAPI edit требует корректные референсы изображений")

    boundary = "VibixPiAPI" + uuid.uuid4().hex
    chunks: list[bytes] = []

    def add_field(name: str, value: str, *, filename: str = "", mime: str = "") -> None:
        header = [f"--{boundary}", f'Content-Disposition: form-data; name="{name}"']
        if filename:
            header[-1] += f'; filename="{filename}"'
        if mime:
            header.append(f"Content-Type: {mime}")
        chunks.append(("\r\n".join(header) + "\r\n\r\n").encode("ascii"))
        chunks.append(value.encode("utf-8"))
        chunks.append(b"\r\n")

    for key, value in payload.items():
        if key == "image":
            continue
        if not re.fullmatch(r"[a-zA-Z0-9_]+", str(key)):
            raise Gpt25ProviderError("Некорректное поле PiAPI")
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif not isinstance(value, (str, int, float)):
            raise Gpt25ProviderError("Некорректное значение поля PiAPI")
        add_field(str(key), str(value))

    image_field = "image" if len(images) == 1 else "image[]"
    for index, image in enumerate(images, start=1):
        match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)", image)
        if match:
            mime, encoded = match.groups()
            try:
                image_bytes = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error) as error:
                raise Gpt25ProviderError("Некорректный референс изображения") from error
            if not image_bytes or len(image_bytes) > MAX_REFERENCE_BYTES:
                raise Gpt25ProviderError("Референс пустой или превышает 10 МБ")
            extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[mime]
            header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{image_field}"; filename="reference-{index}.{extension}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("ascii")
            chunks.extend((header, image_bytes, b"\r\n"))
        else:
            parsed = urlsplit(image)
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username
                    or parsed.password or parsed.port not in (None, 443)
                    or "\r" in image or "\n" in image):
                raise Gpt25ProviderError("Референс должен быть корректным HTTPS URL или изображением")
            add_field(image_field, image)

    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

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
