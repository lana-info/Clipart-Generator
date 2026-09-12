"""Offline request/response boundary for a future text-model adapter.

No network or image generation. Callers must discard responses if their draft
changed while a request was running. Returned requests contain user text, not
instructions that an adapter should execute.
"""
from copy import deepcopy

from studio_clipart_objects import TEXT_FIELDS, validate_objects


def planning_request(recipe, palette='', replace_ids=None):
    """Target unpinned slots, or an explicit subset; never silently unpin."""
    recipe.validate()
    items = validate_objects(recipe.objects)
    if len(items) != recipe.total or any(
        sum(item['role'] == role for item in items) != count
        for role, count in recipe.counts.items()
    ):
        raise ValueError('Сначала согласуйте состав набора с рецептом')
    if not isinstance(palette, str) or len(palette) > 4000:
        raise ValueError('Неверная палитра')
    available = {item['id'] for item in items if not item.get('pinned', False)}
    if replace_ids is None:
        selected = available
    else:
        if (not isinstance(replace_ids, list)
                or any(not isinstance(key, str) for key in replace_ids)
                or len(set(replace_ids)) != len(replace_ids)):
            raise ValueError('Неверный список замен')
        selected = set(replace_ids)
        if not selected <= available:
            raise ValueError('Нельзя заменить закреплённый или отсутствующий объект')
    if not selected:
        raise ValueError('Нет объектов для подбора')
    from studio_holiday_profiles import holiday_planning_hints
    return deepcopy(dict(
        schema_version=1,
        brief=dict(theme=recipe.theme, context=recipe.context, motifs=recipe.motifs,
                   visual=recipe.visual, palette=palette),
        holiday=holiday_planning_hints(recipe.context),
        # Local paths and image bytes are deliberately not sent as observations.
        reference_observations=[dict(roles=ref['roles'], notes=ref['notes'])
                                for ref in recipe.references if ref['notes'].strip()],
        existing=items,
        targets=[dict(id=item['id'], role=item['role']) for item in items
                 if item['id'] in selected],
    ))


def apply_suggestions(recipe, request, response, *, palette=''):
    """Validate a complete response before returning a new object list."""
    target_ids = [target['id'] for target in request['targets']]
    if planning_request(recipe, palette, target_ids) != request:
        raise ValueError('Настройки изменились. Подберите идеи заново')
    if not isinstance(response, list) or len(response) != len(target_ids):
        raise ValueError('Планировщик вернул неверное количество идей')
    suggestions = {}
    for row in response:
        if not isinstance(row, dict) or set(row) != {'id', *TEXT_FIELDS}:
            raise ValueError('Неверный формат идеи')
        key = row['id']
        if not isinstance(key, str) or key not in target_ids or key in suggestions:
            raise ValueError('Неизвестная или повторяющаяся идея')
        if any(not isinstance(row[field], str) or len(row[field]) > 2000
               for field in TEXT_FIELDS) or not row['name'].strip():
            raise ValueError('Идея должна содержать название и допустимые описания')
        suggestions[key] = row
    result = validate_objects(recipe.objects)
    for item in result:
        if item['id'] in suggestions:
            item.update({field: suggestions[item['id']][field] for field in TEXT_FIELDS})
    return validate_objects(result)
