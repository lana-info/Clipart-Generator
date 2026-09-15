"""Core-owned image run admission over the existing legacy WorkerThread stack."""
from __future__ import annotations

import weakref
from dataclasses import replace
from typing import Any, Callable, Mapping

from security_redaction import redact_absolute_paths, redact_text
from studio_job_services import CoreWorkerJobHandle
from v3_flow_runtime import FlowRunRequest
from v3_image_generation_runtime import missing_runtime_requirements
from v3_image_worker_settings import enrich_image_worker_settings


class ImageRunGatewayError(RuntimeError):
    pass


def _store_callback(callback):
    if callback is None:
        return None
    try:
        return weakref.WeakMethod(callback)
    except TypeError:
        return callback


def _load_callback(value, label: str):
    if isinstance(value, weakref.WeakMethod):
        callback = value()
        if callback is None:
            raise ImageRunGatewayError(f"Core {label} service is unavailable")
        return callback
    if not callable(value):
        raise ImageRunGatewayError(f"Core {label} service is unavailable")
    return value

class CoreImageRunGateway:
    __slots__ = (
        "_runtime_settings_provider", "_authorization_provider",
        "_run_preparer", "_worker_factory", "_fal_cost_estimator",
    )

    def __init__(
        self,
        *,
        runtime_settings_provider: Callable[[], Mapping[str, Any]],
        authorization_provider: Callable[[], Any],
        run_preparer: Callable[[], str | None],
        worker_factory: Callable[..., Any],
        fal_cost_estimator: Callable[[str, Mapping[str, int]], tuple[float, str]] | None = None,
    ) -> None:
        self._runtime_settings_provider = _store_callback(runtime_settings_provider)
        self._authorization_provider = _store_callback(authorization_provider)
        self._run_preparer = _store_callback(run_preparer)
        self._worker_factory = _store_callback(worker_factory)
        if fal_cost_estimator is None:
            from v3_api_settings import estimate_fal_cost
            fal_cost_estimator = estimate_fal_cost
        self._fal_cost_estimator = _store_callback(fal_cost_estimator)

    @staticmethod
    def _require_request(request: FlowRunRequest) -> FlowRunRequest:
        if not isinstance(request, FlowRunRequest):
            raise TypeError("request must be a FlowRunRequest")
        return request

    def _runtime_snapshot(self) -> dict[str, Any]:
        provider = _load_callback(self._runtime_settings_provider, "runtime settings")
        value = provider()
        if not isinstance(value, Mapping):
            raise ImageRunGatewayError("Core runtime settings are invalid")
        return dict(value)

    @staticmethod
    def _safe_message(value: Any, runtime: Mapping[str, Any]) -> str:
        secrets = tuple(
            runtime.get(name)
            for name in (
                "kie_api_key", "fal_api_key", "photoroom_api_key",
                "runpod_api_key", "openrouter_api_key",
            )
            if isinstance(runtime.get(name), str)
        )
        text = redact_text(value, secrets)
        return redact_absolute_paths(text)

    @classmethod
    def _safe_error(cls, error: BaseException, runtime: Mapping[str, Any]) -> str:
        return cls._safe_message(
            str(error).strip() or error.__class__.__name__, runtime
        )

    def _enriched_request(
        self, request: FlowRunRequest, runtime: Mapping[str, Any]
    ) -> FlowRunRequest:
        settings = enrich_image_worker_settings(request.settings, runtime)
        return replace(request, settings=settings)

    def preflight(self, request: FlowRunRequest) -> tuple[str, ...]:
        request = self._require_request(request)
        runtime = self._runtime_snapshot()
        internal = self._enriched_request(request, runtime)
        return tuple(
            self._safe_message(label, runtime)
            for label in missing_runtime_requirements(internal)
        )

    def estimate_fal_cost(
        self, endpoint_quantities: Mapping[str, int]
    ) -> tuple[float, str]:
        runtime = self._runtime_snapshot()
        api_key = str(runtime.get("fal_api_key") or "").strip()
        if not api_key:
            raise ImageRunGatewayError("Добавьте Fal.ai API Key в настройках API")
        estimator = _load_callback(self._fal_cost_estimator, "Fal cost")
        try:
            return estimator(api_key, endpoint_quantities)
        except Exception as error:
            raise ImageRunGatewayError(self._safe_error(error, runtime)) from error

    def launch(self, request: FlowRunRequest) -> CoreWorkerJobHandle:
        request = self._require_request(request)
        runtime = self._runtime_snapshot()
        internal = self._enriched_request(request, runtime)
        missing = tuple(
            self._safe_message(label, runtime)
            for label in missing_runtime_requirements(internal)
        )
        if missing:
            raise ImageRunGatewayError(
                "Укажите в настройках: " + ", ".join(missing)
            )
        try:
            authorize = _load_callback(self._authorization_provider, "authorization")
            authorize()
            prepare = _load_callback(self._run_preparer, "run preparation")
            project_id = prepare()
            kwargs = request.worker_kwargs()
            kwargs["settings"] = dict(internal.settings)
            if project_id is not None:
                kwargs["project_id"] = project_id
            factory = _load_callback(self._worker_factory, "worker")
            worker = factory(**kwargs)
        except ImageRunGatewayError:
            raise
        except Exception as error:
            raise ImageRunGatewayError(self._safe_error(error, runtime)) from error
        if isinstance(worker, CoreWorkerJobHandle):
            return worker
        return CoreWorkerJobHandle(
            worker,
            message_redactor=lambda message: self._safe_message(message, runtime),
        )
