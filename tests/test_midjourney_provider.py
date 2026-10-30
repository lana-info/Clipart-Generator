"""Midjourney over the PiAPI task API: request shape, response parsing and routing.

The connection is deliberately not verified live (owner 2026-10-30: connect without a
paid check), so these tests pin the documented contract and the graceful failure paths.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import main
from midjourney_provider import (
    MODEL_ID,
    image_url,
    imagine_payload,
    provider_for_model,
    split_grid,
    task_id,
    task_state,
)


def test_imagine_payload_follows_the_unified_task_shape():
    payload = imagine_payload("  a red fox  ", "2:3")
    assert payload == {
        "model": "midjourney",
        "task_type": "imagine",
        "input": {"prompt": "a red fox", "aspect_ratio": "2:3"},
    }
    assert imagine_payload("fox", "7:5")["input"]["aspect_ratio"] == "1:1"   # unsupported ratio falls back
    try:
        imagine_payload("   ")
    except ValueError as error:
        assert "пустой промпт" in str(error)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("an empty prompt must be refused")


def test_response_parsing_covers_both_url_fields():
    submit = {"code": 200, "data": {"task_id": "abc-1", "status": "pending"}}
    assert task_id(submit) == "abc-1"
    assert task_state(submit) == "pending"
    assert task_state({"data": {"status": "COMPLETED"}}) == "completed"
    assert task_state({"data": {"status": "canceled"}}) == "failed"
    assert image_url({"data": {"output": {"image_url": "https://cdn/x.png"}}}) == "https://cdn/x.png"
    assert image_url({"data": {"output": {"image_urls": ["https://cdn/y.png"]}}}) == "https://cdn/y.png"
    assert image_url({"data": {"output": {}}}) == ""
    assert task_id({}) == "" and task_state({}) == "unknown"
    assert provider_for_model(MODEL_ID) == "piapi"
    assert provider_for_model("kie/qwen") is None


def test_grid_split_makes_four_pictures_in_reading_order():
    grid = Image.new("RGB", (8, 8))
    for index, box in enumerate(((0, 0, 4, 4), (4, 0, 8, 4), (0, 4, 4, 8), (4, 4, 8, 8)), start=1):
        grid.paste((index * 30, 0, 0), box)
    tiles = split_grid(grid)
    assert [tile.size for tile in tiles] == [(4, 4)] * 4
    assert [tile.getpixel((0, 0)) for tile in tiles] == [(30, 0, 0), (60, 0, 0), (90, 0, 0), (120, 0, 0)]
    odd = Image.new("RGB", (5, 5))
    assert split_grid(odd) == [odd]                     # not a grid: returned as is


def _worker(temp):
    return main.WorkerThread("mode1_generate_only", temp, {
        "piapi_api_key": "piapi-test-key",
        "text_generation_model": MODEL_ID,
        "status_poll_interval": 5,
        "generation_wait_timeout": 120,
    })


def test_worker_submits_polls_and_returns_the_image_url():
    with tempfile.TemporaryDirectory(prefix="midjourney-") as temp:
        worker = _worker(temp)
        calls = []

        def request(url, *, method, payload=None, headers=None, timeout=None):
            calls.append((method, url, payload))
            if method == "POST":
                return {"code": 200, "data": {"task_id": "task-9", "status": "pending"}}
            return {"code": 200, "data": {"status": "completed",
                                          "output": {"image_url": "https://cdn.example/grid.png"}}}

        worker._request_json = request
        worker._ensure_running = lambda: None
        worker._wait_for_generation_launch_slot = lambda: None
        messages = []
        worker.progress.connect(messages.append)
        url = worker._midjourney_generate_image("a red fox", MODEL_ID)
        assert url == "https://cdn.example/grid.png"
        assert calls[0][0] == "POST" and calls[0][1].endswith("/api/v1/task")
        assert calls[0][2]["model"] == "midjourney" and calls[0][2]["task_type"] == "imagine"
        assert calls[1][0] == "GET" and calls[1][1].endswith("/api/v1/task/task-9")
        assert any("Task ID: task-9" in message for message in messages)


def test_worker_reports_provider_errors_instead_of_charging_silently():
    with tempfile.TemporaryDirectory(prefix="midjourney-errors-") as temp:
        worker = _worker(temp)
        worker._ensure_running = lambda: None
        worker._wait_for_generation_launch_slot = lambda: None

        worker._request_json = lambda *args, **kwargs: {"code": 200, "data": {}}
        try:
            worker._midjourney_generate_image("a red fox", MODEL_ID)
        except RuntimeError as error:
            assert "Task ID" in str(error)
        else:  # pragma: no cover - the call above must raise
            raise AssertionError("a submit without a task id must fail loudly")

        def failing(url, *, method, payload=None, headers=None, timeout=None):
            if method == "POST":
                return {"code": 200, "data": {"task_id": "task-1", "status": "pending"}}
            return {"code": 200, "data": {"status": "failed"}}

        worker._request_json = failing
        try:
            worker._midjourney_generate_image("a red fox", MODEL_ID)
        except RuntimeError as error:
            assert "ошибкой у провайдера" in str(error)
        else:  # pragma: no cover - the call above must raise
            raise AssertionError("a failed task must fail loudly")

        worker.piapi_api_key = ""
        try:
            worker._midjourney_generate_image("a red fox", MODEL_ID)
        except RuntimeError as error:
            assert "ключ PiAPI" in str(error)
        else:  # pragma: no cover - the call above must raise
            raise AssertionError("a missing key must fail before any request")


def test_model_is_visible_routed_to_piapi_and_keeps_the_ratio():
    from model_catalog import VISIBLE_GENERATION_MODEL_IDS, generation_provider_id, model_spec
    assert MODEL_ID in VISIBLE_GENERATION_MODEL_IDS
    assert generation_provider_id(MODEL_ID) == "piapi"
    assert "1:1" in model_spec(MODEL_ID).ratios and "2:3" in model_spec(MODEL_ID).ratios
