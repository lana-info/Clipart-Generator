"""Midjourney through the PiAPI unified task API (no HTTP side effects here).

The owner asked to connect Midjourney on 2026-10-30 without a paid test, so this
module keeps the request and response handling in one documented place, next to the
GPT Image 2.5 adapters that already poll the same PiAPI task endpoint
(``GET /api/v1/task/{id}``). The submission uses the documented unified shape::

    POST https://api.piapi.ai/api/v1/task
    {"model": "midjourney", "task_type": "imagine",
     "input": {"prompt": "...", "aspect_ratio": "1:1"}}

NOT VERIFIED LIVE. There is no API key in the development environment and the owner
does not want a paid check yet, so the first real use either succeeds or returns the
provider's own error (a rejected request is not billed). Midjourney answers an
``imagine`` with a 2x2 grid of four variants; ``split_grid`` turns one grid into the
four pictures of the owner's flow, and it is wired only after the live check confirms
the response shape.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

MODEL_ID = "piapi/midjourney"
LABEL = "PiAPI — Midjourney"
SUBMIT_URL = "https://api.piapi.ai/api/v1/task"
STATUS_URL = "https://api.piapi.ai/api/v1/task/{task_id}"
ASPECT_RATIOS = ("1:1", "2:3", "3:2")

_COMPLETED = {"completed", "succeeded", "success", "finished"}
_FAILED = {"failed", "canceled", "cancelled", "error"}


def provider_for_model(model_id: object) -> str | None:
    """The provider that serves this model, or None when it is not a Midjourney model."""
    return "piapi" if str(model_id or "").strip() == MODEL_ID else None


def imagine_payload(prompt: object, aspect_ratio: str = "1:1") -> dict[str, Any]:
    """The imagine task body; the ratio must be one of the supported ones."""
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("Midjourney: пустой промпт")
    ratio = str(aspect_ratio or "").strip()
    if ratio not in ASPECT_RATIOS:
        ratio = "1:1"
    return {
        "model": "midjourney",
        "task_type": "imagine",
        "input": {"prompt": text, "aspect_ratio": ratio},
    }


def _data(response: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not isinstance(response, Mapping):
        return {}
    data = response.get("data")
    return data if isinstance(data, Mapping) else {}


def task_id(response: Mapping[str, Any] | None) -> str:
    """The provider's task id from a submit response; empty when it is missing."""
    data = _data(response)
    for key in ("task_id", "taskId", "id"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def task_state(response: Mapping[str, Any] | None) -> str:
    """A normalised status: pending / processing / completed / failed / unknown."""
    state = str(_data(response).get("status") or "").strip().lower()
    if state in _COMPLETED:
        return "completed"
    if state in _FAILED:
        return "failed"
    return state or "unknown"


def image_url(response: Mapping[str, Any] | None) -> str:
    """The first image of a finished task (the 2x2 grid of an imagine)."""
    output = _data(response).get("output")
    if not isinstance(output, Mapping):
        return ""
    single = str(output.get("image_url") or output.get("imageUrl") or "").strip()
    if single:
        return single
    urls = output.get("image_urls") or output.get("imageUrls")
    if isinstance(urls, Sequence) and not isinstance(urls, (str, bytes)):
        for entry in urls:
            value = str(entry or "").strip()
            if value:
                return value
    return ""


def split_grid(image):
    """Cut a 2x2 Midjourney grid into four pictures, in reading order."""
    width, height = image.size
    if width < 2 or height < 2 or width % 2 or height % 2:
        return [image]
    half_w, half_h = width // 2, height // 2
    boxes = ((0, 0, half_w, half_h), (half_w, 0, width, half_h),
             (0, half_h, half_w, height), (half_w, half_h, width, height))
    return [image.crop(box) for box in boxes]
