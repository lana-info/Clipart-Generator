"""Explicit translation boundary for structured prompts.

Translation is deliberately separate from creative rewriting. The base
application can render the user's original values, but must not label them as
translated merely because section headings are in English.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PromptTranslationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PromptTranslationResult:
    source_language: str
    target_language: str
    translated: bool
    fields: dict[str, str | tuple[str, ...]]
    backend_id: str
    warning: str = ""

    def __post_init__(self) -> None:
        if not self.source_language or not self.target_language:
            raise ValueError("source and target languages are required")
        if not self.backend_id:
            raise ValueError("backend_id is required")


class PromptTranslationBackend(Protocol):
    backend_id: str

    def translate_fields(
        self,
        fields: dict[str, str | tuple[str, ...]],
        *,
        source_language: str,
        target_language: str,
    ) -> PromptTranslationResult: ...


class NoopPromptTranslationBackend:
    """Safe offline backend that reports unavailable translation explicitly."""

    backend_id = "none"

    def translate_fields(
        self,
        fields: dict[str, str | tuple[str, ...]],
        *,
        source_language: str,
        target_language: str,
    ) -> PromptTranslationResult:
        normalized = dict(fields)
        if source_language == target_language:
            return PromptTranslationResult(
                source_language=source_language,
                target_language=target_language,
                translated=True,
                fields=normalized,
                backend_id=self.backend_id,
            )
        return PromptTranslationResult(
            source_language=source_language,
            target_language=target_language,
            translated=False,
            fields=normalized,
            backend_id=self.backend_id,
            warning=(
                "Перевод недоступен: исходный текст сохранён без изменений. "
                "Английский provider prompt не заявляется."
            ),
        )


def translate_prompt_fields(
    fields: dict[str, str | tuple[str, ...]],
    *,
    source_language: str,
    target_language: str,
    backend: PromptTranslationBackend | None = None,
) -> PromptTranslationResult:
    if not isinstance(fields, dict):
        raise TypeError("fields must be a dict")
    source = str(source_language or "").strip().casefold()
    target = str(target_language or "").strip().casefold()
    if not source or not target:
        raise PromptTranslationError("source and target languages are required")
    selected = backend or NoopPromptTranslationBackend()
    result = selected.translate_fields(
        dict(fields), source_language=source, target_language=target
    )
    if not isinstance(result, PromptTranslationResult):
        raise PromptTranslationError("translation backend returned invalid result")
    return result


__all__ = [
    "NoopPromptTranslationBackend",
    "PromptTranslationBackend",
    "PromptTranslationError",
    "PromptTranslationResult",
    "translate_prompt_fields",
]
