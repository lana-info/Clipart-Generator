from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
import shutil

import pytest
from PIL import Image
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_client import LicenseAuthorization, ModuleEntitlement
from studio_module_delivery import StudioModuleDelivery
from studio_module_packaging import OFFICIAL_COMPONENT_FILES, prepare_official_workflow_release
from studio_module_api import ModuleApiError
from studio_modules import ModulePackageError
from studio_processing_api import ProcessingEngine
from chroma_provenance import write_receipt, load_receipt

ROOT = Path(__file__).resolve().parents[1]


def authorization(*modules):
    now = datetime.now(timezone.utc)
    return LicenseAuthorization(
        license_id="fixture", product_id="clipart-generator", device_key="fixture",
        issued_at=now, expires_at=now + timedelta(minutes=5),
        module_entitlements=tuple(ModuleEntitlement(m, now, now + timedelta(days=1)) for m in modules),
    )


@pytest.fixture
def delivery(tmp_path):
    key = Ed25519PrivateKey.generate()
    gate = Mock()
    gate.authorize_run.return_value = authorization("processing", "clipart", "auto-clipart")
    service = StudioModuleDelivery(root=tmp_path / "delivery", studio_version="3.2.3",
        platform="windows-x64", license_client=Mock(), license_gate=gate,
        trusted_keys={"fixture": key.public_key().public_bytes_raw()})
    return service, key, gate


def package(tmp_path, key, version="1.0.0", profile=None, bad=False):
    source = tmp_path / ("source-" + version)
    source.mkdir()
    for name in OFFICIAL_COMPONENT_FILES["image-processing"]:
        shutil.copyfile(ROOT / name, source / name)
    if profile:
        (source / "chroma_profile.py").write_text(f"PROFILE_VERSION = {profile!r}\n")
    if bad:
        (source / "studio_processing_engine.py").write_text("def create_engine():\n    return object()\n")
    target = tmp_path / (version + ".zip")
    target.write_bytes(prepare_official_workflow_release(
        source_root=source, module_id="image-processing", version=version,
        studio_min="3.2.3", studio_max_exclusive="4.0.0", platforms=["windows-x64"],
        key_id="fixture", private_key=key,
    ))
    return target


@pytest.mark.parametrize("consumer", ["processing", "clipart", "auto-clipart"])
def test_one_verified_component_is_used_by_each_authorized_consumer(delivery, tmp_path, consumer):
    service, key, gate = delivery
    gate.authorize_run.return_value = authorization(consumer)
    service.lifecycle.stage_package(package(tmp_path, key, profile="opaque-clipart-v10"))
    service.activate("image-processing", "1.0.0")
    lease = service.acquire_processing_engine(consumer)
    try:
        assert lease.engine.profile == "opaque-clipart-v10"
        assert lease.engine.remove_background.__module__.startswith("_studio_module_")
        source = Image.new("RGB", (48, 48), "blue")
        for x in range(14, 34):
            for y in range(14, 34):
                source.putpixel((x, y), (240, 170, 40))
        result = lease.engine.remove(source, "blue")
        assert result.getpixel((0, 0))[3] == 0
        assert result.getpixel((24, 24))[3] == 255
    finally:
        lease.close()


def test_active_job_pins_version_and_failed_activation_preserves_previous(delivery, tmp_path):
    service, key, _ = delivery
    for version, profile in (("1.0.0", "opaque-clipart-v9"), ("1.1.0", "opaque-clipart-v10")):
        service.lifecycle.stage_package(package(tmp_path, key, version, profile))
    service.activate("image-processing", "1.0.0")
    lease = service.acquire_processing_engine("processing")
    with pytest.raises(ModuleApiError):
        service.activate("image-processing", "1.1.0")
    assert service.store.state("image-processing")["active"] == "1.0.0"
    assert lease.engine.profile == "opaque-clipart-v9"
    lease.close()
    lease.close()
    service.activate("image-processing", "1.1.0")
    updated = service.acquire_processing_engine("processing")
    assert updated.engine.profile == "opaque-clipart-v10"
    updated.close()
    service.lifecycle.stage_package(package(tmp_path, key, "1.2.0", bad=True))
    with pytest.raises((ModuleApiError, ValueError)):
        service.activate("image-processing", "1.2.0")
    assert service.store.state("image-processing")["active"] == "1.1.0"
    # Explicit rollback is subject to the same idle/verification/authorization checks.
    service.activate("image-processing", "1.0.0")
    restored = service.acquire_processing_engine("processing")
    assert restored.engine.profile == "opaque-clipart-v9"
    restored.close()


def test_tampered_selected_component_never_silently_falls_back(delivery, tmp_path):
    service, key, _ = delivery
    service.lifecycle.stage_package(package(tmp_path, key))
    service.activate("image-processing", "1.0.0")
    root = service.store.verified_active_path("image-processing")
    (root / "chroma_rim.py").write_text("raise RuntimeError('not trusted')")
    with pytest.raises((ModuleApiError, ModulePackageError)):
        service.acquire_processing_engine("processing")


def test_dependency_does_not_grant_access_to_another_workflow(delivery, tmp_path):
    service, key, gate = delivery
    gate.authorize_run.return_value = authorization("processing")
    service.lifecycle.stage_package(package(tmp_path, key))
    service.activate("image-processing", "1.0.0")
    with pytest.raises(ModuleApiError):
        service.acquire_processing_engine("clipart")
    gate.authorize_run.return_value = authorization("pinterest")
    with pytest.raises(ModuleApiError):
        service.acquire_processing_engine("processing")


def test_engine_api_and_receipt_use_selected_algorithm_identity(tmp_path):
    path = tmp_path / "result.png"
    Image.new("RGBA", (4, 4)).save(path)
    write_receipt(path, source_sha256="a" * 64, requested_background="#0000FF",
                  observed_background="#0000FF", profile="opaque-clipart-v10")
    assert load_receipt(path)["profile"] == "opaque-clipart-v10"
    with pytest.raises(ValueError):
        ProcessingEngine("opaque-clipart-v10", lambda *_a, **_k: None, lambda _i: (0, 0, 255), api_version=2)
    broken = ProcessingEngine("opaque-clipart-v10", lambda *_a, **_k: Image.new("RGB", (4, 4)), lambda _i: (0, 0, 255))
    with pytest.raises(ValueError):
        broken.remove(Image.new("RGB", (4, 4)), "blue")


def test_component_only_offer_uses_existing_workflow_action(delivery, tmp_path):
    from studio_module_updates import ModuleRelease, WorkflowUpdate
    service, key, _ = delivery
    engine_release = ModuleRelease('1.1.0', 'engine.zip', 123, 'a'*64,
        'https://fixture.invalid/downloads/engine', module_id='image-processing',
        studio_min='3.2.3', studio_max_exclusive='4.0.0')
    service.updates.check_module = Mock(side_effect=lambda module, _version:
        engine_release if module == 'image-processing' else None)
    offer = service.check('processing')
    assert isinstance(offer, WorkflowUpdate)
    assert offer.module_id == 'processing' and offer.workflow is None
    service.lifecycle.stage_package(package(tmp_path, key, '1.1.0', 'opaque-clipart-v10'))
    service.activate_update(offer)
    assert service.store.state('processing')['active'] is None
    lease = service.acquire_processing_engine('processing')
    assert lease.engine.profile == 'opaque-clipart-v10'
    lease.close()


def test_group_failure_restores_engine_pointer_and_live_registration(delivery, tmp_path):
    from studio_module_packaging import prepare_module_release
    service, key, _ = delivery
    for version in ('1.0.0', '1.1.0'):
        service.lifecycle.stage_package(package(tmp_path, key, version,
            'opaque-clipart-v9' if version == '1.0.0' else 'opaque-clipart-v10'))
    service.activate('image-processing', '1.0.0')
    broken = tmp_path / 'broken-workflow.zip'
    broken.write_bytes(prepare_module_release(module_id='processing', version='2.0.0',
        studio_min='3.2.3', studio_max_exclusive='4.0.0', platforms=['windows-x64'],
        entrypoint='entry.py', files={'entry.py':b'def register(context):\n    raise ValueError("bad API")\n'},
        key_id='fixture', private_key=key))
    service.lifecycle.stage_package(broken)
    with pytest.raises((ValueError, ModuleApiError)):
        service.host.activate_many({'image-processing':'1.1.0','processing':'2.0.0'})
    assert service.store.state('image-processing')['active'] == '1.0.0'
    assert service.store.state('processing')['active'] is None
    lease = service.acquire_processing_engine('processing')
    assert lease.engine.profile == 'opaque-clipart-v9'
    lease.close()


def test_worker_uses_selected_engine_not_shell_algorithm(delivery, tmp_path):
    import main
    from unittest.mock import patch
    service, key, _ = delivery
    service.lifecycle.stage_package(package(tmp_path, key, profile='opaque-clipart-v10'))
    service.activate('image-processing', '1.0.0')
    lease = service.acquire_processing_engine('processing')
    raw = tmp_path / 'raw'
    raw.mkdir()
    source = tmp_path / 'source.png'
    image = Image.new('RGB', (48, 48), 'blue')
    image.paste((240, 160, 20), (12, 12, 36, 36))
    image.save(source)
    worker = main.WorkerThread('mode2_process', str(tmp_path),
        {'remove_bg':True, 'remove_bg_provider':'local_chroma_key', 'chroma_key_color':'blue',
         'upscale':False, 'unsharp_enabled':False, 'trim_enabled':False, 'export_300_dpi':False},
        processing_engine=lease.engine)
    try:
        with patch.object(main, 'remove_chroma_key_automatic', side_effect=AssertionError('shell keyer used')):
            result = worker._run_processing_pipeline(str(source), None, str(raw), 1, 'file')
        with Image.open(result) as output:
            assert output.getpixel((0, 0))[3] == 0
        assert worker._item_context.chroma_receipt['profile'] == 'opaque-clipart-v10'
    finally:
        lease.close()
