"""Signed announcements and a bounded, content-only offline cache."""
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from update_client import UpdateError

MAX_CACHE_BYTES = 8192


def validate_news(items):
    if not isinstance(items, list) or len(items) > 1:
        raise ValueError("Invalid Studio news")
    clean = []
    for row in items:
        if not isinstance(row, dict) or set(row) != {'id', 'title', 'body', 'published_at'}:
            raise ValueError("Invalid Studio announcement")
        if (not isinstance(row['id'], str) or len(row['id']) != 32
                or any(c not in '0123456789abcdef' for c in row['id'])):
            raise ValueError("Invalid Studio announcement identity")
        for name, limit in (('title', 100), ('body', 600)):
            text = row[name]
            if (not isinstance(text, str) or not text.strip() or len(text) > limit
                    or any(ord(c) < 32 and c not in '\n\t' for c in text)):
                raise ValueError("Invalid Studio announcement text")
        date = row['published_at']
        if not isinstance(date, str) or len(date) > 40 or datetime.fromisoformat(date).tzinfo is None:
            raise ValueError("Invalid Studio announcement date")
        clean.append(dict(row))
    return clean


class StudioNewsClient:
    def __init__(self, updates, cache_path):
        self.updates = updates
        self.cache_path = Path(cache_path)

    def cached(self):
        try:
            with self.cache_path.open('rb') as stream:
                raw = stream.read(MAX_CACHE_BYTES + 1)
            if len(raw) > MAX_CACHE_BYTES:
                return None
            payload = json.loads(raw)
            if payload.get('product_id') != self.updates.license_client.product_id:
                return None
            return validate_news(payload['news'])
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None

    def fetch(self):
        payload = self.updates._request_manifest('/api/v1/studio/news')
        if payload.get('protocol') != 'studio-news-v1':
            raise UpdateError('Неверный формат новостей Studio')
        try:
            items = validate_news(payload.get('news'))
        except (ValueError, TypeError) as exc:
            raise UpdateError('Неверный формат новостей Studio') from exc
        # Cache only bounded display text, never a signed envelope containing
        # license/device identifiers. Cached text never authorizes any action.
        temporary = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.studio-news-', dir=self.cache_path.parent)
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'product_id': self.updates.license_client.product_id, 'news': items}, stream, ensure_ascii=False)
            os.replace(temporary, self.cache_path)
        except OSError:
            pass  # A full/read-only disk must not discard a valid fresh response.
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
        return items
