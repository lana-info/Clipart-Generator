"""Public, path-free DTOs for the projects.v1 module capability."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


class ProjectCapabilityError(ValueError):
    pass


def _copy_state(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProjectCapabilityError("Project document state must be an object")
    try:
        copied = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise ProjectCapabilityError("Project document state must contain JSON values only") from exc
    if not isinstance(copied, dict):
        raise ProjectCapabilityError("Project document state must be an object")
    return copied


@dataclass(frozen=True, slots=True)
class ProjectDocument:
    project_id: str
    module_id: str
    document_type: str
    document_version: int
    name: str
    state: dict[str, Any] = field(repr=False)
    editable: bool = True
    read_only_reason: str = ""

    def __post_init__(self) -> None:
        for value in (self.project_id, self.module_id, self.document_type, self.name):
            if not isinstance(value, str) or not value:
                raise ProjectCapabilityError("Project document metadata is invalid")
        if type(self.document_version) is not int or self.document_version < 1:
            raise ProjectCapabilityError("Project document version is invalid")
        if type(self.editable) is not bool:
            raise ProjectCapabilityError("Project editability flag is invalid")
        object.__setattr__(self, "state", _copy_state(self.state))
