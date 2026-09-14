"""Neutral runtime request and error helpers shared by built-in workflows."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from provider_error_messages import friendly_provider_error
from security_redaction import redact_text


@dataclass
class FlowRunRequest:
    mode: str
    work_dir: str
    settings: dict[str, Any] = field(repr=False)
    generated_prompts: list[dict[str, Any]] = field(default_factory=list)
    selected_files: list[str] = field(default_factory=list, repr=False)

    def worker_kwargs(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "work_dir": self.work_dir,
            "settings": dict(self.settings),
            "selected_files": list(self.selected_files),
            "generated_prompts": [
                {
                    "prompt": entry["prompt"],
                    "references": list(entry["references"]),
                    "chroma_key_color": str(entry.get("chroma_key_color") or ""),
                    "result_kind": str(entry.get("result_kind") or "legacy"),
                    **({"object_id": str(entry["object_id"])} if entry.get("object_id") else {}),
                }
                for entry in self.generated_prompts
            ],
        }


def safe_runtime_error(
    error: Any,
    runtime_settings: Mapping[str, Any] | None = None,
) -> str:
    if isinstance(error, PermissionError) or getattr(error, "winerror", None) == 5:
        return (
            "Нет доступа к файлу или папке. Выберите другую папку результата "
            "или проверьте права доступа."
        )
    source = runtime_settings or {}
    secrets = tuple(
        source.get(name)
        for name in ("kie_api_key", "photoroom_api_key", "fal_api_key")
        if isinstance(source.get(name), str)
    )
    safe_message = redact_text(str(error).strip() or error.__class__.__name__, secrets, limit=500)
    lowered = safe_message.casefold()
    if any(token in lowered for token in (
        "chroma", "birefnet", "rembg", "ben2", "photoroom",
        "remove-background", "remove_background", "background removal",
    )):
        return (
            "Не удалось подготовить прозрачный фон. "
            "Проверьте исходное изображение и повторите."
        )
    classified = friendly_provider_error(safe_message)
    return classified[1] if classified is not None else safe_message
