from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import v3_mode_selection as vms
from studio_modules import ModuleStore


def _store(tmp_path):
    return ModuleStore(tmp_path / "modules", studio_version="3.2.33", platform="windows-x64", trusted_keys={})


def test_cached_verification_is_unknown_until_verified_and_resets_on_change(tmp_path, monkeypatch):
    store = _store(tmp_path)
    module = store.root / "clipart" / "1.0.0"
    module.mkdir(parents=True)
    (module / "a.py").write_text("x")
    (store.root / "clipart" / "active.json").write_text(
        '{"active": "1.0.0", "previous": null, "enabled": true}')
    calls = []
    monkeypatch.setattr(store, "verified_active_path", lambda mid: calls.append(mid) or module)
    assert store.cached_verification("clipart") is None          # never verified: unknown
    assert store.verify_for_display("clipart") is True and calls == ["clipart"]
    assert store.cached_verification("clipart") is True           # served from cache, no re-hash
    assert calls == ["clipart"]
    time.sleep(0.01)
    (module / "a.py").write_text("changed content")               # files changed -> must re-verify
    assert store.cached_verification("clipart") is None


def test_failed_verification_is_remembered_as_false(tmp_path, monkeypatch):
    store = _store(tmp_path)
    module = store.root / "clipart" / "1.0.0"
    module.mkdir(parents=True)
    (store.root / "clipart" / "active.json").write_text(
        '{"active": "1.0.0", "previous": null, "enabled": true}')
    def broken(_mid):
        raise ValueError("bad signature")
    monkeypatch.setattr(store, "verified_active_path", broken)
    assert store.verify_for_display("clipart") is False
    assert store.cached_verification("clipart") is False


def test_exit_watchdog_arms_only_when_configured(monkeypatch):
    app = QApplication.instance() or QApplication([])
    timers = []

    class FakeTimer:
        def __init__(self, seconds, func, args=()):
            self.seconds, self.func, self.args, self.daemon = seconds, func, args, False
            timers.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(vms.threading, "Timer", FakeTimer)
    with tempfile.TemporaryDirectory() as temp:
        plain = vms.V3ApplicationView(draft_path=Path(temp) / "a.json")
        plain.close()
        assert timers == []                                        # tests/dev never self-terminate
        guarded = vms.V3ApplicationView(draft_path=Path(temp) / "b.json", exit_watchdog_seconds=5.0)
        guarded.close()
    assert len(timers) == 1 and timers[0].seconds == 5.0
    assert timers[0].func is os._exit and timers[0].args == (0,) and timers[0].daemon and timers[0].started


def test_refresh_uses_cache_and_verifies_unknown_modules_in_background(monkeypatch):
    app = QApplication.instance() or QApplication([])
    started = []
    monkeypatch.setattr(vms.V3ApplicationView, "_start_module_verification",
                        lambda self, ids: started.append(list(ids)))
    delivery = Mock()
    delivery.has_active_workflow.return_value = True
    delivery.store.cached_verification.return_value = None       # unknown -> background, GUI not blocked
    with tempfile.TemporaryDirectory() as temp:
        view = vms.V3ApplicationView(draft_path=Path(temp) / "a.json", module_delivery=delivery)
        started.clear()
        view.refresh_license_status()
        view.close()
    delivery.store.verified_active_path.assert_not_called()      # the slow full check never ran on the GUI thread
    assert started and set(started[0])


def test_main_arms_watchdog_only_when_frozen():
    import inspect
    import main
    source = inspect.getsource(main.create_v3_application_window)
    assert 'exit_watchdog_seconds=5.0 if getattr(sys, "frozen", False) else None' in source
