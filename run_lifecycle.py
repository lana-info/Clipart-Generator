"""Pure, idempotent lifecycle contract for worker-backed runs."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RunLifecycleState(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunLifecycleEvent:
    name: str
    state: RunLifecycleState
    error_code: str = ""


class RunLifecycle:
    def __init__(self) -> None:
        self.state = RunLifecycleState.CREATED
        self.events: list[RunLifecycleEvent] = []

    def start(self) -> RunLifecycleEvent:
        if self.state is RunLifecycleState.CREATED:
            self.state = RunLifecycleState.RUNNING
            return self._record("started")
        return self._record("start_ignored")

    def request_cancel(self) -> RunLifecycleEvent:
        if self.state is RunLifecycleState.RUNNING:
            self.state = RunLifecycleState.CANCEL_REQUESTED
            return self._record("cancel_requested")
        return self._record("cancel_ignored")

    def finish(self, *, error_code: str = "") -> RunLifecycleEvent:
        if self.state in {RunLifecycleState.SUCCEEDED, RunLifecycleState.FAILED, RunLifecycleState.CANCELLED}:
            return self._record("terminal_ignored", error_code=error_code)
        if self.state is RunLifecycleState.CANCEL_REQUESTED:
            self.state = RunLifecycleState.CANCELLED
            return self._record("cancelled", error_code=error_code)
        self.state = RunLifecycleState.FAILED if error_code else RunLifecycleState.SUCCEEDED
        return self._record("failed" if error_code else "succeeded", error_code=error_code)

    def _record(self, name: str, *, error_code: str = "") -> RunLifecycleEvent:
        event = RunLifecycleEvent(name, self.state, error_code)
        self.events.append(event)
        return event
