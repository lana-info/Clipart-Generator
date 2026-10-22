"""Core-owned, revisioned Patterns projects and imported PNG assets.

Projects are stored as opaque, size-bounded JSON so they survive a missing or
disabled module; the module validates their meaning when it is loaded.  No file
paths are stored in projects or exposed to the module: images are referenced by
content-addressed ``AssetHandle`` records.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from studio_asset_api import AssetHandle
from studio_assets import AssetStore

PROJECT_SCHEMA_VERSION = 1
MODES = ("pngs", "tile")
# Mirrors the engine limits (checked by a test); Core must not import the engine.
MAX_ASSET_SIDE = 8_192
MAX_ASSET_PIXELS = 16_000_000
MAX_ASSET_BYTES = 40 * 1024 * 1024
MAX_PROJECT_BYTES = 1_000_000
MAX_PROJECT_ASSETS = 500


class PatternsConflict(ValueError):
    pass


class PatternsLibrary:
    def __init__(self, root):
        self.root = Path(root).absolute()
        if any(p.is_symlink() for p in (self.root, *self.root.parents)):
            raise ValueError("Папка проектов не должна быть символической ссылкой")
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "projects.sqlite3"
        self.assets = AssetStore(self.root / "assets", max_per_asset=MAX_ASSET_BYTES)
        with self._connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise ValueError("Неподдерживаемая версия проектов; данные сохранены")
            db.execute("CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                       "name TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS owned_assets (id TEXT PRIMARY KEY)")
            db.execute("PRAGMA user_version=1")

    @contextmanager
    def _connect(self):
        if self.path.is_symlink() or self.root.is_symlink():
            raise ValueError("Недопустимый путь проектов")
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    # -- assets -------------------------------------------------------------

    def import_png(self, path):
        """Copy one PNG into the asset store and describe it; never alters the source."""
        from PIL import Image
        source = Path(path)
        if source.suffix.lower() != ".png":
            raise ValueError("Нужен файл PNG")
        if source.stat().st_size > MAX_ASSET_BYTES:
            raise ValueError("Файл больше 40 МБ")

        def verify(filename):
            with Image.open(filename) as image:
                if image.format != "PNG":
                    raise ValueError("Файл не является PNG")
                if (image.width > MAX_ASSET_SIDE or image.height > MAX_ASSET_SIDE
                        or image.width * image.height > MAX_ASSET_PIXELS):
                    raise ValueError("Изображение больше 8192 px по стороне или 16 млн пикселей")
                size, has_alpha = image.size, "A" in image.getbands() or "transparency" in image.info
                image.verify()
                return size, has_alpha

        verify(source)
        record = self.assets.import_file(source)
        size, has_alpha = verify(self.assets.resolve(record))
        handle = self.assets.to_handle(record)
        with self._connect() as db:
            db.execute("INSERT OR IGNORE INTO owned_assets VALUES (?)", (handle.asset_id,))
        return {"handle": handle.to_dict(), "width": size[0], "height": size[1], "has_alpha": has_alpha}

    def asset_path(self, handle):
        """Resolve an owned handle to its stored file (for Core-run jobs only)."""
        parsed = handle if isinstance(handle, AssetHandle) else AssetHandle.from_dict(handle)
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM owned_assets WHERE id=?", (parsed.asset_id,)).fetchone():
                raise ValueError("Файл не принадлежит проектам Patterns")
        return self.assets.resolve_handle(parsed)

    def asset_available(self, handle):
        try:
            self.asset_path(handle)
            return True
        except (OSError, ValueError):
            return False

    # -- projects -----------------------------------------------------------

    def _check_payload(self, payload):
        if not isinstance(payload, dict) or payload.get("schema_version") != PROJECT_SCHEMA_VERSION:
            raise ValueError("Неподдерживаемая схема проекта")
        if payload.get("mode") not in MODES:
            raise ValueError("Неизвестный режим проекта")
        handles = payload.get("assets", [])
        if not isinstance(handles, list) or len(handles) > MAX_PROJECT_ASSETS:
            raise ValueError("Слишком много файлов в проекте")
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        if len(text.encode("utf-8")) > MAX_PROJECT_BYTES:
            raise ValueError("Проект слишком большой")
        owned = [AssetHandle.from_dict(item) for item in handles]
        return text, owned

    @staticmethod
    def _record(row):
        if row is None:
            raise ValueError("Проект не найден")
        record = dict(row)
        record["payload"] = json.loads(record["payload"])
        return record

    def list_projects(self):
        with self._connect() as db:
            rows = db.execute("SELECT id, revision, name, updated_at FROM projects ORDER BY updated_at DESC, id").fetchall()
        return [dict(row) for row in rows]

    def load(self, project_id):
        with self._connect() as db:
            return self._record(db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())

    def save(self, payload, name, project_id=None, expected_revision=None):
        name = name.strip() if isinstance(name, str) else ""
        if not name or len(name) > 120:
            raise ValueError("Введите название проекта до 120 символов")
        text, handles = self._check_payload(payload)
        if project_id is not None and (type(expected_revision) is not int or expected_revision < 1):
            raise PatternsConflict("Для замены нужна текущая ревизия проекта")
        identifier = project_id or uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for handle in handles:
                if not db.execute("SELECT 1 FROM owned_assets WHERE id=?", (handle.asset_id,)).fetchone():
                    raise ValueError("Файл не принадлежит проектам Patterns")
            existing = db.execute("SELECT revision, created_at FROM projects WHERE id=?", (identifier,)).fetchone()
            if project_id is not None and (existing is None or existing["revision"] != expected_revision):
                raise PatternsConflict("Проект изменён в другом окне. Сохраните новую копию")
            revision = existing["revision"] + 1 if existing else 1
            db.execute("INSERT OR REPLACE INTO projects VALUES (?,?,?,?,?,?)",
                       (identifier, revision, name, text, existing["created_at"] if existing else now, now))
            return self._record(db.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone())

    def delete(self, project_id, expected_revision):
        if type(expected_revision) is not int:
            raise PatternsConflict("Для удаления нужна текущая ревизия")
        with self._connect() as db:
            if db.execute("DELETE FROM projects WHERE id=? AND revision=?", (project_id, expected_revision)).rowcount != 1:
                raise PatternsConflict("Проект уже изменён или удалён")
        # Immutable assets may be shared between projects; no eager deletion.
