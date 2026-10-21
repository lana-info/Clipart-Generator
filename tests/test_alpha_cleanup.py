import numpy as np
from PIL import Image

from alpha_cleanup import clean_alpha, clean_alpha_array


def _disc(size=200, radius=60, ramp=1.0):
    y, x = np.mgrid[:size, :size]
    distance = np.hypot(x - size / 2, y - size / 2)
    return np.clip((radius - distance) / ramp + 0.5, 0.0, 1.0).astype(np.float32)


def test_faint_haze_far_from_subject_is_removed():
    alpha = _disc()
    alpha[5:30, 5:30] = 0.08
    cleaned = clean_alpha_array(alpha)
    assert cleaned[5:30, 5:30].max() == 0.0
    assert cleaned[100, 100] == 1.0


def test_faint_edge_next_to_subject_is_kept_as_edge():
    cleaned = clean_alpha_array(_disc(ramp=1.0))
    assert 0.0 < cleaned[100, 100 + 60] < 1.0 or cleaned[100, 100 + 59] > 0.0


def test_smooth_wide_edge_is_tightened_to_few_pixels():
    alpha = _disc(ramp=6.0)
    before = int(((alpha > 0.1) & (alpha < 0.9)).sum())
    cleaned = clean_alpha_array(alpha)
    after = int(((cleaned > 0.1) & (cleaned < 0.9)).sum())
    assert after < before * 0.6


def test_very_wide_fur_like_band_is_left_unchanged():
    alpha = _disc(ramp=30.0)
    cleaned = clean_alpha_array(alpha)
    # Only the faint tail (below the haze floor) may go; the visible fur body stays.
    band = (alpha > 0.3) & (alpha < 0.9)
    assert np.allclose(cleaned[band], alpha[band], atol=1e-6)


def test_practically_opaque_becomes_fully_opaque():
    alpha = np.full((40, 40), 254 / 255, np.float32)
    assert clean_alpha_array(alpha).min() == 1.0


def test_tiny_isolated_weak_speck_is_removed():
    alpha = _disc()
    alpha[10:13, 10:13] = 0.4
    assert clean_alpha_array(alpha)[10:13, 10:13].max() == 0.0


def test_rgb_is_never_modified():
    rng = np.random.default_rng(1)
    pixels = rng.integers(0, 256, (64, 64, 4), dtype=np.uint8)
    pixels[..., 3] = (_disc(64, 20, 4.0) * 255).astype(np.uint8)
    source = Image.fromarray(pixels, "RGBA")
    result = clean_alpha(source)
    assert np.array_equal(np.array(result)[..., :3], pixels[..., :3])
    assert result.size == source.size and result.mode == "RGBA"


def test_small_detached_island_is_removed_but_second_large_object_stays():
    alpha = np.zeros((300, 300), np.float32)
    alpha[20:140, 20:140] = 1.0        # large object
    alpha[160:280, 160:280] = 1.0      # second large object (a set of items)
    alpha[10:16, 280:286] = 1.0        # 6x6 debris, far from both
    cleaned = clean_alpha_array(alpha)
    assert cleaned[10:16, 280:286].max() == 0.0
    assert cleaned[30, 30] == 1.0 and cleaned[200, 200] == 1.0
