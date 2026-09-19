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
