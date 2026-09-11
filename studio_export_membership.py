"""Versioned many-to-many membership; paths locate assets, UUIDs identify them.

Legacy identifiers are deterministic so reopening an unsaved draft is stable.
Titles remain verbatim during migration; subsequent renames retain stored IDs.
"""
from uuid import UUID, uuid5
import hashlib
import json
import os
from pathlib import Path

_NAMESPACE = UUID('ea7451bb-c6fc-49dd-a39c-c588f7b55947')


def set_id_for_title(title):
    return str(uuid5(_NAMESPACE, 'set:' + title))


def _valid_id(value):
    try:
        return isinstance(value, str) and str(UUID(value)) == value
    except ValueError:
        return False


def _validate_link(item, *, legacy=False):
    keys = {'title', 'included'} if legacy else {'set_id', 'title', 'included'}
    if (not isinstance(item, dict) or set(item) != keys
            or not isinstance(item['title'], str) or not item['title'].strip()
            or len(item['title']) > 200 or type(item['included']) is not bool
            or (not legacy and not _valid_id(item['set_id']))):
        raise ValueError('Неверное назначение PNG набору')


def validate_export_membership(value):
    if not isinstance(value, dict) or len(value) > 10000:
        raise ValueError('Допускается до 10000 сохранённых назначений PNG')
    result = {}
    titles = {}
    for path, item in value.items():
        if not isinstance(path, str) or not 1 <= len(path) <= 4000:
            raise ValueError('Неверный путь PNG в распределении наборов')
        if isinstance(item, dict) and set(item) == {'title', 'included'}:
            _validate_link(item, legacy=True)
            item = {'version': 2, 'asset_id': str(uuid5(_NAMESPACE, 'asset:' + path)),
                    'memberships': [dict(item, set_id=set_id_for_title(item['title']))]}
        if (not isinstance(item, dict) or set(item) != {'version', 'asset_id', 'memberships'}
                or type(item['version']) is not int or item['version'] != 2
                or not _valid_id(item['asset_id']) or not isinstance(item['memberships'], list)
                or not 1 <= len(item['memberships']) <= 100):
            raise ValueError('Неверное распределение PNG по наборам')
        seen = set()
        for link in item['memberships']:
            _validate_link(link)
            set_id = link['set_id']
            if set_id in seen or titles.get(set_id, link['title']) != link['title']:
                raise ValueError('Повторное или противоречивое назначение набора')
            seen.add(set_id)
            titles[set_id] = link['title']
        result[path] = dict(item, memberships=[dict(link) for link in item['memberships']])
    return result


def backup_membership_migration(destination, state, *, max_bytes):
    """Keep the exact legacy file before its first migrated write, fail closed.

    A content-addressed .bak is never overwritten and is not a project-list entry.
    Both standalone drafts and Studio envelopes are supported. Loading alone is
    read-only; no backup is needed until the original would be replaced.
    """
    new = state.get('clipart', {}).get('export_membership', {})
    if not new or not any(isinstance(item, dict) and item.get('version') == 2
                          for item in new.values()):
        return
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('Нельзя мигрировать проект по символической ссылке')
    if not destination.exists():
        return
    with destination.open('rb') as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError('Проект превышает допустимый размер')
    old = json.loads(raw)
    old = old.get('state', old)
    membership = old.get('clipart', {}).get('export_membership', {})
    validate_export_membership(membership)
    if not any(set(item) == {'title', 'included'} for item in membership.values()):
        return
    backup = destination.with_name(destination.name + '.membership-v1-' +
                                   hashlib.sha256(raw).hexdigest() + '.bak')
    try:
        with backup.open('xb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if backup.is_symlink() or not backup.is_file():
            raise ValueError('Небезопасный путь резервной копии проекта')
        with backup.open('rb') as stream:
            if stream.read(max_bytes + 1) != raw:
                raise ValueError('Резервная копия проекта повреждена')
