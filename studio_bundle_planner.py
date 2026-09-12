"""Deterministic commercial + thematic Clipart set planning; no provider calls."""
from uuid import UUID, uuid5

from studio_clipart_objects import OBJECT_ROLES, validate_objects

_NAMESPACE = UUID('7be224ab-d215-4bf4-89a6-cf7d20e42de1')
_COMMERCIAL_TITLES = {
    'mini': 'Мини',
    'standard': 'Стандарт',
    'maxi': 'Макси',
    'bundle': 'Полный бандл',
}
_THEMATIC = (
    ('characters', 'Персонажи', ('hero',)),
    ('compositions', 'Композиции', ('composition',)),
    ('frames-wreaths', 'Рамки и венки', ('wreath', 'border')),
    ('decor', 'Декор', ('decor',)),
)


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


def _thematic_limit(total):
    if total < 20:
        return 0
    if total < 40:
        return 2
    if total < 80:
        return 3
    return 4


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


def _thematic_candidates(objects, commercial_sets):
    by_role = {role: [] for role in OBJECT_ROLES}
    for item in sorted(objects, key=lambda value: value['ordinal']):
        by_role[item['role']].append(item['id'])
    existing_sets = {frozenset(item['item_ids']) for item in commercial_sets}
    candidates = []
    for priority, (key, title, roles) in enumerate(_THEMATIC):
        item_ids = [item_id for role in roles for item_id in by_role[role]]
        frozen = frozenset(item_ids)
        if len(item_ids) < 2 or frozen in existing_sets:
            continue
        candidates.append((-len(item_ids), priority, key, title, item_ids))
    candidates.sort()
    return candidates


def _existing_identities(existing):
    if existing is None:
        return {}
    if not isinstance(existing, dict) or set(existing) != {'schema_version', 'sets'} \
            or type(existing.get('schema_version')) is not int \
            or not isinstance(existing.get('sets'), list):
        raise ValueError('Повреждён план комплектов')
    result = {}
    if existing['schema_version'] == 1:
        for item in existing['sets']:
            if (not isinstance(item, dict)
                    or set(item) != {'tier', 'set_id', 'title', 'item_ids'}
                    or item['tier'] not in _COMMERCIAL_TITLES
                    or not _valid_uuid(item['set_id'])
                    or not isinstance(item['title'], str) or not item['title'].strip()
                    or len(item['title']) > 200):
                raise ValueError('Повреждён план комплектов')
            identity = ('commercial', item['tier'])
            if identity in result:
                raise ValueError('Повреждён план комплектов')
            result[identity] = (item['set_id'], item['title'])
        return result
    if existing['schema_version'] != 2:
        raise ValueError('Повреждён план комплектов')
    for item in existing['sets']:
        if (not isinstance(item, dict)
                or set(item) != {'kind', 'key', 'set_id', 'title', 'item_ids'}
                or item['kind'] not in {'commercial', 'thematic'}
                or not isinstance(item['key'], str)
                or not _valid_uuid(item['set_id'])
                or not isinstance(item['title'], str) or not item['title'].strip()
                or len(item['title']) > 200):
            raise ValueError('Повреждён план комплектов')
        identity = (item['kind'], item['key'])
        if identity in result:
            raise ValueError('Повреждён план комплектов')
        result[identity] = (item['set_id'], item['title'])
    return result


def _identity(identities, kind, key, default_title):
    return identities.get(
        (kind, key),
        (str(uuid5(_NAMESPACE, f'{kind}:{key}')), default_title),
    )


def propose_bundle_plan(objects, *, existing=None):
    items = validate_objects(objects)
    if not items:
        raise ValueError('Нельзя составить комплекты без объектов')
    identities = _existing_identities(existing)
    ranked = _ranked_ids(items)
    sets = []
    for key, size in _tier_shape(len(items)):
        set_id, title = _identity(
            identities, 'commercial', key, _COMMERCIAL_TITLES[key]
        )
        sets.append({
            'kind': 'commercial', 'key': key, 'set_id': set_id,
            'title': title, 'item_ids': ranked[:size],
        })

    limit = _thematic_limit(len(items))
    chosen = _thematic_candidates(items, sets)[:limit]
    seen_memberships = {frozenset(item['item_ids']) for item in sets}
    for _, _, key, default_title, item_ids in chosen:
        frozen = frozenset(item_ids)
        if frozen in seen_memberships:
            continue
        set_id, title = _identity(identities, 'thematic', key, default_title)
        sets.append({
            'kind': 'thematic', 'key': key, 'set_id': set_id,
            'title': title, 'item_ids': list(item_ids),
        })
        seen_memberships.add(frozen)

    plan = {'schema_version': 2, 'sets': sets}
    validate_bundle_plan(plan, items)
    return plan


def _validate_v1(plan, items):
    if not isinstance(plan, dict) or set(plan) != {'schema_version', 'sets'} \
            or plan.get('schema_version') != 1 or not isinstance(plan.get('sets'), list) \
            or not 1 <= len(plan['sets']) <= 4:
        raise ValueError('Повреждён план комплектов')
    object_ids = {item['id'] for item in items}
    expected = [key for key, _ in _tier_shape(len(items))]
    if [item.get('tier') if isinstance(item, dict) else None for item in plan['sets']] != expected:
        raise ValueError('Неверные уровни комплектов')
    previous = set()
    previous_size = 0
    seen_ids = set()
    normalized = []
    for entry in plan['sets']:
        if (set(entry) != {'tier', 'set_id', 'title', 'item_ids'}
                or not _valid_uuid(entry['set_id']) or entry['set_id'] in seen_ids
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
        seen_ids.add(entry['set_id'])
        normalized.append({
            'tier': entry['tier'], 'set_id': entry['set_id'],
            'title': entry['title'], 'item_ids': list(entry['item_ids']),
        })
    if previous != object_ids:
        raise ValueError('Полный бандл должен включать все объекты')
    return {'schema_version': 1, 'sets': normalized}


def validate_bundle_plan(plan, objects):
    items = validate_objects(objects)
    if isinstance(plan, dict) and plan.get('schema_version') == 1:
        return _validate_v1(plan, items)
    if (not isinstance(plan, dict) or set(plan) != {'schema_version', 'sets'}
            or type(plan.get('schema_version')) is not int or plan['schema_version'] != 2
            or not isinstance(plan.get('sets'), list) or not 1 <= len(plan['sets']) <= 12):
        raise ValueError('Повреждён план комплектов')

    object_ids = {item['id'] for item in items}
    by_role = {role: [] for role in OBJECT_ROLES}
    for item in sorted(items, key=lambda value: value['ordinal']):
        by_role[item['role']].append(item['id'])
    thematic_roles = {key: roles for key, _, roles in _THEMATIC}
    expected_commercial = [key for key, _ in _tier_shape(len(items))]

    seen_ids = set()
    seen_keys = set()
    seen_memberships = set()
    commercial = []
    normalized = []
    for entry in plan['sets']:
        if (not isinstance(entry, dict)
                or set(entry) != {'kind', 'key', 'set_id', 'title', 'item_ids'}
                or entry['kind'] not in {'commercial', 'thematic'}
                or not isinstance(entry['key'], str)
                or not _valid_uuid(entry['set_id']) or entry['set_id'] in seen_ids
                or (entry['kind'], entry['key']) in seen_keys
                or not isinstance(entry['title'], str) or not entry['title'].strip()
                or len(entry['title']) > 200 or not isinstance(entry['item_ids'], list)
                or not entry['item_ids']
                or len(entry['item_ids']) != len(set(entry['item_ids']))
                or any(not isinstance(item_id, str) or item_id not in object_ids
                       for item_id in entry['item_ids'])):
            raise ValueError('Повреждён план комплектов')
        frozen = frozenset(entry['item_ids'])
        if frozen in seen_memberships:
            raise ValueError('Наборы не должны дублировать один и тот же состав')
        seen_memberships.add(frozen)
        seen_ids.add(entry['set_id'])
        seen_keys.add((entry['kind'], entry['key']))
        if entry['kind'] == 'commercial':
            if entry['key'] not in _COMMERCIAL_TITLES:
                raise ValueError('Неизвестный коммерческий набор')
            commercial.append(entry)
        else:
            roles = thematic_roles.get(entry['key'])
            if roles is None:
                raise ValueError('Неизвестный тематический набор')
            expected_items = [item_id for role in roles for item_id in by_role[role]]
            if entry['item_ids'] != expected_items or len(expected_items) < 2:
                raise ValueError('Тематический набор не соответствует ролям объектов')
        normalized.append({
            'kind': entry['kind'], 'key': entry['key'], 'set_id': entry['set_id'],
            'title': entry['title'], 'item_ids': list(entry['item_ids']),
        })

    if [entry['key'] for entry in commercial] != expected_commercial:
        raise ValueError('Неверные коммерческие уровни наборов')
    previous = set()
    previous_size = 0
    for entry in commercial:
        current = set(entry['item_ids'])
        if not previous <= current or len(current) <= previous_size:
            raise ValueError('Коммерческие наборы должны быть строго вложенными')
        previous, previous_size = current, len(current)
    if previous != object_ids:
        raise ValueError('Полный бандл должен включать все объекты')

    thematic = [entry for entry in normalized if entry['kind'] == 'thematic']
    if len(thematic) > _thematic_limit(len(items)):
        raise ValueError('Слишком много автоматических тематических наборов')
    return {'schema_version': 2, 'sets': normalized}
