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
# underlying worker; built-in workflows receive only this narrow lifecycle and
# event surface while the job system migrates onto the public jobs capability.
from PyQt6.QtCore import QObject, pyqtSignal


class CoreWorkerJobHandle(QObject):
    progress = pyqtSignal(str)
    item_progress = pyqtSignal(object)
    completed = pyqtSignal(str)
    error = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    diagnostic = pyqtSignal(object)

    def __init__(self, worker) -> None:
        super().__init__()
        if worker is None:
            raise TypeError("worker is required")
        self.__worker = worker
        self.__bridge("progress", self.progress.emit)
        self.__bridge("item_progress", self.item_progress.emit)
        self.__bridge("progress_value", self.progress_value.emit)
        self.__bridge("diagnostic", self.diagnostic.emit)
        self.__bridge("error", self.error.emit)
        completed = getattr(worker, "completed", None)
        if completed is not None and hasattr(completed, "connect"):
            completed.connect(lambda message="": self.completed.emit(str(message or "")))
        else:
            finished = getattr(worker, "finished", None)
            if finished is not None and hasattr(finished, "connect"):
                finished.connect(
                    lambda *args: self.completed.emit(str(args[0] if args else ""))
                )

    def __bridge(self, name: str, emit) -> None:
        signal = getattr(self.__worker, name, None)
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(emit)

    def start(self) -> None:
        start = getattr(self.__worker, "start", None)
        if not callable(start):
            raise RuntimeError("Core worker cannot be started")
        start()

    def stop(self) -> None:
        stop = getattr(self.__worker, "stop", None)
        if callable(stop):
            stop()

    def request_stop_after_current(self) -> None:
        request = getattr(self.__worker, "request_stop_after_current", None)
        if callable(request):
            request()
        else:
            self.stop()

    def isRunning(self) -> bool:
        running = getattr(self.__worker, "isRunning", None)
        return bool(running()) if callable(running) else False
