"""Deterministic nested bundle planning for Clipart objects; no provider calls."""
from uuid import UUID, uuid5

from studio_clipart_objects import OBJECT_ROLES, validate_objects

_NAMESPACE = UUID('7be224ab-d215-4bf4-89a6-cf7d20e42de1')
_TITLES = {
    'mini': 'Мини',
    'standard': 'Стандарт',
    'maxi': 'Макси',
    'bundle': 'Полный бандл',
}


def _valid_uuid(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _tier_shape(total):
    if total < 4:
        return [('bundle', total)]
    if total < 10:
        return [('mini', max(2, total // 2)), ('bundle', total)]
    if total < 20:
        return [('mini', max(3, total // 3)),
                ('standard', max(6, (2 * total) // 3)),
                ('bundle', total)]
    return [('mini', max(4, total // 4)),
            ('standard', max(8, total // 2)),
            ('maxi', max(12, (3 * total) // 4)),
            ('bundle', total)]


def _ranked_ids(objects):
    grouped = {role: [] for role in OBJECT_ROLES}
    for item in objects:
        grouped[item['role']].append(item)
    for values in grouped.values():
        values.sort(key=lambda item: item['ordinal'])
    ranked = []
    for role_index, role in enumerate(OBJECT_ROLES):
        values = grouped[role]
        total = len(values)
        for index, item in enumerate(values):
            ranked.append(((index + 1) / total, role_index, item['ordinal'], item['id']))
    ranked.sort()
    return [item_id for _, _, _, item_id in ranked]


def _existing_identities(existing):
    if existing is None:
        return {}
    if not isinstance(existing, dict) or set(existing) != {'schema_version', 'sets'} \
            or existing.get('schema_version') != 1 or not isinstance(existing.get('sets'), list):
        raise ValueError('Повреждён план комплектов')
    result = {}
    for item in existing['sets']:
        if (not isinstance(item, dict) or set(item) != {'tier', 'set_id', 'title', 'item_ids'}
                or item['tier'] not in _TITLES or item['tier'] in result
                or not _valid_uuid(item['set_id']) or not isinstance(item['title'], str)
                or not item['title'].strip() or len(item['title']) > 200):
            raise ValueError('Повреждён план комплектов')
        result[item['tier']] = (item['set_id'], item['title'])
    return result


def propose_bundle_plan(objects, *, existing=None):
    items = validate_objects(objects)
    if not items:
        raise ValueError('Нельзя составить комплекты без объектов')
    identities = _existing_identities(existing)
    ranked = _ranked_ids(items)
    sets = []
    for tier, size in _tier_shape(len(items)):
        set_id, title = identities.get(
            tier, (str(uuid5(_NAMESPACE, 'bundle-tier:' + tier)), _TITLES[tier]))
        sets.append({'tier': tier, 'set_id': set_id, 'title': title,
                     'item_ids': ranked[:size]})
    plan = {'schema_version': 1, 'sets': sets}
    validate_bundle_plan(plan, items)
    return plan


def validate_bundle_plan(plan, objects):
    items = validate_objects(objects)
    if not isinstance(plan, dict) or set(plan) != {'schema_version', 'sets'} \
            or type(plan['schema_version']) is not int or plan['schema_version'] != 1 \
            or not isinstance(plan['sets'], list) or not 1 <= len(plan['sets']) <= 4:
        raise ValueError('Повреждён план комплектов')
    object_ids = {item['id'] for item in items}
    expected_tiers = [tier for tier, _ in _tier_shape(len(items))]
    if [item.get('tier') if isinstance(item, dict) else None for item in plan['sets']] != expected_tiers:
        raise ValueError('Неверные уровни комплектов')
    previous = set()
    previous_size = 0
    seen_set_ids = set()
    for entry in plan['sets']:
        if (set(entry) != {'tier', 'set_id', 'title', 'item_ids'}
                or not _valid_uuid(entry['set_id']) or entry['set_id'] in seen_set_ids
                or not isinstance(entry['title'], str) or not entry['title'].strip()
                or len(entry['title']) > 200 or not isinstance(entry['item_ids'], list)
                or len(entry['item_ids']) != len(set(entry['item_ids']))
                or any(not isinstance(item_id, str) or item_id not in object_ids
                       for item_id in entry['item_ids'])):
            raise ValueError('Повреждён план комплектов')
        current = set(entry['item_ids'])
        if not previous <= current or len(current) <= previous_size:
            raise ValueError('Комплекты должны быть строго вложенными')
        previous, previous_size = current, len(current)
        seen_set_ids.add(entry['set_id'])
    if previous != object_ids:
        raise ValueError('Полный бандл должен включать все объекты')
    return {'schema_version': 1, 'sets': [
        {'tier': entry['tier'], 'set_id': entry['set_id'], 'title': entry['title'],
         'item_ids': list(entry['item_ids'])} for entry in plan['sets']]}
