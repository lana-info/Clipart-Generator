"""Structured prompt contract for the future Pinterest workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


_FIELD_LABELS: Final[dict[str, dict[str, str]]] = {
    "en": {
        "topic": "Topic",
        "object": "Object",
        "background": "Background",
        "text_safe_area": "Text-safe area",
        "headline": "Headline",
        "cta": "CTA",
        "aspect_ratio": "Aspect ratio",
        "branding": "Branding",
        "visual_hierarchy": "Visual hierarchy",
        "style": "Style",
        "restrictions": "Restrictions",
    },
    "ru": {
        "topic": "Тема",
        "object": "Объект",
        "background": "Фон",
        "text_safe_area": "Безопасная зона для текста",
        "headline": "Заголовок",
        "cta": "Призыв к действию",
        "aspect_ratio": "Соотношение сторон",
        "branding": "Брендинг",
        "visual_hierarchy": "Визуальная иерархия",
        "style": "Стиль",
        "restrictions": "Ограничения",
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
class PinterestPromptFields:
    topic: str = ""
    object: str = ""
    background: str = ""
    text_safe_area: str = ""
    headline: str = ""
    cta: str = ""
    aspect_ratio: str = "2:3"
    branding: str = ""
    visual_hierarchy: str = ""
    style: str = ""
    restrictions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "topic",
            "object",
            "background",
            "text_safe_area",
            "headline",
            "cta",
            "aspect_ratio",
            "branding",
            "visual_hierarchy",
            "style",
        ):
            object.__setattr__(self, name, _text(getattr(self, name)))
        object.__setattr__(self, "restrictions", _unique(tuple(self.restrictions)))

    def to_dict(self) -> dict[str, object]:
        return {
            "topic": self.topic,
            "object": self.object,
            "background": self.background,
            "text_safe_area": self.text_safe_area,
            "headline": self.headline,
            "cta": self.cta,
            "aspect_ratio": self.aspect_ratio,
            "branding": self.branding,
            "visual_hierarchy": self.visual_hierarchy,
            "style": self.style,
            "restrictions": list(self.restrictions),
        }


def render_pinterest_prompt(
    fields: PinterestPromptFields,
    *,
    language: str = "en",
) -> str:
    if not isinstance(fields, PinterestPromptFields):
        raise TypeError("fields must be PinterestPromptFields")
    try:
        labels = _FIELD_LABELS[language]
    except KeyError as error:
        raise ValueError("language must be 'en' or 'ru'") from error

    rendered: list[str] = []
    for name in (
        "topic",
        "object",
        "background",
        "text_safe_area",
        "headline",
        "cta",
        "aspect_ratio",
        "branding",
        "visual_hierarchy",
        "style",
        "restrictions",
    ):
        value = fields.to_dict()[name]
        text = "; ".join(value) if isinstance(value, list) else str(value)
        if text:
            rendered.append(f"{labels[name]}: {text}.")
    return "\n".join(rendered)


__all__ = ["PinterestPromptFields", "render_pinterest_prompt"]
