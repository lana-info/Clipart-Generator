"""Path-free, secret-free public contracts for Studio provider capabilities."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

_IDENTIFIER = re.compile(r"[a-z][a-z0-9_.-]{0,127}\Z")
_MAX_PAYLOAD_BYTES = 2 * 1024 * 1024


class ProviderApiError(ValueError):
    pass


class ProviderSubmissionUncertain(RuntimeError):
    """A paid submission may have reached the provider; callers must not retry blindly."""


@dataclass(frozen=True, slots=True)
class ProviderOperationRequest:
    operation: str
    model_id: str
    input_payload: Mapping[str, Any] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not _IDENTIFIER.fullmatch(self.operation):
            raise ProviderApiError("Invalid provider operation")
        if not isinstance(self.model_id, str) or not self.model_id or len(self.model_id) > 255:
            raise ProviderApiError("Invalid provider model")
        if not isinstance(self.input_payload, Mapping):
            raise ProviderApiError("Provider input must be an object")
        try:
            copied = json.loads(json.dumps(dict(self.input_payload), ensure_ascii=False, allow_nan=False))
            encoded = json.dumps(copied, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ProviderApiError("Provider input must contain JSON values only") from exc
        if len(encoded) > _MAX_PAYLOAD_BYTES:
            raise ProviderApiError("Provider input is too large")
        object.__setattr__(self, "input_payload", MappingProxyType(copied))
