"""Deterministic, explainable chroma-key colour heuristic for opaque clipart.

The selector is deliberately a hint, not object recognition. It only sees the
author's text, so a generation can still introduce an unexpected colour. The
chosen colour must travel with the generation record before it can be used for
later removal.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from chroma_key import KEY_COLORS


_WORD = re.compile(r"[a-zа-яё]+", re.IGNORECASE)
_COLOUR_WORDS: dict[str, frozenset[str]] = {
    "blue": frozenset((
        "blue", "cyan", "teal", "aqua", "navy", "turquoise", "azure",
        "синий", "голуб", "бирюз", "лазур", "аквамарин",
    )),
    "green": frozenset((
        "green", "lime", "olive", "emerald", "mint", "leaf", "leaves",
        "plant", "plants", "foliage", "grass", "forest", "зелён", "салатов",
        "оливк", "изумруд", "мят", "лист", "листь", "растен", "трава", "лес",
    )),
    "red": frozenset((
        "red", "pink", "rose", "roses", "coral", "crimson", "scarlet",
        "burgundy", "redhead", "красн", "розов", "корал", "ал", "бордов",
        "роза", "цвет", "мак",
    )),
}
_PREFERENCE = ("blue", "green", "red")


@dataclass(frozen=True)
class ChromaKeyChoice:
    """A supported key and text-only evidence behind a non-guaranteed choice."""

    color: str
    rgb: tuple[int, int, int]
    avoided_terms: tuple[str, ...]
    confidence: str


def select_chroma_key_color(text: str | Iterable[str]) -> ChromaKeyChoice:
    """Choose blue/green/red by least explicit colour conflict in author text.

    Ties intentionally retain the established blue default. The result never
    claims that a model will not render the selected colour in the subject.
    """
    if isinstance(text, str):
        joined = text
    else:
        try:
            joined = " ".join(str(value) for value in text)
        except TypeError as error:
            raise TypeError("text must be a string or iterable of strings") from error
    tokens = tuple(token.casefold() for token in _WORD.findall(joined))
    scores = {
        color: sum(
            any(token == word or token.startswith(word) for word in words)
            for token in tokens
        )
        for color, words in _COLOUR_WORDS.items()
    }
    color = min(_PREFERENCE, key=lambda candidate: (scores[candidate], _PREFERENCE.index(candidate)))
    avoided = tuple(sorted({token for token in tokens if any(
        token == word or token.startswith(word)
        for word in _COLOUR_WORDS[color]
    )}))
    lowest = scores[color]
    confidence = "low" if lowest else "text_only"
    return ChromaKeyChoice(
        color=color,
        rgb=KEY_COLORS[color],
        avoided_terms=avoided,
        confidence=confidence,
    )


__all__ = ["ChromaKeyChoice", "select_chroma_key_color"]
