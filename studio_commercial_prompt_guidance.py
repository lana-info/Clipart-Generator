"""Deterministic commercial collection and prompt-quality guidance for Clipart."""

from copy import deepcopy

from studio_clipart_objects import OBJECT_ROLES

_PLANNING = {
    "collection_first": True,
    "principles": [
        "commercial_purpose",
        "no_filler",
        "cohesive_style_palette",
        "controlled_variety",
        "no_near_duplicates",
        "reusable_design_asset",
    ],
    "roles": {
        "hero": {
            "goal": "clear focal asset with a strong readable identity",
            "guidance": "vary pose, expression, action or useful prop; for character-like subjects include distinctive traits when relevant",
        },
        "composition": {
            "goal": "small intentional isolated group rather than a background scene",
            "guidance": "keep hierarchy readable and avoid heavy overlap",
        },
        "wreath": {
            "goal": "usable decorative wreath with a clean interior opening",
            "guidance": "balanced spacing; preserve the interior opening and readable outer contour",
        },
        "border": {
            "goal": "usable frame or border with clear negative space",
            "guidance": "preserve interior space for design use and avoid canvas-edge crowding",
        },
        "decor": {
            "goal": "small commercially useful accent",
            "guidance": "prefer compact connected shapes and avoid accidental floating fragments",
        },
    },
}

_PROMPT_GUIDANCE = {
    "ru": {
        "consistency": (
            "единый стиль, палитра и уровень детализации всей коллекции; "
            "объект полностью видим; достаточные поля со всех сторон; читаемый силуэт"
        ),
        "common_restrictions": (
            "без обрезания",
            "без случайных лишних объектов",
            "без случайно дублированных элементов",
        ),
        "composition": {
            "hero": "ясный главный объект с читаемой позой или действием",
            "composition": "небольшая связная изолированная композиция без чрезмерного перекрытия элементов",
            "wreath": "сбалансированный венок; чистое внутреннее отверстие; читаемый внешний контур",
            "border": "читаемая рамка или бордюр; чистое внутреннее пространство; достаточные поля до края холста",
            "decor": "компактный самостоятельный декоративный элемент",
        },
        "role_restrictions": {
            "hero": (),
            "composition": ("без полноценной фоновой сцены",),
            "wreath": ("не закрывать внутреннее отверстие случайным декором",),
            "border": ("не прижимать рамку к краю холста",),
            "decor": ("без случайных плавающих фрагментов",),
        },
    },
    "en": {
        "consistency": (
            "consistent style, palette and detail level across the collection; "
            "subject fully visible; generous margins on all sides; readable silhouette"
        ),
        "common_restrictions": (
            "no cropping",
            "no accidental extra objects",
            "no accidental duplicated elements",
        ),
        "composition": {
            "hero": "clear main subject with a readable pose or action",
            "composition": "small connected isolated composition without excessive overlap",
            "wreath": "balanced wreath; clean interior opening; readable outer contour",
            "border": "readable frame or border; clean interior negative space; safe margin from canvas edges",
            "decor": "compact standalone decorative element",
        },
        "role_restrictions": {
            "hero": (),
            "composition": ("no full background scene",),
            "wreath": ("do not close the interior opening with accidental decor",),
            "border": ("do not crowd the frame against the canvas edge",),
            "decor": ("no accidental floating fragments",),
        },
    },
}


def commercial_planning_hints():
    """Return bounded local guidance; never calls a provider."""
    return deepcopy(_PLANNING)


def prompt_guidance_for_role(role, *, language="ru"):
    """Return language-matched quality constraints for one Clipart object role."""
    if role not in OBJECT_ROLES:
        raise ValueError("Неизвестная роль объекта")
    if language not in _PROMPT_GUIDANCE:
        raise ValueError("language must be 'ru' or 'en'")
    values = _PROMPT_GUIDANCE[language]
    return {
        "composition": values["composition"][role],
        "consistency": values["consistency"],
        "restrictions": tuple(
            values["common_restrictions"] + values["role_restrictions"][role]
        ),
    }
