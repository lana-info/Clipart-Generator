from __future__ import annotations

import base64
import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from studio_module_lifecycle import ModuleLifecycleAuthorizationError, ModuleLifecycleService
from studio_module_runtime import ModuleRuntimeError, ModuleRuntimeHost
from studio_modules import ModuleStore, ModulePackageError, canonical_manifest


def _package(root, private, module_id="text-probe", version="1.0.0"):
    code = b'''from studio_module_api import ModuleRegistration\ndef register(context): return ModuleRegistration(context.module_id, context.version)\n'''
    manifest = {
        "schema_version": 1, "module_id": module_id, "version": version, "module_api": 1,
        "studio_min": "3.2.0", "studio_max_exclusive": "4.0.0", "platforms": ["test"],
        "dependencies": [], "entrypoint": "entry.py",
        "files": {"entry.py": hashlib.sha256(code).hexdigest()},
    }
    signature = {
        "key_id": "fixture",
        "signature": base64.b64encode(private.sign(canonical_manifest(manifest))).decode(),
    }
    path = Path(root) / f"{module_id}-{version}.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("signature.json", json.dumps(signature))
        archive.writestr("entry.py", code)
    return path


def _fixture(tmp_path):
    private = Ed25519PrivateKey.generate()
    store = ModuleStore(
        tmp_path / "modules", studio_version="3.2.0", platform="test",
        trusted_keys={"fixture": private.public_key().public_bytes_raw()},
    )
    rights = {"text-probe"}
    authorize = lambda module_id, action: module_id in rights and action in {"download", "activate", "load", "disable", "remove"}
    host = ModuleRuntimeHost(store, authorize)
    service = ModuleLifecycleService(store, host, authorize, lambda module_id: module_id in rights)
    return private, store, host, service, rights


def test_stage_install_is_separate_from_entitlement_activation_and_user_data(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    user_project = tmp_path / "project.json"
    user_project.write_text('{"user":"data"}', encoding="utf-8")
    package = _package(tmp_path, private)

    manifest = service.stage_package(package)
    assert manifest["module_id"] == "text-probe"
    assert store.installed_versions("text-probe") == ("1.0.0",)
    assert store.state("text-probe")["active"] is None
    assert user_project.read_text(encoding="utf-8") == '{"user":"data"}'

    rights.clear()
    with pytest.raises(ModuleLifecycleAuthorizationError):
        service.activate("text-probe", "1.0.0")
    assert store.state("text-probe")["active"] is None
    assert user_project.exists()


def test_package_is_not_written_when_download_right_is_denied(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    package = _package(tmp_path, private)
    rights.clear()
    with pytest.raises(ModuleLifecycleAuthorizationError):
        service.stage_package(package)
    assert store.installed_versions("text-probe") == ()


@pytest.mark.parametrize('identity', [
    {'expected_module_id': 'other-module'},
    {'expected_module_id': 'text-probe', 'expected_version': '2.0.0'},
])
def test_selected_release_identity_is_checked_before_install(tmp_path, identity):
    private, store, host, service, rights = _fixture(tmp_path)
    package = _package(tmp_path, private)
    with pytest.raises(ModulePackageError, match='selected release'):
        service.stage_package(package, **identity)
    assert store.installed_versions('text-probe') == ()


def test_selected_release_can_be_staged_and_activated(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    service.stage_package(_package(tmp_path, private), expected_module_id='text-probe',
                          expected_version='1.0.0')
    service.activate('text-probe', '1.0.0')
    assert host.registration('text-probe').version == '1.0.0'
    host.unload('text-probe')


def test_staged_update_can_wait_but_activation_is_blocked_by_live_job(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    service.stage_package(_package(tmp_path, private, version="1.0.0"))
    service.activate("text-probe", "1.0.0")
    lease = host.acquire_job_lease("text-probe")
    service.stage_package(_package(tmp_path, private, version="1.1.0"))
    assert store.installed_versions("text-probe") == ("1.0.0", "1.1.0")
    with pytest.raises(ModuleRuntimeError, match="active jobs"):
        service.activate("text-probe", "1.1.0")
    assert store.state("text-probe")["active"] == "1.0.0"
    lease.close()
    service.activate("text-probe", "1.1.0")
    assert store.state("text-probe")["active"] == "1.1.0"


def test_availability_keeps_entitlement_and_installation_independent(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    before = service.availability("text-probe", download_supported=True, purchase_supported=True)
    assert before.entitled is True and before.installed is False
    service.stage_package(_package(tmp_path, private))
    installed = service.availability("text-probe", open_supported=True, download_supported=True)
    assert installed.installed is True and installed.entitled is True
    assert installed.open_supported is False  # staged is not active/enabled
    service.activate("text-probe", "1.0.0")
    active = service.availability("text-probe", open_supported=True)
    assert active.open_supported is True
    rights.clear()
    revoked = service.availability("text-probe", open_supported=True, purchase_supported=True)
    assert revoked.installed is True and revoked.entitled is False
    assert revoked.open_supported is False


def test_disable_waits_for_live_job_and_never_deletes_user_data(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    project = tmp_path / "projects" / "note.json"
    project.parent.mkdir()
    project.write_text('{"body":"kept"}', encoding="utf-8")
    service.stage_package(_package(tmp_path, private))
    service.activate("text-probe", "1.0.0")
    lease = host.acquire_job_lease("text-probe")
    with pytest.raises(ModuleRuntimeError, match="active jobs"):
        service.disable("text-probe")
    assert store.state("text-probe")["enabled"] is True
    assert project.read_text(encoding="utf-8") == '{"body":"kept"}'
    lease.close()
    service.disable("text-probe")
    assert store.state("text-probe")["enabled"] is False
    assert project.read_text(encoding="utf-8") == '{"body":"kept"}'


def test_disable_requires_explicit_lifecycle_authorization(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    service.stage_package(_package(tmp_path, private))
    service.activate("text-probe", "1.0.0")
    rights.clear()
    with pytest.raises(ModuleLifecycleAuthorizationError):
        service.disable("text-probe")
    assert store.state("text-probe")["enabled"] is True
    assert host.registration("text-probe") is not None


def test_uninstall_is_authorized_job_safe_and_preserves_user_data(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    project = tmp_path / "projects" / "note.json"
    asset = tmp_path / "assets" / "asset.bin"
    project.parent.mkdir()
    asset.parent.mkdir()
    project.write_text('{"body":"kept"}', encoding="utf-8")
    asset.write_bytes(b"kept")
    service.stage_package(_package(tmp_path, private, version="1.0.0"))
    service.stage_package(_package(tmp_path, private, version="1.1.0"))
    service.activate("text-probe", "1.0.0")
    lease = host.acquire_job_lease("text-probe")
    with pytest.raises(ModuleRuntimeError, match="active jobs"):
        service.uninstall("text-probe")
    assert store.installed_versions("text-probe") == ("1.0.0", "1.1.0")
    lease.close()
    service.uninstall("text-probe")
    assert store.installed_versions("text-probe") == ()
    assert store.state("text-probe") == {"active": None, "previous": None, "enabled": False}
    assert host.registration("text-probe") is None
    assert project.read_text(encoding="utf-8") == '{"body":"kept"}'
    assert asset.read_bytes() == b"kept"


def test_uninstall_denied_leaves_package_and_activation_unchanged(tmp_path):
    private, store, host, service, rights = _fixture(tmp_path)
    service.stage_package(_package(tmp_path, private))
    service.activate("text-probe", "1.0.0")
    rights.clear()
    with pytest.raises(ModuleLifecycleAuthorizationError):
        service.uninstall("text-probe")
    assert store.installed_versions("text-probe") == ("1.0.0",)
    assert store.state("text-probe")["active"] == "1.0.0"
    assert host.registration("text-probe") is not None
