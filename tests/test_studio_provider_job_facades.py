from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

from studio_job_api import JobRequest
from studio_job_services import CoreJobService, JobLauncher
from studio_module_runtime import ModuleRuntimeError, ModuleRuntimeHost
from studio_modules import ModuleStore
from studio_provider_api import ProviderOperationRequest, ProviderSubmissionUncertain
from studio_provider_services import CoreProviderFacade, ProtectedProviderExecutor


class FakeExecutor(ProtectedProviderExecutor):
    def __init__(self, *, uncertain=False):
        self.events = []
        self.uncertain = uncertain

    def preflight(self, module_id, request):
        self.events.append(("preflight", module_id, request.operation))
        return {"estimated_cost": "0.01", "currency": "USD"}

    def execute_protected(self, module_id, request, preflight):
        self.events.append(("execute", module_id, request.operation))
        if self.uncertain:
            raise ProviderSubmissionUncertain("submission outcome unknown")
        return {"status": "complete", "text": "ok"}


def test_public_provider_request_contains_no_credentials_or_self_authorization():
    request = ProviderOperationRequest("summarize", "model-a", {"text": "hello"})
    assert request.operation == "summarize"
    for name in ("api_key", "token", "secret", "approved", "authorization", "idempotency_key"):
        assert not hasattr(request, name)


def test_provider_facade_owns_preflight_and_literal_authorization():
    executor = FakeExecutor()
    facade = CoreProviderFacade("text-probe", "text", executor, lambda *_args: 1)
    with pytest.raises(PermissionError):
        facade.execute(ProviderOperationRequest("summarize", "model-a", {"text": "hello"}))
    assert executor.events == [("preflight", "text-probe", "summarize")]

    executor = FakeExecutor()
    facade = CoreProviderFacade("text-probe", "text", executor, lambda *_args: True)
    result = facade.execute(ProviderOperationRequest("summarize", "model-a", {"text": "hello"}))
    assert result["text"] == "ok"
    assert executor.events == [
        ("preflight", "text-probe", "summarize"),
        ("execute", "text-probe", "summarize"),
    ]


def test_provider_facade_never_silently_retries_uncertain_submission():
    executor = FakeExecutor(uncertain=True)
    facade = CoreProviderFacade("text-probe", "text", executor, lambda *_args: True)
    with pytest.raises(ProviderSubmissionUncertain):
        facade.execute(ProviderOperationRequest("summarize", "model-a", {"text": "hello"}))
    assert [event[0] for event in executor.events].count("execute") == 1


def test_job_service_uses_core_registered_launcher_and_runtime_job_lease(tmp_path):
    # Minimal host/store fixture is supplied by a small fake loaded-module hook below.
    host = object.__new__(ModuleRuntimeHost)
    host._owner_thread = threading.get_ident()
    host._active_jobs = {}
    host._page_leases = {}
    host._job_leases = {}
    host._lease_lock = threading.RLock()
    host._loaded = {"text-probe": object()}
    host._current_loaded = lambda module_id: host._loaded[module_id]

    completions = []
    launched = []
    def launch(module_id, request, complete):
        launched.append((module_id, request.operation, dict(request.payload)))
        completions.append(complete)
        return "job-1"

    jobs = CoreJobService("text-probe", host, (JobLauncher("normalize", launch),))
    ticket = jobs.submit(JobRequest("normalize", {"text": " hi "}))
    assert ticket.job_id == "job-1"
    assert launched == [("text-probe", "normalize", {"text": " hi "})]
    with pytest.raises(ModuleRuntimeError, match="active jobs"):
        host._ensure_idle("text-probe")
    completions[0]()
    host._ensure_idle("text-probe")
