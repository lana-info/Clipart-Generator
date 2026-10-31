"""Local, brand-neutral Clipart style profiles and deterministic recommendations."""
from dataclasses import dataclass


@dataclass(frozen=True)
class StyleModifier:
    key: str
    title: str
    prompt_phrase: str
    aliases: tuple[str, ...] = ()

    def validate(self):
        if not all(isinstance(value, str) and value.strip()
                   for value in (self.key, self.title, self.prompt_phrase)):
            raise ValueError('Неверный модификатор стиля')
        if len(self.prompt_phrase) > 500:
            raise ValueError('Модификатор стиля слишком длинный')
        return self


@dataclass(frozen=True)
class StyleProfile:
    key: str
    title: str
    category: str
    prompt_phrase: str
    best_for: tuple[str, ...]
    aliases: tuple[str, ...] = ()
    default_modifiers: tuple[str, ...] = ()

    def validate(self):
        if not all(isinstance(value, str) and value.strip()
                   for value in (self.key, self.title, self.category, self.prompt_phrase)):
            raise ValueError('Неверный профиль стиля')
        if len(self.prompt_phrase) > 1000 or not self.best_for:
            raise ValueError('Неверное описание профиля стиля')
        if any(not isinstance(value, str) or not value.strip() for value in self.best_for):
            raise ValueError('Неверное применение профиля стиля')
        return self


def _modifier(key, title, phrase, *aliases):
    return StyleModifier(key, title, phrase, tuple(aliases)).validate()


def _profile(key, title, category, phrase, best_for, aliases=(), defaults=()):
    return StyleProfile(
        key, title, category, phrase, tuple(best_for), tuple(aliases), tuple(defaults)
    ).validate()


_MODIFIERS = (
    _modifier('gentle', 'Нежный',
              'gentle, soft visual character in colour and texture, painted in fully opaque colours, no translucent washes',
              'нежное', 'нежный', 'soft', 'gentle'),
    _modifier('vintage', 'Винтажный',
              'subtle vintage character, timeless rather than distressed, crisp readable shapes in fully opaque paint',
              'винтажный', 'vintage'),
    _modifier('nursery', 'Детский / nursery', 'nursery-friendly proportions and approachable shapes', 'детский', 'nursery'),
    _modifier('whimsical', 'Сказочный', 'whimsical, imaginative visual character', 'сказочное', 'сказочный', 'whimsical'),
    _modifier('minimal', 'Минималистичный', 'minimal, visually clean, restrained detail', 'минималистичный', 'minimal'),
    _modifier('rustic', 'Рустикальный', 'rustic, natural, handcrafted character', 'рустикальный', 'rustic'),
    _modifier('elegant', 'Элегантный', 'elegant, refined visual character', 'элегантный', 'elegant'),
    _modifier('muted', 'Приглушённый', 'muted, calm visual character', 'спокойное', 'приглушённый', 'muted', 'calm'),
    _modifier('vibrant', 'Яркий', 'vibrant, celebratory visual character', 'весёлое', 'праздничное', 'яркий', 'vibrant'),
    _modifier('cozy', 'Уютный', 'cozy, warm visual character', 'уютное', 'уютный', 'cozy'),
    _modifier('premium', 'Премиальный', 'refined premium illustration finish', 'премиальный', 'premium'),
    _modifier('dark', 'Тёмный', 'dark atmospheric character without gore', 'тёмный', 'dark'),
)


_PROFILES = (
    _profile('watercolor', 'Акварель', 'Живописные',
             'refined watercolor illustration, hand-painted opaque watercolor texture inside the subject, dense paint coverage, controlled readable edges',
             ('nursery', 'florals', 'animals', 'weddings', 'premium Etsy clipart'),
             ('watercolor', 'акварель', 'акварельная иллюстрация'), ('gentle',)),
    _profile('gouache', 'Гуашь', 'Живописные',
             'gouache illustration, opaque matte paint, rich flat pigment and hand-painted texture',
             ('bold florals', 'food', 'retro themes', 'children illustration'),
             ('gouache', 'гуашь')),
    _profile('hand-drawn', 'Рисованная от руки', 'Рисунок',
             'hand-drawn illustration with natural imperfect line rhythm and crafted detail',
             ('lifestyle objects', 'botanical', 'craft themes'),
             ('hand drawn', 'hand-drawn', 'рисованная от руки')),
    _profile('doodle', 'Doodle / маркер', 'Рисунок',
             'clean hand-drawn doodle illustration, simple playful lines and compact shapes',
             ('school', 'kids', 'stickers', 'icons'),
             ('doodle', 'маркер / doodle', 'дудл')),
    _profile('pencil', 'Карандаш', 'Рисунок',
             'pencil illustration with controlled graphite texture and clear readable contours',
             ('botanical', 'storybook', 'vintage studies'),
             ('pencil', 'карандаш')),
    _profile('minimal-line-art', 'Минималистичный line art', 'Рисунок',
             'minimal line-art illustration, clean intentional strokes and generous negative space',
             ('weddings', 'modern decor', 'icons'),
             ('line art', 'minimalist line art', 'линейная графика')),
    _profile('flat-vector', 'Плоская иллюстрация', 'Графические',
             'flat vector-like illustration, clean geometric shapes, crisp edges and minimal shading',
             ('icons', 'digital kits', 'modern educational graphics'),
             ('flat vector', 'flat illustration', 'плоская иллюстрация')),
    _profile('sticker', 'Sticker style', 'Графические',
             'sticker-style illustration with a compact readable silhouette and bold simplified forms',
             ('stickers', 'kids', 'planner graphics'),
             ('sticker style', 'стикер')),
    _profile('pixel-art', 'Pixel Art', 'Графические',
             'pixel-art illustration with deliberate blocky pixels, limited shading and readable silhouette',
             ('gaming', 'retro', 'kids birthday'),
             ('pixel art', 'пиксельная графика')),
    _profile('kawaii', 'Kawaii', 'Персонажи',
             'kawaii cartoon illustration with simple rounded forms, cute proportions and expressive friendly face',
             ('kids', 'food characters', 'stickers', 'birthday'),
             ('kawaii', 'кавай')),
    _profile('chibi', 'Chibi', 'Персонажи',
             'chibi character illustration with compact body proportions, large expressive head and simplified detail',
             ('character sets', 'fantasy', 'stickers'),
             ('chibi', 'чиби')),
    _profile('storybook', 'Книжная иллюстрация', 'Персонажи',
             'storybook cartoon illustration with expressive character design, gentle narrative detail and cohesive proportions',
             ('fairy tales', 'children books', 'woodland animals', 'fantasy'),
             ('storybook', "children's book", 'детская книжная иллюстрация', 'storybook cartoon'), ('whimsical',)),
    _profile('pastel-nursery', 'Pastel Nursery', 'Персонажи',
             'soft pastel nursery illustration with rounded approachable forms and calm baby-friendly detail',
             ('baby shower', 'first birthday', 'nursery animals'),
             ('pastel nursery', 'нежная детская иллюстрация'), ('gentle', 'nursery')),
    _profile('whimsical', 'Whimsical', 'Атмосферные',
             'whimsical illustration with imaginative shapes, playful storybook detail and light magical character',
             ('fantasy', 'holiday characters', 'garden party', 'children themes'),
             ('whimsical', 'сказочная иллюстрация'), ('whimsical',)),
    _profile('scandinavian-folk', 'Скандинавский фолк', 'Фолк и винтаж',
             'Scandinavian folk-art illustration, simplified ornamental shapes, clean rhythm and restrained handcrafted detail',
             ('winter', 'Christmas', 'woodland', 'hygge themes'),
             ('scandinavian folk', 'скандинавский folk', 'скандинавский стиль'), ('minimal', 'cozy')),
    _profile('vintage-illustration', 'Винтажная иллюстрация', 'Фолк и винтаж',
             'vintage-inspired illustration with timeless printed character, refined classic shapes and subtle aged mood',
             ('botanical', 'holiday', 'storybook', 'tea party'),
             ('vintage illustration', 'винтажная иллюстрация'), ('vintage',)),
    _profile('cottagecore', 'Cottagecore', 'Фолк и винтаж',
             'cottagecore illustration with natural handcrafted detail, garden motifs and cozy rural character',
             ('garden', 'tea party', 'florals', 'woodland'),
             ('cottagecore', 'коттеджкор'), ('cozy', 'rustic')),
    _profile('retro', 'Retro', 'Фолк и винтаж',
             'retro illustration with period-inspired shapes, simplified print-like detail and confident graphic rhythm',
             ('party', 'food', 'mid-century themes'),
             ('retro', 'ретро'), ('vintage',)),
    _profile('gothic-dark', 'Gothic / Dark', 'Атмосферные',
             'dark gothic illustration with ornate but readable shapes, moody contrast and non-graphic spooky atmosphere',
             ('Halloween', 'mystical', 'dark florals'),
             ('gothic', 'dark gothic', 'готический', 'тёмный готический'), ('dark',)),
)


def _normalize(value):
    return ' '.join(str(value or '').strip().casefold().split())


_PROFILE_ALIASES = {
    _normalize(alias): profile
    for profile in _PROFILES
    for alias in (profile.key, profile.title, *profile.aliases)
}
_MODIFIER_ALIASES = {
    _normalize(alias): modifier
    for modifier in _MODIFIERS
    for alias in (modifier.key, modifier.title, *modifier.aliases)
}


def all_style_profiles():
    return _PROFILES


def all_style_modifiers():
    return _MODIFIERS


def featured_style_profiles():
    keys = ('watercolor', 'gouache', 'storybook', 'kawaii', 'cottagecore', 'gothic-dark')
    by_key = {profile.key: profile for profile in _PROFILES}
    return tuple(by_key[key] for key in keys)


def style_categories():
    order = ('Живописные', 'Рисунок', 'Графические', 'Персонажи', 'Фолк и винтаж', 'Атмосферные')
    return tuple(category for category in order if any(p.category == category for p in _PROFILES))


def get_style_profile(value):
    return _PROFILE_ALIASES.get(_normalize(value))


def style_modifier_keys(*values):
    text = ' '.join(_normalize(value) for value in values)
    result = []
    for modifier in _MODIFIERS:
        if any(alias in text for alias in (_normalize(modifier.key), _normalize(modifier.title),
                                           *(_normalize(a) for a in modifier.aliases)) if alias):
            if modifier.key not in result:
                result.append(modifier.key)
    return result


def recommended_style_profiles(theme='', context='', limit=3):
    if type(limit) is not int or not 1 <= limit <= 6:
        raise ValueError('Неверное число рекомендаций стиля')
    haystack = f'{theme} {context}'.casefold()
    theme_text = str(theme or '').casefold()
    keys = []
    if (any(word in haystack for word in ('christmas', 'рождеств'))
            and any(word in theme_text for word in ('teddy', 'bear', 'мишка', 'медвед', 'animal', 'живот'))):
        keys += ['watercolor', 'scandinavian-folk', 'vintage-illustration']
    elif any(word in haystack for word in ('christmas', 'рождеств', 'winter', 'зим')):
        keys += ['scandinavian-folk', 'watercolor', 'vintage-illustration']
    elif any(word in haystack for word in ('halloween', 'хэллоу', 'ghost', 'witch')):
        keys += ['whimsical', 'gothic-dark', 'kawaii']
    elif any(word in haystack for word in ('baby shower', 'first birthday', 'первый день рождения', 'малыш', 'baby')):
        keys += ['pastel-nursery', 'watercolor', 'storybook']
    elif any(word in haystack for word in ('easter', 'пасх', 'spring', 'весн')):
        keys += ['watercolor', 'pastel-nursery', 'cottagecore']
    elif any(word in haystack for word in ('garden', 'сад', 'tea party', 'flower', 'цвет')):
        keys += ['watercolor', 'cottagecore', 'gouache']
    elif any(word in haystack for word in ('book', 'story', 'fairy', 'сказ', 'принцесс', 'dragon', 'дракон')):
        keys += ['storybook', 'watercolor', 'whimsical']
    elif any(word in haystack for word in ('school', 'teacher', 'icon', 'logo')):
        keys += ['doodle', 'flat-vector', 'sticker']
    else:
        keys += ['watercolor', 'storybook', 'gouache']
    by_key = {profile.key: profile for profile in _PROFILES}
    result = []
    for key in keys:
        profile = by_key[key]
        if profile not in result:
            result.append(profile)
        if len(result) >= limit:
            break
    return tuple(result)


def style_prompt_text(technique='', mood=''):
    """Compile one collection-wide style phrase from user-visible choices."""
    technique = str(technique or '').strip()
    mood = str(mood or '').strip()
    profile = get_style_profile(technique) if technique else None
    parts = [profile.prompt_phrase if profile is not None else technique]
    modifier_keys = style_modifier_keys(mood)
    modifier_by_key = {modifier.key: modifier for modifier in _MODIFIERS}
    parts.extend(modifier_by_key[key].prompt_phrase for key in modifier_keys)
    if mood and not modifier_keys:
        parts.append(mood)
    return '; '.join(part for part in parts if part)[:4000]


def style_planning_hints(technique='', *, mood=''):
    technique = str(technique or '').strip()
    if not technique:
        return None
    profile = get_style_profile(technique)
    modifier_keys = style_modifier_keys(mood)
    if profile is None:
        return {
            'key': 'custom',
            'title': technique[:400],
            'prompt_phrase': technique[:1000],
            'modifiers': modifier_keys[:4],
        }
    modifier_by_key = {modifier.key: modifier for modifier in _MODIFIERS}
    return {
        'key': profile.key,
        'title': profile.title,
        'category': profile.category,
        'prompt_phrase': profile.prompt_phrase,
        'best_for': list(profile.best_for),
        'modifiers': modifier_keys[:4],
        'modifier_phrases': [modifier_by_key[key].prompt_phrase for key in modifier_keys[:4]],
    }
