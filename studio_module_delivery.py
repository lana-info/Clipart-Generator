"""Application composition for verified, independently versioned workflows."""
import base64
from pathlib import Path

from studio_module_access import ModuleAccessPolicy
from studio_module_api import ModuleApiError
from studio_module_lifecycle import ModuleLifecycleService
from studio_module_runtime import ModuleRuntimeHost
from studio_module_updates import ModuleUpdateClient
from studio_modules import ModuleStore


# Pinned by the controlled shell release, never supplied by a downloaded package.
OFFICIAL_PUBLISHER_KEYS: dict[str, bytes] = {
    "vibix-publisher-v1": base64.b64decode("sUMfFDeHQIpSFmUCNbZJb+Ts4jMkiWy4CUcNhVO19v0="),
}
EXISTING_WORKFLOW_IDS = frozenset({"clipart", "processing", "pinterest", "auto-clipart"})


class StudioModuleDelivery:
    def __init__(self, *, root: Path, studio_version: str, platform: str,
                 license_client, license_gate, trusted_keys=None):
        keys = OFFICIAL_PUBLISHER_KEYS if trusted_keys is None else trusted_keys
        self.store = ModuleStore(Path(root) / "packages", studio_version=studio_version,
                                 platform=platform, trusted_keys=keys)
        policy = ModuleAccessPolicy(license_gate)
        self.host = ModuleRuntimeHost(self.store, policy)
        self.lifecycle = ModuleLifecycleService(self.store, self.host, policy,
                                                lambda module: policy(module, "load"))
        self.updates = ModuleUpdateClient(license_client, current_version=studio_version,
                                         platform_id=platform, download_directory=Path(root) / "downloads")

    def check(self, module_id):
        if module_id not in EXISTING_WORKFLOW_IDS or not self.store.trusted_keys:
            return None
        return self.updates.check_module(module_id, self.store.state(module_id)["active"])

    def install(self, release, **callbacks):
        if release.module_id not in EXISTING_WORKFLOW_IDS:
            raise ValueError("Workflow is not released")
        return self.updates.install_release(release, self.lifecycle, **callbacks)

    def activate(self, module_id, version):
        return self.lifecycle.activate(module_id, version)

    def has_active_workflow(self, module_id):
        state = self.store.state(module_id)
        return bool(state["enabled"] and state["active"])

    def install_workflow(self, module_id, workflow_host, *, locale, owner):
        if module_id not in EXISTING_WORKFLOW_IDS:
            raise ValueError("Workflow is not released")
        if self.host.registration(module_id) is None:
            self.host.load_active(module_id)
        try:
            controller = self.host.invoke_command(module_id, "install_workflow", workflow_host, locale=locale)
        except Exception as exc:
            raise ModuleApiError("Module workflow could not be opened") from exc
        # A live shell owns controllers/pages and may start background jobs later.
        # Pin the package until Qt actually destroys that shell, not merely hides it.
        lease = self.host.acquire_job_lease(module_id)
        owner.destroyed.connect(lambda _object=None: lease.close())
        return controller
