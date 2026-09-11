import hashlib
import json
from zipfile import ZipFile

from PIL import Image
import pytest

from studio_set_export import export_clipart_sets


def test_separate_archives_and_source_integrity(tmp_path):
    source = tmp_path / 'bear.png'
    Image.new('RGBA', (32, 32), (100, 30, 20, 128)).save(source)
    original = source.read_bytes()
    archives = export_clipart_sets([
        dict(title='Детский праздник', images=[source]),
        dict(title='Детский праздник', images=[source]),
    ], tmp_path)
    assert len(archives) == 2
    assert archives[0] != archives[1]
    for archive in archives:
        with ZipFile(archive) as z:
            manifest = json.loads(z.read('manifest.json'))
            assert manifest['count'] == 1
            entry = manifest['files'][0]
            assert z.read(entry['file']) == original
            assert entry['sha256'] == hashlib.sha256(original).hexdigest()
            assert z.read('overview.pdf').startswith(b'%PDF')
            assert str(tmp_path) not in json.dumps(manifest)
    assert source.read_bytes() == original


def test_failure_publishes_nothing_and_preserves_existing(tmp_path):
    source = tmp_path / 'good.png'
    Image.new('RGBA', (10, 10), 'red').save(source)
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError):
        export_clipart_sets([dict(title='Good', images=[source]),
                            dict(title='Bad', images=[tmp_path / 'missing.png'])], tmp_path)
    assert set(tmp_path.iterdir()) == before


def test_non_png_duplicates_and_empty_rejected(tmp_path):
    source = tmp_path / 'fake.png'
    Image.new('RGB', (10, 10), 'red').save(source, format='JPEG')
    for groups in ([], [dict(title='x', images=[source])],
                   [dict(title='x', images=[source, source])]):
        with pytest.raises(ValueError):
            export_clipart_sets(groups, tmp_path)
    assert list(tmp_path.iterdir()) == [source]
