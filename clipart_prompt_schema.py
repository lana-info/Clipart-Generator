"""Structured prompt data and renderers for the Clipart workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from v3_project_state import PromptGeneratorData


_FIELD_LABELS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "object": "Object",
        "scene": "Scene",
        "style": "Style",
        "palette": "Color palette",
        "composition": "Composition",
        "background": "Background",
        "details": "Details",
        "restrictions": "Restrictions",
        "technical_requirements": "Technical requirements",
    },
    "ru": {
        "object": "Объект",
        "scene": "Сцена",
        "style": "Стиль",
        "palette": "Цветовая палитра",
        "composition": "Композиция",
        "background": "Фон",
        "details": "Детали",
        "restrictions": "Ограничения",
        "technical_requirements": "Технические требования",
    },
}


def _text(value: object) -> str:
    return " ".join(str(value or "").split())


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _text(value)
        key = normalized.casefold()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ClipartPromptFields:
    object: str = ""
    scene: str = ""
    style: str = ""
    palette: str = ""
    composition: str = ""
    background: str = ""
    details: str = ""
    restrictions: tuple[str, ...] = ()
    technical_requirements: str = ""

    def __post_init__(self) -> None:
        for name in (
            "object",
            "scene",
            "style",
            "palette",
            "composition",
            "background",
            "details",
            "technical_requirements",
        ):
            object.__setattr__(self, name, _text(getattr(self, name)))
        object.__setattr__(self, "restrictions", _unique(tuple(self.restrictions)))

    @classmethod
    def from_legacy(cls, data: PromptGeneratorData) -> ClipartPromptFields:
        if not isinstance(data, PromptGeneratorData):
            raise TypeError("data must be PromptGeneratorData")
        return cls(
            object=data.subjects[0] if data.subjects else "",
            scene=data.theme,
            style=data.style,
            palette=data.palette,
            composition=data.composition,
            background=data.background,
            restrictions=tuple(data.restrictions),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "object": self.object,
            "scene": self.scene,
            "style": self.style,
            "palette": self.palette,
            "composition": self.composition,
            "background": self.background,
            "details": self.details,
            "restrictions": list(self.restrictions),
            "technical_requirements": self.technical_requirements,
        }


def render_clipart_prompt(
    fields: ClipartPromptFields,
    *,
    language: str = "en",
) -> str:
    if not isinstance(fields, ClipartPromptFields):
        raise TypeError("fields must be ClipartPromptFields")
    try:
        labels = _FIELD_LABELS[language]
    except KeyError as error:
        raise ValueError("language must be 'en' or 'ru'") from error

    values = fields.to_dict()
    rendered: list[str] = []
    for name in (
        "object",
        "scene",
        "style",
        "palette",
        "composition",
        "background",
        "details",
        "restrictions",
        "technical_requirements",
    ):
        value = values[name]
        if isinstance(value, list):
            text = "; ".join(value)
        else:
            text = str(value)
        if text:
            rendered.append(f"{labels[name]}: {text}.")
    return "\n".join(rendered)


__all__ = ["ClipartPromptFields", "render_clipart_prompt"]
