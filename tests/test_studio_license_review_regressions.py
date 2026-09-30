"""Signed license/store regressions from the Studio 3.2.10 review."""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest
import rfc8785
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from license_client import LicenseClient, LicenseError
from studio_module_access import ModuleAccessPolicy
from studio_module_packaging import prepare_module_release
from studio_module_update_ui import ModuleUpdateWorker
from studio_module_updates import ModuleRelease
from studio_modules import ModulePackageError, ModuleStore, canonical_manifest
from tests.test_license_client_security import FakeOpener, SignedLicenseResponder
from v3_license import OnlineLicenseGate


def encoded(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@pytest.fixture
def signed_client(tmp_path):
    key = Ed25519PrivateKey.generate()

    def create():
        return LicenseClient(base_url="https://license.example", product_id="clipart-generator",
                             state_path=str(tmp_path / "license-state.json"),
                             public_keys={"test": encoded(key.public_key().public_bytes_raw())})

    now = datetime.now(timezone.utc)
    grants = {"schema_version": 1, "grants": [{
        "module_id": "processing", "not_before": (now - timedelta(days=1)).isoformat(),
        "expires_at": (now + timedelta(days=7)).isoformat(),
    }]}
    responder = SignedLicenseResponder(key, kid="test", mutate_payload=lambda payload:
                                       payload.update(module_entitlements=grants))
    client = create()
    with patch("license_client.request.build_opener", return_value=FakeOpener(responder)):
        client.activate("ephemeral-fixture")
    assert client._state.load()["offline_authorization"] is not None
    return client, create, responder


@pytest.mark.parametrize("restart", [False, True])
def test_validate_rejection_cannot_restore_module_rights_on_later_outage(signed_client, restart):
    client, create, responder = signed_client
    gate = OnlineLicenseGate(client)
    denied = HTTPError("https://license.example/api/v1/licenses/validate", 403, "fixture", {}, None)
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=denied)):
        with pytest.raises(LicenseError) as raised:
            gate.authorize_run()
    assert raised.value.code == "license_rejected"
    assert gate.current_authorization is None
    if restart:
        gate = OnlineLicenseGate(create())
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=TimeoutError("fixture"))):
        with pytest.raises(LicenseError):
            ModuleAccessPolicy(gate)("processing", "load")
    assert gate.current_authorization is None
    state = create()._state.load()
    assert state["license_id"] == client._state.load()["license_id"]
    assert state["offline_authorization"] is None
    # Only a fresh, signed success restores offline rights.
    with patch("license_client.request.build_opener", return_value=FakeOpener(responder)):
        assert ModuleAccessPolicy(gate)("processing", "load")
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=TimeoutError("fixture"))):
        assert ModuleAccessPolicy(OnlineLicenseGate(create()))("processing", "load")


def test_module_endpoint_rejection_does_not_invalidate_valid_license_cache(signed_client):
    client, create, _ = signed_client
    denied = HTTPError("https://license.example/api/v1/modules/check", 403, "fixture", {}, None)
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=denied)):
        with pytest.raises(LicenseError):
            client.authenticated_request("/api/v1/modules/check")
    assert create().authorize_offline_grace().allows_module("processing")


def test_validate_rejection_blocks_same_client_grace_when_cache_cannot_be_written(signed_client):
    client, _, responder = signed_client
    gate = OnlineLicenseGate(client)
    denied = HTTPError("https://license.example/api/v1/licenses/validate", 403, "fixture", {}, None)
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=denied)), \
            patch.object(client._state, "save_activation", side_effect=OSError("fixture read-only store")):
        with pytest.raises(LicenseError):
            gate.authorize_run()
    # The failed write left the original signed record on disk.
    assert client._state.load()["offline_authorization"] is not None
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=TimeoutError("fixture"))):
        with pytest.raises(LicenseError):
            ModuleAccessPolicy(gate)("processing", "load")
    assert gate.current_authorization is None
    # A fresh signed success, after writes recover, can restore offline access.
    with patch("license_client.request.build_opener", return_value=FakeOpener(responder)):
        assert ModuleAccessPolicy(gate)("processing", "load")
    with patch("license_client.request.build_opener", return_value=FakeOpener(failure=TimeoutError("fixture"))):
        assert ModuleAccessPolicy(gate)("processing", "load")


@pytest.fixture
def upgraded_store(tmp_path):
    key = Ed25519PrivateKey.generate()
    trust = {"test": key.public_key().public_bytes_raw()}

    def package(version, lower, upper):
        data = prepare_module_release(module_id="processing", version=version,
            studio_min=lower, studio_max_exclusive=upper, platforms=["windows-x64"],
            entrypoint="entry.py", files={"entry.py": b"# signed fixture, never executed\n"},
            key_id="test", private_key=key)
        path = tmp_path / (version + ".zip")
        path.write_bytes(data)
        return path

    old = ModuleStore(tmp_path / "store", studio_version="3.2.10", platform="windows-x64", trusted_keys=trust)
    old.install(package("1.5.1", "3.2.0", "3.3.0"))
    old.activate("processing", "1.5.1")
    new = ModuleStore(tmp_path / "store", studio_version="3.3.0", platform="windows-x64", trusted_keys=trust)
    latest = package("1.6.0", "3.3.0", "4.0.0")
    new.install(latest)
    new.activate("processing", "1.6.0")
    return new, latest


def test_inventory_and_uninstall_retained_history_after_core_upgrade(upgraded_store, tmp_path):
    store, _ = upgraded_store
    user_data = tmp_path / "project.png"
    user_data.write_bytes(b"fixture user artwork")
    assert store.verified_active_path("processing").name == "1.6.0"
    assert store.installed_versions("processing") == ("1.5.1", "1.6.0")
    with pytest.raises(ModulePackageError, match="Incompatible Studio"):
        store.rollback("processing")
    assert store.state("processing")["active"] == "1.6.0"
    store.uninstall("processing")
    assert store.installed_versions("processing") == ()
    assert store.state("processing") == {"active": None, "previous": None, "enabled": False}
    assert user_data.read_bytes() == b"fixture user artwork"


def test_update_retry_uses_compatible_staged_package_despite_old_history(upgraded_store):
    store, latest = upgraded_store
    content = latest.read_bytes()
    release = ModuleRelease("1.6.0", "processing.zip", len(content), hashlib.sha256(content).hexdigest(),
                            "https://license.example/downloads/fixture", module_id="processing",
                            studio_min="3.3.0", studio_max_exclusive="4.0.0")
    delivery = Mock()
    delivery.store = store
    delivery.check.return_value = release
    worker = ModuleUpdateWorker(delivery, release)
    worker.run()
    assert not worker.failed
    assert worker.result == {"module_id": "processing", "version": "1.6.0"}
    delivery.install.assert_not_called()


@pytest.mark.parametrize("damage", ["hash", "signature", "identity", "symlink"])
def test_inventory_keeps_integrity_checks_for_incompatible_history(upgraded_store, damage):
    store, _ = upgraded_store
    state_path = store.root / "processing" / "active.json"
    original_state = state_path.read_bytes()
    old = store.root / "processing" / "1.5.1"
    if damage == "hash":
        (old / "entry.py").write_bytes(b"tampered")
    elif damage == "signature":
        (old / "signature.json").write_text('{}')
    elif damage == "identity":
        old.rename(old.with_name("1.5.2"))
    else:
        (old / "link").symlink_to(old / "entry.py")
    with pytest.raises(ModulePackageError):
        store.installed_versions("processing")
    with pytest.raises(ModulePackageError):
        store.uninstall("processing")
    assert state_path.read_bytes() == original_state
    assert json.loads(original_state)["active"] == "1.6.0"


@pytest.mark.parametrize("lower,upper", [("3.3.0", "3.3.0"), ("4.0.0", "3.2.0")])
def test_inventory_rejects_signed_empty_or_inverted_studio_range(upgraded_store, lower, upper):
    store, _ = upgraded_store
    old = store.root / "processing" / "1.5.1"
    manifest = json.loads((old / "manifest.json").read_text())
    manifest.update(studio_min=lower, studio_max_exclusive=upper)
    key = Ed25519PrivateKey.generate()
    store.trusted_keys["range-fixture"] = key.public_key().public_bytes_raw()
    (old / "manifest.json").write_text(json.dumps(manifest))
    (old / "signature.json").write_text(json.dumps({"key_id": "range-fixture", "signature":
        base64.b64encode(key.sign(canonical_manifest(manifest))).decode("ascii")}))
    with pytest.raises(ModulePackageError, match="Invalid Studio version range"):
        store.installed_versions("processing")


@pytest.mark.parametrize("skew", [120, 300])
def test_signed_module_rights_accept_bounded_authorization_clock_skew(tmp_path, skew):
    key = Ed25519PrivateKey.generate()
    now = datetime.now(timezone.utc)
    client = LicenseClient(base_url="https://license.example", product_id="clipart-generator",
                           state_path=str(tmp_path / "license-state.json"),
                           public_keys={"test": encoded(key.public_key().public_bytes_raw())})
    grant_start = now - timedelta(days=1)
    grant_end = now + timedelta(minutes=10)
    payload = {"license_id": "fixture", "product_id": client.product_id, "device_key": "device",
               "nonce": "nonce", "issued_at": (now + timedelta(seconds=skew)).isoformat(),
               "expires_at": (now + timedelta(minutes=15)).isoformat(),
               "module_entitlements": {"schema_version": 1, "grants": [{
                   "module_id": "processing", "not_before": grant_start.isoformat(),
                   "expires_at": grant_end.isoformat(),
               }]}}

    def verify():
        envelope = {"schema_version": 1, "algorithm": "Ed25519", "kid": "test", "payload": payload,
                    "signature": encoded(key.sign(rfc8785.dumps(payload)))}
        return client._verify_authorization(envelope, "device", "nonce", now=now)

    authorization = verify()
    assert authorization.allows_module("processing", now=now)
    earliest = authorization.issued_at - timedelta(seconds=300)
    assert authorization.allows_module("processing", now=earliest)
    assert not authorization.allows_module("processing", now=earliest - timedelta(microseconds=1))
    assert not authorization.allows_module("processing", now=now - timedelta(seconds=301))
    assert not authorization.allows_module("processing", now=grant_start - timedelta(microseconds=1))
    assert not authorization.allows_module("processing", now=grant_end)
    assert not authorization.allows_module("processing", now=authorization.expires_at)
    assert not authorization.allows_module("processing", now=now.replace(tzinfo=None))
    payload["issued_at"] = (now + timedelta(seconds=301)).isoformat()
    with pytest.raises(LicenseError, match="Время выдачи"):
        verify()


def test_signed_clock_skew_is_preserved_when_offline_grace_reuses_authorization(signed_client):
    client, create, responder = signed_client
    now = datetime.now(timezone.utc)
    add_grants = responder.mutate_payload

    def future_issued(payload):
        add_grants(payload)
        payload["issued_at"] = (now + timedelta(seconds=120)).isoformat()

    responder.mutate_payload = future_issued
    with patch("license_client.request.build_opener", return_value=FakeOpener(responder)):
        online = client.validate()
    assert online.allows_module("processing", now=now)
    offline = create().authorize_offline_grace(now=now)
    assert offline.is_offline_grace
    assert offline.allows_module("processing", now=now)
    assert not offline.allows_module("processing", now=offline.grace_expires_at)
