import base64
import json
import struct
import zlib
from unittest.mock import Mock

import pytest

from studio_upcoming import StudioUpcomingClient, validate_upcoming, MAX_CACHE_BYTES, preview_bytes
from update_client import UpdateError


def png(width=2, height=2, color=6, raster=None):
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    channels = 4 if color == 6 else 3
    pixels = raster if raster is not None else (b'\0' + b'\x25\xc6\xb4\xff'[:channels] * width) * height
    raw = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, color, 0, 0, 0))
    return base64.b64encode(raw + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b'')).decode()


def card(**changes):
    return dict(dict(id='a'*32, title='Узоры', description='Создание бесшовных узоров', sort_order=0, preview_png=png()), **changes)


def test_signed_request_offline_invalid_and_fresh_withdrawal(tmp_path):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    updates._request_manifest.return_value = dict(protocol='studio-upcoming-v1', cards=[card()], device_key='private', license_id='private')
    client = StudioUpcomingClient(updates, tmp_path / 'upcoming.json')
    assert client.cached() is None
    assert client.fetch() == [card()]
    updates._request_manifest.assert_called_once_with('/api/v1/studio/upcoming')
    assert 'private' not in client.cache_path.read_text()
    updates._request_manifest.side_effect = UpdateError('offline')
    with pytest.raises(UpdateError):
        client.fetch()
    assert client.cached() == [card()]
    updates._request_manifest.side_effect = None
    for bad in (None, {}, dict(protocol='wrong', cards=[]), dict(protocol='studio-upcoming-v1', cards=[card(title='')])):
        updates._request_manifest.return_value = bad
        with pytest.raises(UpdateError):
            client.fetch()
        assert client.cached() == [card()]
    updates._request_manifest.return_value = dict(protocol='studio-upcoming-v1', cards=[])
    assert client.fetch() == client.cached() == []
    updates.download.assert_not_called()


@pytest.mark.parametrize('changes', [dict(id='../unsafe'), dict(id='A'*32), dict(title=' '), dict(title='x'*101),
    dict(description='x'*201), dict(description='\0'), dict(sort_order=True), dict(sort_order=-1),
    dict(sort_order=10000), dict(url='https://example.org'), dict(preview_png='x'*131073),
    dict(preview_png='bad'), dict(preview_png=png(width=513)), dict(preview_png=png(color=0)),
    dict(preview_png=png(raster=b'x'*1000000))])
def test_invalid_card(changes):
    with pytest.raises(ValueError):
        validate_upcoming([card(**changes)])


def test_order_count_duplicates_and_png_integrity():
    assert [x['id'] for x in validate_upcoming([card(id='b'*32), card(), card(id='c'*32, sort_order=1)])] == ['a'*32, 'b'*32, 'c'*32]
    for items in ([card()]*2, [card(id=f'{i:032x}') for i in range(13)]):
        with pytest.raises(ValueError):
            validate_upcoming(items)
    raw = bytearray(base64.b64decode(png()))
    raw[30] ^= 1
    for value in (base64.b64encode(raw).decode(), png() + '!', base64.b64encode(base64.b64decode(png()) + b'x').decode()):
        with pytest.raises(ValueError):
            preview_bytes(value)


def test_module_order_is_validated_cached_and_optional(tmp_path):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    client = StudioUpcomingClient(updates, tmp_path / 'upcoming.json')
    updates._request_manifest.return_value = dict(protocol='studio-upcoming-v1', cards=[], module_order=['patterns', 'clipart'])
    client.fetch()
    assert client.module_order == ['patterns', 'clipart']
    fresh = StudioUpcomingClient(updates, tmp_path / 'upcoming.json')
    assert fresh.cached() == [] and fresh.module_order == ['patterns', 'clipart']
    for bad in ('x', [1], ['A'], ['a', 'a'], ['a b'], ['x'] * 2, [f'm{i}' for i in range(33)], ['../x']):
        updates._request_manifest.return_value = dict(protocol='studio-upcoming-v1', cards=[], module_order=bad)
        with pytest.raises(UpdateError):
            client.fetch()
        assert client.module_order == ['patterns', 'clipart']  # a rejected feed keeps the last order
    updates._request_manifest.return_value = dict(protocol='studio-upcoming-v1', cards=[])  # older server
    client.fetch()
    assert client.module_order == []


def test_cache_bound_scope_and_content_validation(tmp_path):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    client = StudioUpcomingClient(updates, tmp_path / 'upcoming.json')
    for raw in ('x'*(MAX_CACHE_BYTES+1), '[]', '{', json.dumps(dict(product_id='other', cards=[])),
                json.dumps(dict(product_id='clipart-generator', cards=[card(title='')]))):
        client.cache_path.write_text(raw)
        assert client.cached() is None


def test_read_only_cache_does_not_discard_fresh_content(tmp_path, monkeypatch):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    updates._request_manifest.return_value = dict(protocol='studio-upcoming-v1', cards=[card()])
    client = StudioUpcomingClient(updates, tmp_path / 'upcoming.json')
    monkeypatch.setattr('studio_upcoming.os.replace', Mock(side_effect=OSError('full')))
    assert client.fetch() == [card()]
    assert list(tmp_path.iterdir()) == []
