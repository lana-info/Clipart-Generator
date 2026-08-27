from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any

from v3_project_state import (
    MAX_PROMPT_ENTRIES,
    MAX_PROMPT_GENERATOR_TEXT_LENGTH,
    MAX_PROMPT_SERIES_COUNT,
    MAX_TEXT_LENGTH,
    ClipartModeData,
    PinterestModeData,
    ProjectMode,
    ProjectState,
    PromptEntry,
    PromptGeneratorData,
    clipart_prompt_generator_defaults,
    pinterest_prompt_generator_defaults,
)
from clipart_prompt_schema import ClipartPromptFields, render_clipart_prompt


class PromptGeneratorError(ValueError):
    pass


def normalize_prompt_text(value: Any, *, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    if type(limit) is not int or not 1 <= limit <= MAX_TEXT_LENGTH:
        raise ValueError(f"limit must be between 1 and {MAX_TEXT_LENGTH}")
    normalized = unicodedata.normalize("NFC", value[: limit * 4])
    safe_characters: list[str] = []
    for character in normalized:
        if character.isspace():
            safe_characters.append(" ")
        elif not unicodedata.category(character).startswith("C"):
            safe_characters.append(character)
    return " ".join("".join(safe_characters).split())[:limit]


def _normalize_strings(
    values: Sequence[Any],
    *,
    limit: int,
) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = normalize_prompt_text(value, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        if normalized:
            result.append(normalized)
        if len(result) >= limit:
            break
    return result


def prompt_generator_defaults(
    mode: ProjectMode | str,
) -> PromptGeneratorData:
    normalized_mode = (
        mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    )
    if normalized_mode is ProjectMode.CLIPART:
        defaults = clipart_prompt_generator_defaults()
    elif normalized_mode is ProjectMode.PINTEREST:
        defaults = pinterest_prompt_generator_defaults()
    else:
        raise PromptGeneratorError(
            "Prompt generation is only available for clipart and Pinterest"
        )
    return PromptGeneratorData.from_dict(defaults.to_dict())


def normalize_generator_data(
    mode: ProjectMode | str,
    data: PromptGeneratorData,
) -> PromptGeneratorData:
    if not isinstance(data, PromptGeneratorData):
        raise TypeError("data must be PromptGeneratorData")
    subjects = _normalize_strings(
        data.subjects,
        limit=MAX_PROMPT_SERIES_COUNT,
    )
    variations = _normalize_strings(
        data.variations,
        limit=MAX_PROMPT_SERIES_COUNT,
    )
    restrictions = _normalize_strings(
        data.restrictions,
        limit=MAX_PROMPT_SERIES_COUNT,
    )
    return PromptGeneratorData(
        theme=normalize_prompt_text(data.theme, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        subjects=subjects,
        variations=variations,
        style=normalize_prompt_text(data.style, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        palette=normalize_prompt_text(data.palette, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        composition=normalize_prompt_text(data.composition, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        background=normalize_prompt_text(data.background, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        consistency=normalize_prompt_text(data.consistency, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        restrictions=restrictions,
        count=data.count,
    )


def _prompt_sentence(value: str) -> str:
    normalized = normalize_prompt_text(value)
    if not normalized:
        return ""
    if normalized[-1] not in ".!?":
        normalized += "."
    return normalized


def _prompt_language_for_clipart(data: PromptGeneratorData) -> str:
    """Keep section labels in the same language as entered field values.

    This is intentionally language detection, not translation. A future
    translation backend must transform values explicitly before rendering an
    English provider prompt.
    """

    values = (
        data.theme,
        *data.subjects,
        *data.variations,
        data.style,
        data.palette,
        data.composition,
        data.background,
        data.consistency,
        *data.restrictions,
    )
    return "ru" if any(any("а" <= character.casefold() <= "я" for character in value) for value in values) else "en"


def generate_prompt_series(
    mode: ProjectMode | str,
    data: PromptGeneratorData,
) -> list[PromptEntry]:
    normalized_mode = (
        mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    )
    normalized = normalize_generator_data(normalized_mode, data)
    fixed_parts = (
        normalized.theme,
        normalized.style,
        normalized.palette,
        normalized.composition,
        normalized.background,
        normalized.consistency,
        *normalized.restrictions,
    )
    if not normalized.subjects and not normalized.variations and not any(fixed_parts):
        raise PromptGeneratorError("At least one field or object is required")

    subjects = normalized.subjects or [""]
    variations = normalized.variations or [""]
    if len(subjects) * len(variations) > MAX_PROMPT_SERIES_COUNT:
        raise PromptGeneratorError(
            f"A prompt series can contain at most {MAX_PROMPT_SERIES_COUNT} combinations"
        )
    prompts: list[PromptEntry] = []
    for subject in subjects:
        for variation in variations:
            if normalized_mode is ProjectMode.CLIPART:
                prompt = render_clipart_prompt(
                    ClipartPromptFields(
                        object=subject,
                        scene=normalized.theme,
                        style=normalized.style,
                        palette=normalized.palette,
                        composition=normalized.composition,
                        background=normalized.background,
                        details=variation,
                        restrictions=tuple(normalized.restrictions),
                        technical_requirements=normalized.consistency,
                    ),
                    language=_prompt_language_for_clipart(normalized),
                )
            else:
                prompt_parts = (
                    normalized.theme,
                    subject,
                    variation,
                    normalized.style,
                    normalized.palette,
                    normalized.composition,
                    normalized.background,
                    normalized.consistency,
                    *normalized.restrictions,
                )
                prompt = " ".join(
                    sentence
                    for part in prompt_parts
                    if (sentence := _prompt_sentence(part))
                )
            prompts.append(PromptEntry(prompt=prompt))
    return normalize_prompt_entries(
        prompts,
        limit=MAX_PROMPT_SERIES_COUNT,
        deduplicate=False,
    )


def normalize_prompt_entries(
    values: Sequence[Any],
    *,
    limit: int = MAX_PROMPT_ENTRIES,
    deduplicate: bool = True,
) -> list[PromptEntry]:
    if not isinstance(values, Sequence) or isinstance(
        values,
        (str, bytes, bytearray),
    ):
        return []
    if type(limit) is not int:
        raise TypeError("limit must be an integer")
    bounded_limit = max(1, min(limit, MAX_PROMPT_ENTRIES))
    result: list[PromptEntry] = []
    seen: set[str] = set()
    for value in values:
        entry = (
            value
            if isinstance(value, PromptEntry)
            else PromptEntry.from_value(value)
        )
        if entry is None:
            continue
        prompt = normalize_prompt_text(entry.prompt)
        key = prompt.casefold()
        if not prompt or (deduplicate and key in seen):
            continue
        seen.add(key)
        result.append(
            PromptEntry(
                prompt=prompt,
                references=entry.references,
            )
        )
        if len(result) >= bounded_limit:
            break
    return result


def _mode_data(
    state: ProjectState,
    mode: ProjectMode,
) -> ClipartModeData | PinterestModeData:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    if mode is ProjectMode.CLIPART:
        return state.clipart
    if mode is ProjectMode.PINTEREST:
        return state.pinterest
    raise PromptGeneratorError(
        "Prompt generation is only available for clipart and Pinterest"
    )


def generate_into_project(
    state: ProjectState,
    mode: ProjectMode | str,
    data: PromptGeneratorData,
) -> list[PromptEntry]:
    normalized_mode = (
        mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    )
    target = _mode_data(state, normalized_mode)
    normalized_data = normalize_generator_data(normalized_mode, data)
    target.prompt_generator = PromptGeneratorData.from_dict(
        normalized_data.to_dict()
    )
    target.prompts = generate_prompt_series(normalized_mode, normalized_data)
    return target.prompts


def replace_project_prompts(
    state: ProjectState,
    mode: ProjectMode | str,
    values: Sequence[Any],
    *,
    deduplicate: bool = True,
) -> list[PromptEntry]:
    normalized_mode = (
        mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    )
    target = _mode_data(state, normalized_mode)
    target.prompts = normalize_prompt_entries(values, deduplicate=deduplicate)
    return target.prompts
