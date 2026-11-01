"""Deterministic commercial collection and prompt-quality guidance for Clipart."""

from copy import deepcopy

from studio_clipart_objects import OBJECT_ROLES

_PLANNING = {
    "collection_first": True,
    "material_policy": (
        "All subjects and decorative details must be fully opaque. Do not propose "
        "glass, transparent or translucent materials, see-through petals, tulle, "
        "veils, smoke, mist or glow. Watercolor is an opaque painted texture, "
        "never a translucent wash. If a theme implies a transparent material, "
        "depict it as a solid opaque illustration. Background and real gaps "
        "between parts are removed later; preserve clean, anti-aliased boundaries."
    ),
    "detail_policy": (
        "Plan one readable asset per image, not a contact sheet of miniature assets. "
        "A small decorative accent describes its use, not a tiny subject on the canvas. "
        "Keep the complete asset large in frame with safe margins. Preserve explicitly "
        "requested counts; otherwise prefer fewer clearly formed flowers and leaves "
        "over dense micro-detail: distinct petals, coherent "
        "flower centres, continuous stems and intentional branch junctions. Do not "
        "invent fused, melted or floating parts. Gentle or watercolor styling means "
        "colour and painted texture, not defocus, blurred boundaries or translucent petals. "
        "Clean quality outranks lushness: for wreaths and borders plan five to eight large "
        "clearly formed flowers with a few leaves and berries, never wildflower or meadow-grass "
        "wording, clusters of tiny blossoms or filler sprigs; near-white palette tones belong "
        "to petals, never to a backing or surface behind the subject."
    ),
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
            "объект полностью видим; достаточные поля со всех сторон; читаемый силуэт; "
            "все части объекта полностью непрозрачны; акварель только как текстура "
            "непрозрачной краски; это правило важнее описания материала; "
            "один готовый элемент крупно в кадре с сохранением полей, не лист миниатюр; "
            "мелкий декор не означает маленькое изображение на холсте; "
            "каждый лепесток и лист различим, центры цветов оформлены, стебли непрерывны, "
            "соединения ветвей естественны; сохранять заданное количество элементов, "
            "иначе предпочитать меньше ясно прорисованных деталей вместо скопления "
            "микродеталей; "
            "мягкость стиля относится к цвету и фактуре, не к резкости контура"
        ),
        "common_restrictions": (
            "без обрезания",
            "без случайных лишних объектов",
            "без случайно дублированных элементов",
            "без размытия, расфокуса, размазанных или сросшихся лепестков и листьев, "
            "бесформенных цветов и оборванных стеблей",
            "без стекла, просвечивающих лепестков, полупрозрачных материалов, "
            "тюля, вуалей, дыма, тумана и свечения; фон не просвечивает сквозь объект",
            "без белой или кремовой подложки, ореола, контура-наклейки и белых пятен "
            "за частями объекта и между ними; фон между элементами чистый",
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
            "subject fully visible; generous margins on all sides; readable silhouette; "
            "all parts of the subject fully opaque; watercolor only as an opaque "
            "painted texture; this rule overrides material descriptions; "
            "one finished asset large in frame with safe margins, not a contact sheet; "
            "small decorative use does not mean a tiny image on the canvas; "
            "distinct petals and leaves, coherent flower centres, continuous stems "
            "and natural branch junctions; preserve requested counts, otherwise prefer "
            "fewer clearly formed details over crowded micro-detail; "
            "softness describes colour and texture, not edge focus"
        ),
        "common_restrictions": (
            "no cropping",
            "no accidental extra objects",
            "no accidental duplicated elements",
            "no blur, defocus, smeared or fused petals and leaves, malformed flowers or broken stems",
            "no glass, see-through petals, translucent or semi-transparent materials, "
            "tulle, veils, smoke, mist or glow; background never shows through the subject",
            "no white or cream backing, halo, sticker outline or white patches behind "
            "or between parts of the subject; the background between elements stays clean",
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


# Only wreaths and borders are made of flowers; any other subject must not be told to grow them.
_FLOWER_RULE = {
    "ru": (
        "для венков и рамок 5-8 крупных ясно прорисованных цветков, "
        "без россыпи мелких цветов, полевых трав и заполняющих веточек; "
        "почти белые тона палитры только для лепестков, не для подложки"
    ),
    "en": (
        "for wreaths and borders use 5-8 large clearly formed flowers, no clusters of "
        "tiny flowers, wildflower grass or filler sprigs; near-white palette tones "
        "only for petals, never for a backing"
    ),
}
_FLOWER_ROLES = ("wreath", "border")


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
    consistency = values["consistency"]
    if role in _FLOWER_ROLES:
        consistency = f"{consistency}; {_FLOWER_RULE[language]}"
    return {
        "composition": values["composition"][role],
        "consistency": consistency,
        "restrictions": tuple(
            values["common_restrictions"] + values["role_restrictions"][role]
        ),
    }
