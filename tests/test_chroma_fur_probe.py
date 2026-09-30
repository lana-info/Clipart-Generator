"""Known-truth opaque fur and safeguards for fractional openings."""
import numpy as np
import cv2
import pytest
from PIL import Image

from chroma_key import KEY_COLORS, remove_chroma_key_automatic
from scripts.probe_chroma_fur import composite, fixture, measure


@pytest.mark.parametrize('connected,conflicting', [(True, False), (False, False), (True, True)])
def test_extended_boundary_reference_requires_connection_and_depth_agreement(connected, conflicting):
    from chroma_key import _refine_opaque_boundary
    key = np.array([0, 0, 255], np.float32)
    truth = np.zeros((64, 64, 4), np.uint8)
    truth[..., :3] = (240, 210, 45)
    truth[15:45, 15:35, 3] = 255
    if conflicting:
        truth[15:45, 33:35, :3] = (235, 125, 30)
    if connected:
        truth[30, 35:44, 3] = 255
    truth[29, 43, 3] = 128
    source = composite(Image.fromarray(truth), tuple(map(int, key)))
    provisional = truth.copy()
    provisional[29, 43] = (140, 120, 140, 220)
    actual = np.array(_refine_opaque_boundary(source, Image.fromarray(provisional), key))
    if connected and not conflicting:
        assert np.max(np.abs(actual[29, 43].astype(int)-truth[29, 43].astype(int))) <= 2
    else:
        np.testing.assert_array_equal(actual, provisional)


@pytest.mark.parametrize('textured', [False, True])
def test_blue_fur_subpixel_gap_is_not_promoted_to_solid_background_color(textured):
    truth = fixture(textured)
    source = composite(truth, KEY_COLORS['blue'])
    result = np.array(remove_chroma_key_automatic(source, 'blue', subject_profile='opaque_clipart'))
    # This gap is surrounded by fibres but has only quarter-pixel coverage.
    expected = np.array(truth)[88, 281].astype(int)
    assert expected[3] == 64
    actual = result[88, 281].astype(int)
    assert abs(actual[3]-expected[3]) <= 2
    assert np.max(np.abs(actual[:3]-expected[:3])) <= 3


def test_probe_distinguishes_rgb_damage_from_alpha_damage():
    truth = Image.new('RGBA', (16, 16), (240, 210, 45, 255))
    assert measure(truth, truth)['opaque_rgb_error_over_20'] == 0
    pixels = np.array(truth)
    pixels[8, 8, :3] = (0, 0, 0)
    rgb = measure(Image.fromarray(pixels), truth)
    assert rgb['opaque_rgb_error_over_20'] == 1
    assert rgb['opaque_alpha_loss_over_20'] == 0
    pixels = np.array(truth)
    pixels[8, 8, 3] = 100
    alpha = measure(Image.fromarray(pixels), truth)
    assert alpha['opaque_rgb_error_over_20'] == 0
    assert alpha['opaque_alpha_loss_over_20'] == 1


@pytest.mark.parametrize('textured,key', [
    (False, 'blue'), (True, 'blue'), (False, 'green'), (True, 'green'),
    (False, 'red'), (True, 'red'),
])
def test_fur_opaque_details_preserve_color_and_opacity(textured, key):
    truth = fixture(textured)
    source = composite(truth, KEY_COLORS[key])
    result = remove_chroma_key_automatic(source, key, subject_profile='opaque_clipart')
    metrics = measure(result, truth)
    assert metrics['opaque_rgb_error_over_20'] == 0, metrics
    assert metrics['opaque_alpha_loss_over_20'] == 0, metrics


@pytest.mark.parametrize('textured', [False, True])
@pytest.mark.parametrize('key', ['red', 'green', 'blue'])
def test_fur_interior_keeps_exact_source_rgb_and_full_opacity(textured, key):
    truth = fixture(textured)
    expected = np.asarray(truth)
    source = composite(truth, KEY_COLORS[key])
    result = np.asarray(remove_chroma_key_automatic(source, key, subject_profile='opaque_clipart'))
    depth = cv2.distanceTransform((expected[..., 3] == 255).astype(np.uint8), cv2.DIST_L2, 5)
    interior = depth > 3
    np.testing.assert_array_equal(result[..., :3][interior], expected[..., :3][interior])
    assert np.all(result[..., 3][interior] == 255)


@pytest.mark.parametrize('background', [(0, 0, 255), (15, 30, 245), (20, 45, 240)])
@pytest.mark.parametrize('shade', [(240, 210, 45), (250, 230, 160), (170, 130, 25)])
def test_yellow_fur_on_blue_preserves_interior(background, shade):
    expected = np.array(fixture(True))
    shift = np.array(shade)-np.array([240, 210, 45])
    expected[..., :3] = np.clip(expected[..., :3].astype(int)+shift, 0, 255)
    source = composite(Image.fromarray(expected), background)
    result = np.array(remove_chroma_key_automatic(source, 'blue', subject_profile='opaque_clipart'))
    depth = cv2.distanceTransform((expected[..., 3] == 255).astype(np.uint8), cv2.DIST_L2, 5)
    interior = depth > 3
    np.testing.assert_array_equal(result[..., :3][interior], expected[..., :3][interior])
    assert np.all(result[..., 3][interior] == 255)


def test_opaque_recovery_keeps_real_holes_and_existing_alpha():
    truth = np.array(fixture(True))
    truth[210:230, 160:180, 3] = 0
    source = np.array(composite(Image.fromarray(truth), KEY_COLORS['red']).convert('RGBA'))
    source[160:180, 170:190, 3] = 128
    result = np.array(remove_chroma_key_automatic(Image.fromarray(source), 'red', subject_profile='opaque_clipart'))
    assert np.all(result[210:230, 160:180, 3] == 0)
    assert np.all(result[160:180, 170:190, 3] <= 128)


@pytest.mark.parametrize('kind', ['slit', 'hole_ring'])
def test_opaque_profile_does_not_fill_subpixel_openings(kind):
    key = np.array([255, 0, 0], dtype=float)
    foreground = np.array([240, 210, 45], dtype=float)
    alpha = np.zeros((80, 80), dtype=np.uint8)
    alpha[12:68, 12:68] = 255
    if kind == 'slit':
        alpha[20:60, 39:41] = 128
    else:
        alpha[28:52, 28:52] = 128
        alpha[36:44, 36:44] = 0
    rgb = np.rint(alpha[..., None]/255*foreground + (1-alpha[..., None]/255)*key).astype(np.uint8)
    actual = np.array(remove_chroma_key_automatic(Image.fromarray(rgb), 'red', subject_profile='opaque_clipart'))
    assert np.all(actual[..., 3][alpha == 128] < 200)
    assert np.all(actual[..., 3][alpha == 0] == 0)


def test_color_extension_does_not_cross_gaps_or_follow_chroma_drift():
    from chroma_key import _extend_opaque_color_runs
    rgb = np.full((64, 64, 3), (0, 0, 255), dtype=np.float32)
    matte = np.zeros((64, 64), dtype=np.float32)
    rgb[10:40, 10:30] = (230, 180, 30)
    matte[10:40, 10:30] = 1
    rgb[20, 30:55] = (230, 180, 30)
    matte[20, 30:55] = .5
    rgb[50:52, 50:52] = (230, 180, 30)
    matte[50:52, 50:52] = .5
    for x in range(30, 55):
        rgb[30, x] = (230, 180+x-29, 30)
    matte[30, 30:55] = .5
    before_rgb, before_matte = rgb.copy(), matte.copy()
    actual, _ = _extend_opaque_color_runs(rgb, matte, np.array([0, 0, 255], np.float32))
    assert np.all(actual[20, 30:55] == 1)
    assert np.all(actual[50:52, 50:52] == .5)
    assert np.all(actual[30, 30:55] == .5)
    np.testing.assert_array_equal(rgb, before_rgb)
    np.testing.assert_array_equal(matte, before_matte)


def test_color_extension_accepts_shading_without_replacing_source_rgb():
    from chroma_key import _extend_opaque_color_runs
    key = np.array([255, 0, 0], dtype=np.float32)
    rgb = np.broadcast_to(key, (64, 64, 3)).copy()
    matte = np.zeros((64, 64), dtype=np.float32)
    rgb[10:40, 10:30] = (230, 180, 30)
    matte[10:40, 10:30] = 1
    for x in range(30, 50):
        rgb[20, x] = np.array([230, 180, 30])-(x-29)
    matte[20, 30:50] = .85
    before = rgb.copy()
    actual, _ = _extend_opaque_color_runs(rgb, matte, key)
    assert np.all(actual[20, 30:50] == 1)
    np.testing.assert_array_equal(rgb, before)


def test_provisional_opaque_pixel_is_not_its_own_color_evidence():
    from chroma_key import _opaque_colors_explained_by_key_mix
    key = np.array([20, 45, 240], dtype=np.float32)
    foreground = np.array([255, 236, 166], dtype=np.float32)
    rgb = np.broadcast_to(key, (40, 40, 3)).copy()
    matte = np.zeros((40, 40), dtype=np.float32)
    rgb[6:34, 6:34] = foreground
    matte[6:34, 6:34] = 1
    rgb[12, 10] = np.rint(.565*foreground+.435*key)
    before = matte.copy()
    dubious = _opaque_colors_explained_by_key_mix(rgb, matte, key)
    assert dubious[12, 10]
    assert not dubious[12, 13]
    np.testing.assert_array_equal(matte, before)


def test_recurring_opaque_pigment_survives_other_colours_but_not_a_background_gap():
    from chroma_key import _extend_opaque_color_runs
    key = np.array([255, 0, 0], np.float32)
    rgb = np.broadcast_to(key, (64, 64, 3)).copy()
    matte = np.zeros((64, 64), np.float32)
    rgb[10:50, 10:50] = (100, 170, 60)
    matte[10:50, 10:50] = 1
    rgb[14:26, 14:26] = (180, 145, 35)
    # The same warm pigment returns at a thin boundary after a different hue.
    rgb[40:42, 45:56] = (180, 145, 35)
    matte[40:42, 45:56] = .86
    # Identical observed RGB alone cannot establish a disconnected detail.
    rgb[55:57, 55:57] = (180, 145, 35)
    matte[55:57, 55:57] = .86
    before_rgb, before_matte = rgb.copy(), matte.copy()
    actual, _ = _extend_opaque_color_runs(rgb, matte, key)
    assert np.all(actual[40:42, 45:56] == 1)
    assert np.all(actual[55:57, 55:57] == .86)
    np.testing.assert_array_equal(rgb, before_rgb)
    np.testing.assert_array_equal(matte, before_matte)


@pytest.mark.parametrize('kind', ['rim', 'slit', 'long_fibre'])
@pytest.mark.parametrize('coverage', [.05, .6, .96])
def test_repeated_palette_colour_cannot_fill_a_supported_key_mixture(kind, coverage):
    from chroma_key import _extend_opaque_color_runs
    key = np.array([0, 0, 255], np.float32)
    foreground = np.array([240, 200, 40], np.float32)
    mixed = np.rint(coverage * foreground + (1-coverage) * key)
    rgb = np.broadcast_to(key, (64, 64, 3)).copy()
    matte = np.zeros((64, 64), np.float32)
    rgb[10:50, 10:50] = foreground
    matte[10:50, 10:50] = 1
    # This legitimate opaque pigment exactly matches the rim/slit's source RGB.
    rgb[15:27, 15:27] = mixed
    region = {
        'rim': np.s_[30:45, 49:50],
        'slit': np.s_[30:45, 35:37],
        'long_fibre': np.s_[40:41, 49:62],
    }[kind]
    rgb[region] = mixed
    matte[region] = coverage
    before_rgb, before_matte = rgb.copy(), matte.copy()
    actual, _ = _extend_opaque_color_runs(rgb, matte, key)
    np.testing.assert_array_equal(actual[region], before_matte[region])
    np.testing.assert_array_equal(rgb, before_rgb)
    np.testing.assert_array_equal(matte, before_matte)
