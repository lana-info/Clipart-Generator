"""Local holiday-aware Clipart guidance; no provider calls or user secrets."""
from dataclasses import dataclass


@dataclass(frozen=True)
class HolidayProfile:
    key: str
    title: str
    aliases: tuple[str, ...]
    palette: tuple[str, ...]
    palette_character: str
    character_accessories: tuple[str, ...]
    props: tuple[str, ...]
    decor: tuple[str, ...]
    composition_ideas: tuple[str, ...]
    moods: tuple[str, ...]
    background_hints: tuple[str, ...]
    exclusions: tuple[str, ...] = ()

    def validate(self):
        if not self.key or not self.title or not self.aliases:
            raise ValueError('Holiday Profile должен иметь key/title/aliases')
        if len(self.palette) != 5:
            raise ValueError('Holiday palette должна содержать ровно 5 цветов')
        if any(not isinstance(c, str) or len(c) != 7 or not c.startswith('#')
               or any(ch not in '0123456789ABCDEF' for ch in c[1:].upper())
               for c in self.palette):
            raise ValueError('Неверный цвет Holiday Profile')
        for values in (self.character_accessories, self.props, self.decor,
                       self.composition_ideas, self.moods, self.background_hints,
                       self.exclusions):
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError('Пустое значение Holiday Profile')
        return self


def _profile(**kwargs):
    return HolidayProfile(**kwargs).validate()


_PROFILES = (
    _profile(
        key='christmas', title='Рождество', aliases=('Christmas', 'Рождество', 'Xmas'),
        palette=('#1F5D42', '#C62828', '#F6EBDD', '#C8A24A', '#6B4A32'),
        palette_character='классическая рождественская',
        character_accessories=('Santa hat', 'knit scarf', 'holiday sweater', 'earmuffs'),
        props=('gift box', 'candy cane', 'Christmas ornament', 'stocking', 'hot cocoa mug'),
        decor=('holly', 'pine branches', 'red berries', 'bows', 'bells', 'snowflakes'),
        composition_ideas=('with wrapped gifts', 'beside a small Christmas tree', 'inside a wreath', 'with ornament cluster'),
        moods=('cozy', 'festive', 'nostalgic', 'magical'),
        background_hints=('subtle snow accents', 'pine and berry accents', 'warm holiday details'),
    ),
    _profile(
        key='halloween', title='Хэллоуин', aliases=('Halloween', 'Хэллоуин', 'Хэллоуинский праздник'),
        palette=('#F47C20', '#1B1B1B', '#6B3FA0', '#F3E6D0', '#5F7A4A'),
        palette_character='классическая хэллоуинская',
        character_accessories=('witch hat', 'small cape', 'costume bow', 'striped scarf'),
        props=('jack-o-lantern', 'candy bucket', 'lantern', 'cauldron', 'pumpkin'),
        decor=('bats', 'spider webs', 'tiny ghosts', 'crescent moon', 'stars'),
        composition_ideas=('with pumpkin cluster', 'inside a spooky wreath', 'with candy and bats', 'under a crescent moon accent'),
        moods=('cute spooky', 'whimsical', 'playful', 'gothic light'),
        background_hints=('moon and star accents', 'pumpkin accents', 'subtle web details'),
        exclusions=('graphic gore', 'realistic injury'),
    ),
    _profile(
        key='easter', title='Пасха', aliases=('Easter', 'Пасха'),
        palette=('#F6D6E3', '#CFE4B8', '#C9DCF4', '#F6E8A8', '#E7D8F2'),
        palette_character='нежная пасхальная',
        character_accessories=('pastel bow', 'flower crown', 'small bonnet'),
        props=('painted egg', 'Easter basket', 'carrot', 'spring flowers'),
        decor=('tulips', 'daisies', 'tiny eggs', 'ribbons'),
        composition_ideas=('with Easter basket', 'with spring flower cluster', 'inside an egg-shaped frame'),
        moods=('fresh', 'gentle', 'springtime', 'playful'),
        background_hints=('spring floral accents', 'soft grass hints'),
    ),
    _profile(
        key='valentines-day', title='День святого Валентина', aliases=("Valentine's Day", 'Valentines Day', 'День святого Валентина'),
        palette=('#C6283D', '#E9859D', '#F6D8DE', '#FFF1E8', '#8F4055'),
        palette_character='романтическая',
        character_accessories=('heart bow', 'romantic ribbon', 'small floral crown'),
        props=('heart', 'rose', 'chocolate box', 'love letter', 'bouquet'),
        decor=('hearts', 'roses', 'ribbons', 'tiny sparkles'),
        composition_ideas=('holding a heart', 'with rose bouquet', 'inside a heart wreath'),
        moods=('sweet', 'romantic', 'gentle', 'playful'),
        background_hints=('heart accents', 'soft rose accents'),
    ),
    _profile(
        key='thanksgiving', title='День благодарения', aliases=('Thanksgiving', 'День благодарения'),
        palette=('#A64B2A', '#D8893C', '#C5A45B', '#6F6A43', '#F0DFC3'),
        palette_character='тёплая осенняя',
        character_accessories=('cozy scarf', 'autumn bow', 'knit hat'),
        props=('pumpkin', 'pie', 'corn', 'harvest basket', 'mug'),
        decor=('autumn leaves', 'wheat', 'acorns', 'berries'),
        composition_ideas=('with harvest basket', 'with pumpkin cluster', 'inside autumn wreath'),
        moods=('warm', 'grateful', 'cozy', 'rustic'),
        background_hints=('harvest accents', 'autumn foliage accents'),
    ),
    _profile(
        key='independence-day', title='4 июля / День независимости',
        aliases=('4th of July', 'Independence Day', 'Fourth of July', 'День независимости США'),
        palette=('#B22234', '#FFFFFF', '#3C3B6E', '#D8E1F0', '#8A1F2D'),
        palette_character='патриотическая красно-бело-синяя',
        character_accessories=('star bow', 'patriotic scarf', 'red-white-blue ribbon'),
        props=('American flag', 'star wand', 'picnic basket', 'sparkler'),
        decor=('stars', 'stripes', 'bunting', 'firework accents'),
        composition_ideas=('with flag', 'with patriotic star cluster', 'inside red-white-blue wreath'),
        moods=('celebratory', 'bright', 'patriotic', 'summer'),
        background_hints=('stars and stripes accents', 'subtle firework accents'),
    ),
    _profile(
        key='st-patricks-day', title='День святого Патрика',
        aliases=("St. Patrick's Day", 'St Patricks Day', 'День святого Патрика'),
        palette=('#1F6B45', '#4E9A61', '#D4AF37', '#F4EBD8', '#2D4F3A'),
        palette_character='зелёно-золотая',
        character_accessories=('green bow', 'small top hat', 'green scarf'),
        props=('shamrock', 'pot of gold', 'gold coin', 'rainbow'),
        decor=('clover', 'gold stars', 'green ribbons'),
        composition_ideas=('with shamrock cluster', 'beside pot of gold', 'inside clover wreath'),
        moods=('lucky', 'cheerful', 'festive'),
        background_hints=('clover accents', 'small gold accents'),
    ),
    _profile(
        key='baby-shower', title='Baby Shower', aliases=('Baby Shower', 'Бэби шауэр', 'Детский душ'),
        palette=('#E7C8CF', '#C7D8EA', '#C9D8BB', '#F5EAD7', '#D6C7DD'),
        palette_character='нежная детская',
        character_accessories=('soft bow', 'tiny bonnet', 'gentle ribbon'),
        props=('baby blocks', 'rattle', 'balloon', 'gift box', 'moon and star'),
        decor=('clouds', 'stars', 'bows', 'tiny flowers'),
        composition_ideas=('with balloons', 'with baby blocks', 'inside cloud and star wreath'),
        moods=('gentle', 'sweet', 'calm', 'celebratory'),
        background_hints=('cloud accents', 'soft stars'),
    ),
    _profile(
        key='birthday', title='День рождения', aliases=('Birthday', 'День рождения', 'День рождения ребёнка'),
        palette=('#EFA6B2', '#F2CF69', '#8FC5C6', '#AFCF9E', '#F7E9D8'),
        palette_character='яркая праздничная',
        character_accessories=('party hat', 'birthday crown', 'bow tie'),
        props=('birthday cake', 'gift box', 'balloon', 'cupcake', 'party horn'),
        decor=('confetti', 'bunting', 'stars', 'streamers'),
        composition_ideas=('with birthday cake', 'with balloon cluster', 'inside party wreath'),
        moods=('joyful', 'playful', 'festive', 'bright'),
        background_hints=('confetti accents', 'balloon accents'),
    ),
    _profile(
        key='first-birthday', title='Первый день рождения',
        aliases=('First Birthday', 'Первый день рождения', '1st Birthday'),
        palette=('#E9C8D3', '#C9D9EA', '#D1DFC0', '#F2DFB7', '#E2D4E8'),
        palette_character='мягкая пастельная',
        character_accessories=('number-one crown', 'soft party hat', 'small bow'),
        props=('number 1 topper', 'small cake', 'balloon', 'gift', 'cupcake'),
        decor=('stars', 'bows', 'soft confetti', 'tiny flowers'),
        composition_ideas=('with number 1', 'with first-birthday cake', 'with pastel balloon cluster'),
        moods=('gentle', 'celebratory', 'sweet', 'playful'),
        background_hints=('soft confetti accents', 'pastel stars'),
    ),
)

FIRST_WAVE_HOLIDAYS = tuple(profile.title for profile in _PROFILES)


def _normalize(value):
    return ' '.join(str(value or '').strip().casefold().split())


_ALIASES = {
    _normalize(alias): profile
    for profile in _PROFILES
    for alias in (profile.title, *profile.aliases)
}


def get_holiday_profile(context):
    """Return the matching local profile, or None for ordinary/custom contexts."""
    return _ALIASES.get(_normalize(context))


def holiday_palette_presets(context):
    profile = get_holiday_profile(context)
    if profile is None:
        return ()
    return ({
        'key': profile.key,
        'title': profile.title,
        'category': 'Праздники',
        'character': profile.palette_character,
        'colors': list(profile.palette),
    },)


def holiday_planning_hints(context):
    profile = get_holiday_profile(context)
    if profile is None:
        return None
    return {
        'holiday': profile.title,
        'palette': list(profile.palette),
        'palette_character': profile.palette_character,
        'character_accessories': list(profile.character_accessories),
        'props': list(profile.props),
        'decor': list(profile.decor),
        'composition_ideas': list(profile.composition_ideas),
        'moods': list(profile.moods),
        'background_hints': list(profile.background_hints),
        'exclusions': list(profile.exclusions),
    }
