import json
import pytest
from cloud_gpu_backend import RunPodClient, RunPodConfig

@pytest.mark.parametrize('key', ['dummy', 'Bearer dummy'])
@pytest.mark.parametrize('operation', ['submit', 'status'])
def test_runpod_uses_documented_bearer_auth(monkeypatch, key, operation):
    seen = []
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, limit):
            return json.dumps({'id': 'job-1', 'status': 'COMPLETED'}).encode()
    def fake(request, timeout):
        seen.append(request.get_header('Authorization'))
        return Response()
    monkeypatch.setattr('urllib.request.urlopen', fake)
    client = RunPodClient(RunPodConfig(key, 'endpoint-1'))
    if operation == 'submit':
        client.submit({'mode': 'invisible'})
    else:
        client.status('job-1')
    assert seen == ['Bearer dummy']
