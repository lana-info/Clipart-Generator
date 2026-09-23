"""Botanical interior/geometry safety, not a claim of perfect boundary colour."""
import numpy as np
import pytest

from chroma_key import remove_chroma_key_automatic
from scripts.probe_chroma_botanical import fixture
from scripts.probe_chroma_fur import composite


@pytest.mark.parametrize('size', [256, 512])
@pytest.mark.parametrize('key', [(0, 0, 255), (20, 45, 240)])
def test_botanical_opaque_details_and_true_gaps_survive(size, key):
    truth = fixture(size)
    expected = np.array(truth)
    actual = np.array(remove_chroma_key_automatic(
        composite(truth, key), 'blue', subject_profile='opaque_clipart',
    ))
    opaque = expected[..., 3] == 255
    background = expected[..., 3] == 0
    assert np.any(opaque) and np.any(background)
    assert np.all(actual[..., 3][opaque] == 255)
    assert np.all(actual[..., 3][background] == 0)


@pytest.mark.parametrize('size', [256, 512])
@pytest.mark.parametrize('key', [(0, 0, 255), (20, 45, 240)])
def test_botanical_opaque_colors_are_exact(size, key):
    truth = fixture(size)
    expected = np.array(truth)
    actual = np.array(remove_chroma_key_automatic(
        composite(truth, key), 'blue', subject_profile='opaque_clipart',
    ))
    opaque = expected[..., 3] == 255
    np.testing.assert_array_equal(actual[..., :3][opaque], expected[..., :3][opaque])


def test_botanical_fixture_is_reproducible_and_has_subpixel_boundaries():
    first, second = np.array(fixture()), np.array(fixture())
    np.testing.assert_array_equal(first, second)
    assert np.any((first[..., 3] > 0) & (first[..., 3] < 255))
