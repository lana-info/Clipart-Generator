"""Application composition for verified, independently versioned workflows."""
import base64
from pathlib import Path

from studio_module_access import ModuleAccessPolicy
from studio_module_api import ModuleApiError
from studio_module_lifecycle import ModuleLifecycleService
from studio_module_runtime import ModuleRuntimeHost, CapabilityBroker, CapabilityProvider
from studio_processing_api import (
    PROCESSING_COMPONENT_ID, PROCESSING_CONSUMERS, PROCESSING_CAPABILITY,
    ProcessingEngine, ProcessingEngineLease,
)
from studio_module_updates import ModuleUpdateClient, WorkflowUpdate
from studio_modules import ModuleStore


# Pinned by the controlled shell release, never supplied by a downloaded package.
OFFICIAL_PUBLISHER_KEYS: dict[str, bytes] = {
    "vibix-publisher-v1": base64.b64decode("sUMfFDeHQIpSFmUCNbZJb+Ts4jMkiWy4CUcNhVO19v0="),
}
EXISTING_WORKFLOW_IDS = frozenset({"clipart", "processing", "pinterest", "auto-clipart"})
DELIVERABLE_IDS = EXISTING_WORKFLOW_IDS | {PROCESSING_COMPONENT_ID}


class StudioModuleDelivery:
    def __init__(self, *, root: Path, studio_version: str, platform: str,
                 license_client, license_gate, trusted_keys=None):
        keys = OFFICIAL_PUBLISHER_KEYS if trusted_keys is None else trusted_keys
        self.store = ModuleStore(Path(root) / "packages", studio_version=studio_version,
                                 platform=platform, trusted_keys=keys)
        policy = ModuleAccessPolicy(license_gate)
        self._policy = policy
        self.host = ModuleRuntimeHost(self.store, policy, capability_broker=CapabilityBroker((
            CapabilityProvider(PROCESSING_CAPABILITY, lambda _module: PROCESSING_CAPABILITY),
        )))
        self.lifecycle = ModuleLifecycleService(self.store, self.host, policy,
                                                lambda module: policy(module, "load"))
        self.updates = ModuleUpdateClient(license_client, current_version=studio_version,
                                         platform_id=platform, download_directory=Path(root) / "downloads")
        from studio_news import StudioNewsClient
        self.news = StudioNewsClient(self.updates, Path(root) / "studio-news.json")

    def check(self, module_id):
        if module_id not in DELIVERABLE_IDS or not self.store.trusted_keys:
            return None
        release = self.updates.check_module(module_id, self.store.state(module_id)["active"])
        if module_id in PROCESSING_CONSUMERS:
            processing = self.updates.check_module(
                PROCESSING_COMPONENT_ID, self.store.state(PROCESSING_COMPONENT_ID)["active"])
            if processing is not None:
                return WorkflowUpdate(module_id, release, processing)
        return release

    def install(self, release, **callbacks):
        if release.module_id not in DELIVERABLE_IDS:
            raise ValueError("Workflow is not released")
        if isinstance(release, WorkflowUpdate):
            for item in (release.processing, release.workflow):
                if item is None:
                    continue
                if item.version not in self.store.installed_versions(item.module_id):
                    self.updates.install_release(item, self.lifecycle, **callbacks)
            return {"module_id": release.module_id, "version": release.version}
        return self.updates.install_release(release, self.lifecycle, **callbacks)

    def activate_update(self, release: WorkflowUpdate):
        versions = {PROCESSING_COMPONENT_ID: release.processing.version}
        if release.workflow is not None:
            versions[release.module_id] = release.workflow.version
        if self._policy(release.module_id, "activate") is not True:
            raise ModuleApiError("Workflow update is not authorized")
        self.host.activate_many(versions)

    def activate(self, module_id, version):
        return self.lifecycle.activate(module_id, version)

    def acquire_processing_engine(self, consumer):
        """Select once on the owner thread; pin package code until job completion.

        No selected package means the shipped implementation. A selected but
        damaged or incompatible package is an error, never a silent fallback.
        """
        if consumer not in PROCESSING_CONSUMERS or self._policy(consumer, "load") is not True:
            raise ModuleApiError("Processing consumer is not authorized")
        state = self.store.state(PROCESSING_COMPONENT_ID)
        if not state["enabled"] or not state["active"]:
            from studio_processing_engine import create_engine
            return ProcessingEngineLease(create_engine())
        if self.host.registration(PROCESSING_COMPONENT_ID) is None:
            self.host.load_active(PROCESSING_COMPONENT_ID)
        engine = self.host.invoke_command(PROCESSING_COMPONENT_ID, "engine")
        if not isinstance(engine, ProcessingEngine):
            raise ModuleApiError("Unsupported image-processing component")
        return ProcessingEngineLease(engine, self.host.acquire_job_lease(PROCESSING_COMPONENT_ID))

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
