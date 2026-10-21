import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_module_update_ui import ModuleUpdatesDialog
from studio_module_updates import ModuleRelease


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def wait_until(app, predicate):
    for _ in range(500):
        app.processEvents()
        if predicate():
            return
        QTest.qWait(10)
    pytest.fail("Qt operation did not finish")


@pytest.fixture
def setup(app):
    owner_thread = threading.get_ident()
    release = ModuleRelease("1.1.0", "fixture.zip", 20, "a" * 64, "https://fixture.invalid/downloads/x",
                            module_id="pinterest", studio_min="3.2.0", studio_max_exclusive="4.0.0")
    active = {}
    versions = []
    delivery = Mock()
    delivery.store.trusted_keys = {"fixture": b"public"}
    delivery.store.state.side_effect = lambda module: {"active": active.get(module), "enabled": module in active}
    delivery.store.installed_versions.side_effect = lambda module: tuple(versions)
    delivery.updates.current_version = "3.2.0"
    delivery.updates.license_client.validate.return_value = SimpleNamespace(allows_module=lambda module: module == "pinterest")
    delivery.check.side_effect = lambda module: release if module == "pinterest" else None

    def install(selected, **callbacks):
        assert threading.get_ident() != owner_thread
        callbacks["progress"](8, 20)
        callbacks["phase"]("verifying")
        versions.append(selected.version)
        return {"module_id": selected.module_id, "version": selected.version}

    def activate(module, version):
        assert threading.get_ident() == owner_thread
        active[module] = version

    delivery.install.side_effect = install
    delivery.activate.side_effect = activate
    dialog = ModuleUpdatesDialog(delivery)
    dialog.show()
    try:
        yield dialog, delivery, release
    finally:
        dialog._shutdown()
        wait_until(app, lambda: not dialog.busy)
        dialog.close()
        dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_check_exact_access_then_install_on_owner_thread(app, setup):
    dialog, delivery, _release = setup
    dialog.check_button.click()
    wait_until(app, lambda: not dialog.busy)
    assert dialog.rows["clipart"][1].text() == "Нет доступа"
    assert not dialog.rows["clipart"][2].isEnabled()
    assert dialog.rows["pinterest"][2].isEnabled()
    dialog.rows["pinterest"][2].click()
    wait_until(app, lambda: not dialog.busy)
    assert dialog.rows["pinterest"][0].text() == "1.1.0"
    assert not dialog.rows["pinterest"][2].isEnabled()
    delivery.activate.assert_called_once_with("pinterest", "1.1.0")


def test_progress_and_close_guard_while_worker_running(app, setup):
    dialog, delivery, _release = setup
    release_worker = threading.Event()
    phase_worker = threading.Event()
    original = delivery.install.side_effect

    def slow_install(release, **callbacks):
        callbacks["progress"](8, 20)
        phase_worker.wait(3)
        callbacks["phase"]("verifying")
        release_worker.wait(3)
        return original(release, **callbacks)

    delivery.install.side_effect = slow_install
    dialog.check()
    wait_until(app, lambda: not dialog.busy)
    dialog.download("pinterest")
    try:
        wait_until(app, lambda: dialog.progress.maximum() == 100)
        assert dialog.progress.value() == 40
        assert not dialog.close_button.isEnabled()
        dialog.close()
        assert dialog.isVisible()
        phase_worker.set()
        wait_until(app, lambda: dialog.progress.maximum() == 0)
        assert not dialog.progress.isTextVisible()
    finally:
        phase_worker.set()
        release_worker.set()
    wait_until(app, lambda: not dialog.busy)


def test_busy_project_prevents_transfer(app, setup):
    dialog, delivery, _ = setup
    dialog.busy_module = lambda module: True
    dialog.check()
    wait_until(app, lambda: not dialog.busy)
    dialog.download("pinterest")
    delivery.install.assert_not_called()
    assert "Проект открыт" in dialog.status.text()


def test_activation_retry_uses_staged_package(app, setup):
    dialog, delivery, _ = setup
    original = delivery.activate.side_effect
    delivery.activate.side_effect = RuntimeError("fixture path and token must not be shown")
    dialog.check()
    wait_until(app, lambda: not dialog.busy)
    dialog.download("pinterest")
    wait_until(app, lambda: not dialog.busy)
    assert "Текущая версия сохранена" in dialog.status.text()
    assert "token" not in dialog.status.text()
    delivery.activate.side_effect = original
    dialog.download("pinterest")
    wait_until(app, lambda: not dialog.busy)
    assert delivery.install.call_count == 1
    assert dialog.rows["pinterest"][0].text() == "1.1.0"


def test_empty_trust_set_never_contacts_server(app, setup):
    dialog, delivery, _ = setup
    delivery.store.trusted_keys = {}
    other = ModuleUpdatesDialog(delivery)
    try:
        assert not other.check_button.isEnabled()
        other.check()
        delivery.check.assert_not_called()
        assert "пока недоступны" in other.status.text()
    finally:
        other.deleteLater()


def test_failed_transfer_keeps_previous_version_and_does_not_activate(app, setup):
    dialog, delivery, _ = setup
    delivery.store.state.side_effect = lambda module: {"active": "1.0.0", "enabled": True}
    delivery.install.side_effect = ValueError("invalid signature /private/file token=secret-fixture")
    dialog.check()
    wait_until(app, lambda: not dialog.busy)
    dialog.download("pinterest")
    wait_until(app, lambda: not dialog.busy)
    delivery.activate.assert_not_called()
    assert dialog.rows["pinterest"][0].text() == "1.0.0"
    assert "secret-fixture" not in dialog.status.text()
    assert dialog.rows["pinterest"][2].isEnabled()


def test_refreshed_release_cannot_silently_change_selected_bytes(app, setup):
    from dataclasses import replace
    dialog, delivery, release = setup
    dialog.check()
    wait_until(app, lambda: not dialog.busy)
    delivery.check.side_effect = lambda module: replace(release, sha256="b" * 64)
    dialog.download("pinterest")
    wait_until(app, lambda: not dialog.busy)
    delivery.install.assert_not_called()
    delivery.activate.assert_not_called()


def test_catalog_request_checks_then_installs_only_selected_module(app, setup):
    dialog, delivery, _ = setup
    dialog.request_module('pinterest')
    wait_until(app, lambda: delivery.activate.called and not dialog.busy)
    delivery.activate.assert_called_once_with('pinterest', '1.1.0')
    assert delivery.install.call_count == 1
    assert dialog.checked['clipart'] == ('denied', None)


def test_cancel_after_staging_never_activates_package(app, setup):
    dialog, delivery, _ = setup
    started, finish = threading.Event(), threading.Event()
    original = delivery.install.side_effect

    def staged(release, **callbacks):
        result = original(release, **callbacks)
        started.set()
        finish.wait(3)
        return result

    delivery.install.side_effect = staged
    dialog.check()
    wait_until(app, lambda: not dialog.busy)
    dialog.download('pinterest')
    try:
        wait_until(app, started.is_set)
        dialog.cancel_button.click()
    finally:
        finish.set()
    wait_until(app, lambda: not dialog.busy)
    delivery.activate.assert_not_called()
    assert dialog.rows['pinterest'][0].text() == 'Не установлен'
    assert 'отменено' in dialog.status.text()
    # A new explicit attempt may use the already verified staged bytes.
    dialog.download('pinterest')
    wait_until(app, lambda: not dialog.busy)
    delivery.activate.assert_called_once_with('pinterest', '1.1.0')
    assert delivery.install.call_count == 1


@pytest.mark.parametrize('outage', [False, True])
def test_discovery_denial_invalidates_composer_but_outage_keeps_cached_right(app, tmp_path, outage):
    from datetime import datetime, timedelta, timezone
    from license_client import LicenseAuthorization, ModuleEntitlement, LicenseError, LicenseUnavailableError
    from v3_mode_selection import V3ApplicationView
    now = datetime.now(timezone.utc)
    auth = LicenseAuthorization('fixture', 'clipart-generator', 'device', now - timedelta(minutes=1),
        now + timedelta(minutes=5), module_entitlements=(ModuleEntitlement('prompt-composer', now - timedelta(minutes=1), now + timedelta(minutes=5)),))
    gate = SimpleNamespace(current_authorization=auth, status_text='Лицензия активна', verification_text='Проверено')
    delivery = Mock()
    delivery.store.trusted_keys = {'fixture': b'public'}
    delivery.store.state.return_value = {'active': None, 'enabled': True}
    delivery.has_active_workflow.return_value = False
    delivery.updates.current_version = '3.2.9'
    delivery.updates.license_client.validate.side_effect = LicenseUnavailableError('outage') if outage else LicenseError('denied', code='license_rejected')
    view = V3ApplicationView(draft_path=tmp_path / 'draft.json', license_gate=gate, module_delivery=delivery)
    try:
        assert view._composer_allowed()
        view._refresh_module_discovery()
        wait_until(app, lambda: not view._module_updates_dialog.busy)
        assert view._composer_allowed() is outage
        assert (gate.current_authorization is auth) is outage
    finally:
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def test_late_discovery_for_previous_account_cannot_restore_old_cards(app, tmp_path):
    from datetime import datetime, timedelta, timezone
    from dataclasses import replace
    from license_client import LicenseAuthorization, ModuleEntitlement
    from v3_mode_selection import V3ApplicationView
    now = datetime.now(timezone.utc)
    old = LicenseAuthorization('old', 'clipart-generator', 'device', now - timedelta(minutes=1),
        now + timedelta(minutes=5), module_entitlements=(ModuleEntitlement('prompt-composer', now - timedelta(minutes=1), now + timedelta(minutes=5)),))
    current = replace(old, license_id='new', module_entitlements=())
    gate = SimpleNamespace(current_authorization=current, status_text='Лицензия активна', verification_text='Проверено')
    delivery = Mock()
    delivery.store.trusted_keys = {'fixture': b'public'}
    delivery.store.state.return_value = {'active': None, 'enabled': True}
    delivery.has_active_workflow.return_value = False
    delivery.updates.current_version = '3.2.9'
    view = V3ApplicationView(draft_path=tmp_path / 'draft.json', license_gate=gate, module_delivery=delivery)
    try:
        dialog = view._ensure_module_updates_dialog()
        dialog.checked_authorization = old
        dialog.checked = {'prompt-composer': ('ready', object())}
        dialog.releases = {'prompt-composer': object()}
        dialog._pending_download = 'prompt-composer'
        view._module_state_changed()
        assert gate.current_authorization is current
        assert not dialog.checked and not dialog.releases
        assert dialog._pending_download is None
        assert view.mode_selection.module_cards['prompt-composer'].start_button.text() == 'Нет доступа'
        dialog.denied_authorization = old
        view._module_state_changed()
        assert gate.current_authorization is current
    finally:
        view.close()
        view.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _queue_setup(dialog, delivery, base_release):
    """Two installed modules with verified offers; pinterest second in row order."""
    installed = {"processing": "1.5.0", "pinterest": "2.0.0"}
    delivery.store.state.side_effect = lambda module: {
        "enabled": module in installed, "active": installed.get(module)}
    offers = {
        "processing": ModuleRelease(
            "1.6.0", "fixture-processing.zip", 20, "b" * 64, "https://fixture.invalid/downloads/p",
            module_id="processing", studio_min="3.2.0", studio_max_exclusive="4.0.0"),
        "pinterest": base_release,
    }
    delivery.check.side_effect = lambda module: offers.get(module)
    dialog.releases.update(offers)
    return installed


def test_update_all_installs_each_module_sequentially(app, setup):
    dialog, delivery, base_release = setup
    installed = _queue_setup(dialog, delivery, base_release)
    activated = []
    delivery.activate.side_effect = lambda module, version: (
        activated.append((module, version)), installed.__setitem__(module, version))

    dialog.update_all_button.click()
    wait_until(app, lambda: not dialog.busy and not dialog._queue)
    app.processEvents()

    # Row order is the queue order, never parallel workers.
    assert activated == [("processing", "1.6.0"), ("pinterest", "1.1.0")]
    assert installed["processing"] == "1.6.0"
    assert dialog.status.text().startswith("Готово: обновлены все 2 модулей.")
    assert dialog.update_all_button.isEnabled()


def test_update_all_stops_on_failure_and_keeps_previous_version(app, setup):
    dialog, delivery, base_release = setup
    installed = _queue_setup(dialog, delivery, base_release)
    activated = []
    delivery.activate.side_effect = lambda module, version: activated.append((module, version))

    original = delivery.install.side_effect

    def install(selected, **callbacks):
        if selected.module_id == "processing":
            raise RuntimeError("broken staging")
        return original(selected, **callbacks)

    delivery.install.side_effect = install

    dialog.update_all_button.click()
    wait_until(app, lambda: not dialog.busy and not dialog._queue)
    app.processEvents()

    assert activated == []
    assert installed["processing"] == "1.5.0"
    assert "Обновлено 0 из 2" in dialog.status.text()
    assert "Остановка на «Обработка изображений»" in dialog.status.text()


def test_update_all_skips_modules_that_are_not_installed(app, setup):
    dialog, delivery, base_release = setup
    installed = {"processing": "1.5.0", "pinterest": None}
    delivery.store.state.side_effect = lambda module: {
        "enabled": module in installed and installed[module] is not None,
        "active": installed.get(module),
    }
    offers = {
        "processing": ModuleRelease(
            "1.6.0", "fixture-processing.zip", 20, "b" * 64, "https://fixture.invalid/downloads/p",
            module_id="processing", studio_min="3.2.0", studio_max_exclusive="4.0.0"),
        "pinterest": base_release,
    }
    delivery.check.side_effect = lambda module: offers.get(module)
    dialog.releases.update(offers)
    activated = []
    delivery.activate.side_effect = lambda module, version: (
        activated.append((module, version)), installed.__setitem__(module, version))

    dialog.update_all_button.click()
    wait_until(app, lambda: not dialog.busy and not dialog._queue)
    app.processEvents()

    assert activated == [("processing", "1.6.0")]
    assert dialog.status.text().startswith("Готово: обновлены все 1 модулей.")


def test_update_all_button_replaces_check_only_when_updates_found(app, setup):
    dialog, _delivery, _release = setup
    assert dialog.update_all_button.isHidden() and not dialog.check_button.isHidden()
    dialog.check_button.click()
    wait_until(app, lambda: not dialog.busy)
    # Updates exist only for a module that is installed; otherwise no "update all".
    has_updates = dialog._has_updates()
    assert dialog.update_all_button.isHidden() == (not has_updates)
    assert dialog.check_button.isHidden() == has_updates


def test_shared_update_rechecks_automatically_so_other_modules_stay_updatable(app, setup):
    from studio_module_updates import WorkflowUpdate
    from studio_processing_api import PROCESSING_COMPONENT_ID

    dialog, delivery, pinterest_release = setup
    delivery.updates.license_client.validate.return_value = SimpleNamespace(allows_module=lambda module: True)
    installed = {"clipart": "1.0.0", "pinterest": "2.0.0"}
    delivery.store.state.side_effect = lambda module: {
        "enabled": module in installed, "active": installed.get(module)}
    processing = ModuleRelease(
        "1.6.0", "fixture-processing.zip", 20, "b" * 64, "https://fixture.invalid/downloads/p",
        module_id=PROCESSING_COMPONENT_ID, studio_min="3.2.0", studio_max_exclusive="4.0.0")
    shared_offer = WorkflowUpdate("clipart", None, processing)
    shared_installed = {"done": False}

    def check(module):
        if module == "clipart":
            return None if shared_installed["done"] else shared_offer
        return pinterest_release if module == "pinterest" else None

    delivery.check.side_effect = check
    delivery.install.side_effect = lambda selected, **_callbacks: {
        "module_id": selected.module_id, "version": selected.version}
    delivery.activate_update.side_effect = lambda _selected: shared_installed.__setitem__("done", True)

    dialog.check_button.click()
    wait_until(app, lambda: not dialog.busy)
    assert dialog.rows["clipart"][2].isEnabled() and dialog.rows["pinterest"][2].isEnabled()

    dialog.rows["clipart"][2].click()
    wait_until(app, lambda: shared_installed["done"])
    # No manual "check" click: the other module's offer comes back on its own.
    wait_until(app, lambda: not dialog.busy and dialog.rows["pinterest"][2].isEnabled())
    assert set(dialog.releases) == {"pinterest"}
    assert dialog.rows["pinterest"][1].text() == "1.1.0"
