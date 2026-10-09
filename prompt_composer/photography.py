"""Concrete bilingual shooting direction for the current scenario catalogue.

These are editable defaults, never facts about the user's subject. No new draft
fields are needed, so saved snapshots and their user overrides stay independent.
"""
from copy import deepcopy

_LIGHT = {
    ('people', 'portrait'): (
        'большой мягкий источник сбоку под 45°, плавный переход света на лице, лёгкое заполнение теней и отделение от фона',
        'a large soft key at 45 degrees to one side, gradual facial shading, gentle shadow fill and separation from the background'),
    ('people', 'fashion'): (
        'мягкий направленный свет вдоль силуэта, читаемая фактура ткани, сохранённые детали в светах и тенях',
        'soft directional light along the silhouette, readable fabric texture, retained detail in highlights and shadows'),
    ('people', 'editorial'): (
        'выразительный боковой свет с контролируемой границей тени, объём лица и фигуры без проваленных теней',
        'expressive side lighting with a controlled shadow edge, dimensional face and figure without crushed shadows'),
    ('people', 'beauty'): (
        'крупный рассеянный источник чуть выше лица, деликатные блики и мягкое заполнение, кожа без пересвеченных участков',
        'a large diffused source just above the face, delicate highlights and soft fill, no clipped skin highlights'),
    ('people', 'lifestyle'): (
        'доступный мягкий свет со стороны окна, естественные тени, спокойный баланс яркости героя и помещения',
        'available soft light from the window side, natural shadows, a calm brightness balance between subject and room'),
    ('people', 'ugc'): (
        'доступный свет помещения с мягким освещением лица, естественный баланс белого без студийного блеска',
        'available room light with soft facial illumination, natural white balance without studio gloss'),
    ('products', 'catalogue'): (
        'широкий рассеянный источник сбоку и мягкое заполнение, контролируемые блики по форме товара и чистая контактная тень',
        'a broad diffused side source and soft fill, controlled highlights following the product shape and a clean contact shadow'),
    ('products', 'composition'): (
        'мягкий направленный свет поперёк поверхности, объём предметов и читаемые контактные тени без выбитых бликов',
        'soft directional light across the surface, dimensional objects and readable contact shadows without clipped reflections'),
    ('products', 'on_person'): (
        'мягкий боковой свет на человеке и товаре, точная передача цвета и читаемые детали в месте взаимодействия',
        'soft side light on person and product, faithful color and readable detail at the interaction point'),
    ('products', 'lifestyle'): (
        'естественный свет окружения, мягкое отделение товара от фона, правдоподобные отражения без рекламного пересвета',
        'natural environmental light, soft separation of product from background, plausible reflections without advertising overexposure'),
    ('products', 'ugc'): (
        'доступный рассеянный свет помещения, руки и товар освещены одинаково, блики не скрывают форму и важные детали',
        'available diffused room light, hands and product evenly exposed, reflections do not obscure shape or important detail'),
    ('products', 'handmade'): (
        'мягкий скользящий боковой свет раскрывает рельеф ручной работы, небольшие естественные неровности и контактные тени',
        'soft raking side light reveals handcrafted relief, small natural irregularities and contact shadows'),
    ('food', 'menu'): (
        'широкий мягкий боковой свет, деликатные блики на поверхности блюда, объём ингредиентов и спокойные тени',
        'broad soft side light, delicate food-surface highlights, dimensional ingredients and gentle shadows'),
    ('food', 'serving'): (
        'мягкий свет сбоку вдоль стола, плавные тени под посудой, естественный цвет еды и сдержанные блики',
        'soft side light along the table, gradual shadows under tableware, natural food color and restrained highlights'),
    ('food', 'cooking'): (
        'ровный рассеянный рабочий свет с мягким боковым объёмом, хорошо видны руки и рабочая зона без жёстких бликов',
        'even diffused task light with soft side modeling, clear hands and work area without harsh reflections'),
    ('food', 'ugc'): (
        'доступный домашний свет с мягким заполнением, естественный цвет блюда и лица без искусственного глянца',
        'available home light with soft fill, natural food and facial color without artificial gloss'),
    ('spaces', 'interior'): (
        'естественный оконный свет с сохранёнными деталями за окном и в тенях, мягкие переходы яркости по комнате',
        'natural window light retaining detail outside the window and in shadows, soft brightness transitions through the room'),
    ('spaces', 'architecture'): (
        'мягкий направленный дневной свет раскрывает плоскости и глубину фасада, фактура стен читается без чрезмерного HDR',
        'soft directional daylight reveals facade planes and depth, readable wall texture without excessive HDR'),
    ('spaces', 'atmosphere'): (
        'направленный свет от существующего источника, мягкий рисунок теней на поверхностях и спокойный тональный переход в глубину',
        'directional light from an existing source, soft shadow patterns on surfaces and a calm tonal transition into depth'),
    ('animals', 'portrait'): (
        'мягкий боковой свет на животном, сохранённые детали естественного покрова, деликатные блики в глазах',
        'soft side light on the animal, retained detail in its natural surface covering, delicate eye highlights'),
    ('animals', 'everyday'): (
        'доступный мягкий свет окружения, естественные тени и правдоподобное отделение животного от фона',
        'available soft environmental light, natural shadows and plausible separation of animal from background'),
    ('animals', 'story'): (
        'ровный мягкий свет на всей зоне действия, читаемые движения животного без пересветов и провалов в тенях',
        'even soft light across the action area, readable animal movement without clipped highlights or crushed shadows'),
    ('nature', 'landscape'): (
        'мягкий боковой естественный свет, различимые ближний и дальний планы, сохранённые детали неба и земли',
        'soft natural side light, distinct near and distant planes, retained detail in sky and ground'),
    ('nature', 'travel'): (
        'естественный свет места, мягкий контраст и достоверный баланс белого, детали сохраняются в светах и тенях',
        'natural light of the location, soft contrast and faithful white balance, detail retained in highlights and shadows'),
    ('nature', 'detail'): (
        'мягкий боковой свет вдоль поверхности, читаемый микрорельеф, плавный уход фона в тень без жёстких бликов',
        'soft side light across the surface, readable micro-relief, gradual background falloff without harsh reflections'),
}

_FINISH = {
    'people': ('естественная фактура кожи без восковой ретуши, достоверные пропорции и цвета',
               'natural skin texture without waxy retouching, faithful proportions and colors'),
    'products': ('точная форма, цвет и фактура товара, достоверные тени и отражения',
                 'faithful product shape, color and texture, plausible shadows and reflections'),
    'food': ('естественная фактура и цвет ингредиентов, без пластиковой поверхности',
             'natural ingredient texture and color without plastic surfaces'),
    'spaces': ('прямые вертикали, достоверные пропорции и естественная фактура поверхностей',
               'straight verticals, faithful proportions and natural surface textures'),
    'animals': ('достоверная анатомия и естественный покров животного без очеловечивания',
                'faithful animal anatomy and natural surface covering without anthropomorphism'),
    'nature': ('естественные фактуры и цвета, плавная атмосферная перспектива без перешарпа',
               'natural textures and colors, gradual atmospheric perspective without oversharpening'),
}

_EMPHASIS = {
    'people': [
        ('эмоциональный акцент на заданном жесте и позе без постановочного пафоса',
         'emotional emphasis on the specified gesture and posture without staged drama'),
        ('редакционный акцент на силуэте и деталях заданного образа',
         'editorial emphasis on silhouette and specified appearance details'),
    ],
    'products': [
        ('акцент на материале, рельефе и кромках без изменения товара',
         'emphasize material, relief and edges without changing the product'),
        ('акцент на масштабе и заданном контексте товара без нового реквизита',
         'emphasize product scale and specified context without new props'),
    ],
    'food': [
        ('акцент на фактуре заданных ингредиентов без выдуманного декора',
         'emphasize specified ingredient texture without invented garnish'),
        ('акцент на подаче: блюдо доминирует среди заданных элементов',
         'emphasize presentation: food dominates the specified elements'),
    ],
    'spaces': [
        ('акцент на геометрии, линиях и глубине пространства',
         'emphasize geometry, lines and spatial depth'),
        ('атмосферный акцент на существующем свете и фактурах',
         'atmospheric emphasis on existing light and textures'),
    ],
    'animals': [
        ('акцент на заданной позе и характере без новых действий',
         'emphasize specified posture and character without new actions'),
        ('акцент на масштабе животного и связи с заданным окружением',
         'emphasize animal scale and its specified environmental context'),
    ],
    'nature': [
        ('акцент на масштабе и соотношении ближнего и дальнего планов',
         'emphasize scale and near-to-far relationships'),
        ('акцент на существующем свете и природных фактурах',
         'emphasize existing light and natural textures'),
    ],
}


def shooting_details(category, direction, scene, mode):
    """Describe how to photograph the given shot, without changing its content."""
    shot = scene['shot'][1].lower()
    identifier = scene['id']
    ugc = direction == 'ugc'
    detail = any(word in shot for word in ('detail', 'close', 'surface'))
    wide = any(word in shot for word in ('wide', 'full-length', 'full-body', 'surrounding'))
    overhead = 'overhead' in shot or 'top-down' in shot
    face = category == 'people' and any(word in shot for word in ('face', 'facial', 'portrait')) and 'hands' not in shot

    if ugc:
        optics = ('основная камера телефона, эквивалент 26 мм без сверхширокоугольного искажения',
                  'main phone camera, 26mm equivalent without ultrawide distortion')
    else:
        portrait_close = (face or (category == 'animals' and detail)) and not wide
        focal = (85 if portrait_close else 50) if category in ('people', 'animals') else (
            (85 if detail else 50) if category in ('products', 'food') else
            (50 if detail else 24) if category == 'spaces' else
            (100 if direction == 'detail' else 50 if detail else 35 if direction == 'travel' else 24))
        macro = category == 'nature' and direction == 'detail'
        optics = (f'{"макрообъектив" if macro else "объектив"} {focal} мм, без перспективной деформации',
                  f'{focal}mm {"macro " if macro else ""}lens, no perspective distortion')

    if identifier in ('people_beauty_02', 'people_beauty_03'):
        focus = (('точный фокус на выбранном участке кожи, микрофактура без искусственного перешарпа',
                  'precise focus on the selected skin area, micro-texture without artificial oversharpening')
                 if identifier == 'people_beauty_02' else
                 ('точный фокус на заданной детали макияжа, без смещения внимания на другие части лица',
                  'precise focus on the specified makeup detail, without shifting attention to other facial areas'))
    elif face and not wide:
        focus = ('резкие глаза, мягкое отделение фона, сохранённый контур лица',
                 'sharp eyes, softly separated background, intact facial outline')
    elif category == 'animals' and 'portrait' in identifier:
        focus = ('фокус на глазах животного, весь заданный силуэт остаётся читаемым',
                 'focus on the animal eyes with the entire specified silhouette readable')
    elif category in ('products', 'food'):
        focus = ('резкие главный объект и зона взаимодействия, подчинённый фон',
                 'sharp main subject and interaction area, subordinate background')
    elif wide or category == 'spaces':
        focus = ('достаточная глубина резкости, ясные ближний и дальний планы',
                 'sufficient depth of field, clear near and distant planes')
    else:
        focus = ('фокус на детали действия, мягкий фон с сохранением контекста',
                 'focus on the main action detail, soft background retaining context')

    if overhead:
        angle = ('строго сверху, оптическая ось перпендикулярна поверхности, геометрия предметов без завала',
                 'directly overhead, optical axis perpendicular to the surface, level object geometry')
    elif 'from above' in shot:
        angle = ('приподнятый ракурс около 45°, видны поверхность и высота главного объекта',
                 'elevated viewpoint around 45 degrees, showing the surface and height of the main subject')
    elif 'low' in shot:
        angle = ('низкая точка съёмки в соответствии с заданным планом, горизонт без случайного завала',
                 'low viewpoint consistent with the specified shot, no accidental horizon tilt')
    elif any(word in shot for word in ('side', 'diagonal', 'three-quarter', 'slight angle')):
        side = 'side' in shot
        angle = (('боковой ракурс на уровне главного объекта, читаемый контур и глубина',
                  'side view at main-subject level with a clear outline and depth') if side else
                 ('ракурс в три четверти на уровне главного объекта, читаемые передняя и боковая плоскости',
                  'three-quarter view at main-subject level with readable front and side planes'))
    elif category == 'animals':
        angle = ('камера на уровне животного, естественный масштаб без нависающей перспективы',
                 'camera at the animal level, natural scale without a looming perspective')
    elif category == 'spaces':
        angle = ('ракурс на уровне глаз, камера выровнена, вертикали без схождения и случайного наклона',
                 'eye-level viewpoint, level camera, verticals without convergence or accidental tilt')
    elif category in ('products', 'food'):
        angle = ('ракурс на уровне главного объекта с читаемой формой и свободной зоной действия',
                 'main-subject-level view with readable form and a clear action area')
    elif 'elevated' in shot:
        angle = ('приподнятая точка обзора, ровный горизонт и читаемая глубина пространства',
                 'elevated viewpoint, level horizon and readable spatial depth')
    else:
        angle = ('ракурс на уровне глаз, естественная перспектива и ровный горизонт',
                 'eye-level viewpoint, natural perspective and level horizon')

    lighting = scene.get('lighting', _LIGHT[category, direction])
    if 'evening_room' in identifier:
        lighting = ('тёплый свет существующих интерьерных источников, мягкие тени, сохранённые детали в тёмных участках',
                    'warm light from existing interior sources, soft shadows and retained detail in dark areas')
    finish = _FINISH[category]
    if category == 'nature' and direction == 'detail':
        finish = ('достоверная микрофактура, естественные цвета и плавные тона без перешарпа',
                  'faithful micro-texture, natural colors and gradual tones without oversharpening')
    return dict(lighting=lighting, angle=scene.get('angle', angle), optics=optics,
                focus=focus, finish=finish)


def enrich_recipe(recipe, category, direction, scene, mode):
    details = shooting_details(category, direction, scene, mode)
    fields = recipe['draft']['fields']
    # Recognize saved drafts made by the preceding catalogue without rewriting
    # their fields or accumulating its former relative suffixes.
    recipe['style_aliases'] = [deepcopy(fields['style'])]
    recipe['legacy_variation_options'] = deepcopy(recipe['variation_options'])
    # Do not inherit the legacy default "morning" into every indoor/night scene.
    fields.pop('time', None)
    for key in ('lighting', 'angle'):
        fields[key] = dict(zip(('ru', 'en'), details[key]))
    for language, index in (('ru', 0), ('en', 1)):
        fields['style'][language] = fields['style'][language].rstrip(' .;') + '; ' + details['finish'][index]
        fields['shot'][language] = fields['shot'][language].rstrip(' .;') + '; ' + details['focus'][index]
        camera = fields['camera'][language].rstrip(' .;')
        if camera == 'locked camera with natural perspective for the selected framing':
            camera = 'locked camera'
        elif camera == 'неподвижная камера с естественной перспективой выбранного плана':
            camera = 'неподвижная камера'
        if mode == 'image':
            camera = ('камера телефона' if direction == 'ugc' else 'фотокамера') if language == 'ru' else (
                'phone camera' if direction == 'ugc' else 'still camera')
        fields['camera'][language] = camera + '; ' + details['optics'][index]
        if mode == 'reels':
            fields['camera'][language] += ('; стабильные экспозиция и фокус'
                                           if language == 'ru' else
                                           '; stable exposure and focus')
    # Meaningful, compatible differences: tonal modeling, depth and visual space.
    # These remain relative to the user's current values; locks still win.
    options = {
        'style': [(', ' + ru, ', ' + en) for ru, en in _EMPHASIS[category]],
        'lighting': [
            (', мягкое заполнение теней сохраняет детали без потери объёма',
             ', gentle shadow fill retains detail without flattening the subject'),
            (', усиленное тональное отделение главного объекта от фона без изменения направления света',
             ', stronger tonal separation of the main subject from the background without changing light direction'),
        ],
        'shot': [
            (', немного больше свободного пространства сверху, акцент на силуэте',
             ', slightly more free space above, emphasize the silhouette'),
            (', немного больше свободного пространства слева, баланс объекта и фона',
             ', slightly more free space on the left, balance subject and background'),
            (', немного больше свободного пространства справа, ясный визуальный ритм',
             ', slightly more free space on the right, clear visual rhythm'),
        ],
    }
    if direction == 'ugc':
        options['style'] = [
            (', честный пользовательский акцент на заданной реакции без рекламного пафоса',
             ', honest user emphasis on the specified reaction without advertising drama'),
            (', практичный акцент на предмете и заданном действии без студийной стилизации',
             ', practical emphasis on subject and specified action without studio styling'),
        ]
    for key, suffixes in options.items():
        recipe['variation_options'][key] = [{'ru': '', 'en': ''}] + [dict(zip(('ru', 'en'), pair)) for pair in suffixes]
    return recipe
