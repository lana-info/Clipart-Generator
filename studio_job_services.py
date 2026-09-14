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
