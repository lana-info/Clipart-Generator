import json

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
    result = RunPodClient(RunPodConfig("secret", "ep-1")).submit({"mode": "invisible"})
    assert result["id"] == "job-1"
    assert seen["limit"] == 2 * 1024 * 1024
    assert seen["url"].endswith("/run")
    assert seen["auth"] == "secret"
