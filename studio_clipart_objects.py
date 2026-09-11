"""Concrete object planning and explicit handoff to the existing prompt builder."""
from copy import deepcopy
from uuid import uuid4

OBJECT_ROLES = ('hero', 'composition', 'wreath', 'border', 'decor')
TEXT_FIELDS = ('name', 'action', 'extras', 'layout', 'details')


def validate_objects(items):
    if not isinstance(items, list) or len(items) > 1000:
        raise ValueError('Допускается до 1000 объектов')
    ids, ordinals = set(), set()
    for item in items:
        if not isinstance(item, dict) or set(item) - {'pinned'} != {'id', 'ordinal', 'role', *TEXT_FIELDS}:
            raise ValueError('Повреждённая запись объекта')
        if 'pinned' in item and type(item['pinned']) is not bool:
            raise ValueError('Неверный признак закрепления объекта')
        if not isinstance(item['id'], str) or not 1 <= len(item['id']) <= 64 or item['id'] in ids:
            raise ValueError('Неверный или повторяющийся идентификатор объекта')
        if type(item['ordinal']) is not int or not 1 <= item['ordinal'] <= 1_000_000 or item['ordinal'] in ordinals:
            raise ValueError('Неверный или повторяющийся номер объекта')
        if item['role'] not in OBJECT_ROLES:
            raise ValueError('Неизвестная роль объекта')
        for key in TEXT_FIELDS:
            if not isinstance(item[key], str) or len(item[key]) > 2000:
                raise ValueError('Каждое описание объекта ограничено 2000 символами')
        ids.add(item['id'])
        ordinals.add(item['ordinal'])
    return deepcopy(items)


def new_object(role, ordinal):
    item = dict(id=str(uuid4()), ordinal=ordinal, role=role, **dict.fromkeys(TEXT_FIELDS, ''))
    validate_objects([item])
    return item


def fill_recipe(items, counts):
    """Add blank slots; never delete edited objects when a recipe shrinks."""
    result = validate_objects(items)
    if set(counts) != set(OBJECT_ROLES) or any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError('Неверные количества ролей')
    next_number = max((item['ordinal'] for item in result), default=0) + 1
    for role in OBJECT_ROLES:
        missing = counts[role] - sum(item['role'] == role for item in result)
        if len(result) + max(0, missing) > 1000:
            raise ValueError('Допускается до 1000 объектов')
        for _ in range(max(0, missing)):
            result.append(new_object(role, next_number))
            next_number += 1
    return result


def compile_objects(recipe, generator):
    from v3_project_state import ProjectMode, PromptGeneratorData
    from v3_prompt_generator import generate_prompt_series
    recipe.validate()
    items = validate_objects(recipe.objects)
    if not items or any(not item['name'].strip() for item in items):
        raise ValueError('Укажите название каждого объекта перед сборкой промптов')
    if len(items) != recipe.total or any(
        sum(item['role'] == role for item in items) != recipe.counts[role] for role in OBJECT_ROLES
    ):
        raise ValueError('Состав объектов не совпадает с рецептом')
    prompts = []
    role_names = dict(zip(OBJECT_ROLES, ('главный объект', 'композиция', 'венок', 'бордюр / рамка', 'декор')))
    for item in items:
        fields = generator.to_dict()
        fields.update(theme='; '.join(s for s in (recipe.theme, recipe.context) if s),
                      subjects=[item['name']], variations=['; '.join(s for s in
                          (item['action'], item['extras'], item['details']) if s)],
                      composition='; '.join(s for s in (role_names[item['role']], item['layout']) if s))
        if any(len(s) > 4000 for s in (fields['theme'], fields['composition'], *fields['variations'])):
            raise ValueError('Сократите объединённое описание объекта до 4000 символов')
        # Use the existing language/chroma pipeline, preserving its validation.
        entry = generate_prompt_series(ProjectMode.CLIPART, PromptGeneratorData(**fields))[0]
        entry.result_kind = 'clipart'
        prompts.append(entry)
    return prompts
