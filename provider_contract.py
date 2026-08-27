"""Provider-neutral request and task contracts for paid operations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping


MAX_PROVIDER_PAYLOAD_BYTES = 16 * 1024 * 1024
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class ProviderContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProviderTaskRequest:
    provider_id: str
    operation: str
    model_id: str
    input_payload: Mapping[str, Any]
    request_id: str = ""
    idempotency_key: str = ""

    def validate(self) -> None:
        for name, value in (
            ("provider_id", self.provider_id),
            ("operation", self.operation),
            ("model_id", self.model_id),
        ):
            normalized = str(value or "").strip()
            if not _IDENTIFIER_RE.fullmatch(normalized) or ".." in normalized:
                raise ProviderContractError(f"Некорректный {name}")
        if not isinstance(self.input_payload, Mapping):
            raise ProviderContractError("input_payload должен быть объектом")
        try:
            encoded = json.dumps(dict(self.input_payload), ensure_ascii=False).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ProviderContractError("input_payload должен быть JSON-сериализуемым") from error
        if len(encoded) > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ProviderContractError("provider payload слишком большой")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "provider_id": self.provider_id,
            "operation": self.operation,
            "model_id": self.model_id,
            "input_payload": dict(self.input_payload),
            "request_id": self.request_id,
            "idempotency_key": self.idempotency_key,
        }


@dataclass(frozen=True, slots=True)
class ProviderTaskResult:
    provider_id: str
    model_id: str
    operation: str
    request_id: str
    status: str
    result: Mapping[str, Any] | None = None
    error_code: str = ""
    error_message: str = ""


__all__ = [
    "MAX_PROVIDER_PAYLOAD_BYTES",
    "ProviderContractError",
    "ProviderTaskRequest",
    "ProviderTaskResult",
]
