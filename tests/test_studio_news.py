import json
from unittest.mock import Mock

import pytest

from studio_news import StudioNewsClient
from update_client import UpdateError


def test_verified_feed_and_empty_withdrawal_replace_cache_without_credentials(tmp_path):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    item = dict(id='a' * 32, title='Новость', body='<b>Обычный текст</b>', published_at='2026-09-23T12:00:00+00:00')
    updates._request_manifest.return_value = dict(protocol='studio-news-v1', news=[item], license_id='private', device_key='private')
    client = StudioNewsClient(updates, tmp_path / 'news.json')
    assert client.cached() is None
    assert client.fetch() == [item]
    updates._request_manifest.assert_called_once_with('/api/v1/studio/news')
    assert client.cached() == [item]
    assert 'private' not in client.cache_path.read_text()
    updates._request_manifest.side_effect = UpdateError('offline')
    with pytest.raises(UpdateError):
        client.fetch()
    assert client.cached() == [item]
    updates._request_manifest.side_effect = None
    updates._request_manifest.return_value = dict(protocol='studio-news-v1', news=[])
    assert client.fetch() == []
    assert client.cached() == []


@pytest.mark.parametrize('change', [dict(title='x' * 101), dict(body='x' * 601), dict(body='\x00'), dict(published_at='bad'), dict(published_at='2026-01-01'), dict(id='../unsafe')])
def test_invalid_feed_never_overwrites_saved_news(tmp_path, change):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    item = dict(id='a' * 32, title='Title', body='Body', published_at='2026-09-23T12:00:00+00:00')
    updates._request_manifest.return_value = dict(protocol='studio-news-v1', news=[item])
    client = StudioNewsClient(updates, tmp_path / 'news.json')
    client.fetch()
    updates._request_manifest.return_value['news'] = [dict(item, **change)]
    with pytest.raises(UpdateError):
        client.fetch()
    assert client.cached() == [item]


def test_cache_is_bounded_and_scoped_to_product(tmp_path):
    updates = Mock()
    updates.license_client.product_id = 'clipart-generator'
    client = StudioNewsClient(updates, tmp_path / 'news.json')
    for raw in ('x' * 9000, '[]', '{', json.dumps(dict(product_id='other', news=[]))):
        client.cache_path.write_text(raw)
        assert client.cached() is None
