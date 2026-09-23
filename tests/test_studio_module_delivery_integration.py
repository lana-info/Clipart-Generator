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
    server = make_server(api, port=0, admin=api.admin_service)
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
    service.grant_module(record.license_id, "auto-clipart", now - timedelta(seconds=1), source="purchase")
    client.activate(key)
    publisher = ed25519.Ed25519PrivateKey.generate()
    gate = OnlineLicenseGate(client)
    bridge = StudioModuleDelivery(root=tmp_path / "client-modules", studio_version="3.2.0",
                                  platform="windows-x64", license_client=client, license_gate=gate,
                                  trusted_keys={"test-publisher": publisher.public_key().public_bytes_raw()})
    # Expose only ephemeral fixture objects for the real administrative upload test.
    bridge.test_admin = api.admin_service
    bridge.test_service_url = base
    bridge.test_publisher = publisher

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


@pytest.mark.parametrize("module_id", ["clipart", "processing", "pinterest", "auto-clipart"])
def test_publisher_https_admin_draft_then_licensed_install(delivery, tmp_path, module_id):
    from license_service.admin import current_totp
    from studio_module_release import AdminDraftUploader

    bridge, _publish, _gate, service, _record = delivery
    bootstrap = bridge.test_admin.bootstrap("fixture-admin-password-only")
    secret = base64.b32decode(bootstrap.totp_secret_base32 + "=" * (-len(bootstrap.totp_secret_base32) % 8))
    uploader = AdminDraftUploader(bridge.test_service_url)
    uploader.login("admin", "fixture-admin-password-only", current_totp(secret))
    package = tmp_path / "official.zip"
    package.write_bytes(prepare_official_workflow_release(
        source_root=Path(__file__).resolve().parents[1], module_id=module_id, version="1.0.0",
        studio_min="3.2.0", studio_max_exclusive="3.3.0", platforms=["windows-x64"],
        key_id="test-publisher", private_key=bridge.test_publisher))
    try:
        receipt = uploader.upload(package, product_id="clipart-generator", platform="windows-x64",
            studio_version="3.2.0", trusted_keys=bridge.store.trusted_keys)
        assert receipt["status"] == "draft"
        assert bridge.check(module_id) is None
        service.set_release_status(receipt["draft_id"], "published")
        release = bridge.check(module_id)
        assert release.version == "1.0.0"
        bridge.install(release)
        bridge.activate(module_id, release.version)
        assert bridge.has_active_workflow(module_id)
    finally:
        uploader.close()


@pytest.mark.parametrize("mode", (*ProjectMode, "auto-clipart"))
def test_https_release_to_real_home_controller_and_independent_update(delivery, app, tmp_path, mode):
    bridge, publish, gate, service, record = delivery
    module = mode.value if isinstance(mode, ProjectMode) else mode
    publish(module)
    first = bridge.check(module)
    assert first.version == "1.0.0"
    bridge.install(first)
    bridge.activate(module, first.version)
    workers = Mock(side_effect=AssertionError("No paid work during project opening"))
    view = V3ApplicationView(draft_path=tmp_path / "draft.json", license_gate=gate,
                             module_delivery=bridge, worker_factory=workers)
    try:
        if module == "auto-clipart":
            view.mode_selection.module_cards[module].start_button.click()
        else:
            view.mode_selection.mode_cards[mode].start_button.click()
        controller = view.shell.workflow_controller(module)
        assert controller is not None
        assert controller.__class__.__module__.startswith("_studio_module_")
        if module == "auto-clipart":
            import sys
            from studio_clipart_recipe import ClipartRecipe
            from studio_clipart_objects import fill_recipe
            assert controller.brief.planning.__class__.__module__.startswith('_studio_module_')
            planning_ui = sys.modules[controller.brief.planning.__class__.__module__]
            assert planning_ui.planning_request.__module__.startswith('_studio_module_')
            recipe = ClipartRecipe(theme='Package-local prompt rules')
            recipe.objects = fill_recipe([], recipe.counts)
            # Changing the shell's guidance cannot override package-owned rules.
            from unittest.mock import patch
            with patch('studio_commercial_prompt_guidance.commercial_planning_hints', side_effect=AssertionError('shell guidance used')):
                assert planning_ui.planning_request(recipe)['commercial']['detail_policy']
            controller.brief.project_name.setText("Preserved project")
        else:
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


@pytest.mark.parametrize("module", ["pinterest", "auto-clipart"])
def test_revoked_link_untrusted_key_and_wrong_identity_never_install(delivery, module):
    bridge, publish, _gate, service, record = delivery
    publish(module)
    release = bridge.check(module)
    with pytest.raises(ModulePackageError):
        bridge.install(replace(release, module_id="processing"))
    assert bridge.store.installed_versions("processing") == ()
    publish(module, "1.1.0", private_key=ed25519.Ed25519PrivateKey.generate())
    with pytest.raises(ModulePackageError):
        bridge.install(bridge.check(module))
    assert bridge.store.installed_versions(module) == ()
    service.revoke_module(record.license_id, module, "test revocation")
    with pytest.raises(UpdateError):
        bridge.install(release)
    with pytest.raises(UpdateError):
        bridge.check(module)
    assert bridge.store.installed_versions(module) == ()


def test_newer_incompatible_release_does_not_hide_compatible_version(delivery):
    bridge, publish, *_ = delivery
    publish("pinterest")
    publish("pinterest", "2.0.0", studio_min="4.0.0", studio_max_exclusive="5.0.0")
    assert bridge.check("pinterest").version == "1.0.0"


def test_shared_engine_only_update_and_signed_news_over_real_https(delivery):
    from studio_module_updates import WorkflowUpdate
    bridge, publish, _gate, service, _record = delivery
    publish('image-processing')
    offer = bridge.check('processing')
    assert isinstance(offer, WorkflowUpdate) and offer.workflow is None
    bridge.install(offer)
    bridge.activate_update(offer)
    assert bridge.store.state('processing')['active'] is None
    lease = bridge.acquire_processing_engine('processing')
    assert lease.engine.remove_background.__module__.startswith('_studio_module_')
    publish('image-processing', '1.1.0')
    update = bridge.check('clipart')
    bridge.install(update)
    with pytest.raises(ModuleApiError):
        bridge.activate_update(update)
    assert bridge.store.state('image-processing')['active'] == '1.0.0'
    lease.close()
    bridge.activate_update(update)
    assert bridge.store.state('image-processing')['active'] == '1.1.0'
    assert bridge.check('processing') is None
    draft = service.news.save('Independent announcement', 'No module release is required.')
    assert bridge.news.fetch() == []
    published = service.news.set_status(draft['id'], 'published', draft['revision'])
    assert bridge.news.fetch()[0]['title'] == 'Independent announcement'
    assert bridge.news.cached()[0]['body'] == 'No module release is required.'
    service.news.set_status(draft['id'], 'withdrawn', published['revision'])
    assert bridge.news.fetch() == [] and bridge.news.cached() == []


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


@pytest.mark.parametrize("mode", (*ProjectMode, "auto-clipart"))
def test_real_update_dialog_downloads_and_opens_workflow(delivery, app, tmp_path, mode):
    bridge, publish, gate, *_ = delivery
    module = mode.value if isinstance(mode, ProjectMode) else mode
    publish(module)
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
        assert dialog.rows[module][2].isEnabled()
        dialog.rows[module][2].click()
        finish(dialog)
        assert bridge.store.state(module)["active"] == "1.0.0", dialog.status.text()
        assert dialog.rows[module][0].text() == "1.0.0"
        dialog.close_button.click()
        if module == "auto-clipart":
            view.mode_selection.module_cards[module].start_button.click()
        else:
            view.mode_selection.mode_cards[mode].start_button.click()
        assert view.shell.workflow_controller(module).__class__.__module__.startswith("_studio_module_")
    finally:
        if view._module_updates_dialog is not None:
            view._module_updates_dialog._shutdown()
            finish(view._module_updates_dialog)
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
