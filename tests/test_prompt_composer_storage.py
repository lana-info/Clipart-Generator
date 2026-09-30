import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import Image

from studio_prompt_composer_storage import LibraryConflict, PromptLibrary


def draft():
    from prompt_composer.model import new_draft
    return new_draft()


def test_copy_restart_and_conflict(tmp_path):
    store = PromptLibrary(tmp_path / 'library')
    first = store.save(draft(), {'name': 'Оригинал'})
    copy = store.save(first['payload'], {'name': 'Копия', 'parent_id': first['id']})
    assert copy['id'] != first['id']
    other = PromptLibrary(store.root)
    changed = other.save(draft(), {'name': 'Новое имя'}, first['id'], 1)
    assert changed['revision'] == 2
    with pytest.raises(LibraryConflict):
        store.save(draft(), {'name': 'Потерянное обновление'}, first['id'], 1)
    with pytest.raises(LibraryConflict):
        store.delete(first['id'], 1)
    assert other.load(first['id'])['name'] == 'Новое имя'
    assert len(other.list_entries()) == 2


def test_two_writers_only_one_wins(tmp_path):
    store = PromptLibrary(tmp_path)
    item = store.save(draft(), {'name': 'Один'})
    def write(name):
        try:
            return store.save(draft(), {'name': name}, item['id'], 1)['revision']
        except LibraryConflict:
            return 'conflict'
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(write, ['Два', 'Три']))
    assert sorted(map(str, results)) == ['2', 'conflict']


def test_managed_reference_survives_source_and_record_deletion(tmp_path):
    image = tmp_path / 'original.png'
    Image.new('RGB', (12, 12), 'red').save(image)
    store = PromptLibrary(tmp_path / 'library')
    ref = store.import_reference(image)
    image.unlink()
    value = draft()
    value['references'] = [ref]
    a = store.save(value, {'name': 'A'})
    b = store.save(value, {'name': 'B', 'kind': 'profile'})
    store.delete(a['id'], a['revision'])
    assert store.reference_available(store.load(b['id'])['payload']['references'][0])
    assert not PromptLibrary(tmp_path / 'other').reference_available(ref)
    with pytest.raises(ValueError, match='принадлежит'):
        PromptLibrary(tmp_path / 'other').save(value, {'name': 'Чужой'})


def test_corrupt_and_future_data_not_reset(tmp_path):
    bad = tmp_path / 'bad'
    bad.mkdir()
    (bad / 'library.sqlite3').write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        PromptLibrary(bad)
    assert (bad / 'library.sqlite3').read_bytes() == b'not a database'
    store = PromptLibrary(tmp_path / 'future')
    with sqlite3.connect(store.path) as db:
        db.execute('PRAGMA user_version=9')
    with pytest.raises(ValueError, match='версия'):
        PromptLibrary(store.root)


def test_invalid_reference_not_published(tmp_path):
    store = PromptLibrary(tmp_path / 'library')
    bad = tmp_path / 'broken.png'
    bad.write_bytes(b'not an image')
    with pytest.raises(OSError):
        store.import_reference(bad)
    assert not list(store.assets.root.glob('*.png'))


def test_corrupt_row_does_not_hide_healthy_entries(tmp_path):
    store = PromptLibrary(tmp_path)
    bad = store.save(draft(), {'name': 'Повреждённый'})
    good = store.save(draft(), {'name': 'Здоровый'})
    with sqlite3.connect(store.path) as db:
        db.execute('UPDATE entries SET payload=? WHERE id=?', ('broken JSON', bad['id']))
    rows = {row['id']: row for row in store.list_entries()}
    assert rows[bad['id']]['error']
    assert rows[good['id']]['payload'] == good['payload']
    with sqlite3.connect(store.path) as db:
        assert db.execute('SELECT payload FROM entries WHERE id=?', (bad['id'],)).fetchone()[0] == 'broken JSON'
