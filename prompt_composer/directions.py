"""Approved navigation groups and bilingual scenario data, without draft state."""

from .scenario_people_products import SCENARIOS as PEOPLE_PRODUCTS
from .scenario_other import SCENARIOS as OTHER


# base selects a compatible, preserved recipe for light, camera and neutral hero.
DIRECTIONS = [
    ("people", "portrait", "Портреты", "Классический, деловой или эмоциональный портрет.", "portrait"),
    ("people", "fashion", "Модная и каталожная", "Одежда, образ и поза в кадре.", "fashion"),
    ("people", "editorial", "Редакционная съёмка", "Выразительная журнальная композиция.", "fashion"),
    ("people", "beauty", "Бьюти", "Лицо, макияж и фактура кожи.", "beauty"),
    ("people", "lifestyle", "Lifestyle", "Естественные сцены повседневной жизни.", "everyday"),
    ("people", "ugc", "UGC", "Обращение, отзыв или показ на телефон.", "ugc_review"),
    ("products", "catalogue", "Каталожная съёмка", "Товар, его детали и упаковка.", "catalogue"),
    ("products", "composition", "Предметная композиция", "Раскладки и сочетания с реквизитом.", "composition"),
    ("products", "on_person", "На человеке", "Одежда, аксессуары и масштаб товара.", "on_person"),
    ("products", "lifestyle", "Lifestyle", "Товар в привычной обстановке.", "in_use"),
    ("products", "ugc", "UGC", "Распаковка, впечатления и использование.", "ugc_hands"),
    ("products", "handmade", "Handmade / Etsy", "Изделие, процесс создания и упаковка.", "composition"),
    ("food", "menu", "Для меню", "Блюдо или напиток в понятной подаче.", "menu"),
    ("food", "serving", "Подача и сервировка", "Стол, посуда и сочетание блюд.", "table_setting"),
    ("food", "cooking", "Приготовление", "Ингредиенты, процесс и фактура.", "preparation"),
    ("food", "ugc", "UGC", "Проба, впечатления и домашняя подача.", "preparation"),
    ("spaces", "interior", "Интерьер", "Помещение и его функциональные зоны.", "overview"),
    ("spaces", "architecture", "Архитектура", "Здание, фасад и окружение.", "exterior"),
    ("spaces", "atmosphere", "Атмосфера", "Свет, материалы и выразительные детали.", "detail"),
    ("animals", "portrait", "Портрет питомца", "Внешность, взгляд и характер.", "portrait"),
    ("animals", "everyday", "Повседневная жизнь", "Питомец в привычной обстановке.", "portrait"),
    ("animals", "story", "Игра и мини-истории", "Небольшое естественное действие.", "play"),
    ("nature", "landscape", "Пейзаж", "Природный вид и выразительный свет.", "landscape"),
    ("nature", "travel", "Путешествие", "Места, прогулки и взгляд от первого лица.", "city"),
    ("nature", "detail", "Детали и эстетика", "Цвет, свет и небольшие находки.", "detail"),
]

SCENARIOS = {**PEOPLE_PRODUCTS, **OTHER}

STYLE_OVERRIDES = {
    ("people", "editorial"): ("выразительная журнальная фотография с осмысленной композицией", "expressive editorial photography with deliberate composition"),
    ("products", "handmade"): ("товарная фотография ручной работы с точной фактурой", "handmade product photography with accurate texture"),
    ("animals", "everyday"): ("естественная фотография животного в привычной обстановке", "natural animal photography in familiar surroundings"),
    ("nature", "travel"): ("естественная фотография путешествия с атмосферой места", "natural travel photography with a sense of place"),
    ("food", "ugc"): ("естественная съёмка еды на телефон с домашней подачей", "natural phone food photography with home presentation"),
}
