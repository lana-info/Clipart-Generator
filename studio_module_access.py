"""Bridge the existing verified application-license gate to the module runtime.

No cached pointer, publisher signature or installed package grants module rights.
Actual package downloads must additionally be authorized by the server.
"""
from __future__ import annotations

from typing import Protocol

from license_client import LicenseAuthorization, LicenseError
from studio_processing_api import PROCESSING_COMPONENT_ID, PROCESSING_CONSUMERS


def allows_package(authorization: LicenseAuthorization, module_id: str) -> bool:
    """The shared dependency grants no workflow right of its own."""
    if not isinstance(authorization, LicenseAuthorization):
        return False
    if module_id == PROCESSING_COMPONENT_ID:
        return any(authorization.allows_module(consumer) for consumer in PROCESSING_CONSUMERS)
    return authorization.allows_module(module_id)


class AuthorizationGate(Protocol):
    def authorize_run(self) -> LicenseAuthorization: ...


def authorize_module_run(gate: AuthorizationGate, module_id: str) -> LicenseAuthorization:
    """Return fresh signed authorization only when this exact module is granted."""
    authorization = gate.authorize_run()
    if not isinstance(authorization, LicenseAuthorization) or not authorization.allows_module(module_id):
        raise LicenseError("Нет доступа к этому модулю")
    return authorization


class ModuleAccessPolicy:
    def __init__(self, gate: AuthorizationGate):
        self._gate = gate

    def __call__(self, module_id: str, action: str) -> bool:
        if action not in {"activate", "load", "download"} and not (
            isinstance(action, str) and action.startswith(("command:", "page:"))
        ):
            return False
        # This performs the existing fresh online verification, with its existing
        # signed outage fallback only. Explicit denials still propagate.
        authorization = self._gate.authorize_run()
        if not isinstance(authorization, LicenseAuthorization):
            return False
        if action == "download" and authorization.is_offline_grace:
            return False
        return allows_package(authorization, module_id)
