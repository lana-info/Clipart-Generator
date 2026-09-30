"""Bilingual, stable local recipes and compatible presentation choices."""

from __future__ import annotations

from copy import deepcopy

from .model import new_draft

# IDs are persisted identifiers. Change text freely, but never recycle an ID.
_OPTIONS = {
    "style": [
        ("natural", "естественная фотография", "natural photography"),
        ("editorial", "редакционная фотография", "editorial photography"),
        ("commercial", "сдержанная коммерческая съёмка", "restrained commercial photography"),
        ("film", "мягкая плёночная эстетика", "soft film aesthetic"),
        ("illustration", "детальная иллюстрация", "detailed illustration"),
        ("minimal", "минималистичная композиция", "minimalist composition"),
    ],
    "lighting": [
        ("window", "мягкий свет из окна", "soft window light"),
        ("daylight", "чистый дневной свет", "clear daylight"),
        ("side", "выразительный боковой свет", "expressive side light"),
        ("backlit", "мягкий контровой свет", "soft backlight"),
        ("studio", "рассеянный студийный свет", "diffused studio light"),
        ("overcast", "ровный пасмурный свет", "even overcast light"),
    ],
    "time": [
        ("morning", "утро", "morning"), ("midday", "полдень", "midday"),
        ("afternoon", "после полудня", "afternoon"),
        ("golden", "золотой час", "golden hour"),
        ("evening", "вечер", "evening"), ("night", "ночь", "night"),
    ],
    "camera": [
        ("tripod", "неподвижная камера на штативе", "locked tripod camera"),
        ("phone", "естественная камера телефона", "natural phone camera"),
        ("portrait", "портретный объектив", "portrait lens"),
        ("fifty", "объектив 50 мм", "50mm lens"),
        ("wide", "широкоугольный объектив", "wide-angle lens"),
        ("macro", "макрообъектив", "macro lens"),
    ],
    "shot": [
        ("macro", "макроплан", "macro framing"),
        ("close", "крупный план", "close-up framing"),
        ("medium", "средний план", "medium framing"),
        ("full", "общий план", "wide framing"),
        ("detail", "акцент на детали", "detail framing"),
        ("balanced", "сбалансированный план", "balanced framing"),
    ],
    "angle": [
        ("front", "прямой ракурс", "front view"),
        ("three_quarter", "ракурс в три четверти", "three-quarter view"),
        ("overhead", "ракурс сверху", "overhead view"),
        ("low", "низкий ракурс", "low-angle view"),
        ("side", "боковой ракурс", "side view"),
        ("eye", "ракурс на уровне глаз", "eye-level view"),
    ],
}


def _pair(ru: str, en: str) -> dict:
    return {"ru": ru, "en": en}


def _recipe(identifier: str, label: str, description: str, mode: str,
            kind: str, subject: tuple[str, str], location: tuple[str, str],
            action: tuple[str, str] | None = None, **details: tuple[str, str]) -> dict:
    draft = new_draft()
    draft["mode"] = mode
    draft["subject_type"] = kind
    draft["name"] = label
    draft["fields"] = {
        "subject": _pair(*subject), "location": _pair(*location),
        "style": _pair(*details.pop("style", ("естественная фотография", "natural photography"))),
        "lighting": _pair(*details.pop("lighting", ("мягкий свет из окна", "soft window light"))),
        "shot": _pair(*details.pop("shot", ("средний план", "medium framing"))),
        "angle": _pair(*details.pop("angle", ("ракурс на уровне глаз", "eye-level view"))),
        "aspect": _pair("9:16" if mode == "reels" else "4:5", "9:16" if mode == "reels" else "4:5"),
    }
    for key, value in details.items():
        draft["fields"][key] = _pair(*value)
    if action is not None:
        draft["fields"]["action"] = _pair(*action)
    if mode == "reels":
        assert action is not None
        draft["fields"]["camera"] = _pair("неподвижная камера на штативе", "locked tripod camera")
        draft["fields"]["duration"] = _pair("8 секунд", "8 seconds")
    return {"id": identifier, "label": label, "description": description, "draft": draft}


_TEMPLATES = [
    # Seven recipes adapted from the TrendWatcher Content Studio inventory.
    _recipe("tw_morning_look", "Утренний образ", "Естественный портрет в начале дня.", "image", "person", ("женщина в простом утреннем образе", "woman in a simple morning outfit"), ("светлая спальня у окна", "bright bedroom by a window"), wardrobe=("льняная рубашка", "linen shirt")),
    _recipe("tw_man_at_work", "Мужчина в деле", "Портрет человека за привычной работой.", "image", "person", ("мастер за работой", "craftsperson at work"), ("мастерская с инструментами", "workshop with tools"), action=("обрабатывает деталь руками", "works on a small piece by hand")),
    _recipe("tw_mature_audience", "Зрелая аудитория", "Спокойный жизненный портрет.", "image", "person", ("пожилая женщина с естественной мимикой", "older woman with a natural expression"), ("уютная гостиная", "comfortable living room"), style=("редакционная фотография", "editorial photography")),
    _recipe("tw_living_portrait", "Живой портрет", "Непостановочный портрет персонажа.", "image", "character", ("любопытный персонаж в зелёном плаще", "curious character in a green coat"), ("тихая городская улица", "quiet city street"), shot=("крупный план", "close-up framing")),
    _recipe("tw_product_in_life", "Товар в жизни", "Предмет в узнаваемой бытовой обстановке.", "image", "product", ("керамическая кружка ручной работы", "handmade ceramic mug"), ("домашняя кухня", "home kitchen"), surface=("деревянный стол", "wooden table")),
    _recipe("tw_unboxing", "Распаковка товара", "Одна непрерывная распаковка.", "reels", "product", ("коробка с керамической чашкой", "box containing a ceramic cup"), ("домашний стол", "table at home"), ("руки открывают коробку и достают чашку одним движением", "hands open the box and lift out the cup in one continuous action")),
    _recipe("tw_character_micro_story", "Мини-история персонажа", "Одно действие персонажа без смены места.", "reels", "character", ("маленький лисёнок в синем шарфе", "small fox in a blue scarf"), ("лесная тропинка", "forest path"), ("поднимает опавший лист и рассматривает его", "picks up a fallen leaf and studies it")),
    # Seven new still-image scenes.
    _recipe("image_paper_podium", "Товар на бумажном подиуме", "Товарная композиция с мягкими бумажными формами.", "image", "product", ("матовый флакон сыворотки", "matte serum bottle"), ("чистая студия", "clean studio"), surface=("сложенный бумажный подиум", "folded paper podium"), style=("сдержанная коммерческая съёмка", "restrained commercial photography")),
    _recipe("image_botanical_still_life", "Ботанический натюрморт", "Растения и предметы в спокойной композиции.", "image", "object", ("веточки эвкалипта и стеклянная ваза", "eucalyptus sprigs and a glass vase"), ("светлая комната", "bright room"), surface=("каменная столешница", "stone tabletop"), angle=("ракурс в три четверти", "three-quarter view")),
    _recipe("image_pet_window", "Питомец у окна", "Животное в естественном домашнем свете.", "image", "animal", ("рыжий кот с белой грудкой", "ginger cat with a white chest"), ("подоконник в тихой комнате", "windowsill in a quiet room"), shot=("крупный план", "close-up framing")),
    _recipe("image_greeting_card", "Иллюстрация для открытки", "Цельная иллюстрация с ясным главным образом.", "image", "character", ("маленький медведь с букетом", "small bear holding a bouquet"), ("цветущий сад", "flowering garden"), style=("детальная иллюстрация", "detailed illustration")),
    _recipe("image_handmade_texture", "Фактура ручной работы", "Фактура изделия вблизи.", "image", "object", ("вязаный шерстяной шарф", "knitted wool scarf"), ("ремесленная мастерская", "craft workshop"), material=("объёмные шерстяные петли", "raised wool stitches"), shot=("макроплан", "macro framing")),
    _recipe("image_workshop_portrait", "Портрет в мастерской", "Человек и материалы его работы.", "image", "person", ("гончар за кругом", "potter at a wheel"), ("керамическая мастерская", "ceramics studio"), appearance=("руки в глине", "clay-covered hands")),
    _recipe("image_backlit_dessert", "Десерт в контровом свете", "Аппетитная фактура на одном кадре.", "image", "product", ("ягодный тарт", "berry tart"), ("столик небольшого кафе", "table in a small cafe"), lighting=("мягкий контровой свет", "soft backlight"), shot=("крупный план", "close-up framing")),
    # Seven new Reels scenes. Each action happens once in one location.
    _recipe("reels_cup_turn", "Чашка поворачивается в руке", "Рука показывает форму одной чашки.", "reels", "product", ("керамическая чашка", "ceramic cup"), ("стол у окна", "table by a window"), ("рука медленно поворачивает чашку", "a hand slowly turns the cup")),
    _recipe("reels_fabric_window", "Ткань у окна", "Ткань слегка колышется в одном кадре.", "reels", "object", ("льняная занавеска", "linen curtain"), ("окно светлой комнаты", "window in a bright room"), ("ткань мягко колышется от лёгкого воздуха", "the fabric gently sways in a light breeze")),
    _recipe("reels_petal_fall", "Лепесток падает на стол", "Один лепесток опускается на поверхность.", "reels", "object", ("розовый лепесток", "pink petal"), ("стол в саду", "table in a garden"), ("лепесток медленно падает на стол", "the petal slowly falls onto the table")),
    _recipe("reels_cocoa_stir", "Ложка размешивает какао", "Одно плавное движение ложки.", "reels", "product", ("чашка горячего какао", "cup of hot cocoa"), ("кухонный стол", "kitchen table"), ("ложка плавно размешивает какао", "a spoon gently stirs the cocoa")),
    _recipe("reels_brush_paper", "Кисть касается бумаги", "Появляется один мазок краски.", "reels", "object", ("кисть с синей краской", "brush loaded with blue paint"), ("стол художника", "artist's table"), ("кисть проводит один мазок по бумаге", "the brush draws one stroke across the paper")),
    _recipe("reels_cat_blink", "Кот медленно моргает", "Тихий момент с питомцем.", "reels", "animal", ("полосатый домашний кот", "striped house cat"), ("подоконник", "windowsill"), ("кот медленно моргает, глядя в камеру", "the cat slowly blinks toward the camera")),
    _recipe("reels_bottle_drop", "Капля на флаконе", "Капля проходит по поверхности флакона.", "reels", "product", ("стеклянный флакон с кремом", "glass skincare bottle"), ("чистый студийный стол", "clean studio table"), ("капля медленно стекает по флакону", "one drop slowly runs down the bottle"), shot=("макроплан", "macro framing")),
]


def catalogue() -> dict:
    return {
        "templates": deepcopy(_TEMPLATES),
        "options": {key: [{"id": option_id, "ru": ru, "en": en} for option_id, ru, en in values]
                    for key, values in _OPTIONS.items()},
        "subject_types": [
            {"id": "person", "label": "Человек"}, {"id": "character", "label": "Персонаж"},
            {"id": "animal", "label": "Животное"}, {"id": "product", "label": "Товар"},
            {"id": "object", "label": "Предмет"}, {"id": "place", "label": "Место"},
        ],
    }


def apply_template(template_id: str) -> dict:
    for recipe in _TEMPLATES:
        if recipe["id"] == template_id:
            return deepcopy(recipe["draft"])
    raise ValueError(f"Unknown template: {template_id}")
