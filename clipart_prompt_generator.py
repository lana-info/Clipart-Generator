"""Clipart-owned prompt-series rendering built on shared prompt normalization."""
from __future__ import annotations

from clipart_prompt_schema import ClipartPromptFields, render_clipart_prompt
from chroma_key import chroma_key_prompt_block
from chroma_key_selection import select_chroma_key_color
from prompt_translation import PromptTranslationBackend, translate_prompt_fields
from v3_project_state import (
    MAX_PROMPT_SERIES_COUNT,
    ProjectMode,
    ProjectState,
    PromptEntry,
    PromptGeneratorData,
)
from v3_prompt_generator import (
    PromptGeneratorError,
    normalize_generator_data,
    normalize_prompt_entries,
)


# Shared by ordinary and automatic Clipart; append after choosing the key so
# color words in the rules cannot influence subject-palette detection.
_CUTOUT_PROMPT_RULES = (
    "Flat clean background: no gradients, shadows or textures. The background color "
    "must be absent from the subject; never yellow or green beside yellow or green details. "
    "Wide empty margins; separate elements must not touch each other or frame edges. "
    "Crisp contours: no blur, glow, halo or soft shadows. "
    "Omit nonessential loose threads and strings; essential ones must be thick, bright and continuous. "
    "No tiny detached fragments, confetti, splinters or splashes. "
    "Fully opaque subject; no background color inside its solid parts. "
    "Prefer fewer clean elements over dense ornament."
)


def _prompt_language(data: PromptGeneratorData) -> str:
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
    return "ru" if any(
        any("а" <= character.casefold() <= "я" for character in value)
        for value in values
    ) else "en"


def generate_clipart_prompt_series(
    data: PromptGeneratorData,
    *,
    edge_quality_standard: bool = False,
    translation_backend: PromptTranslationBackend | None = None,
    provider_language: str | None = None,
) -> list[PromptEntry]:
    normalized = normalize_generator_data(ProjectMode.CLIPART, data)
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
            fields = ClipartPromptFields(
                object=subject,
                scene=normalized.theme,
                style=normalized.style,
                palette=normalized.palette,
                composition=normalized.composition,
                background=normalized.background,
                details=variation,
                restrictions=tuple(normalized.restrictions),
                technical_requirements=normalized.consistency,
            )
            source_language = _prompt_language(normalized)
            target_language = provider_language or source_language
            translation = translate_prompt_fields(
                fields.to_dict(),
                source_language=source_language,
                target_language=target_language,
                backend=translation_backend,
            )
            if translation.translated:
                translated = dict(translation.fields)
                translated["restrictions"] = tuple(translated.get("restrictions", ()))
                fields = ClipartPromptFields(**translated)
            prompt = render_clipart_prompt(
                fields,
                language=target_language if translation.translated else source_language,
            )
            chroma_key_color = ""
            if normalized.chroma_key_enabled:
                chroma_key_color = select_chroma_key_color(prompt).color
                try:
                    key_block = chroma_key_prompt_block(
                        chroma_key_color,
                        watercolor=(
                            "watercolor" in " ".join((normalized.style, normalized.theme)).casefold()
                            or "акварел" in " ".join((normalized.style, normalized.theme)).casefold()
                        ),
                        materials=normalized.chroma_key_materials,
                        edge_quality=edge_quality_standard,
                    )
                except ValueError as error:
                    raise PromptGeneratorError(str(error)) from error
                prompt += "\n" + key_block + "\n" + _CUTOUT_PROMPT_RULES
            prompts.append(PromptEntry(prompt=prompt, chroma_key_color=chroma_key_color))
    return normalize_prompt_entries(
        prompts,
        limit=MAX_PROMPT_SERIES_COUNT,
        deduplicate=False,
    )


def generate_clipart_into_project(
    state: ProjectState,
    data: PromptGeneratorData,
) -> list[PromptEntry]:
    if not isinstance(state, ProjectState):
        raise TypeError("state must be a ProjectState")
    normalized = normalize_generator_data(ProjectMode.CLIPART, data)
    state.clipart.prompt_generator = PromptGeneratorData.from_dict(normalized.to_dict())
    state.clipart.prompts = generate_clipart_prompt_series(normalized)
    return state.clipart.prompts
