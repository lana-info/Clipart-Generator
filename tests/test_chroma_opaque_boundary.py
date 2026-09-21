import numpy as np
import pytest
from PIL import Image

from chroma_key import KEY_COLORS, remove_chroma_key_automatic


@pytest.mark.parametrize('key_name', ['red', 'green', 'blue'])
def test_opaque_profile_unmixes_narrow_aa_edge_without_recoloring_core(key_name):
    key = np.array(KEY_COLORS[key_name], dtype=float)
    foreground = np.array([130, 150, 170], dtype=float)
    rgb = np.tile(key, (24, 24, 1))
    rgb[5:19, 7:19] = foreground
    rgb[5:19, 6] = np.rint(0.4 * foreground + 0.6 * key)
    source = Image.fromarray(rgb.astype('uint8'))
    before = source.tobytes()
    result = np.asarray(remove_chroma_key_automatic(source, key_name, subject_profile='opaque_clipart'))
    assert abs(int(result[12, 6, 3]) - 102) <= 2
    assert np.max(np.abs(result[12, 6, :3].astype(float) - foreground)) <= 3
    np.testing.assert_array_equal(result[8:16, 9:17, :3], rgb[8:16, 9:17])
    assert np.all(result[8:16, 9:17, 3] == 255)
    assert np.all(result[:3, :, 3] == 0)
    assert source.tobytes() == before


def test_golden_opening_boundary_composites_improve_without_eroding_subject():
    from chroma_benchmark import load_manifest, load_golden_fixture
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[1] / 'benchmarks/chroma/manifest.json')
    case = next(c for c in manifest['cases'] if c['id'] == 'openings-blue')
    fixture = load_golden_fixture(manifest, case)
    result = np.asarray(remove_chroma_key_automatic(
        fixture.input_image, fixture.key_color, subject_profile='opaque_clipart')).astype(float)
    mask = np.asarray(fixture.expected_mask)
    truth = np.asarray(fixture.expected_foreground).astype(float)
    edge = (mask > 5) & (mask < 250)
    for background in [(0, 0, 0), (255, 255, 255), (255, 0, 255)]:
        actual_composite = result[..., :3] * result[..., 3:] / 255 + np.array(background) * (1-result[..., 3:]/255)
        expected_composite = truth * mask[..., None] / 255 + np.array(background) * (1-mask[..., None]/255)
        assert np.abs(actual_composite - expected_composite)[edge].mean() < 12
    assert np.all(result[..., 3][mask == 255] == 255)


@pytest.mark.parametrize('case_kind', ['no_core', 'distant', 'different_color', 'existing_alpha', 'near_key'])
def test_boundary_repair_declines_unreliable_references(case_kind):
    from chroma_key import _refine_opaque_boundary
    key = np.array([0, 0, 255], dtype=np.float32)
    source = np.full((24, 24, 4), [0, 0, 255, 255], dtype=np.uint8)
    result = np.zeros((24, 24, 4), dtype=np.uint8)
    source[5:19, 7:19] = [200, 100, 50, 255]
    result[5:19, 7:19] = [200, 100, 50, 255]
    source[12, 6] = [80, 40, 173, 255]
    result[12, 6] = [140, 70, 110, 150]
    if case_kind == 'no_core':
        result[5:19, 7:19, 3] = 180
    elif case_kind == 'distant':
        result[12, 1] = result[12, 6]
        result[12, 6] = 0
        source[12, 1] = source[12, 6]
    elif case_kind == 'different_color':
        source[12, 6] = [10, 220, 120, 255]
    elif case_kind == 'existing_alpha':
        source[12, 6, 3] = 128
    elif case_kind == 'near_key':
        result[5:19, 7:19] = [0, 0, 250, 255]
    before = result.copy()
    actual = _refine_opaque_boundary(Image.fromarray(source), Image.fromarray(result), key)
    np.testing.assert_array_equal(actual, before)


def test_boundary_stage_preserves_every_opaque_and_background_pixel():
    from chroma_benchmark import load_manifest, load_golden_fixture
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[1] / 'benchmarks/chroma/manifest.json')
    for case in manifest['cases']:
        fixture = load_golden_fixture(manifest, case)
        stages = {}
        remove_chroma_key_automatic(fixture.input_image, fixture.key_color,
                                   subject_profile='opaque_clipart',
                                   stage_observer=lambda name, image: stages.update({name: np.array(image)}))
        before, after = stages['source_rgb_restore'], stages['opaque_boundary']
        protected = (before[..., 3] == 0) | (before[..., 3] == 255)
        np.testing.assert_array_equal(after[protected], before[protected])


@pytest.mark.parametrize('key,channels', [('green', [0, 1, 2]), ('red', [1, 0, 2]), ('blue', [0, 2, 1])])
def test_opaque_rim_cleanup_is_not_undone_by_source_colour_restore(key, channels):
    from chroma_benchmark import load_manifest, load_golden_fixture
    from pathlib import Path
    manifest = load_manifest(Path(__file__).resolve().parents[1] / 'benchmarks/chroma/manifest.json')
    case = next(c for c in manifest['cases'] if c['id'] == 'color-spill-green')
    fixture = load_golden_fixture(manifest, case)
    source = Image.fromarray(np.asarray(fixture.input_image)[..., channels])
    actual = np.asarray(remove_chroma_key_automatic(source, key, subject_profile='opaque_clipart'))
    opaque = np.asarray(fixture.expected_mask) == 255
    truth = np.asarray(fixture.expected_foreground)[..., channels].astype(float)
    assert np.abs(actual[..., :3].astype(float) - truth)[opaque].mean() < 1.0
    assert np.all(actual[..., 3][opaque] == 255)


def test_opaque_profile_keeps_unprovable_interior_colour_patch():
    from tests.test_chroma_fine_detail import _opaque_subject_with_interior_blue_spill
    source, _, patch = _opaque_subject_with_interior_blue_spill()
    actual = np.asarray(remove_chroma_key_automatic(source, 'blue', subject_profile='opaque_clipart'))
    np.testing.assert_array_equal(actual[..., :3][patch], np.asarray(source)[patch])
    assert np.all(actual[..., 3][patch] == 255)


@pytest.mark.parametrize('kind', ['detached', 'non_key_colour', 'too_deep'])
def test_rim_support_does_not_authorize_unrelated_colour_changes(kind):
    from chroma_key import _supported_rim_correction
    cleaned = np.full((40, 40, 4), (160, 100, 60, 255), dtype=np.uint8)
    source = cleaned[..., :3].copy()
    depth = np.full((40, 40), 10.0, dtype=np.float32)
    depth[:, :2] = 1.0
    key = np.array([0, 0, 255], dtype=np.float32)
    if kind == 'detached':
        source[10:20, 5:9] = [112, 70, 118]
    elif kind == 'non_key_colour':
        source[10:20, :9] = [30, 210, 120]
    else:
        source[10:20, :20] = [112, 70, 118]
        depth[:, 2:] = 33
    supported = _supported_rim_correction(source, cleaned, key, depth)
    assert not np.any(supported[:, 2:])


def test_cleaned_pixels_survive_png_and_delivery_zip(tmp_path):
    from io import BytesIO
    from pathlib import Path
    from zipfile import ZipFile
    from chroma_benchmark import load_manifest, load_golden_fixture
    from studio_set_export import export_clipart_sets
    manifest = load_manifest(Path(__file__).resolve().parents[1] / 'benchmarks/chroma/manifest.json')
    case = next(c for c in manifest['cases'] if c['id'] == 'color-spill-green')
    fixture = load_golden_fixture(manifest, case)
    result = remove_chroma_key_automatic(fixture.input_image, fixture.key_color,
                                        subject_profile='opaque_clipart')
    output = tmp_path / 'clean.png'
    result.save(output)
    archives = export_clipart_sets([{'title': 'Clean rim', 'images': [output]}], tmp_path)
    with ZipFile(archives[0]) as archive:
        name = next(name for name in archive.namelist() if name.endswith('.png'))
        with Image.open(BytesIO(archive.read(name))) as delivered:
            np.testing.assert_array_equal(delivered, result)
