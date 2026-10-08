"""Bilingual, stable local recipes and compatible presentation choices."""

from __future__ import annotations

from copy import deepcopy

from .model import new_draft
from .directions import DIRECTIONS, SCENARIOS, STYLE_OVERRIDES

# IDs are persisted identifiers. Change text freely, but never recycle an ID.
_OPTIONS = {
    'location': [
        ('studio', 'светлая студия', 'bright studio'),
        ('room', 'уютная комната', 'cozy room'),
        ('garden', 'цветущий сад', 'flowering garden'),
        ('forest', 'лесная поляна', 'forest clearing'),
        ('street', 'тихая городская улица', 'quiet city street'),
        ('coast', 'морское побережье', 'seashore'),
    ],
    'surface': [
        ('wood', 'деревянный стол', 'wooden table'),
        ('stone', 'каменная столешница', 'stone tabletop'),
        ('paper', 'матовая бумага', 'matte paper'),
        ('linen', 'льняная ткань', 'linen fabric'),
        ('glass', 'стеклянная поверхность', 'glass surface'),
        ('sand', 'мелкий песок', 'fine sand'),
    ],
    'aspect': [
        ('square', '1:1', '1:1'),
        ('portrait', '4:5', '4:5'),
        ('vertical', '9:16', '9:16'),
        ('wide', '16:9', '16:9'),
        ('photo', '3:2', '3:2'),
        ('classic', '4:3', '4:3'),
    ],
    'duration': [
        ('three', '3 секунды', '3 seconds'),
        ('five', '5 секунд', '5 seconds'),
        ('eight', '8 секунд', '8 seconds'),
        ('ten', '10 секунд', '10 seconds'),
        ('fifteen', '15 секунд', '15 seconds'),
    ],
    'action': [
        ('turn', 'медленно поворачивается', 'slowly turns'),
        ('rotate', 'плавно вращается', 'gently rotates'),
        ('sway', 'слегка покачивается', 'sways slightly'),
        ('rise', 'медленно поднимается', 'slowly rises'),
        ('lower', 'плавно опускается', 'gently lowers'),
        ('slide', 'плавно скользит вперёд', 'slides gently forward'),
        ('approach', 'медленно приближается', 'slowly approaches'),
        ('retreat', 'медленно отдаляется', 'slowly moves away'),
        ('tilt', 'слегка наклоняется', 'tilts slightly'),
        ('unfold', 'плавно раскрывается', 'gently unfolds'),
        ('fold', 'медленно складывается', 'slowly folds'),
        ('bounce', 'слегка подпрыгивает', 'bounces slightly'),
        ('stop', 'плавно останавливается', 'gently comes to a stop'),
        ('roll', 'медленно перекатывается', 'slowly rolls'),
        ('stretch', 'медленно вытягивается', 'slowly stretches'),
        ('spin', 'делает один оборот', 'makes one full turn'),
        ('shift', 'слегка смещается в сторону', 'shifts slightly to the side'),
        ('vibrate', 'едва заметно вибрирует', 'vibrates subtly'),
        ('lift', 'плавно приподнимается', 'gently lifts up'),
        ('settle', 'мягко оседает', 'settles softly'),
    ],
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


# Legacy recipes remain addressable by persisted IDs and are hidden by scene UIs.
for _legacy_recipe in _TEMPLATES:
    _legacy_recipe["legacy"] = True

_CATEGORIES = [{'id': 'people', 'label': 'Люди'}, {'id': 'products', 'label': 'Товары'}, {'id': 'food', 'label': 'Еда и напитки'}, {'id': 'spaces', 'label': 'Интерьеры и архитектура'}, {'id': 'animals', 'label': 'Животные'}, {'id': 'nature', 'label': 'Природа и путешествия'}]

# Each specification supplies a distinct scene treatment for both output modes.
_SCENE_SPECS = [
    {
        'category': 'people',
        'id': 'portrait',
        'label': 'Портрет',
        'descriptions': ['Выразительный портрет с акцентом на лице.', 'Лёгкий поворот головы и естественная мимика.'],
        'kind': 'person',
        'subject': ('человек', 'person'),
        'location': ('нейтральное пространство с отделённым фоном', 'neutral space with a separated background'),
        'style': ('выразительная портретная фотография с естественной фактурой лица', 'expressive portrait photography with natural facial texture'),
        'lighting': ('мягкий боковой свет с плавными тенями на лице', 'soft side light with gradual facial shadows'),
        'shot': ('крупный план лица с фокусом на глазах', 'close facial framing focused on the eyes'),
        'angle': ('ракурс на уровне глаз в три четверти', 'eye-level three-quarter view'),
        'action': ('слегка поворачивает голову с естественной мимикой одним движением', 'gently turns the head with a natural expression in one movement'),
        'camera': ('неподвижная камера с портретной перспективой', 'locked camera with portrait perspective'),
    },
    {
        'category': 'people',
        'id': 'business',
        'label': 'Деловой портрет',
        'descriptions': ['Профессиональный образ для профиля или сайта.', 'Спокойное обращение к камере в рабочей обстановке.'],
        'kind': 'person',
        'subject': ('человек', 'person'),
        'location': ('спокойная рабочая обстановка без отвлекающих деталей', 'quiet work setting with unobtrusive surroundings'),
        'style': ('сдержанный профессиональный портрет с открытой композицией', 'restrained professional portrait with an open composition'),
        'lighting': ('ровный рассеянный дневной свет на лице', 'even diffused daylight on the face'),
        'shot': ('поясной портрет с пространством вокруг фигуры', 'waist-up portrait with space around the figure'),
        'angle': ('прямой ракурс на уровне глаз', 'front view at eye level'),
        'action': ('спокойно обращается к камере с небольшим естественным жестом', 'calmly addresses the camera with a small natural gesture'),
        'camera': ('неподвижная камера на уровне лица', 'locked camera at face level'),
    },
    {
        'category': 'people',
        'id': 'fashion',
        'label': 'Модная съёмка',
        'descriptions': ['Образ, поза и выразительная композиция.', 'Один плавный поворот с сохранением образа.'],
        'kind': 'person',
        'subject': ('человек', 'person'),
        'location': ('просторная съёмочная площадка с простым фоном', 'spacious shooting area with a simple background'),
        'style': ('редакционная модная съёмка с акцентом на силуэт и позу', 'editorial fashion photography emphasizing silhouette and pose'),
        'lighting': ('направленный мягкий свет, выделяющий силуэт', 'directional soft light defining the silhouette'),
        'shot': ('ростовой кадр с выразительным свободным пространством', 'full-length framing with expressive negative space'),
        'angle': ('слегка низкий ракурс без искажения пропорций', 'slightly low viewpoint without distorted proportions'),
        'action': ('выполняет один плавный поворот с сохранением исходного образа', 'performs one smooth turn preserving the original look'),
        'camera': ('неподвижная камера с естественной перспективой тела', 'locked camera with natural body perspective'),
    },
    {
        'category': 'people',
        'id': 'beauty',
        'label': 'Бьюти',
        'descriptions': ['Макияж и фактура кожи в мягком крупном плане.', 'Небольшой поворот лица в мягком свете.'],
        'kind': 'person',
        'subject': ('человек', 'person'),
        'location': ('нейтральная бьюти-студия с мягким фоном', 'neutral beauty studio with a soft background'),
        'style': ('детальная бьюти-фотография с сохранением реальной фактуры кожи', 'detailed beauty photography preserving real skin texture'),
        'lighting': ('широкий мягкий фронтальный свет без жёстких бликов', 'broad soft frontal light without harsh highlights'),
        'shot': ('очень крупный план лица с читаемой фактурой кожи', 'tight facial close-up with visible skin texture'),
        'angle': ('прямой ракурс на уровне лица', 'front view at face level'),
        'action': ('слегка поворачивает лицо в мягком свете одним движением', 'slightly turns the face in soft light in one movement'),
        'camera': ('неподвижная камера для детального портрета', 'locked camera for a detailed portrait'),
    },
    {
        'category': 'people',
        'id': 'everyday',
        'label': 'Повседневная сцена',
        'descriptions': ['Естественный момент дома или на прогулке.', 'Одно привычное действие в выбранной обстановке.'],
        'kind': 'person',
        'subject': ('человек', 'person'),
        'location': ('естественная повседневная обстановка с простым фоном', 'natural everyday setting with a simple background'),
        'style': ('непостановочная жизненная фотография с естественной позой', 'candid lifestyle photography with a natural pose'),
        'lighting': ('мягкий окружающий дневной свет', 'soft ambient daylight'),
        'shot': ('средний план человека и ближайшего окружения', 'medium framing of the person and immediate surroundings'),
        'angle': ('наблюдательный ракурс на уровне глаз', 'observational viewpoint at eye level'),
        'action': ('делает один спокойный шаг в выбранной обстановке', 'takes one calm step in the chosen setting'),
        'camera': ('спокойная камера с лёгким естественным движением', 'calm camera with slight natural movement'),
    },
    {
        'category': 'people',
        'id': 'ugc_review',
        'label': 'Отзыв в кадре · UGC',
        'descriptions': ['Непостановочный кадр на телефон.', 'Естественная подача на телефон в одном кадре.'],
        'kind': 'person',
        'subject': ('человек', 'person'),
        'location': ('обычная домашняя обстановка без специально добавленного декора', 'ordinary home setting without added staging decor'),
        'style': ('естественная съёмка на телефон с живой фактурой', 'natural phone photography with lifelike texture'),
        'lighting': ('доступный свет из окна без студийного эффекта', 'available window light without a studio effect'),
        'shot': ('погрудный кадр с прямым контактом с камерой', 'chest-up framing with direct camera engagement'),
        'angle': ('фронтальный ракурс телефона на уровне глаз', 'front phone viewpoint at eye level'),
        'action': ('естественно обращается к телефону с небольшим жестом', 'naturally addresses the phone with a small gesture'),
        'camera': ('телефон в устойчивом положении с лёгкой ручной подвижностью', 'steadily held phone with slight handheld movement'),
    },
    {
        'category': 'products',
        'id': 'catalogue',
        'label': 'Каталожная съёмка',
        'descriptions': ['Форма, цвет и детали товара хорошо различимы.', 'Плавный показ товара на нейтральном фоне.'],
        'kind': 'product',
        'subject': ('товар', 'product'),
        'location': ('предметная студия с нейтральным непрерывным фоном', 'product studio with a neutral seamless background'),
        'style': ('чистая каталожная съёмка с точной передачей формы и деталей', 'clean catalogue photography with accurate shape and detail'),
        'lighting': ('равномерный рассеянный свет без потери деталей', 'even diffused light preserving details'),
        'shot': ('товар целиком с достаточным пространством по краям', 'entire product framed with sufficient edge space'),
        'angle': ('ракурс в три четверти на уровне товара', 'three-quarter view at product level'),
        'action': ('остаётся неподвижным на нейтральном фоне', 'remains stationary against a neutral background'),
        'camera': ('камера медленно проходит по небольшой дуге вокруг товара', 'camera slowly moves along a small arc around the product'),
    },
    {
        'category': 'products',
        'id': 'composition',
        'label': 'Композиция с реквизитом',
        'descriptions': ['Товар в центре композиции с уместными деталями.', 'Плавный проход камеры вдоль композиции.'],
        'kind': 'product',
        'subject': ('товар', 'product'),
        'location': ('съёмочная зона с реквизитом только из описания пользователя', 'shooting area with props only from the user description'),
        'style': ('предметная композиция с товаром как главным визуальным центром', 'product composition with the product as the main visual focus'),
        'lighting': ('мягкий направленный свет с разделением планов', 'soft directional light separating depth planes'),
        'shot': ('общий план композиции с доминирующим товаром', 'wide composition framing with the product dominant'),
        'angle': ('приподнятый ракурс в три четверти', 'elevated three-quarter viewpoint'),
        'action': ('остаётся неподвижным среди заданного пользователем реквизита', 'remains stationary among the props specified by the user'),
        'camera': ('камера плавно проходит вдоль одной композиции', 'camera smoothly tracks along one composition'),
    },
    {
        'category': 'products',
        'id': 'on_person',
        'label': 'Демонстрация на человеке',
        'descriptions': ['Посадка, размер и внешний вид товара.', 'Человек одним движением демонстрирует товар.'],
        'kind': 'product',
        'subject': ('товар', 'product'),
        'location': ('нейтральная зона демонстрации без отвлекающего фона', 'neutral demonstration area with an unobtrusive background'),
        'style': ('коммерческая съёмка с акцентом на масштаб и положение товара', 'commercial photography emphasizing product scale and placement'),
        'lighting': ('мягкий ровный свет на человеке и товаре', 'soft even light on the person and product'),
        'shot': ('кадр товара на человеке с достаточным контекстом масштаба', 'framing of the product on a person with sufficient scale context'),
        'angle': ('ракурс в три четверти на уровне демонстрируемого товара', 'three-quarter view at the displayed product level'),
        'action': ('человек одним плавным движением показывает товар, сохраняя его форму', 'a person displays the product in one smooth movement preserving its shape'),
        'camera': ('неподвижная камера с естественными пропорциями', 'locked camera with natural proportions'),
    },
    {
        'category': 'products',
        'id': 'in_use',
        'label': 'Использование товара',
        'descriptions': ['Товар в подходящей повседневной ситуации.', 'Одно понятное действие с товаром.'],
        'kind': 'product',
        'subject': ('товар', 'product'),
        'location': ('повседневная обстановка, соответствующая назначению товара', 'everyday setting appropriate to the product purpose'),
        'style': ('жизненная предметная фотография с ясным способом использования', 'lifestyle product photography with a clear use context'),
        'lighting': ('естественный рассеянный свет с читаемыми деталями товара', 'natural diffused light with readable product details'),
        'shot': ('средний план товара и зоны взаимодействия', 'medium framing of the product and interaction area'),
        'angle': ('ракурс в три четверти с открытой зоной использования', 'three-quarter view exposing the use area'),
        'action': ('человек выполняет одно простое действие по назначению товара', 'a person performs one simple action appropriate to the product purpose'),
        'camera': ('неподвижная камера с фокусом на зоне использования', 'locked camera focused on the use area'),
    },
    {
        'category': 'products',
        'id': 'ugc_hands',
        'label': 'Показывает в руках · UGC',
        'descriptions': ['Естественный крупный кадр товара в руках.', 'Руки медленно поворачивают товар перед камерой.'],
        'kind': 'product',
        'subject': ('товар', 'product'),
        'location': ('простая домашняя зона показа без лишних предметов', 'simple home demonstration area without extra objects'),
        'style': ('естественная предметная съёмка на телефон в руках', 'natural phone product photography held in hands'),
        'lighting': ('мягкий доступный дневной свет на товаре', 'soft available daylight on the product'),
        'shot': ('крупный план товара в руках целиком в границах кадра', 'close framing of the whole product in hands within the frame'),
        'angle': ('фронтальный ракурс на уровне рук', 'front viewpoint at hand level'),
        'action': ('руки медленно поворачивают товар одним движением перед камерой', 'hands slowly turn the product in one movement before the camera'),
        'camera': ('устойчивый телефон с минимальным естественным дрожанием', 'steady phone with minimal natural handheld motion'),
    },
    {
        'category': 'products',
        'id': 'ugc_unboxing',
        'label': 'Распаковка · UGC',
        'descriptions': ['Товар и открытая упаковка в одном кадре.', 'Открытие упаковки в одном непрерывном кадре.'],
        'kind': 'product',
        'subject': ('товар', 'product'),
        'location': ('свободная рабочая поверхность в домашней обстановке', 'clear work surface in a home setting'),
        'style': ('естественная телефонная съёмка распаковки с акцентом на товар', 'natural phone unboxing photography focused on the product'),
        'lighting': ('ровный доступный свет на товаре и упаковке', 'even available light on the product and packaging'),
        'shot': ('товар и его упаковка целиком в одном кадре', 'product and its packaging fully within one frame'),
        'angle': ('приподнятый ракурс на зону распаковки', 'elevated viewpoint onto the unboxing area'),
        'action': ('руки одним движением открывают исходную упаковку товара', 'hands open the original product packaging in one movement'),
        'camera': ('неподвижный телефон с обзором зоны распаковки', 'locked phone overlooking the unboxing area'),
    },
    {
        'category': 'food',
        'id': 'menu',
        'label': 'Фото для меню',
        'descriptions': ['Блюдо хорошо видно, фон не отвлекает.', 'Медленный показ готового блюда.'],
        'kind': 'product',
        'subject': ('блюдо или напиток', 'dish or drink'),
        'location': ('нейтральная зона подачи без отвлекающего фона', 'neutral serving area without a distracting background'),
        'style': ('аппетитная фотография для меню с точной фактурой', 'appetizing menu photography with accurate texture'),
        'lighting': ('мягкий боковой свет для объёма и фактуры еды', 'soft side light for food volume and texture'),
        'shot': ('блюдо или напиток целиком с читаемыми деталями', 'entire dish or drink with readable details'),
        'angle': ('приподнятый ракурс в три четверти', 'elevated three-quarter viewpoint'),
        'action': ('остаётся неподвижным в готовом к подаче виде', 'remains stationary ready to serve'),
        'camera': ('камера медленно приближается к готовому блюду или напитку', 'camera slowly approaches the finished dish or drink'),
    },
    {
        'category': 'food',
        'id': 'table_setting',
        'label': 'Сервировка',
        'descriptions': ['Еда и посуда в продуманной композиции.', 'Плавный проход камеры вдоль сервировки.'],
        'kind': 'product',
        'subject': ('блюдо или напиток', 'dish or drink'),
        'location': ('стол с сервировкой, заданной пользователем', 'table with the place setting specified by the user'),
        'style': ('фуд-фотография с ритмом сервировки и главным блюдом', 'food photography balancing the place setting and main dish'),
        'lighting': ('мягкий дневной свет вдоль поверхности стола', 'soft daylight along the table surface'),
        'shot': ('общий план сервировки с ясным главным объектом', 'wide framing of the place setting with a clear main subject'),
        'angle': ('ракурс сверху с читаемым расположением предметов', 'overhead view with a readable arrangement'),
        'action': ('остаётся неподвижным в заданной сервировке', 'remains stationary in the specified place setting'),
        'camera': ('камера плавно проходит вдоль одной сервировки', 'camera smoothly tracks along one place setting'),
    },
    {
        'category': 'food',
        'id': 'preparation',
        'label': 'Приготовление',
        'descriptions': ['Один выразительный момент приготовления.', 'Одно действие: перемешивание или наливание.'],
        'kind': 'product',
        'subject': ('блюдо или напиток', 'dish or drink'),
        'location': ('чистая зона приготовления с необходимыми рабочими предметами', 'clean preparation area with the necessary working items'),
        'style': ('репортажная фуд-съёмка одного момента приготовления', 'documentary food photography of one preparation moment'),
        'lighting': ('ровный рабочий свет с читаемой фактурой ингредиентов', 'even task lighting with readable ingredient texture'),
        'shot': ('крупный план блюда или напитка и одного рабочего движения', 'close framing of the dish or drink and one working movement'),
        'angle': ('приподнятый боковой ракурс с открытой зоной действия', 'elevated side view exposing the action area'),
        'action': ('рука выполняет одно перемешивающее движение, подходящее блюду или напитку', 'a hand performs one stirring movement appropriate to the dish or drink'),
        'camera': ('неподвижная камера с фокусом на одном действии', 'locked camera focused on one action'),
    },
    {
        'category': 'spaces',
        'id': 'overview',
        'label': 'Обзор помещения',
        'descriptions': ['Планировка, свет и основные предметы интерьера.', 'Плавное движение камеры по одной комнате.'],
        'kind': 'place',
        'subject': ('помещение', 'space'),
        'location': ('одна комната с исходной планировкой и обстановкой', 'one room with its original layout and furnishings'),
        'style': ('архитектурная фотография с естественными пропорциями помещения', 'architectural photography with natural room proportions'),
        'lighting': ('естественный свет помещения с сохранением объёма', 'natural room lighting preserving volume'),
        'shot': ('широкий обзор одной комнаты с ясной глубиной', 'wide view of one room with clear depth'),
        'angle': ('ракурс на уровне глаз с ровными вертикалями', 'eye-level view with straight verticals'),
        'action': ('обстановка остаётся неподвижной в одной комнате', 'furnishings remain stationary in one room'),
        'camera': ('камера плавно движется вперёд внутри одной комнаты', 'camera smoothly moves forward within one room'),
    },
    {
        'category': 'spaces',
        'id': 'detail',
        'label': 'Интерьерная деталь',
        'descriptions': ['Фактуры и предметы обстановки крупным планом.', 'Медленное приближение к детали интерьера.'],
        'kind': 'place',
        'subject': ('помещение', 'space'),
        'location': ('выбранная зона одного помещения без добавленного декора', 'selected area of one room without added decor'),
        'style': ('детальная интерьерная фотография с акцентом на фактуры', 'detailed interior photography emphasizing textures'),
        'lighting': ('мягкий скользящий свет, выявляющий фактуру', 'soft grazing light revealing texture'),
        'shot': ('крупный план выбранной интерьерной детали', 'close framing of the selected interior detail'),
        'angle': ('боковой ракурс с естественной глубиной', 'side view with natural depth'),
        'action': ('выбранная деталь интерьера остаётся неподвижной', 'the selected interior detail remains stationary'),
        'camera': ('камера медленно приближается к одной интерьерной детали', 'camera slowly approaches one interior detail'),
    },
    {
        'category': 'spaces',
        'id': 'exterior',
        'label': 'Внешний вид здания',
        'descriptions': ['Архитектура и окружающее пространство.', 'Плавное движение камеры вдоль фасада.'],
        'kind': 'place',
        'subject': ('здание', 'building'),
        'location': ('пространство перед одним зданием с исходным окружением', 'space in front of one building with its original surroundings'),
        'style': ('архитектурная фотография с ясным ритмом фасада', 'architectural photography with a clear facade rhythm'),
        'lighting': ('ровный наружный дневной свет с читаемым рельефом', 'even outdoor daylight with readable relief'),
        'shot': ('общий план одного здания и ближайшего окружения', 'wide framing of one building and immediate surroundings'),
        'angle': ('ракурс в три четверти с ровными вертикалями', 'three-quarter view with straight verticals'),
        'action': ('здание и его архитектурные элементы остаются неподвижными', 'the building and its architectural elements remain stationary'),
        'camera': ('камера плавно движется вдоль одного фасада', 'camera smoothly tracks along one facade'),
    },
    {
        'category': 'animals',
        'id': 'portrait',
        'label': 'Портрет питомца',
        'descriptions': ['Мордочка, взгляд и фактура шерсти.', 'Естественное движение головы или моргание.'],
        'kind': 'animal',
        'subject': ('животное', 'animal'),
        'location': ('спокойное привычное животному окружение', 'calm surroundings familiar to the animal'),
        'style': ('естественный портрет животного с точной фактурой покрова', 'natural animal portrait with accurate coat texture'),
        'lighting': ('мягкий рассеянный свет с бликом в глазах', 'soft diffused light with catchlights in the eyes'),
        'shot': ('крупный план головы с фокусом на взгляде', 'close head framing focused on the gaze'),
        'angle': ('ракурс на уровне глаз животного', 'viewpoint at the animal eye level'),
        'action': ('слегка поворачивает голову одним естественным движением', 'slightly turns its head in one natural movement'),
        'camera': ('неподвижная камера на уровне животного', 'locked camera at the animal level'),
    },
    {
        'category': 'animals',
        'id': 'play',
        'label': 'Игра',
        'descriptions': ['Выразительный момент игры животного.', 'Одно короткое игровое действие.'],
        'kind': 'animal',
        'subject': ('животное', 'animal'),
        'location': ('свободная безопасная зона для естественного движения', 'clear safe area for natural movement'),
        'style': ('живая анималистическая фотография с читаемой позой', 'lively animal photography with a readable pose'),
        'lighting': ('ровный дневной свет, сохраняющий детали движения', 'even daylight preserving movement details'),
        'shot': ('общий план животного с пространством для движения', 'wide framing of the animal with room for movement'),
        'angle': ('низкий ракурс на уровне животного', 'low viewpoint at the animal level'),
        'action': ('делает один короткий игривый шаг без добавленной игрушки', 'takes one short playful step without an added toy'),
        'camera': ('неподвижная камера с запасом пространства для движения', 'locked camera with room for movement'),
    },
    {
        'category': 'animals',
        'id': 'with_person',
        'label': 'Рядом с человеком',
        'descriptions': ['Естественное взаимодействие с человеком.', 'Одно спокойное взаимодействие в кадре.'],
        'kind': 'animal',
        'subject': ('животное', 'animal'),
        'location': ('спокойная общая зона для человека и животного', 'calm shared area for a person and animal'),
        'style': ('естественная фотография спокойного взаимодействия', 'natural photography of calm interaction'),
        'lighting': ('мягкий общий свет на обоих участниках', 'soft shared light on both participants'),
        'shot': ('средний план животного и человека вместе', 'medium framing of the animal and person together'),
        'angle': ('боковой ракурс на уровне животного', 'side viewpoint at the animal level'),
        'action': ('спокойно приближается к находящемуся рядом человеку одним движением', 'calmly approaches the nearby person in one movement'),
        'camera': ('неподвижная камера, удерживающая обоих в кадре', 'locked camera keeping both within the frame'),
    },
    {
        'category': 'nature',
        'id': 'landscape',
        'label': 'Пейзаж',
        'descriptions': ['Пространство, глубина и выбранное время суток.', 'Плавное движение камеры по одному пейзажу.'],
        'kind': 'place',
        'subject': ('пейзаж', 'landscape'),
        'location': ('открытое природное пространство с ясными планами глубины', 'open natural space with clear depth planes'),
        'style': ('пейзажная фотография с глубиной и естественными деталями', 'landscape photography with depth and natural details'),
        'lighting': ('мягкий наружный свет, согласованный со временем суток', 'soft outdoor light consistent with the time of day'),
        'shot': ('широкий план с передним, средним и дальним планами', 'wide framing with foreground, middle ground and background'),
        'angle': ('ракурс с ровным горизонтом на уровне наблюдателя', 'observer-level viewpoint with a level horizon'),
        'action': ('сохраняет единую географию и естественное состояние окружения', 'maintains consistent geography and the natural environment state'),
        'camera': ('камера медленно панорамирует по одному пейзажу', 'camera slowly pans across one landscape'),
    },
    {
        'category': 'nature',
        'id': 'city',
        'label': 'Городская сцена',
        'descriptions': ['Улица, архитектура и атмосфера места.', 'Непрерывное движение камеры по улице.'],
        'kind': 'place',
        'subject': ('пейзаж', 'landscape'),
        'location': ('одна городская улица с исходной архитектурой', 'one city street with its original architecture'),
        'style': ('городская фотография с перспективой улицы и атмосферой места', 'urban photography with street perspective and local atmosphere'),
        'lighting': ('естественный уличный свет с читаемыми фасадами', 'natural street light with readable facades'),
        'shot': ('широкий план улицы с выраженной точкой схода', 'wide street framing with a clear vanishing point'),
        'angle': ('ракурс пешехода на уровне глаз с ровным горизонтом', 'pedestrian eye-level viewpoint with a level horizon'),
        'action': ('сохраняет неподвижную архитектуру и единую географию улицы', 'maintains stationary architecture and consistent street geography'),
        'camera': ('камера непрерывно движется вперёд вдоль одной улицы', 'camera moves continuously forward along one street'),
    },
    {
        'category': 'nature',
        'id': 'detail',
        'label': 'Атмосферная деталь',
        'descriptions': ['Растение, вода или деталь окружения.', 'Лёгкое естественное движение выбранной детали.'],
        'kind': 'place',
        'subject': ('пейзаж', 'landscape'),
        'location': ('небольшой участок природного окружения выбранной детали', 'small area of the selected detail natural surroundings'),
        'style': ('детальная природная фотография с акцентом на фактуру', 'detailed nature photography emphasizing texture'),
        'lighting': ('мягкий естественный свет на выбранной детали окружения', 'soft natural light on the selected environmental detail'),
        'shot': ('крупный план одной природной детали с мягким фоном', 'close framing of one natural detail with a soft background'),
        'angle': ('боковой ракурс на уровне выбранной детали', 'side viewpoint at the selected detail level'),
        'action': ('выбранная природная деталь слегка движется естественным для неё образом', 'the selected natural detail moves slightly in a way natural to it'),
        'camera': ('неподвижная камера с фокусом на одной природной детали', 'locked camera focused on one natural detail'),
    },
]


def _scene_recipe(spec: dict, mode: str) -> dict:
    details = {key: spec[key] for key in ("style", "lighting", "shot", "angle")}
    details["exclusions"] = (
        "выдуманные надписи и логотипы, незаданный реквизит, искажение формы и анатомии",
        "invented lettering and logos, unspecified props, distorted shape and anatomy",
    )
    recipe = _recipe(
        f"scene_{spec['category']}_{spec['id']}_{mode}", spec["label"],
        spec["descriptions"][mode == "reels"], mode, spec["kind"],
        spec["subject"], spec["location"],
        action=spec["action"], **details,
    )
    # _recipe supplies the compatible legacy video camera; scenes specify their own.
    if mode == "reels":
        recipe["draft"]["fields"]["camera"] = _pair(*spec["camera"])
    else:
        recipe["draft"]["fields"]["action"] = _pair(
            "пойманный в одном кадре момент: " + spec["action"][0],
            "moment captured in one still frame: " + spec["action"][1],
        )
        phone_scene = spec["id"].startswith("ugc_")
        recipe["draft"]["fields"]["camera"] = _pair(
            "камера телефона с естественной перспективой" if phone_scene else "фотокамера с естественной перспективой и точной детализацией",
            "phone camera with natural perspective" if phone_scene else "still camera with natural perspective and precise detail",
        )
        if spec["category"] == "products" and spec["id"] == "ugc_unboxing":
            recipe["draft"]["fields"]["action"] = _pair(
                "руки удерживают открытую исходную упаковку рядом с видимым товаром",
                "hands hold the original packaging open beside the visible product",
            )
            recipe["draft"]["fields"]["surface"] = _pair(
                "свободная поверхность с открытой исходной упаковкой товара",
                "clear surface with the product original packaging open",
            )
    # Relative options apply to the user's current field, including edited values.
    # The empty suffix deliberately retains the current value without inventing one.
    variations = {key: [_pair("", "")] for key in
                  ("style", "lighting", "time", "camera", "shot", "angle")}
    adjustments = {
        "shot": [
            (", немного больше свободного пространства сверху", ", slightly more free space above"),
            (", немного больше свободного пространства слева", ", slightly more free space on the left"),
            (", немного больше свободного пространства справа", ", slightly more free space on the right"),
        ],
        "angle": [
            (", небольшое смещение точки съёмки влево", ", slight viewpoint shift to the left"),
            (", небольшое смещение точки съёмки вправо", ", slight viewpoint shift to the right"),
        ],
        "lighting": [
            (", мягкое заполнение теней", ", gentle shadow fill"),
            (", немного усиленный заполняющий свет", ", slightly stronger fill light"),
        ],
    }
    for key, suffixes in adjustments.items():
        variations[key].extend(_pair(ru, en) for ru, en in suffixes)
    recipe.update(category=spec["category"], reusable=True, variation_options=variations)
    return recipe


_TEMPLATES.extend(_scene_recipe(spec, mode) for mode in ("image", "reels") for spec in _SCENE_SPECS)


def _nested_recipes():
    bases = {(spec["category"], spec["id"]): spec for spec in _SCENE_SPECS}
    for category, direction, label, description, base_id in DIRECTIONS:
        base = bases[category, base_id]
        for scene in SCENARIOS[category, direction]:
            for mode in ("image", "reels"):
                spec = deepcopy(base)
                spec.update(
                    id=f"v2_{direction}_{scene['id']}",
                    label=scene["labels"][mode == "reels"],
                    descriptions=scene["descriptions"],
                    action=scene["action_" + mode],
                    shot=scene["shot"], location=scene["location"],
                    angle=scene.get("angle", ("естественный ракурс, согласованный с выбранным планом",
                                               "natural viewpoint consistent with selected framing")),
                    lighting=scene.get("lighting", ("подходящее выбранной сцене освещение с читаемой фактурой",
                                                     "lighting appropriate to the selected scene with clear texture")),
                )
                style = STYLE_OVERRIDES.get((category, direction), base["style"])
                spec["style"] = tuple(style[i] + "; " + scene["signature"][i] for i in (0, 1))
                recipe = _scene_recipe(spec, mode)
                # The new scenarios explicitly describe a still instant, not a
                # video action prefixed with a still-frame label.
                recipe["draft"]["fields"]["action"] = _pair(*scene["action_" + mode])
                if mode == "reels":
                    recipe["draft"]["fields"]["camera"] = _pair(*scene.get("camera_reels", (
                        "неподвижная камера с естественной перспективой выбранного плана",
                        "locked camera with natural perspective for the selected framing")))
                if direction == "ugc":
                    camera = ("устойчиво удерживаемый телефон с небольшим естественным движением",
                              "steadily held phone with slight natural movement") if mode == "reels" else (
                              "камера телефона с естественной перспективой", "phone camera with natural perspective")
                    recipe["draft"]["fields"]["camera"] = _pair(*camera)
                recipe.update(direction=direction, scenario_id=scene["id"])
                yield recipe


_TEMPLATES.extend(_nested_recipes())


def catalogue() -> dict:
    return {
        "templates": deepcopy(_TEMPLATES),
        "categories": deepcopy(_CATEGORIES),
        "directions": [{"category": category, "id": identifier, "label": label, "description": description}
                       for category, identifier, label, description, base in DIRECTIONS],
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
