"""Signed promotional content with bounded validation and a content-only cache."""
import base64
import binascii
import json
import os
from pathlib import Path
import struct
import tempfile
import zlib

from update_client import UpdateError

MAX_CACHE_BYTES = 2 * 1024 * 1024
MAX_PNG_BYTES = 96 * 1024
MAX_CARDS = 12
MAX_MODULE_ORDER = 32


def preview_bytes(value):
    """Validate PNG structure and bounded raster before any GUI decoder sees it."""
    if not isinstance(value, str) or len(value) > 4 * ((MAX_PNG_BYTES + 2) // 3):
        raise ValueError('Invalid preview size')
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('Invalid preview encoding') from exc
    if len(raw) > MAX_PNG_BYTES or raw[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Invalid preview PNG')
    offset, compressed, dimensions = 8, bytearray(), None
    ended = False
    while offset < len(raw):
        if offset + 12 > len(raw):
            raise ValueError('Truncated PNG')
        length = struct.unpack('>I', raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + length
        if end > len(raw):
            raise ValueError('Truncated PNG chunk')
        data = raw[offset + 8:end - 4]
        crc = struct.unpack('>I', raw[end - 4:end])[0]
        if zlib.crc32(kind + data) & 0xffffffff != crc:
            raise ValueError('Invalid PNG checksum')
        if kind == b'IHDR':
            if offset != 8 or length != 13:
                raise ValueError('Invalid PNG header')
            w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if not (1 <= w <= 512 and 1 <= h <= 512 and depth == 8 and color in (2, 6)
                    and compression == filtering == interlace == 0):
                raise ValueError('Unsupported PNG raster')
            dimensions = (w, h, 3 if color == 2 else 4)
        elif kind == b'IDAT':
            if dimensions is None:
                raise ValueError('Invalid PNG data order')
            compressed.extend(data)
        elif kind == b'IEND':
            if length or not compressed or end != len(raw):
                raise ValueError('Invalid PNG end')
            ended = True
        else:
            # The server publishes canonical raster PNG, without metadata or animation.
            raise ValueError('Unsupported PNG chunk')
        offset = end
    if not ended or dimensions is None:
        raise ValueError('Incomplete PNG')
    w, h, channels = dimensions
    expected = h * (1 + w * channels)
    try:
        decoder = zlib.decompressobj()
        raster = decoder.decompress(bytes(compressed), expected + 1)
    except zlib.error as exc:
        raise ValueError('Invalid PNG raster') from exc
    if (len(raster) != expected or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail
            or any(raster[i] > 4 for i in range(0, expected, 1 + w * channels))):
        raise ValueError('Invalid PNG raster size')
    return raw


def validate_module_order(value):
    """Owner-defined order of module ids; display only, never an authorization decision."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > MAX_MODULE_ORDER:
        raise ValueError('Invalid module order')
    clean = []
    for item in value:
        if (not isinstance(item, str) or not 1 <= len(item) <= 64 or not item[0].islower() or not item[0].isascii()
                or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789_-' for c in item) or item in clean):
            raise ValueError('Invalid module order')
        clean.append(item)
    return clean


def validate_upcoming(items):
    if not isinstance(items, list) or len(items) > MAX_CARDS:
        raise ValueError('Invalid upcoming cards')
    clean, identities = [], set()
    for row in items:
        if not isinstance(row, dict) or set(row) != {'id', 'title', 'description', 'sort_order', 'preview_png'}:
            raise ValueError('Invalid upcoming card')
        identity = row['id']
        if (not isinstance(identity, str) or len(identity) != 32
                or any(c not in '0123456789abcdef' for c in identity) or identity in identities):
            raise ValueError('Invalid upcoming identity')
        identities.add(identity)
        for name, limit in (('title', 100), ('description', 200)):
            value = row[name]
            if (not isinstance(value, str) or not value.strip() or len(value) > limit
                    or any(ord(c) < 32 and c not in '\n\t' for c in value)):
                raise ValueError('Invalid upcoming text')
        if type(row['sort_order']) is not int or not 0 <= row['sort_order'] <= 9999:
            raise ValueError('Invalid upcoming order')
        preview_bytes(row['preview_png'])
        clean.append(dict(row))
    return sorted(clean, key=lambda row: (row['sort_order'], row['id']))


class StudioUpcomingClient:
    def __init__(self, updates, cache_path):
        self.updates, self.cache_path = updates, Path(cache_path)
        self.module_order = []

    def cached(self):
        try:
            with self.cache_path.open('rb') as stream:
                raw = stream.read(MAX_CACHE_BYTES + 1)
            if len(raw) > MAX_CACHE_BYTES:
                return None
            payload = json.loads(raw)
            if (not {'product_id', 'cards'} <= set(payload) <= {'product_id', 'cards', 'module_order'}
                    or payload['product_id'] != self.updates.license_client.product_id):
                return None
            items = validate_upcoming(payload['cards'])
            self.module_order = validate_module_order(payload.get('module_order'))
            return items
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
            return None

    def fetch(self):
        payload = self.updates._request_manifest('/api/v1/studio/upcoming')
        try:
            if not isinstance(payload, dict) or payload.get('protocol') != 'studio-upcoming-v1':
                raise ValueError('Invalid protocol')
            items = validate_upcoming(payload.get('cards'))
            order = validate_module_order(payload.get('module_order'))
            raw = json.dumps({'product_id': self.updates.license_client.product_id, 'cards': items,
                              'module_order': order}, ensure_ascii=False).encode('utf-8')
            if len(raw) > MAX_CACHE_BYTES:
                raise ValueError('Cache too large')
        except (ValueError, TypeError) as exc:
            raise UpdateError('Неверный формат будущих модулей Studio') from exc
        self.module_order = order
        temporary = None
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(prefix='.studio-upcoming-', dir=self.cache_path.parent)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
            os.replace(temporary, self.cache_path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
        return items
