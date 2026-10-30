"""Midjourney V8.2 over AtlasCloud: request shape, response parsing and routing.

The contract comes from the provider's own model page (2026-10-30): the endpoint id,
the price of a job (four pictures) and the response fields. These tests pin that
contract and the graceful failure paths — the first paid run is still the owner's call.
"""
import tempfile

import main
from midjourney_provider import (
    ENDPOINT_MODEL,
    MODEL_ID,
    imagine_payload,
    provider_for_model,
    status_url,
    submitted_task_id,
    submit_url,
    task_result,
)


def test_imagine_payload_follows_the_documented_shape():
    payload = imagine_payload("  a red fox  ", "2:3")
    assert payload == {"model": ENDPOINT_MODEL, "prompt": "a red fox", "aspect_ratio": "2:3"}
    assert ENDPOINT_MODEL == "midjourney/v8.2/text-to-image"
    assert imagine_payload("fox", "7:5")["aspect_ratio"] == "1:1"   # unsupported ratio falls back
    try:
        imagine_payload("   ")
    except ValueError as error:
        assert "пустой промпт" in str(error)
    else:  # pragma: no cover - the call above must raise
        raise AssertionError("an empty prompt must be refused")


def test_response_parsing_uses_the_atlascloud_fields():
    submit = {"data": {"id": "pred-1", "status": "processing"}}
    assert submitted_task_id(submit) == "pred-1"
    assert task_result({"data": {"status": "processing"}}) == ("pending", None)
    assert task_result({"data": {"status": "succeeded",
                                 "outputs": ["https://cdn.example/one.png"]}}) == (
        "completed", "https://cdn.example/one.png")
    assert task_result({"data": {"status": "failed"}})[0] == "failed"
    assert submit_url().endswith("/api/v1/model/generateImage")
    assert status_url("pred-1").endswith("/api/v1/model/prediction/pred-1")
    assert provider_for_model(MODEL_ID) == "atlascloud"
    assert provider_for_model("piapi/gpt-image-2.5") is None


def _worker(temp):
    return main.WorkerThread("mode1_generate_only", temp, {
        "atlascloud_api_key": "atlas-test-key",
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
                return {"data": {"id": "pred-9", "status": "processing"}}
            return {"data": {"status": "succeeded", "outputs": ["https://cdn.example/first.png"]}}

        worker._request_json = request
        worker._ensure_running = lambda: None
        worker._wait_for_generation_launch_slot = lambda: None
        messages = []
        worker.progress.connect(messages.append)
        url = worker._midjourney_generate_image("a red fox", MODEL_ID)
        assert url == "https://cdn.example/first.png"
        assert calls[0][0] == "POST" and calls[0][1].endswith("/api/v1/model/generateImage")
        assert calls[0][2]["model"] == ENDPOINT_MODEL and calls[0][2]["aspect_ratio"] == "1:1"
        assert calls[1][0] == "GET" and calls[1][1].endswith("/api/v1/model/prediction/pred-9")
        assert any("Task ID: pred-9" in message for message in messages)


def test_worker_reports_provider_errors_instead_of_charging_silently():
    with tempfile.TemporaryDirectory(prefix="midjourney-errors-") as temp:
        worker = _worker(temp)
        worker._ensure_running = lambda: None
        worker._wait_for_generation_launch_slot = lambda: None

        worker._request_json = lambda *args, **kwargs: {"data": {}}
        try:
            worker._midjourney_generate_image("a red fox", MODEL_ID)
        except Exception as error:
            assert "идентификатор задачи" in str(error)
        else:  # pragma: no cover - the call above must raise
            raise AssertionError("a submit without a task id must fail loudly")

        def failing(url, *, method, payload=None, headers=None, timeout=None):
            if method == "POST":
                return {"data": {"id": "pred-1", "status": "processing"}}
            return {"data": {"status": "failed"}}

        worker._request_json = failing
        try:
            worker._midjourney_generate_image("a red fox", MODEL_ID)
        except RuntimeError as error:
            assert "ошибкой у провайдера" in str(error)
        else:  # pragma: no cover - the call above must raise
            raise AssertionError("a failed task must fail loudly")

        worker.atlascloud_api_key = ""
        try:
            worker._midjourney_generate_image("a red fox", MODEL_ID)
        except RuntimeError as error:
            assert "ключ AtlasCloud" in str(error)
        else:  # pragma: no cover - the call above must raise
            raise AssertionError("a missing key must fail before any request")


def test_model_is_visible_routed_to_atlascloud_and_keeps_the_ratio():
    from model_catalog import VISIBLE_GENERATION_MODEL_IDS, generation_provider_id, model_spec
    assert MODEL_ID in VISIBLE_GENERATION_MODEL_IDS
    assert generation_provider_id(MODEL_ID) == "atlascloud"
    assert "1:1" in model_spec(MODEL_ID).ratios and "21:9" in model_spec(MODEL_ID).ratios
    assert "0.086" in model_spec(MODEL_ID).pricing
