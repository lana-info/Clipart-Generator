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


class PromptGeneratorError(ValueError):
    pass


PROMPT_SECTION_LENGTH = 2000
PROMPT_RESTRICTIONS_LENGTH = 3000


def normalize_prompt_text(value: Any, *, limit: int = MAX_TEXT_LENGTH) -> str:
    if not isinstance(value, str):
        return ""
    if type(limit) is not int or not 1 <= limit <= MAX_TEXT_LENGTH:
        raise ValueError(f"limit must be between 1 and {MAX_TEXT_LENGTH}")
    normalized = unicodedata.normalize("NFKC", value[: limit * 4])
    safe_characters: list[str] = []
    for character in normalized:
        if character.isspace():
            safe_characters.append(" ")
        elif not unicodedata.category(character).startswith("C"):
            safe_characters.append(character)
    return " ".join("".join(safe_characters).split())[:limit]


def _normalize_unique_strings(
    values: Sequence[Any],
    *,
    limit: int,
) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_prompt_text(value, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
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
    defaults = prompt_generator_defaults(mode)
    subjects = _normalize_unique_strings(
        data.subjects,
        limit=MAX_PROMPT_SERIES_COUNT,
    )
    restrictions = _normalize_unique_strings(
        [*defaults.restrictions, *data.restrictions],
        limit=MAX_PROMPT_SERIES_COUNT,
    )
    return PromptGeneratorData(
        theme=normalize_prompt_text(data.theme, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH),
        subjects=subjects,
        style=normalize_prompt_text(data.style, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        or defaults.style,
        palette=normalize_prompt_text(data.palette, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        or defaults.palette,
        composition=normalize_prompt_text(data.composition, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        or defaults.composition,
        background=normalize_prompt_text(data.background, limit=MAX_PROMPT_GENERATOR_TEXT_LENGTH)
        or defaults.background,
        restrictions=restrictions,
        count=data.count,
    )


def _mode_instruction(mode: ProjectMode) -> str:
    if mode is ProjectMode.CLIPART:
        return (
            "Output intent: one clean isolated clipart asset, suitable for "
            "background removal and a consistent PNG set."
        )
    return (
        "Output intent: one complete vertical Pinterest image generated from "
        "this prompt, not a layered layout or publishing action."
    )


def generate_prompt_series(
    mode: ProjectMode | str,
    data: PromptGeneratorData,
) -> list[PromptEntry]:
    normalized_mode = (
        mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    )
    normalized = normalize_generator_data(normalized_mode, data)
    if not normalized.theme and not normalized.subjects:
        raise PromptGeneratorError("A theme or at least one subject is required")

    subjects = normalized.subjects or [normalized.theme]
    prompts: list[PromptEntry] = []
    for index in range(normalized.count):
        subject = subjects[index % len(subjects)]
        restrictions = normalize_prompt_text(
            "; ".join(normalized.restrictions),
            limit=PROMPT_RESTRICTIONS_LENGTH,
        )
        prompt_parts = [
            _mode_instruction(normalized_mode),
            (
                f"Series item {index + 1} of {normalized.count}: create a "
                "distinct pose, arrangement, or interpretation while preserving "
                "the shared art direction."
            ),
            f"Restrictions: {restrictions}.",
            (
                "Series consistency: keep the same visual language, rendering "
                "quality, palette logic, and scale across the complete set."
            ),
            "Theme: "
            + normalize_prompt_text(
                normalized.theme or subject,
                limit=PROMPT_SECTION_LENGTH,
            )
            + ".",
            "Subject or scene: "
            + normalize_prompt_text(subject, limit=PROMPT_SECTION_LENGTH)
            + ".",
            "Style: "
            + normalize_prompt_text(normalized.style, limit=PROMPT_SECTION_LENGTH)
            + ".",
            "Palette: "
            + normalize_prompt_text(normalized.palette, limit=PROMPT_SECTION_LENGTH)
            + ".",
            "Composition: "
            + normalize_prompt_text(
                normalized.composition,
                limit=PROMPT_SECTION_LENGTH,
            )
            + ".",
            "Background: "
            + normalize_prompt_text(
                normalized.background,
                limit=PROMPT_SECTION_LENGTH,
            )
            + ".",
        ]
        prompt = normalize_prompt_text(" ".join(prompt_parts))
        prompts.append(PromptEntry(prompt=prompt))
    return normalize_prompt_entries(prompts, limit=normalized.count)


def normalize_prompt_entries(
    values: Sequence[Any],
    *,
    limit: int = MAX_PROMPT_ENTRIES,
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
        if not prompt or key in seen:
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
) -> list[PromptEntry]:
    normalized_mode = (
        mode if isinstance(mode, ProjectMode) else ProjectMode(mode)
    )
    target = _mode_data(state, normalized_mode)
    target.prompts = normalize_prompt_entries(values)
    return target.prompts
