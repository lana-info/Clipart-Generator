"""Core-owned, revisioned prompt library. No project paths are exposed to modules."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path

from studio_asset_api import AssetHandle
from studio_assets import AssetStore


class LibraryConflict(ValueError):
    pass


class PromptLibrary:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError('Папка библиотеки не должна быть символической ссылкой')
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'library.sqlite3'
        self.assets = AssetStore(self.root / 'references', max_per_asset=25 * 1024 * 1024)
        with self._connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2):
                raise ValueError('Неподдерживаемая версия библиотеки; данные сохранены')
            db.execute('CREATE TABLE IF NOT EXISTS entries (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL, tags TEXT NOT NULL, favorite INTEGER NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL, parent_id TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS owned_assets (id TEXT PRIMARY KEY)')
            columns = {row[1] for row in db.execute('PRAGMA table_info(entries)')}
            if 'source' not in columns:
                db.execute("ALTER TABLE entries ADD COLUMN source TEXT NOT NULL DEFAULT 'local'")
                db.execute("ALTER TABLE entries ADD COLUMN created_at TEXT NOT NULL DEFAULT ''")
                db.execute("UPDATE entries SET created_at=updated_at")
            db.execute('PRAGMA user_version=2')

    @contextmanager
    def _connect(self):
        if self.path.is_symlink() or self.root.is_symlink():
            raise ValueError('Недопустимый путь библиотеки')
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _record(row):
        if row is None:
            raise ValueError('Запись не найдена')
        record = dict(row)
        from prompt_composer.model import validate_draft
        record['payload'] = validate_draft(json.loads(record['payload']))
        record['tags'] = json.loads(record['tags'])
        if not isinstance(record['tags'], list) or any(not isinstance(tag, str) for tag in record['tags']):
            raise ValueError('Повреждены теги записи')
        record['favorite'] = bool(record['favorite'])
        from prompt_composer.model import rendered_text
        record['description'] = rendered_text(record['payload'], 'ru')[:240] or rendered_text(record['payload'], 'en')[:240]
        return record

    def list_entries(self, kind='prompt'):
        if kind not in ('prompt', 'profile'):
            raise ValueError('Неизвестный тип записи')
        with self._connect() as db:
            records = []
            for row in db.execute('SELECT * FROM entries WHERE kind=? ORDER BY updated_at DESC, id', (kind,)):
                try:
                    records.append(self._record(row))
                except (ValueError, TypeError):
                    records.append({'id': row['id'], 'revision': row['revision'], 'name': row['name'],
                                    'kind': row['kind'], 'tags': [], 'favorite': False, 'payload': {},
                                    'updated_at': row['updated_at'], 'error': 'Запись повреждена или создана новой версией. Исходные данные сохранены.'})
            return records

    def load(self, entry_id):
        with self._connect() as db:
            return self._record(db.execute('SELECT * FROM entries WHERE id=?', (entry_id,)).fetchone())

    def save(self, draft, metadata, entry_id=None, expected_revision=None):
        from prompt_composer.model import validate_draft
        payload = validate_draft(draft)
        name = metadata.get('name', '').strip()
        tags = metadata.get('tags', [])
        kind = metadata.get('kind', 'prompt')
        favorite = metadata.get('favorite', False)
        if not name or len(name) > 120 or kind not in ('prompt', 'profile'):
            raise ValueError('Введите название до 120 символов и корректный тип')
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or not t.strip() or len(t) > 50 for t in tags):
            raise ValueError('Допустимо до 20 тегов по 50 символов')
        if type(favorite) is not bool:
            raise ValueError('Неверное значение избранного')
        if entry_id is not None and (type(expected_revision) is not int or expected_revision < 1):
            raise LibraryConflict('Для замены нужна текущая ревизия записи')
        refs = [AssetHandle.from_dict(ref) for ref in payload.get('references', [])]
        if len(refs) > 5:
            raise ValueError('Можно добавить до 5 референсов')
        identifier = entry_id or uuid.uuid4().hex
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for ref in refs:
                # Missing bytes remain representable so an existing draft can be recovered.
                if not db.execute('SELECT 1 FROM owned_assets WHERE id=?', (ref.asset_id,)).fetchone():
                    raise ValueError('Референс не принадлежит библиотеке')
            existing = db.execute('SELECT revision,kind,source,created_at FROM entries WHERE id=?', (identifier,)).fetchone()
            if entry_id is not None and (existing is None or existing['revision'] != expected_revision):
                raise LibraryConflict('Запись изменена в другом окне. Сохраните новую копию')
            if existing and existing['kind'] != kind:
                raise ValueError('Нельзя заменить запись другого типа')
            revision = existing['revision'] + 1 if existing else 1
            values = (identifier, revision, name, kind, json.dumps(list(dict.fromkeys(tags)), ensure_ascii=False), int(favorite), json.dumps(payload, ensure_ascii=False), datetime.now(timezone.utc).isoformat(), metadata.get('parent_id'))
            source = metadata.get('source', existing['source'] if existing else 'local')
            if source not in ('local', 'ai', 'saved'):
                raise ValueError('Неизвестный источник промпта')
            values += (source, existing['created_at'] if existing else values[7])
            db.execute('INSERT OR REPLACE INTO entries VALUES (?,?,?,?,?,?,?,?,?,?,?)', values)
            record = self._record(db.execute('SELECT * FROM entries WHERE id=?', (identifier,)).fetchone())
        return record

    def delete(self, entry_id, expected_revision):
        if type(expected_revision) is not int:
            raise LibraryConflict('Для удаления нужна текущая ревизия')
        with self._connect() as db:
            cursor = db.execute('DELETE FROM entries WHERE id=? AND revision=?', (entry_id, expected_revision))
            if cursor.rowcount != 1:
                raise LibraryConflict('Запись уже изменена или удалена')
        # Immutable assets may be shared by profiles/copies; no eager deletion.

    def import_reference(self, path):
        from PIL import Image
        source = Path(path)
        if source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('Референс должен быть PNG, JPEG или WebP')
        def verify(filename):
            with Image.open(filename) as image:
                if image.format not in ('PNG', 'JPEG', 'WEBP') or image.width * image.height > 40_000_000:
                    raise ValueError('Недопустимый формат или больше 40 млн пикселей')
                image.verify()
        if source.stat().st_size > 25 * 1024 * 1024:
            raise ValueError('Размер референса больше 25 МБ')
        verify(source)
        record = self.assets.import_file(source)
        verify(self.assets.resolve(record))
        handle = self.assets.to_handle(record)
        with self._connect() as db:
            db.execute('INSERT OR IGNORE INTO owned_assets VALUES (?)', (handle.asset_id,))
        return handle.to_dict()

    def reference_available(self, value):
        try:
            handle = AssetHandle.from_dict(value)
            with self._connect() as db:
                if not db.execute('SELECT 1 FROM owned_assets WHERE id=?', (handle.asset_id,)).fetchone():
                    return False
            self.assets.resolve_handle(handle)
            return True
        except (OSError, ValueError):
            return False
