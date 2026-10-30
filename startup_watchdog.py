"""Startup window watchdog: a window that never appears must not leave a zombie process.

Owner diagnostics 2026-10-30 (3.2.52, Windows 11): in roughly one launch out of three the
process starts, the window is created but never shown, the interface thread stops before the
event loop handles a single event (no update_check_started 1,2 s later) and the journal ends
after startup_status_refreshed. The user then had to kill the process and start again.

This is the last-resort safety net for exactly that case: if the window has not been shown
and the event loop has not handled one event by the deadline, the journal records
startup_window_timeout, a stack snapshot of every Python thread is saved next to the journal
(faulthandler, no dump needed - the interface thread's last Python frame names the exact call,
e.g. window.show()), and the process ends; on a frozen build the first attempt also restarts
itself once (the recovery process carries ``--startup-recovered`` and never restarts again, so
a deterministic failure cannot loop forever).
"""
from __future__ import annotations

import os
import subprocess
import threading
import time

STACK_SNAPSHOT_FILENAME = "startup-timeout-stacks.txt"

# Normal start-to-window time is a few seconds; even a busy antivirus does not push the
# first show past ~20 s. 30 s leaves room for a dump to be taken before the process ends.
STARTUP_WINDOW_TIMEOUT_SECONDS = 30.0
RECOVERY_ARGUMENT = "--startup-recovered"


class StartupWindowWatchdog:
    """Watches one startup: window_shown() stops it, otherwise it fires exactly once."""

    def __init__(
        self,
        *,
        timeout_seconds: float = STARTUP_WINDOW_TIMEOUT_SECONDS,
        journal=None,
        retry_enabled: bool = False,
        executable: str | None = None,
        restart_arguments: tuple[str, ...] = (),
        attempt: int = 1,
        exit_process=os._exit,
        launcher=None,
    ) -> None:
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.journal = journal
        self.retry_enabled = bool(retry_enabled)
        self.executable = executable
        self.restart_arguments = tuple(restart_arguments)
        self.attempt = max(1, int(attempt))
        self._exit_process = exit_process
        self._launcher = launcher or (lambda argv, **kwargs: subprocess.Popen(argv, **kwargs))
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._shown = False
        self._fired = False
        self._started_at: float | None = None

    def arm(self) -> None:
        with self._lock:
            if self._timer is not None or self._shown or self._fired:
                return
            self._started_at = time.monotonic()
            self._timer = threading.Timer(self.timeout_seconds, self._on_timeout)
            self._timer.daemon = True
            self._timer.start()

    def window_shown(self) -> None:
        """Called from the event loop once it handles an event; disarms the watchdog."""
        with self._lock:
            self._shown = True
            timer, self._timer = self._timer, None
        if timer is not None:
            timer.cancel()

    def _elapsed_ms(self) -> int:
        if self._started_at is None:
            return 0
        return int((time.monotonic() - self._started_at) * 1000)

    def _save_stack_snapshot(self) -> str | None:
        """Write the Python stacks of all threads next to the journal; never raise.

        The interface thread's last Python frame names the exact startup call it is
        stuck in, so the first repeat is diagnosable without a memory dump.
        """
        saver = getattr(self.journal, "save_thread_stacks", None) if self.journal is not None else None
        if not callable(saver):
            return None
        try:
            return saver(STACK_SNAPSHOT_FILENAME)
        except Exception:
            return None

    def _on_timeout(self) -> None:
        with self._lock:
            if self._shown or self._fired:
                return
            self._fired = True
        restart = self.retry_enabled and self.attempt == 1 and bool(self.executable)
        decision = "restarted" if restart else "stopped"
        # Snapshot before the journal event so the event can name the saved file.
        stacks_filename = self._save_stack_snapshot()
        if self.journal is not None:
            try:
                details = {
                    "elapsed_ms": self._elapsed_ms(),
                    "attempt": self.attempt,
                    "decision": decision,
                }
                if stacks_filename is not None:
                    details["filename"] = stacks_filename
                self.journal.record(
                    "startup_window_timeout",
                    "Окно приложения не появилось за отведённое время.",
                    severity="warning",
                    outcome="failed",
                    details=details,
                )
            except Exception:
                pass  # a journal failure must never keep the zombie process alive
        if restart:
            try:
                self._launcher([self.executable, *self.restart_arguments], close_fds=True)
            except Exception:
                pass  # the process still ends; the user can start the app again
        self._exit_process(1)
