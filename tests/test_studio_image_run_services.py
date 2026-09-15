from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from studio_job_services import CoreWorkerJobHandle
from studio_image_run_services import CoreImageRunGateway, ImageRunGatewayError
from v3_flow_runtime import FlowRunRequest


class RawWorker(QObject):
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    diagnostic = pyqtSignal(object)

    def start(self):
        pass

    def stop(self):
        pass

    def isRunning(self):
        return False


def generation_request(model: str = "gpt-image-2") -> FlowRunRequest:
    return FlowRunRequest(
        mode="mode1_generate_only",
        work_dir=".",
        settings={"text_generation_model": model},
        generated_prompts=[{"prompt": "test", "references": []}],
    )

def test_preflight_uses_core_credentials_without_returning_them():
    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {"kie_api_key": "core-secret"},
        authorization_provider=lambda: None,
        run_preparer=lambda: None,
        worker_factory=lambda **_kwargs: RawWorker(),
    )

    assert gateway.preflight(generation_request()) == ()
    assert gateway.preflight(generation_request("fal-ai/flux/schnell")) == (
        "Fal.ai API Key",
    )


def test_preflight_reports_processing_provider_requirement_safely():
    request = FlowRunRequest(
        mode="mode2_process",
        work_dir=".",
        settings={"remove_bg": True, "remove_bg_provider": "photoroom"},
        selected_files=["input.png"],
    )
    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {},
        authorization_provider=lambda: None,
        run_preparer=lambda: None,
        worker_factory=lambda **_kwargs: RawWorker(),
    )
    assert gateway.preflight(request) == ("PhotoRoom API Key",)

def test_fal_cost_estimate_keeps_key_inside_core():
    seen = {}

    def estimate(api_key, quantities):
        seen["key"] = api_key
        seen["quantities"] = dict(quantities)
        return 1.25, "USD"

    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {"fal_api_key": "fal-secret"},
        authorization_provider=lambda: None,
        run_preparer=lambda: None,
        worker_factory=lambda **_kwargs: RawWorker(),
        fal_cost_estimator=estimate,
    )
    assert gateway.estimate_fal_cost({"fal-ai/flux/schnell": 2}) == (1.25, "USD")
    assert seen == {
        "key": "fal-secret",
        "quantities": {"fal-ai/flux/schnell": 2},
    }


def test_launch_orders_authorize_save_then_enriched_worker_creation():
    events = []
    captured = {}

    def worker_factory(**kwargs):
        events.append("worker")
        captured.update(kwargs)
        return RawWorker()

    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {
            "kie_api_key": "kie-secret",
            "local_realesrgan_dir": "/core/realesrgan",
        },
        authorization_provider=lambda: events.append("authorize"),
        run_preparer=lambda: events.append("prepare") or "project-123",
        worker_factory=worker_factory,
    )
    handle = gateway.launch(generation_request())

    assert isinstance(handle, CoreWorkerJobHandle)
    assert events == ["authorize", "prepare", "worker"]
    assert captured["project_id"] == "project-123"
    assert captured["settings"]["kie_api_key"] == "kie-secret"
    assert captured["settings"]["local_realesrgan_dir"] == "/core/realesrgan"
    assert "kie_api_key" not in generation_request().settings


def test_authorization_failure_creates_no_worker():
    calls = []

    def deny():
        calls.append("authorize")
        raise PermissionError("denied")

    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {"kie_api_key": "secret"},
        authorization_provider=deny,
        run_preparer=lambda: calls.append("prepare"),
        worker_factory=lambda **_kwargs: calls.append("worker"),
    )

    try:
        gateway.launch(generation_request())
    except ImageRunGatewayError as error:
        assert "denied" in str(error)
    else:
        raise AssertionError("launch should fail")
    assert calls == ["authorize"]


def test_worker_factory_error_is_redacted_before_module_sees_it():
    secret = "kie-secret-value"

    def fail_worker(**_kwargs):
        raise RuntimeError(f"provider failed api_key={secret}")

    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {"kie_api_key": secret},
        authorization_provider=lambda: None,
        run_preparer=lambda: "project-1",
        worker_factory=fail_worker,
    )
    try:
        gateway.launch(generation_request())
    except ImageRunGatewayError as error:
        assert secret not in str(error)
    else:
        raise AssertionError("launch should fail")

def test_worker_signal_error_is_redacted_before_handle_emits_it():
    secret = "signal-secret-value"
    raw = RawWorker()
    gateway = CoreImageRunGateway(
        runtime_settings_provider=lambda: {"kie_api_key": secret},
        authorization_provider=lambda: None,
        run_preparer=lambda: None,
        worker_factory=lambda **_kwargs: raw,
    )
    handle = gateway.launch(generation_request())
    seen = []
    handle.error.connect(seen.append)

    raw.error.emit(f"worker failed with {secret}")

    assert seen
    assert secret not in seen[-1]
