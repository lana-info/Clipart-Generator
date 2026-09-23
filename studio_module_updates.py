"""Licensed module delivery using the existing signed update transport."""
from __future__ import annotations

from dataclasses import dataclass

from studio_module_lifecycle import ModuleLifecycleService
from studio_modules import MAX_PACKAGE_BYTES, ModulePackageError, _identifier, _version
from update_client import UpdateClient, UpdateError, UpdateRelease


@dataclass(frozen=True)
class ModuleRelease(UpdateRelease):
    module_id: str = ""
    studio_min: str = ""
    studio_max_exclusive: str = ""


@dataclass(frozen=True)
class WorkflowUpdate:
    """One user-facing update action, optionally including the shared engine."""
    module_id: str
    workflow: ModuleRelease | None
    processing: ModuleRelease

    def __post_init__(self):
        from studio_processing_api import PROCESSING_CONSUMERS, PROCESSING_COMPONENT_ID
        if (self.module_id not in PROCESSING_CONSUMERS
                or not isinstance(self.processing, ModuleRelease)
                or self.processing.module_id != PROCESSING_COMPONENT_ID
                or (self.workflow is not None and (not isinstance(self.workflow, ModuleRelease)
                    or self.workflow.module_id != self.module_id))):
            raise ValueError('Invalid workflow update identity')

    @property
    def version(self):
        return self.workflow.version if self.workflow else self.processing.version


def update_identity(release):
    if isinstance(release, WorkflowUpdate):
        return (release.module_id, update_identity(release.workflow) if release.workflow else None,
                update_identity(release.processing))
    return tuple(getattr(release, name) for name in
                 ('module_id', 'version', 'sha256', 'size', 'studio_min', 'studio_max_exclusive'))


class ModuleUpdateClient(UpdateClient):
    """Module and shell versions are independent, including on Windows."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._artifact_suffix = ".zip"
        self._artifact_mime = "application/zip"
        self._artifact_max_bytes = MAX_PACKAGE_BYTES

    def check_module(self, module_id: str, installed_version: str | None = None) -> ModuleRelease | None:
        _identifier(module_id)
        current = _version(installed_version) if installed_version is not None else None
        payload = self._request_manifest("/api/v1/modules/manifest", {"module_id": module_id})
        if payload.get("protocol") != "studio-module-releases-v1" or payload.get("module_id") != module_id:
            raise UpdateError("Module manifest does not match the request")
        candidates = []
        for item in payload["releases"]:
            base = self._parse_release(item, payload["correlation_id"])
            if item.get("module_id") != module_id:
                raise UpdateError("Module release identity mismatch")
            try:
                lower, upper = _version(item.get("studio_min")), _version(item.get("studio_max_exclusive"))
                version = _version(base.version)
                if lower >= upper:
                    raise ModulePackageError("Invalid compatibility range")
            except ModulePackageError as exc:
                raise UpdateError("Invalid module release compatibility") from exc
            if lower <= _version(self.current_version) < upper and (current is None or version > current):
                candidates.append(ModuleRelease(
                    **vars(base), module_id=module_id,
                    studio_min=item["studio_min"], studio_max_exclusive=item["studio_max_exclusive"],
                ))
        return max(candidates, key=lambda item: _version(item.version), default=None)

    def install_release(self, release: ModuleRelease, lifecycle: ModuleLifecycleService,
                        *, cancelled=None, progress=None, phase=None) -> dict:
        """Download and stage only; activation stays on the runtime owner thread."""
        if not isinstance(release, ModuleRelease):
            raise UpdateError("Expected a module release")
        _identifier(release.module_id)
        # Validate even manually constructed release objects before using the filename.
        self._parse_release({**vars(release), "platform": self.platform_id, "channel": "stable"}, "")
        package = self.download(release, cancelled=cancelled, progress=progress)
        try:
            if cancelled is not None and cancelled():
                raise UpdateError("Module download cancelled")
            if phase is not None:
                phase("verifying")
            manifest = lifecycle.store.inspect_package(package)
            if (manifest["studio_min"] != release.studio_min
                    or manifest["studio_max_exclusive"] != release.studio_max_exclusive):
                raise ModulePackageError("Package compatibility differs from the selected release")
            if cancelled is not None and cancelled():
                raise UpdateError("Module download cancelled")
            return lifecycle.stage_package(package, expected_module_id=release.module_id,
                                           expected_version=release.version)
        finally:
            package.unlink(missing_ok=True)
