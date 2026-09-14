"""Authorized desktop lifecycle over the existing signed ModuleStore/RuntimeHost."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from studio_catalog import ModuleAvailability
from studio_module_runtime import ModuleRuntimeHost
from studio_modules import ModuleStore


class ModuleLifecycleAuthorizationError(PermissionError):
    pass


class ModuleLifecycleService:
    """Keep entitlement, installed package state, and user data as separate concerns."""

    __slots__ = ("store", "host", "_authorize", "_entitled")

    def __init__(
        self,
        store: ModuleStore,
        host: ModuleRuntimeHost,
        authorize: Callable[[str, str], bool],
        entitled: Callable[[str], bool],
    ) -> None:
        if not isinstance(store, ModuleStore) or not isinstance(host, ModuleRuntimeHost):
            raise TypeError("ModuleLifecycleService requires ModuleStore and ModuleRuntimeHost")
        if not callable(authorize) or not callable(entitled):
            raise TypeError("Lifecycle authorization callbacks must be callable")
        self.store = store
        self.host = host
        self._authorize = authorize
        self._entitled = entitled

    def _allowed(self, module_id: str, action: str) -> None:
        if self._authorize(module_id, action) is not True:
            raise ModuleLifecycleAuthorizationError("Module lifecycle operation is not authorized")

    def stage_package(self, package: str | Path) -> dict:
        """Verify first, authorize the identified module, then stage without activation."""
        manifest = self.store.inspect_package(Path(package))
        module_id = manifest["module_id"]
        self._allowed(module_id, "download")
        # Reverify on install so a package changed after inspection cannot bypass trust checks.
        return self.store.install(
            Path(package), expected_module_id=module_id, expected_version=manifest["version"],
        )

    def activate(self, module_id: str, version: str):
        self._allowed(module_id, "activate")
        if self._entitled(module_id) is not True:
            raise ModuleLifecycleAuthorizationError("Module entitlement is not active")
        return self.host.activate(module_id, version)

    def disable(self, module_id: str) -> None:
        """Disable executable package state only; user projects/assets are outside ModuleStore."""
        self._allowed(module_id, "disable")
        if self.host.registration(module_id) is not None:
            self.host.unload(module_id)
        self.store.disable(module_id, busy=False)

    def uninstall(self, module_id: str) -> None:
        """Remove installed package inventory only; never touch projects or assets."""
        self._allowed(module_id, "remove")
        if self.host.registration(module_id) is not None:
            self.host.unload(module_id)
        self.store.uninstall(module_id, busy=False)

    def availability(
        self,
        module_id: str,
        *,
        open_supported: bool = False,
        download_supported: bool = False,
        purchase_supported: bool = False,
        update_available: bool = False,
    ) -> ModuleAvailability:
        versions = self.store.installed_versions(module_id)
        state = self.store.state(module_id)
        installed = bool(versions)
        entitled = self._entitled(module_id) is True
        active_enabled = bool(state["enabled"] and state["active"])
        return ModuleAvailability(
            installed=installed,
            entitled=entitled,
            compatible=True,
            update_available=bool(update_available),
            open_supported=bool(open_supported and installed and entitled and active_enabled),
            download_supported=bool(download_supported and entitled),
            purchase_supported=bool(purchase_supported),
        )
