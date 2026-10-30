"""Midjourney V8.2 through AtlasCloud (no HTTP side effects here).

Verified against the provider's own model page (2026-10-30): the model id is
``midjourney/v8.2/text-to-image``, one job costs $0.086 and returns four pictures,
the submit endpoint is ``POST /api/v1/model/generateImage`` and the status is polled
at ``GET /api/v1/model/prediction/{id}``. The response fields (``id``, ``status``,
``outputs``) are the same ones the GPT Image 2.5 path already parses, so the task id,
the terminal status and the image URL are read by the shared helpers instead of a
second implementation.

The first owner note claimed KIE or PiAPI; both were checked: KIE's published model
list has no Midjourney at all, and PiAPI states plainly that it does not provide a
Midjourney API service. AtlasCloud is the provider of ours that does.

One job returns four pictures; the picture of the item is the first of them (the
flow keeps one picture per item, the paid job still produced all four).
"""
from __future__ import annotations

from typing import Any, Mapping

from gpt25_provider import (
    status_url as _status_url,
    submitted_task_id as _submitted_task_id,
    submit_url as _submit_url,
    task_result as _task_result,
)

MODEL_ID = "atlascloud/midjourney-v8.2"
ENDPOINT_MODEL = "midjourney/v8.2/text-to-image"
LABEL = "AtlasCloud — Midjourney V8.2"
PRICING = "$0.086 за задание (4 картинки)"
# The provider's own list for v8.2 text-to-image.
ASPECT_RATIOS = ("1:1", "9:16", "16:9", "4:3", "3:4", "2:3", "3:2", "9:21", "21:9")


def provider_for_model(model_id: object) -> str | None:
    """The provider that serves this model, or None when it is not the Midjourney model."""
    return "atlascloud" if str(model_id or "").strip() == MODEL_ID else None


def imagine_payload(prompt: object, aspect_ratio: str = "1:1") -> dict[str, Any]:
    """The documented request body: the model, the prompt and the aspect ratio only."""
    text = str(prompt or "").strip()
    if not text:
        raise ValueError("Midjourney: пустой промпт")
    if len(text) > 1024:
        raise ValueError("Midjourney принимает промпт до 1024 символов")
    ratio = str(aspect_ratio or "").strip()
    if ratio not in ASPECT_RATIOS:
        ratio = "1:1"
    return {"model": ENDPOINT_MODEL, "prompt": text, "aspect_ratio": ratio}


def submit_url() -> str:
    return _submit_url("atlascloud")


def status_url(task_id: str) -> str:
    return _status_url("atlascloud", str(task_id))


def submitted_task_id(response: Mapping[str, Any] | None) -> str:
    return _submitted_task_id("atlascloud", response)


def task_result(response: Mapping[str, Any] | None) -> tuple[str, str | None]:
    """(pending|completed|failed, https-image-url) — the shared AtlasCloud parsing."""
    state, result = _task_result("atlascloud", response)
    return state, result if isinstance(result, str) or result is None else None
