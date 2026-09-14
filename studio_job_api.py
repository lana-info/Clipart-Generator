"""Public request/ticket contracts for Core-owned jobs."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

_OPERATION = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")


class JobApiError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JobRequest:
    operation: str
    payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not _OPERATION.fullmatch(self.operation):
            raise JobApiError("Invalid job operation")
        if not isinstance(self.payload, Mapping):
            raise JobApiError("Job payload must be an object")
        try:
            copied = json.loads(json.dumps(dict(self.payload), ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError) as exc:
            raise JobApiError("Job payload must contain JSON values only") from exc
        object.__setattr__(self, "payload", MappingProxyType(copied))


@dataclass(frozen=True, slots=True)
class JobTicket:
    job_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.job_id, str) or not self.job_id or len(self.job_id) > 256:
            raise JobApiError("Invalid job id")
