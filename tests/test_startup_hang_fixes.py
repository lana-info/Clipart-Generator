from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

import v3_mode_selection as vms
from diagnostics import DiagnosticJournal
from studio_modules import MAX_TREE_ENTRIES, ModulePackageError, ModuleStore


def _store(tmp_path):
    return ModuleStore(tmp_path / "modules", studio_version="3.2.33", platform="windows-x64", trusted_keys={})


def _enabled_module(store: ModuleStore, module_id: str = "clipart", version: str = "1.0.0") -> Path:
    module = store.root / module_id / version
    module.mkdir(parents=True, exist_ok=True)
    (module / "a.py").write_text("x")
    (store.root / module_id / "active.json").write_text(
        '{"active": "%s", "previous": null, "enabled": true}' % version)
    return module


def test_cached_verification_is_unknown_until_verified_and_resets_on_change(tmp_path, monkeypatch):
    store = _store(tmp_path)
    module = _enabled_module(store)
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
    _enabled_module(store)
    def broken(_mid):
        raise ValueError("bad signature")
    monkeypatch.setattr(store, "verified_active_path", broken)
    assert store.verify_for_display("clipart") is False
    assert store.cached_verification("clipart") is False


def test_display_verdict_never_walks_the_installed_tree(tmp_path, monkeypatch):
    """The GUI thread may only read the in-memory verdict; walking is background-only."""
    store = _store(tmp_path)
    _enabled_module(store)
    walked = []
    monkeypatch.setattr(store, "_tree_signature",
                        lambda path: walked.append(path) or "signature")
    assert store.display_verdict("clipart") is None
    assert walked == []
    store._display_verdicts[("clipart", "1.0.0")] = ("signature", True)
    assert store.display_verdict("clipart") is True
    assert walked == []
    assert store.cached_verification("clipart") is True
    assert walked == [store.root / "clipart" / "1.0.0"]


def test_tree_signature_is_bounded_and_cycle_safe(tmp_path):
    store = _store(tmp_path)
    module = _enabled_module(store)
    loop = module / "loop"
    try:
        # A link pointing back at the package root must never be descended into.
        loop.symlink_to(module, target_is_directory=True)
    except (OSError, NotImplementedError):
        loop = None
    started = time.monotonic()
    signature = store._tree_signature(module)
    assert isinstance(signature, str) and signature
    assert time.monotonic() - started < 5
    if loop is not None:
        assert store._tree_signature(module) == signature      # the loop added nothing

    crowded = store.root / "crowded" / "1.0.0"
    crowded.mkdir(parents=True)
    for index in range(MAX_TREE_ENTRIES + 1):
        (crowded / f"f{index}.py").write_text("x")
    try:
        store._tree_signature(crowded)
        raise AssertionError("an oversized tree must not be fingerprinted")
    except ModulePackageError:
        pass


def test_unreadable_tree_reports_unknown_verdict_instead_of_raising(tmp_path, monkeypatch):
    store = _store(tmp_path)
    _enabled_module(store)
    def refuse(path):
        raise ModulePackageError("Installed module tree cannot be read")
    monkeypatch.setattr(store, "_tree_signature", refuse)
    assert store.cached_verification("clipart") is None           # unknown, never a crash


def test_exit_watchdog_arms_only_when_configured(monkeypatch):
    _app = QApplication.instance() or QApplication([])
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


def test_refresh_uses_in_memory_verdict_and_verifies_unknown_modules_in_background(monkeypatch):
    _app = QApplication.instance() or QApplication([])
    started = []
    monkeypatch.setattr(vms.V3ApplicationView, "_start_module_verification",
                        lambda self, ids: started.append(list(ids)))
    delivery = Mock()
    delivery.has_active_workflow.return_value = True
    delivery.store.display_verdict.return_value = None           # unknown -> background, GUI not blocked
    with tempfile.TemporaryDirectory() as temp:
        view = vms.V3ApplicationView(draft_path=Path(temp) / "a.json", module_delivery=delivery)
        started.clear()
        view.refresh_license_status()
        view.close()
    delivery.store.verified_active_path.assert_not_called()      # the slow full check never ran on the GUI thread
    delivery.store.cached_verification.assert_not_called()       # nor any tree walk
    assert started and set(started[0])


def test_startup_refresh_never_walks_module_trees_even_on_a_slow_disk(tmp_path, monkeypatch):
    """Regression: the start must not touch the installed trees on the GUI thread."""
    _app = QApplication.instance() or QApplication([])
    store = _store(tmp_path)
    _enabled_module(store)
    store._display_verdicts[("clipart", "1.0.0")] = ("signature", True)
    walks = []
    real_walk = os.walk

    def slow_walk(*args, **kwargs):
        walks.append(args[0])
        time.sleep(0.5)
        return real_walk(*args, **kwargs)

    monkeypatch.setattr(os, "walk", slow_walk)
    delivery = Mock()
    delivery.store = store
    delivery.has_active_workflow.return_value = True
    with tempfile.TemporaryDirectory() as temp:
        view = vms.V3ApplicationView(draft_path=Path(temp) / "a.json", module_delivery=delivery)
        started = time.monotonic()
        view.refresh_license_status()
        assert time.monotonic() - started < 1.0
        view.close()
    assert walks == []


def test_module_verification_timeout_is_recorded_and_window_keeps_working(tmp_path):
    _app = QApplication.instance() or QApplication([])
    journal = DiagnosticJournal(tmp_path, app_version="3.2.52")
    view = vms.V3ApplicationView(draft_path=tmp_path / "a.json", diagnostic_journal=journal)

    class RunningThread:
        module_ids = ["patterns", "prompt-composer"]
        durations_ms: dict = {}

        def isRunning(self):
            return True

        def requestInterruption(self):
            pass

        def wait(self, _ms):
            return True

    view._module_verifier = RunningThread()
    view._verification_started_at = time.monotonic() - 16
    view._module_verification_timeout()
    events = [event["event"] for event in journal.read_events()]
    assert "module_verification_timeout" in events
    assert view.mode_selection.verification_note.text() == vms.MODULE_VERIFICATION_TIMEOUT_NOTE
    timeout_event = [event for event in journal.read_events()
                     if event["event"] == "module_verification_timeout"][0]
    stacks = tmp_path / "diagnostics" / "module-verification-timeout-stacks.txt"
    assert timeout_event["details"]["filename"] == "module-verification-timeout-stacks.txt"
    assert stacks.is_file() and "Thread 0x" in stacks.read_text(encoding="utf-8")

    class FinishedThread(RunningThread):
        durations_ms = {"patterns": 120}

        def isRunning(self):
            return False


    view._module_verifier = FinishedThread()
    view._module_verification_timeout()                            # a finished thread never times out
    assert view.mode_selection.verification_note.text() == vms.MODULE_VERIFICATION_TIMEOUT_NOTE
    view._module_verification_done()
    finished = [event for event in journal.read_events() if event["event"] == "module_verification_finished"]
    assert finished and finished[0]["details"]["timed_out"] is True
    assert view.mode_selection.verification_note.text() == ""
    view.close()
    journal.close()


def test_verification_thread_emits_finished_even_on_unexpected_error():
    _app = QApplication.instance() or QApplication([])
    emitted = []
    thread = vms._ModuleVerifyThread(object(), ["clipart"])
    thread.verified.connect(lambda: emitted.append(True))
    thread.store = Mock(verify_for_display=Mock(side_effect=BaseException("store wedged")))
    try:
        thread.run()
    except BaseException:
        pass                                                      # PyQt reports it; the signal still fires
    assert emitted == [True]


def test_verification_runs_once_per_session_and_never_raises(tmp_path, monkeypatch):
    store = _store(tmp_path)
    (store.root / "clipart").mkdir()
    (store.root / "clipart" / "active.json").write_text(
        '{"active": "1.0.0", "previous": null, "enabled": true}')
    monkeypatch.setattr(store, "_tree_signature", lambda path: (_ for _ in ()).throw(OSError("locked")))
    assert store.verify_for_display("clipart") is False           # no exception escapes the thread

    _app = QApplication.instance() or QApplication([])
    started = []

    class FakeThread:
        def __init__(self, *a, **k):
            started.append(a)
            self.verified = Mock()
            self.finished = Mock()

        def start(self):
            pass

    monkeypatch.setattr(vms, "_ModuleVerifyThread", FakeThread)
    with tempfile.TemporaryDirectory() as temp:
        view = vms.V3ApplicationView(draft_path=Path(temp) / "a.json", module_delivery=Mock())
        view._start_module_verification(["clipart"])
        view._module_verifier = None
        view._start_module_verification(["clipart"])               # same module again: skipped
        view.close()
    assert len(started) == 1


def test_deferred_startup_refresh_runs_in_the_event_loop_and_is_recorded(tmp_path):
    app = QApplication.instance() or QApplication([])
    journal = DiagnosticJournal(tmp_path, app_version="3.2.52")
    view = vms.V3ApplicationView(draft_path=tmp_path / "a.json", diagnostic_journal=journal)
    assert "startup_status_refreshed" not in [e["event"] for e in journal.read_events()]
    view.schedule_startup_status_refresh()
    view.schedule_startup_status_refresh()                        # idempotent: one refresh
    for _ in range(50):
        app.processEvents()
    events = [event["event"] for event in journal.read_events()]
    assert events.count("startup_status_refreshed") == 1
    view.close()
    journal.close()


def test_startup_refresh_failure_is_journaled_and_never_escapes(tmp_path):
    app = QApplication.instance() or QApplication([])
    journal = DiagnosticJournal(tmp_path, app_version="3.2.52")
    view = vms.V3ApplicationView(draft_path=tmp_path / "a.json", diagnostic_journal=journal)
    view.refresh_license_status = Mock(side_effect=RuntimeError("status store unavailable"))
    view.schedule_startup_status_refresh()
    for _ in range(50):
        app.processEvents()
    events = [event["event"] for event in journal.read_events()]
    assert "startup_status_refresh_failed" in events
    assert "startup_status_refreshed" not in events
    view.close()
    journal.close()


def test_missing_studio_upcoming_cache_is_not_a_hang(tmp_path):
    _app = QApplication.instance() or QApplication([])
    from studio_upcoming import StudioUpcomingClient
    from studio_upcoming_ui import StudioUpcomingController

    updates = Mock()
    updates.license_client.product_id = "clipart-generator"
    client = StudioUpcomingClient(updates, tmp_path / "modules" / "studio-upcoming.json")
    assert client.cached() is None                                # absent file: empty catalogue
    screen = Mock()
    controller = StudioUpcomingController(client, screen, None)
    screen.set_upcoming_cards.assert_called_once_with([])
    assert controller.worker is None
    controller.shutdown()                                         # no worker: must not wait or raise


def test_shutdown_waits_are_bounded():
    root = Path(__file__).resolve().parents[1]
    for name in ("studio_news_ui.py", "studio_upcoming_ui.py", "studio_module_update_ui.py"):
        source = (root / name).read_text(encoding="utf-8")
        assert ".wait(2000)" in source, f"{name} must bound its worker wait"
        assert ".wait()" not in source, f"{name} must not wait for a worker without a bound"


def test_main_arms_watchdog_only_when_frozen():
    import inspect
    import main
    source = inspect.getsource(main.create_v3_application_window)
    assert 'exit_watchdog_seconds=5.0 if getattr(sys, "frozen", False) else None' in source


def test_main_prefers_deferred_status_refresh_for_the_real_window():
    import inspect
    import main
    source = inspect.getsource(main.create_authorized_v3_application_window)
    assert "schedule_startup_status_refresh" in source


def test_entrypoint_journals_window_show_and_event_loop_start():
    """At the next repeat these two events separate a window that never showed from a later stall."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert '"application_window_shown"' in source
    assert '"application_event_loop_started"' in source
    assert source.index("window.show()") < source.index('"application_window_shown"')


def test_startup_window_watchdog_restarts_once_and_journals_the_timeout(tmp_path):
    from startup_watchdog import RECOVERY_ARGUMENT, StartupWindowWatchdog

    journal = DiagnosticJournal(tmp_path, app_version="3.2.53")
    launches, exits = [], []
    watchdog = StartupWindowWatchdog(
        timeout_seconds=1.0, journal=journal, retry_enabled=True,
        executable="Vibix Images.exe", restart_arguments=(RECOVERY_ARGUMENT,),
        exit_process=lambda code: exits.append(code),
        launcher=lambda argv, **kwargs: launches.append((list(argv), kwargs)),
    )
    watchdog._started_at = time.monotonic() - 31
    watchdog._on_timeout()                                         # fire deterministically
    assert exits == [1]
    assert launches and launches[0][0] == ["Vibix Images.exe", RECOVERY_ARGUMENT]
    events = [event for event in journal.read_events() if event["event"] == "startup_window_timeout"]
    assert events and events[0]["severity"] == "warning"
    assert events[0]["details"]["decision"] == "restarted"
    assert events[0]["details"]["attempt"] == 1
    assert events[0]["details"]["elapsed_ms"] >= 30000
    watchdog._on_timeout()                                         # fires exactly once
    assert exits == [1] and len(launches) == 1
    journal.close()


def test_startup_window_watchdog_stays_silent_when_the_window_shows(tmp_path):
    from startup_watchdog import StartupWindowWatchdog

    journal = DiagnosticJournal(tmp_path, app_version="3.2.53")
    exits = []
    watchdog = StartupWindowWatchdog(
        timeout_seconds=0.05, journal=journal, retry_enabled=True,
        executable="Vibix Images.exe", exit_process=lambda code: exits.append(code),
        launcher=lambda argv, **kwargs: None,
    )
    watchdog.arm()
    watchdog.window_shown()
    time.sleep(0.2)
    assert exits == []
    assert [event["event"] for event in journal.read_events()] == []
    journal.close()


def test_startup_window_watchdog_saves_a_thread_stack_snapshot_on_timeout(tmp_path):
    """The next repeat must name the stuck call without a memory dump."""
    from startup_watchdog import STACK_SNAPSHOT_FILENAME, StartupWindowWatchdog

    journal = DiagnosticJournal(tmp_path, app_version="3.2.53")
    watchdog = StartupWindowWatchdog(
        timeout_seconds=1.0, journal=journal, retry_enabled=False,
        executable="Vibix Images.exe", exit_process=lambda code: None,
        launcher=lambda argv, **kwargs: None,
    )
    watchdog._started_at = time.monotonic() - 31
    watchdog._on_timeout()
    snapshot = tmp_path / "diagnostics" / STACK_SNAPSHOT_FILENAME
    assert snapshot.is_file()
    text = snapshot.read_text(encoding="utf-8")
    assert "Thread 0x" in text                      # faulthandler writes every thread
    assert "test_startup_window_watchdog_saves_a_thread_stack_snapshot_on_timeout" in text
    events = [event for event in journal.read_events() if event["event"] == "startup_window_timeout"]
    assert events and events[0]["details"]["filename"] == STACK_SNAPSHOT_FILENAME
    journal.close()


def test_startup_window_watchdog_never_restarts_the_recovery_launch(tmp_path):
    from startup_watchdog import StartupWindowWatchdog

    journal = DiagnosticJournal(tmp_path, app_version="3.2.53")
    launches, exits = [], []
    watchdog = StartupWindowWatchdog(
        timeout_seconds=1.0, journal=journal, retry_enabled=False,   # the recovery launch
        executable="Vibix Images.exe", exit_process=lambda code: exits.append(code),
        launcher=lambda argv, **kwargs: launches.append(argv),
    )
    watchdog._started_at = time.monotonic() - 31
    watchdog._on_timeout()
    assert exits == [1] and launches == []
    events = [event for event in journal.read_events() if event["event"] == "startup_window_timeout"]
    assert events and events[0]["details"]["decision"] == "stopped"
    journal.close()


def test_startup_window_watchdog_arms_in_frozen_entrypoint_only():
    root = Path(__file__).resolve().parents[1]
    source = (root / "main.py").read_text(encoding="utf-8")
    assert "StartupWindowWatchdog" in source
    assert '"--startup-recovered"' in source
    assert 'getattr(sys, "frozen", False)' in source
    # the watchdog disarms from the event loop, and the recovery flag never restarts again
    assert "window_watchdog.window_shown" in source
    assert "retry_enabled=not startup_recovered" in source
    watchdog_source = (root / "startup_watchdog.py").read_text(encoding="utf-8")
    assert "os._exit" in watchdog_source and "startup_window_timeout" in watchdog_source


def test_watchdog_is_disarmed_by_a_real_event_loop_timer(tmp_path):
    """The entrypoint disarms the watchdog with singleShot(0); a live loop must beat the deadline."""
    from PyQt6.QtCore import QTimer
    from startup_watchdog import StartupWindowWatchdog

    app = QApplication.instance() or QApplication([])
    journal = DiagnosticJournal(tmp_path, app_version="3.2.53")
    exits = []
    watchdog = StartupWindowWatchdog(
        timeout_seconds=0.3, journal=journal, retry_enabled=True,
        executable="Vibix Images.exe", exit_process=lambda code: exits.append(code),
        launcher=lambda argv, **kwargs: None,
    )
    watchdog.arm()
    QTimer.singleShot(0, watchdog.window_shown)                    # what the entrypoint does
    app.processEvents()
    time.sleep(0.5)                                                # past the original deadline
    assert exits == []
    assert [event["event"] for event in journal.read_events()] == []
    journal.close()
