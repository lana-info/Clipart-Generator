import json
import urllib.error

import pytest

from cloud_gpu_backend import CloudGpuError, RunPodClient, RunPodConfig


def test_runpod_config_requires_credentials():
    with pytest.raises(CloudGpuError):
        RunPodConfig("", "endpoint").validate()
    with pytest.raises(CloudGpuError):
        RunPodConfig("secret", "").validate()


def test_runpod_submit_uses_bounded_json_request(monkeypatch):
    seen = {}

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            seen["limit"] = limit
            return json.dumps({"id": "job-1", "status": "IN_QUEUE"}).encode()

    def fake_urlopen(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.headers.get("Authorization")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = RunPodClient(RunPodConfig("secret", "ep-1")).submit(
        {"mode": "invisible"}, allow_upload=True
    )
    assert result["id"] == "job-1"
    assert seen["limit"] == 2 * 1024 * 1024
    assert seen["url"].endswith("/run")
    assert seen["auth"] == "Bearer secret"


def test_runpod_submit_defaults_to_user_started_upload(monkeypatch):
    client = RunPodClient(RunPodConfig("secret", "ep-1"))
    monkeypatch.setattr(client, "_request", lambda path, payload: {"id": "job-1"})
    assert client.submit({"mode": "invisible"})["id"] == "job-1"


def test_runpod_rejects_unsafe_endpoint_id():
    with pytest.raises(CloudGpuError):
        RunPodConfig("secret", "../endpoint").validate()


def test_runpod_emits_safe_submit_and_status_events(monkeypatch):
    responses = iter(
        [
            {"id": "job-123", "status": "IN_QUEUE"},
            {"id": "job-123", "status": "COMPLETED", "output": {"url": "https://private"}},
        ]
    )

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, _limit):
            return json.dumps(next(responses)).encode()

    monkeypatch.setattr("urllib.request.urlopen", lambda request, timeout: Response())
    events = []
    client = RunPodClient(
        RunPodConfig("secret-api-key", "ep-1"),
        diagnostic_callback=events.append,
    )

    client.submit({"prompt": "private prompt", "image": "private bytes"})
    client.status("job-123")

    encoded = json.dumps(events)
    assert [event["event"] for event in events] == [
        "provider_task_submitted",
        "provider_task_polled",
    ]
    assert events[0]["task"] == "job-123"
    assert events[1]["provider_state"] == "COMPLETED"
    assert "private prompt" not in encoded
    assert "secret-api-key" not in encoded
    assert "https://private" not in encoded


def test_runpod_diagnostic_callback_cannot_break_request(monkeypatch):
    monkeypatch.setattr(
        RunPodClient,
        "_request",
        lambda self, path, payload=None: {"id": "job-1"},
    )
    client = RunPodClient(
        RunPodConfig("secret", "ep-1"),
        diagnostic_callback=lambda event: (_ for _ in ()).throw(RuntimeError("callback")),
    )

    assert client.submit({"mode": "invisible"})["id"] == "job-1"


def test_runpod_http_error_emits_safe_failure(monkeypatch):
    def fail_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url,
            503,
            "unavailable secret-api-key",
            {},
            None,
        )

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    events = []
    client = RunPodClient(
        RunPodConfig("secret-api-key", "ep-1"),
        diagnostic_callback=events.append,
    )

    with pytest.raises(CloudGpuError):
        client.submit({"prompt": "private prompt"})

    assert events[-1]["event"] == "provider_task_failed"
    assert events[-1]["http_status"] == 503
    assert "secret-api-key" not in json.dumps(events)
