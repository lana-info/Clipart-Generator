"""A distant painted material must not recolour known opaque local paint.

The source fixtures are constructed here, without private audit artifacts or
coordinate-specific solver interventions. Their truth is chosen before keying.
Identical RGB can have conflicting latent explanations; these tests adopt the
opaque-clipart paint-preservation policy and use distinct sources for mixture
and additive-spill controls.
"""

import hashlib

import numpy as np
import pytest
from PIL import Image, ImageDraw

from chroma_key import remove_chroma_key_automatic


KEYS = [('blue', (0, 1, 2)), ('green', (0, 2, 1)), ('red', (2, 1, 0))]
TARGET = (15, 32)
DISTANT = (35, 36)
PAINT = np.array((218, 213, 216), dtype=np.uint8)
STAGES = (
    'staged_result', 'opaque_spill', 'source_rgb_restore', 'opaque_boundary',
    'rim_reclassification', 'edge_mixture', 'edge_key_spill',
    'edge_chroma_repair', 'opaque_edge_cleanup',
)


def _petal_source(order, *, distant_paint=True, supplied_alpha=False):
    image = Image.new('RGB', (96, 96), (0, 2, 253))
    draw = ImageDraw.Draw(image)
    draw.ellipse((22, 16, 86, 82), fill=(230, 203, 138))
    draw.ellipse((15, 25, 43, 39), fill=(245, 240, 225))
    pixels = np.array(image)
    pixels[TARGET[1], TARGET[0]] = PAINT
    if distant_paint:
        pixels[DISTANT[1], DISTANT[0]] = (227, 217, 197)
    # Separate physically composited AA fragment selects the public fallback.
    # It is not a modification to the petal's known opaque target.
    foreground = np.array((200, 150, 80))
    background = np.array((0, 2, 253))
    pixels[60:80, 10:20] = foreground
    pixels[60:80, 20] = np.rint(.5 * foreground + .5 * background)
    pixels = pixels[..., order]
    if supplied_alpha:
        alpha = np.full((96, 96, 1), 255, dtype=np.uint8)
        alpha[TARGET[1], TARGET[0], 0] = 173
        alpha[0, 0, 0] = 0
        pixels = np.concatenate((pixels, alpha), axis=2)
    return Image.fromarray(pixels)


def _automatic(image, key, profile='opaque_clipart'):
    stages = {}
    original = image.tobytes()
    result = np.array(remove_chroma_key_automatic(
        image, key, subject_profile=profile,
        stage_observer=lambda name, snapshot: stages.update({name: np.array(snapshot)}),
    ))
    assert image.tobytes() == original
    return result, stages


@pytest.mark.parametrize('key,order', KEYS)
def test_public_petal_keeps_known_opaque_foreground_and_alpha(key, order):
    result, stages = _automatic(_petal_source(order), key)
    assert 'staged_result' in stages
    expected = np.append(PAINT[list(order)], 255)
    np.testing.assert_array_equal(result[TARGET[1], TARGET[0]], expected)
    # RGB at alpha zero is intentionally not interpreted as foreground truth.
    assert np.all(result[:10, :, 3] == 0)


@pytest.mark.parametrize('key,order', KEYS)
def test_distant_material_cannot_change_local_paint_at_any_refinement(key, order):
    _, with_distant = _automatic(_petal_source(order), key)
    _, control = _automatic(_petal_source(order, distant_paint=False), key)
    assert tuple(with_distant) == STAGES
    assert tuple(control) == STAGES
    expected = np.append(PAINT[list(order)], 255)
    for stage in STAGES:
        local = with_distant[stage][TARGET[1], TARGET[0]]
        unchanged = control[stage][TARGET[1], TARGET[0]]
        np.testing.assert_array_equal(unchanged, expected, err_msg=f'control: {stage}')
        np.testing.assert_array_equal(local, unchanged, err_msg=f'distant paint: {stage}')


def _edge_source(order, coverage, spill):
    foreground = np.array((240, 200, 70), dtype=float)
    background = np.array((20, 45, 240), dtype=float)
    pixels = np.broadcast_to(background, (96, 96, 3)).copy().astype(np.uint8)
    pixels[20:76, 20:76] = foreground
    edge = coverage * foreground + (1 - coverage + spill) * background
    assert np.all((edge >= 0) & (edge <= 255))
    pixels[20, 20:76] = np.rint(edge)
    return Image.fromarray(pixels[..., order]), foreground[list(order)]


@pytest.mark.parametrize('key,order', KEYS)
@pytest.mark.parametrize('coverage,spill', [(1., 0.), (.8, 0.), (.8, .25), (1., .25)])
def test_distinct_opaque_mixture_and_additive_sources_keep_their_truth(key, order, coverage, spill):
    image, foreground = _edge_source(order, coverage, spill)
    result, _ = _automatic(image, key)
    np.testing.assert_allclose(result[20, 48, :3], foreground, atol=2)
    assert abs(int(result[20, 48, 3]) - round(coverage * 255)) <= 6
    np.testing.assert_array_equal(result[35, 48], np.append(foreground, 255))


# These byte-level compatibility baselines are recorded before the material fix.
# They are compatibility evidence, not a claim of truth for hidden RGB.
BASELINE_SHA256 = {
    ('legacy', 'blue'): '77eef4bfb1278aa1e775a588bf2a7fed65f497ed5bb6fcf832a1386644dccb51',
    ('supplied_alpha', 'blue'): '3fa3cc9c55a1747ecf0e25c17a21e6138b58f3f2b866a04d58000e7ffa7423e2',
    ('legacy', 'green'): '10df2825a029a87cd412ab43c5c37887425c28dbccfb008d3f6756e991dd7195',
    ('supplied_alpha', 'green'): 'ac69cbec1fbaa03cea082ee6c235b8b74100dd700ec256c0d77f3cb883481b31',
    ('legacy', 'red'): 'e1446dcfe32626fdb3f5658b04df4b7bb64736e3816c3f08e5d34cde706a31e0',
    ('supplied_alpha', 'red'): 'cae095e8c0da9525c199fe29a7b01886f9269e21d0fbb876ffe5cf6360bd390c',
}


@pytest.mark.parametrize('key,order', KEYS)
@pytest.mark.parametrize('case,profile,supplied_alpha', [
    ('legacy', 'legacy', False), ('supplied_alpha', 'opaque_clipart', True),
])
def test_legacy_and_supplied_alpha_keep_frozen_baseline_bytes(key, order, case, profile, supplied_alpha):
    result, _ = _automatic(_petal_source(order, supplied_alpha=supplied_alpha), key, profile)
    assert hashlib.sha256(result.tobytes()).hexdigest() == BASELINE_SHA256[(case, key)]


def _late_material_source(order, *, reflected_key=False):
    background = np.array((0, 2, 253))
    clean_material = np.array((252, 246, 210))
    pixels = np.broadcast_to(background, (96, 96, 3)).copy().astype(np.uint8)
    if reflected_key:
        # A distinct uniform opaque surface with a localized key-colour cast.
        # This is illumination mixing on alpha255 paint, not fractional AA.
        pixels[16:80, 16:80] = clean_material
        target = (21, 45)
        pixels[target[1], target[0]] = np.rint(.86 * clean_material + .14 * background)
        truth = clean_material
    else:
        # The two opaque painted materials are deliberately different. The
        # nearest key-poor donor belongs to the deeper, yellower material.
        pixels[16:80, 16:80] = (245, 240, 225)
        pixels[22:74, 22:74] = clean_material
        target = (16, 45)
        pixels[target[1], target[0]] = PAINT
        truth = PAINT
    # Independent quantified AA fragment selects the public staged branch.
    pixels[60:80, 4:10] = (200, 150, 80)
    pixels[60:80, 10] = (100, 76, 166)
    return Image.fromarray(pixels[..., order]), target, np.append(truth[list(order)], 255)


@pytest.mark.parametrize('key,order', KEYS)
def test_late_material_prior_keeps_already_correct_opaque_paint(key, order):
    image, (x, y), expected = _late_material_source(order)
    result, stages = _automatic(image, key)
    assert tuple(stages) == STAGES
    for stage in STAGES:
        np.testing.assert_array_equal(stages[stage][y, x], expected, err_msg=stage)
    np.testing.assert_array_equal(result[y, x], expected)


@pytest.mark.parametrize('key,order', KEYS)
def test_late_material_prior_still_removes_supported_key_reflection(key, order):
    image, (x, y), expected = _late_material_source(order, reflected_key=True)
    result, stages = _automatic(image, key)
    # Establish that correction actually occurs at this stage. Merely disabling
    # opaque_spill must fail this control even if another stage later helps.
    np.testing.assert_array_equal(stages['staged_result'][y, x], np.append(np.asarray(image)[y, x], 255))
    assert not np.array_equal(stages['staged_result'][y, x, :3], expected[:3])
    np.testing.assert_allclose(stages['opaque_spill'][y, x, :3], expected[:3], atol=1)
    assert stages['opaque_spill'][y, x, 3] == 255
    np.testing.assert_allclose(result[y, x, :3], expected[:3], atol=1)
    assert result[y, x, 3] == 255
