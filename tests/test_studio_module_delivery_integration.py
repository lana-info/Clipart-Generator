"""Real local HTTPS + signed packages + Qt controllers, without paid operations.

Run with LICENSE_SERVICE_SOURCE pointing to the matching service checkout's src.
Only ephemeral keys, licenses, artifacts and the loopback server are used.
"""
import base64
import io
import ipaddress
import os
import ssl
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import request
from unittest.mock import Mock

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
from cryptography.x509.oid import NameOID
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from license_client import LicenseClient
from studio_module_delivery import StudioModuleDelivery
from studio_module_packaging import prepare_official_workflow_release
from studio_module_api import ModuleApiError
from studio_modules import ModulePackageError
from update_client import UpdateError
from v3_license import OnlineLicenseGate
from v3_mode_selection import V3ApplicationView
from v3_project_state import ProjectMode

pytestmark = pytest.mark.network


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    source = os.environ.get("LICENSE_SERVICE_SOURCE")
    if not source:
        pytest.skip("Set LICENSE_SERVICE_SOURCE to the matching service src directory")
    monkeypatch.syspath_prepend(source)
    from license_service.http_server import create_staging_api, make_server
    from license_service.update_delivery import DownloadTokenStore

    monkeypatch.setenv("LICENSE_SERVICE_ARTIFACT_ROOT", str(tmp_path / "server-artifacts"))
    license_key = ed25519.Ed25519PrivateKey.generate()
    api, _ = create_staging_api(signing_key_bytes=license_key.private_bytes_raw(), artifact_min_free_bytes=0)
    service = api._service
    server = make_server(api, port=0)
    now = datetime.now(timezone.utc)
    tls_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(tls_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .sign(tls_key, hashes.SHA256()))
    cert_path, key_path = tmp_path / "test-cert.pem", tmp_path / "test-key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(tls_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_path, key_path)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    base = f"https://127.0.0.1:{server.server_port}"
    api.download_tokens = DownloadTokenStore(service, base)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    real_build_opener = request.build_opener
    trusted_tls = ssl.create_default_context(cafile=str(cert_path))
    monkeypatch.setattr(request, "build_opener", lambda *handlers: real_build_opener(
        *handlers, request.HTTPSHandler(context=trusted_tls)))
    client = LicenseClient(base_url=base, state_path=tmp_path / "license.json", product_id="clipart-generator",
                           public_keys={"license-v1": base64.b64encode(license_key.public_key().public_bytes_raw()).decode()})
    key, record = service.generate_license("clipart-generator", now - timedelta(seconds=1))
    for mode in ProjectMode:
        service.grant_module(record.license_id, mode.value, now - timedelta(seconds=1), source="purchase")
    client.activate(key)
    publisher = ed25519.Ed25519PrivateKey.generate()
    gate = OnlineLicenseGate(client)
    bridge = StudioModuleDelivery(root=tmp_path / "client-modules", studio_version="3.2.0",
                                  platform="windows-x64", license_client=client, license_gate=gate,
                                  trusted_keys={"test-publisher": publisher.public_key().public_bytes_raw()})

    def publish(module_id, version="1.0.0", **overrides):
        args = dict(source_root=Path(__file__).resolve().parents[1], module_id=module_id,
                    version=version, studio_min="3.2.0", studio_max_exclusive="4.0.0",
                    platforms=["windows-x64"], key_id="test-publisher", private_key=publisher)
        args.update(overrides)
        content = prepare_official_workflow_release(**args)
        row = service.create_release("clipart-generator", version, "stable", "windows-x64", module_id=module_id,
                                     studio_min=args["studio_min"], studio_max_exclusive=args["studio_max_exclusive"])
        service.attach_release_artifact(row["id"], io.BytesIO(content), len(content), f"{module_id}-{version}.zip")
        service.set_release_status(row["id"], "published")
        return row

    try:
        yield bridge, publish, gate, service, record
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("mode", tuple(ProjectMode))
def test_https_release_to_real_home_controller_and_independent_update(delivery, app, tmp_path, mode):
    bridge, publish, gate, service, record = delivery
    module = mode.value
    publish(module)
    first = bridge.check(module)
    assert first.version == "1.0.0"
    bridge.install(first)
    bridge.activate(module, first.version)
    workers = Mock(side_effect=AssertionError("No paid work during project opening"))
    view = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate,
                             module_delivery=bridge, worker_factory=workers)
    try:
        view.mode_selection.mode_cards[mode].start_button.click()
        controller = view.shell.workflow_controller(module)
        assert controller is not None
        assert controller.__class__.__module__.startswith("_studio_module_")
        view.project_state.common.project_name = "Preserved project"
        view.shell.mark_dirty()
        saved = view.project_state.to_dict()
        project_id = view._active_project_id
        publish(module, "1.1.0")
        second = bridge.check(module)
        bridge.install(second)
        with pytest.raises(ModuleApiError, match="active jobs or live pages"):
            bridge.activate(module, second.version)
        assert bridge.store.state(module)["active"] == "1.0.0"
        workers.assert_not_called()
    finally:
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    bridge.activate(module, "1.1.0")
    restored = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate,
                                 module_delivery=bridge, worker_factory=workers)
    try:
        assert restored.continue_saved_project(project_id)
        assert restored.project_state.to_dict() == saved
        assert restored.shell.workflow_controller(module).__class__.__module__.startswith("_studio_module_")
        assert bridge.store.state(module)["active"] == "1.1.0"
        workers.assert_not_called()
    finally:
        restored.close()
        restored.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    bridge.activate(module, "1.0.0")
    assert bridge.store.state(module)["active"] == "1.0.0"


def test_revoked_link_untrusted_key_and_wrong_identity_never_install(delivery):
    bridge, publish, _gate, service, record = delivery
    publish("pinterest")
    release = bridge.check("pinterest")
    with pytest.raises(ModulePackageError):
        bridge.install(replace(release, module_id="processing"))
    assert bridge.store.installed_versions("processing") == ()
    publish("pinterest", "1.1.0", private_key=ed25519.Ed25519PrivateKey.generate())
    with pytest.raises(ModulePackageError):
        bridge.install(bridge.check("pinterest"))
    assert bridge.store.installed_versions("pinterest") == ()
    service.revoke_module(record.license_id, "pinterest", "test revocation")
    with pytest.raises(UpdateError):
        bridge.install(release)
    with pytest.raises(UpdateError):
        bridge.check("pinterest")
    assert bridge.store.installed_versions("pinterest") == ()


def test_newer_incompatible_release_does_not_hide_compatible_version(delivery):
    bridge, publish, *_ = delivery
    publish("pinterest")
    publish("pinterest", "2.0.0", studio_min="4.0.0", studio_max_exclusive="5.0.0")
    assert bridge.check("pinterest").version == "1.0.0"


def test_revoked_installed_module_preserves_open_project(delivery, app, tmp_path, monkeypatch):
    bridge, publish, gate, service, record = delivery
    publish("pinterest")
    bridge.install(bridge.check("pinterest"))
    bridge.activate("pinterest", "1.0.0")
    view = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate, module_delivery=bridge)
    warning = Mock()
    monkeypatch.setattr("v3_mode_selection.QMessageBox.warning", warning)
    try:
        view.mode_selection.mode_cards[ProjectMode.PROCESSING].start_button.click()
        previous = view.shell
        project_id = view._active_project_id
        service.revoke_module(record.license_id, "pinterest", "test revocation")
        view.show_new_project()
        view.mode_selection.mode_cards[ProjectMode.PINTEREST].start_button.click()
        warning.assert_called_once()
        assert view.shell is previous
        assert view._active_project_id == project_id
        assert view.shell.state.mode is ProjectMode.PROCESSING
    finally:
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@pytest.mark.parametrize("mode", tuple(ProjectMode))
def test_real_update_dialog_downloads_and_opens_workflow(delivery, app, tmp_path, mode):
    bridge, publish, gate, *_ = delivery
    publish(mode.value)
    view = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate, module_delivery=bridge)
    view.show()

    def finish(dialog):
        for _ in range(1500):
            app.processEvents()
            if not dialog.busy:
                return
            QTest.qWait(10)
        pytest.fail("Module UI operation timed out")

    try:
        view.mode_selection.module_updates_button.click()
        dialog = view._module_updates_dialog
        assert dialog.isVisible()
        dialog.check_button.click()
        finish(dialog)
        assert dialog.rows[mode.value][2].isEnabled()
        dialog.rows[mode.value][2].click()
        finish(dialog)
        assert bridge.store.state(mode.value)["active"] == "1.0.0", dialog.status.text()
        assert dialog.rows[mode.value][0].text() == "1.0.0"
        dialog.close_button.click()
        view.mode_selection.mode_cards[mode].start_button.click()
        assert view.shell.workflow_controller(mode.value).__class__.__module__.startswith("_studio_module_")
    finally:
        if view._module_updates_dialog is not None:
            view._module_updates_dialog._shutdown()
            finish(view._module_updates_dialog)
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
