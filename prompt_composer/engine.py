"""Deterministic, offline selection of at most seven distinct prompt snapshots."""

from __future__ import annotations

from math import gcd, prod
import re

from .catalog import catalogue
from .model import validate_draft

_VARIABLE_KEYS = ("style", "lighting", "time", "camera", "shot", "angle")
_ORDER = (
    "subject", "appearance", "wardrobe", "material", "color", "location",
    "surface", "style", "lighting", "time", "camera", "shot", "angle",
    "action", "duration", "aspect",
)
_EXCLUSION_PREFIXES = {
    "no", "not", "without", "avoid", "exclude", "excluding", "never",
    "не", "без", "исключить", "избегать", "никаких", "никакого",
}
_SCENE_CONFLICTS = (
    "montage", "cut to", "cuts to", "scene 2", "scene two", "multiple scenes",
    "sequence of scenes", "scene change", "transition to", "склейка", "монтаж",
    "смена сцены", "несколько сцен", "кадр 2", "сменить локацию",
)
_SCENE_CAUTIONS = ("then", "after that", "затем", "после этого")


def _normalized(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold()))


def _check_translations(fields: dict) -> None:
    for key, pair in fields.items():
        if pair["ru"].strip() and not pair["en"].strip():
            raise ValueError(f"Поле «{key}» требует английского перевода перед генерацией")
        if pair["en"].strip() and not pair["ru"].strip():
            raise ValueError(f"Поле «{key}» требует русского перевода перед генерацией")


def _exclusion_clauses(fields: dict) -> list[tuple[str, frozenset[str]]]:
    excluded = fields.get("exclusions", {"ru": "", "en": ""})
    clauses = []
    for language in ("ru", "en"):
        for raw in re.split(r"[,;]|\b(?:or|или)\b", excluded[language], flags=re.IGNORECASE):
            tokens = frozenset(_normalized(raw).split()) - _EXCLUSION_PREFIXES
            if tokens:
                clauses.append((language, tokens))
    return clauses


def _excluded_by(pair: dict, clauses: list[tuple[str, frozenset[str]]]) -> str | None:
    for language, tokens in clauses:
        if tokens <= set(_normalized(pair[language]).split()):
            return " ".join(sorted(tokens))
    return None


def _scene_issue(snapshot: dict) -> tuple[str | None, list[str]]:
    if snapshot["mode"] != "reels":
        return None, []
    fields = snapshot["fields"]
    scene_parts = [_normalized(fields.get(key, {}).get(language, ""))
                   for key in fields if key != "exclusions" for language in ("ru", "en")]
    scene_text = " ".join(scene_parts)
    padded = f" {scene_text} "
    for phrase in _SCENE_CONFLICTS:
        for part in scene_parts:
            matches = re.finditer(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", part)
            negation = r"\b(?:no|not|without|avoid|exclude|без|не|никаких)\s+(?:(?:any|sudden|abrupt|rapid|quick|sharp|additional|резких|внезапных|быстрых|дополнительных)\s+){0,3}$"
            if any(not re.search(negation, part[:match.start()]) for match in matches):
                return f"Reels допускает одну непрерывную сцену; уберите «{phrase}» из параметров сцены.", []
    warnings = []
    if any(f" {phrase} " in padded for phrase in _SCENE_CAUTIONS):
        warnings.append("Проверьте, что действие Reels остаётся одним непрерывным эпизодом в одном месте.")
    return None, warnings


def _choice_sets(snapshot: dict, clauses: list[tuple[str, frozenset[str]]]) -> tuple[list[tuple[str, list[dict]]], str | None]:
    options = catalogue()["options"]
    choices = []
    for key in _VARIABLE_KEYS:
        if key in snapshot["locks"]:
            continue
        current = snapshot["fields"].get(key, {"ru": "", "en": ""})
        pool = ([current] if current["ru"].strip() or current["en"].strip() else []) + [
            {"ru": item["ru"], "en": item["en"]} for item in options[key]
        ]
        unique = []
        seen = set()
        for pair in pool:
            semantic = (_normalized(pair["ru"]), _normalized(pair["en"]))
            if semantic in seen:
                continue
            if _excluded_by(pair, clauses):
                continue
            seen.add(semantic)
            unique.append(pair)
        if not unique:
            return [], f"Исключения не оставили допустимых значений для поля «{key}». Измените исключение или параметры."
        choices.append((key, unique))
    return choices, None


def _render(snapshot: dict, language: str) -> str:
    fields = snapshot["fields"]
    subject = fields.get("subject", {}).get(language, "").strip()
    if not subject:
        raise ValueError("Укажите героя или объект в поле «subject» для генерации")
    reels = snapshot["mode"] == "reels"
    if reels:
        action = fields.get("action", {}).get(language, "").strip()
        location = fields.get("location", {}).get(language, "").strip()
        if not action or not location:
            raise ValueError("Для Reels нужны одно действие «action» и одно место «location»")
        start = (f"Одна непрерывная короткая видеосцена: {subject}; место: {location}; действие: {action}. "
                 if language == "ru" else
                 f"One continuous short video scene: {subject}; location: {location}; action: {action}. ")
    else:
        start = f"Один статичный кадр: {subject}. " if language == "ru" else f"One still image: {subject}. "
    excluded_keys = {"subject", "duration"}
    if reels:
        excluded_keys.add("action")
        excluded_keys.add("location")
    keys = tuple(key for key in _ORDER if key not in excluded_keys)
    labels = {
        "ru": {"appearance": "внешность", "wardrobe": "одежда", "material": "материал", "color": "цвет",
               "location": "место", "surface": "поверхность", "style": "стиль", "lighting": "свет",
               "time": "время", "camera": "камера", "shot": "крупность", "angle": "ракурс",
               "action": "действие в кадре", "aspect": "формат"},
        "en": {"appearance": "appearance", "wardrobe": "wardrobe", "material": "material", "color": "color",
               "location": "location", "surface": "surface", "style": "style", "lighting": "lighting",
               "time": "time", "camera": "camera", "shot": "framing", "angle": "angle",
               "action": "captured action", "aspect": "aspect ratio"},
    }
    details = [f"{labels[language][key]}: {fields[key][language].strip()}"
               for key in keys if key in fields and fields[key][language].strip()]
    if reels and fields.get("duration", {}).get(language, "").strip():
        details.append(("пожелание по длительности" if language == "ru" else "preferred duration")
                       + ": " + fields["duration"][language].strip())
    if details:
        start += "; ".join(details) + ". "
    exclusions = fields.get("exclusions", {}).get(language, "").strip()
    if exclusions:
        start += ("Исключить: " if language == "ru" else "Exclude: ") + exclusions + ". "
    return start.strip()


def _at_ordinal(choices: list[tuple[str, list[dict]]], ordinal: int) -> dict[str, dict]:
    result = {}
    for key, values in choices:
        ordinal, index = divmod(ordinal, len(values))
        result[key] = values[index]
    return result


def generate_variants(draft: dict, limit: int = 7) -> dict:
    """Generate up to ``limit`` untouched JSON snapshots, never using a service.

    ``selection_seed`` is a non-wrapping cursor. Persist ``next_seed`` to ask for
    further combinations; after exhaustion the result is explicitly insufficient.
    """
    if type(limit) is not int or not 1 <= limit <= 7:
        raise ValueError("limit must be an integer from 1 to 7")
    snapshot = validate_draft(draft)
    if snapshot["manual_en"] is not None or snapshot["manual_ru"] is not None:
        raise ValueError("Сначала сохраните ручной текст копией или явно замените его новой сборкой")
    _check_translations(snapshot["fields"])
    # Validate required bilingual scene properties even if there is no option space.
    _render(snapshot, "en")
    _render(snapshot, "ru")
    scene_error, scene_warnings = _scene_issue(snapshot)
    if scene_error:
        return {"status": "insufficient", "variants": [], "reason": scene_error,
                "next_seed": snapshot["selection_seed"]}
    clauses = _exclusion_clauses(snapshot["fields"])
    for key, pair in snapshot["fields"].items():
        if key == "exclusions" or (snapshot["mode"] == "image" and key == "duration"):
            continue
        if key in snapshot["locks"] or key not in _VARIABLE_KEYS:
            conflict = _excluded_by(pair, clauses)
            if conflict:
                return {"status": "insufficient", "variants": [],
                        "reason": f"Исключение «{conflict}» конфликтует с полем «{key}». Измените исключение или значение поля.",
                        "next_seed": snapshot["selection_seed"]}
    choices, choice_error = _choice_sets(snapshot, clauses)
    if choice_error:
        return {"status": "insufficient", "variants": [], "reason": choice_error,
                "next_seed": snapshot["selection_seed"]}
    total = prod(len(values) for _, values in choices)
    cursor = snapshot["selection_seed"]
    count = min(limit, max(0, total - cursor))
    # A coprime stride spreads consecutive results across several axes while
    # still visiting every semantic tuple exactly once before exhaustion.
    stride = 997
    while gcd(stride, total) != 1:
        stride += 2
    variants = []
    for offset in range(count):
        resolved = validate_draft(snapshot)
        selected = _at_ordinal(choices, ((cursor + offset) * stride) % total)
        resolved["fields"].update(selected)
        resolved["selection_seed"] = cursor + offset
        resolved["base_en"] = _render(resolved, "en")
        resolved["base_ru"] = _render(resolved, "ru")
        resolved["translation_stale"] = False
        changed = [key for key, pair in selected.items() if pair != snapshot["fields"].get(key)]
        difference = ", ".join(resolved["fields"][key]["ru"] for key in changed[:2])
        variants.append({
            "label": f"Вариант {cursor + offset + 1}" + (f": {difference}" if difference else ""),
            "draft": resolved, "en": resolved["base_en"], "ru": resolved["base_ru"],
            "source": "local", "warnings": scene_warnings[:],
        })
    if count == limit:
        return {"status": "complete", "variants": variants, "reason": "", "next_seed": cursor + count}
    movable = ", ".join(key for key in _VARIABLE_KEYS if key in snapshot["locks"])
    reason = (f"Доступно только {count} из {limit} новых сочетаний. "
              + (f"Освободите закреплённые поля: {movable}." if movable else "Сочетания исчерпаны."))
    return {"status": "insufficient", "variants": variants, "reason": reason, "next_seed": cursor + count}


def preflight_ai(draft: dict) -> None:
    """Reject required-field and frozen-constraint conflicts, not catalogue limits.

    AI may fill blank, unlocked fields and invent values outside local choice pools.
    """
    from .model import FIELD_KEYS
    snapshot = validate_draft(draft)
    _check_translations(snapshot['fields'])
    _render(snapshot, 'en')
    _render(snapshot, 'ru')
    validate_single_scene(snapshot)
    clauses = _exclusion_clauses(snapshot['fields'])
    for key in set(snapshot['locks']) | {'subject'}:
        pair = snapshot['fields'].get(key, {'ru': '', 'en': ''})
        if _excluded_by(pair, clauses):
            raise ValueError(f'Закреплённое поле «{key}» противоречит исключениям.')
    if set(FIELD_KEYS) <= set(snapshot['locks']) | {'subject', 'exclusions'}:
        raise ValueError('Все направления изменения закреплены. Освободите несколько параметров.')


def validate_single_scene(draft: dict) -> list[str]:
    issue, warnings = _scene_issue(draft)
    if issue:
        raise ValueError(issue)
    return warnings
