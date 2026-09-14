"""Core-owned provider facade; modules never receive provider transports or credentials."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Mapping

from studio_provider_api import ProviderOperationRequest


class ProtectedProviderExecutor(ABC):
    """Core/provider port that owns secrets, journal/resume, idempotency and paid transport."""

    @abstractmethod
    def preflight(self, module_id: str, request: ProviderOperationRequest) -> Mapping[str, Any]: ...

    @abstractmethod
    def execute_protected(
        self, module_id: str, request: ProviderOperationRequest, preflight: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class CoreProviderFacade:
    __slots__ = ("_module_id", "_family", "_executor", "_authorize")

    def __init__(
        self, module_id: str, family: str, executor: ProtectedProviderExecutor,
        authorize: Callable[..., bool],
    ) -> None:
        if not isinstance(module_id, str) or not module_id:
            raise TypeError("module_id is required")
        if family not in {"text", "image"}:
            raise ValueError("Unsupported provider family")
        if not isinstance(executor, ProtectedProviderExecutor):
            raise TypeError("executor must be a ProtectedProviderExecutor")
        if not callable(authorize):
            raise TypeError("authorize must be callable")
        self._module_id = module_id
        self._family = family
        self._executor = executor
        self._authorize = authorize

    def execute(self, request: ProviderOperationRequest) -> Mapping[str, Any]:
        if not isinstance(request, ProviderOperationRequest):
            raise TypeError("request must be a ProviderOperationRequest")
        preflight = self._executor.preflight(self._module_id, request)
        if self._authorize(self._module_id, self._family, request, preflight) is not True:
            raise PermissionError("Provider operation is not explicitly authorized")
        # Deliberately exactly one attempt. The protected executor owns journal/resume
        # and raises ProviderSubmissionUncertain when a paid POST outcome is ambiguous.
        return self._executor.execute_protected(self._module_id, request, preflight)
