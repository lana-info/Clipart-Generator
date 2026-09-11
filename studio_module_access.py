"""Bridge the existing verified application-license gate to the module runtime.

No cached pointer, publisher signature or installed package grants module rights.
Actual package downloads must additionally be authorized by the server.
"""
from __future__ import annotations

from typing import Protocol

from license_client import LicenseAuthorization


class AuthorizationGate(Protocol):
    def authorize_run(self) -> LicenseAuthorization: ...


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
        return authorization.allows_module(module_id)
