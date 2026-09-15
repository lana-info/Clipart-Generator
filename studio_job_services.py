"""Core-owned job facade over existing ModuleRuntimeHost lifecycle leases."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from studio_job_api import JobRequest, JobTicket
from studio_module_runtime import ModuleRuntimeHost


@dataclass(frozen=True, slots=True)
class JobLauncher:
    operation: str
    launch: Callable[[str, JobRequest, Callable[[], None]], str]

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation or not callable(self.launch):
            raise TypeError("Invalid Core job launcher")


class CoreJobService:
    __slots__ = ("_module_id", "_host", "_launchers")

    def __init__(self, module_id: str, host: ModuleRuntimeHost, launchers=()) -> None:
        if not isinstance(module_id, str) or not module_id:
            raise TypeError("module_id is required")
        if not isinstance(host, ModuleRuntimeHost):
            raise TypeError("host must be ModuleRuntimeHost")
        mapping = {}
        for launcher in tuple(launchers):
            if not isinstance(launcher, JobLauncher) or launcher.operation in mapping:
                raise ValueError("Invalid or duplicate Core job launcher")
            mapping[launcher.operation] = launcher
        self._module_id = module_id
        self._host = host
        self._launchers = mapping

    def submit(self, request: JobRequest) -> JobTicket:
        if not isinstance(request, JobRequest):
            raise TypeError("request must be JobRequest")
        launcher = self._launchers.get(request.operation)
        if launcher is None:
            raise ValueError("Job operation is not registered by Core")
        lease = self._host.acquire_job_lease(self._module_id)
        try:
            job_id = launcher.launch(self._module_id, request, lease.close)
            return JobTicket(job_id)
        except BaseException:
            lease.close()
            raise


# Compatibility handle for the legacy desktop WorkerThread. Core owns the
# underlying worker in a private capability registry; built-in workflows
# receive only this narrow lifecycle and event surface.
from PyQt6.QtCore import QObject, pyqtSignal

from _studio_worker_core import (
    register_worker, worker_is_running, worker_request_stop_after_current,
    worker_start, worker_stop,
)


class CoreWorkerJobHandle(QObject):
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    diagnostic = pyqtSignal(object)

    __slots__ = ("_capability_id",)

    def __init__(self, worker, *, message_redactor=None) -> None:
        super().__init__()
        self._capability_id = register_worker(
            worker, self, message_redactor=message_redactor
        )

    def start(self) -> None:
        worker_start(self._capability_id)

    def stop(self) -> None:
        worker_stop(self._capability_id)

    def request_stop_after_current(self) -> None:
        worker_request_stop_after_current(self._capability_id)

    def isRunning(self) -> bool:
        return worker_is_running(self._capability_id)
