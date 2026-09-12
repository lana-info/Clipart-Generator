"""Curated five-color palette library and local recommendation rules."""
from dataclasses import dataclass

from studio_holiday_profiles import FIRST_WAVE_HOLIDAYS, holiday_palette_presets


@dataclass(frozen=True)
class PalettePreset:
    key: str
    title: str
    category: str
    character: str
    colors: tuple[str, ...]

    def validate(self):
        if not all(isinstance(value, str) and value.strip()
                   for value in (self.key, self.title, self.category, self.character)):
            raise ValueError('Неверная карточка палитры')
        if len(self.colors) != 5:
            raise ValueError('Карточка палитры должна содержать ровно 5 цветов')
        return self


def _preset(key, title, category, character, colors):
    return PalettePreset(key, title, category, character, tuple(colors)).validate()


_GENERAL = (
    _preset('spring-garden', 'Весенний сад', 'Сезоны', 'пастельная',
            ('#F2C9CF', '#D7E2C2', '#B8D5E5', '#FFF1D4', '#D6B7C9')),
    _preset('summer-garden', 'Летний сад', 'Сезоны', 'свежая',
            ('#F2C46D', '#E88F77', '#7FB7A3', '#82B9D7', '#F7E8C9')),
    _preset('autumn-ochre', 'Осенняя охра', 'Сезоны', 'насыщенная',
            ('#9C4A2C', '#CE7B3E', '#D9A85F', '#7B6D46', '#E7D5B6')),
    _preset('winter-frost', 'Морозная зима', 'Сезоны', 'приглушённая',
            ('#5C7387', '#9DB4C3', '#D5E2E8', '#EEF3F5', '#B7AFC4')),
    _preset('sea-breeze', 'Морской бриз', 'Природа', 'спокойная',
            ('#2F6273', '#6FA8B8', '#A9CDD5', '#D8C4A6', '#F4EDE1')),
    _preset('forest', 'Лес', 'Природа', 'естественная',
            ('#365A45', '#668064', '#9FA785', '#C7B995', '#E8DFCC')),
    _preset('mountains', 'Горы', 'Природа', 'естественная',
            ('#667B69', '#9FA795', '#C8C0A8', '#8B735D', '#D9D2C3')),
    _preset('sand-clay', 'Песок и глина', 'Природа', 'тёплая',
            ('#D5B28C', '#B9835A', '#A76B4E', '#E2C9A8', '#80604B')),
    _preset('wildflowers', 'Полевые цветы', 'Природа', 'мягкая',
            ('#E5B8C6', '#DCCB79', '#A8C49C', '#AFC7DD', '#F1E5D4')),
    _preset('berries', 'Ягоды', 'Природа', 'насыщенная',
            ('#702D46', '#A84762', '#D8899C', '#71835E', '#F1DFD3')),
    _preset('sage-family', 'Шалфейная', 'Семейства цветов', 'приглушённая',
            ('#73866B', '#95A88B', '#B8C5AE', '#D9DDCC', '#EFE9DD')),
    _preset('dusty-rose', 'Пыльно-розовая', 'Семейства цветов', 'пастельная',
            ('#B86F83', '#CF91A0', '#E2B1BC', '#F1D4DA', '#F7E9E8')),
    _preset('lilac-family', 'Сиренево-лиловая', 'Семейства цветов', 'пастельная',
            ('#766A99', '#9C8FB8', '#BDAFD0', '#DED3E7', '#F2EAF1')),
    _preset('blue-family', 'Голубая', 'Семейства цветов', 'спокойная',
            ('#5F8FA8', '#83ABC0', '#A9C7D5', '#D2E2E7', '#EEF2EE')),
    _preset('gentle-child', 'Нежная детская', 'По назначению', 'пастельная',
            ('#E7C8CF', '#C7D8EA', '#C9D8BB', '#F5EAD7', '#D6C7DD')),
    _preset('vintage-paper', 'Винтажная бумага', 'По назначению', 'приглушённая',
            ('#66584D', '#A68B72', '#C8B89F', '#DED2BD', '#F3EBDD')),
)


def _holiday_presets():
    result = []
    for context in FIRST_WAVE_HOLIDAYS:
        for item in holiday_palette_presets(context):
            result.append(_preset(
                'holiday-' + item['key'], item['title'], item['category'],
                item['character'], item['colors'],
            ))
    return tuple(result)


_HOLIDAYS = _holiday_presets()


def all_palette_presets():
    return _HOLIDAYS + _GENERAL


def palette_categories():
    order = ('Праздники', 'Сезоны', 'Природа', 'Семейства цветов', 'По назначению')
    return tuple(category for category in order if any(p.category == category for p in all_palette_presets()))


def _first(key):
    return next(preset for preset in all_palette_presets() if preset.key == key)


def recommended_palette_presets(theme='', context='', limit=3):
    """Return deterministic local recommendations; holiday canonical card wins first."""
    if type(limit) is not int or not 1 <= limit <= 6:
        raise ValueError('Неверное число рекомендаций палитр')
    result = []
    holiday = holiday_palette_presets(context)
    if holiday:
        result.append(_first('holiday-' + holiday[0]['key']))
    haystack = f'{theme} {context}'.casefold()
    keys = []
    if any(word in haystack for word in ('весн', 'garden', 'сад', 'flower', 'цвет')):
        keys += ['spring-garden', 'wildflowers']
    if any(word in haystack for word in ('лет', 'summer')):
        keys += ['summer-garden', 'sea-breeze']
    if any(word in haystack for word in ('осен', 'autumn', 'fall', 'thanksgiving', 'halloween')):
        keys += ['autumn-ochre', 'vintage-paper']
    if any(word in haystack for word in ('зим', 'winter', 'christmas', 'рождеств')):
        keys += ['winter-frost', 'vintage-paper']
    if any(word in haystack for word in ('baby', 'детск', 'teddy', 'мишка', 'first birthday')):
        keys += ['gentle-child', 'dusty-rose']
    if any(word in haystack for word in ('sea', 'мор', 'beach', 'coastal')):
        keys += ['sea-breeze', 'sand-clay']
    if not keys:
        keys = ['spring-garden', 'gentle-child', 'vintage-paper']
    seen = {item.key for item in result}
    for key in keys:
        item = _first(key)
        if item.key not in seen:
            result.append(item)
            seen.add(item.key)
        if len(result) >= limit:
            break
    if len(result) < limit:
        for item in _GENERAL:
            if item.key not in seen:
                result.append(item)
                seen.add(item.key)
            if len(result) >= limit:
                break
    return tuple(result[:limit])
