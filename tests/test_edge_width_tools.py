"""Alpha edge buttons: harder/softer transition width and 1 px shrink/grow (PRD item 4), Qt-free."""
import numpy as np
from PIL import Image
import pytest

from studio_edge_operations import EDGE_MIN_WIDTH, area_scope, edge_proposal, edge_width

ROW = 30


def vertical_edge(width=6.0, at=50.0):
    """Opaque on the left, a linear ramp of ``width`` px centred at ``at``."""
    x = np.arange(100, dtype=np.float64)
    profile = np.clip((at - x) / width + 0.5, 0, 1)
    return np.rint(np.tile(profile, (60, 1)) * 255).astype(np.uint8)


def run(alpha, operation, **kw):
    return np.asarray(edge_proposal(Image.fromarray(alpha), operation, **kw))


def transition(alpha):
    row = alpha[ROW]
    return int(np.count_nonzero((row > 0) & (row < 255)))


def crossing(alpha):
    row = alpha[ROW].astype(np.float64)
    i = int(np.nonzero(row < 127.5)[0][0])
    return i - 1 + (row[i - 1] - 127.5) / (row[i - 1] - row[i])


def test_width_is_measured_from_the_ramp():
    assert edge_width(vertical_edge(6)) == pytest.approx(6, abs=0.2)
    assert edge_width(vertical_edge(12)) == pytest.approx(12, abs=0.3)
    binary = (vertical_edge(6) >= 128).astype(np.uint8) * 255
    assert edge_width(binary) == 1.0
    assert edge_width(np.full((20, 20), 255, np.uint8)) is None


def test_harder_narrows_a_6px_edge_to_2_3px_without_a_staircase():
    alpha = vertical_edge(6)
    harder = run(alpha, 'harder')
    assert 2 <= transition(harder) <= 3
    assert transition(harder) >= 2, 'never a bare 0/255 step'
    assert crossing(harder) == pytest.approx(crossing(alpha), abs=0.15), 'the edge stays in place'
    again = run(harder, 'harder')
    np.testing.assert_array_equal(again, harder)   # the 3 px limit: further presses do nothing
    assert edge_width(harder) <= EDGE_MIN_WIDTH * 1.35


def test_softer_widens_by_the_same_step_and_repeats():
    alpha = vertical_edge(6)
    softer = run(alpha, 'softer')
    assert edge_width(softer) > edge_width(alpha) + 1.5
    assert transition(softer) > transition(alpha)
    softer2 = run(softer, 'softer')
    assert edge_width(softer2) > edge_width(softer) + 1.5
    # Fully transparent pixels stay transparent: their hidden colour is never revealed.
    assert np.all(softer[alpha == 0] == 0)
    hard_back = run(softer, 'harder')
    assert abs(edge_width(hard_back) - edge_width(alpha)) <= 1.5


@pytest.mark.parametrize('operation, delta', [('shrink', -1), ('grow', 1)])
@pytest.mark.parametrize('width', [1, 6])
def test_shrink_and_grow_move_the_edge_exactly_one_pixel(operation, delta, width):
    alpha = vertical_edge(width) if width > 1 else (vertical_edge(6) >= 128).astype(np.uint8) * 255
    moved = run(alpha, operation)
    assert crossing(moved) - crossing(alpha) == pytest.approx(delta, abs=0.1)
    assert abs(transition(moved) - transition(alpha)) <= 1, 'softness is kept'
    twice = run(moved, operation)
    assert crossing(twice) - crossing(alpha) == pytest.approx(2 * delta, abs=0.15)


def test_round_object_shrinks_by_one_pixel_of_radius():
    y, x = np.mgrid[:200, :200]
    radius = np.hypot(x - 100, y - 100)
    circle = np.rint(np.clip((70 - radius) / 6 + 0.5, 0, 1) * 255).astype(np.uint8)
    area_radius = lambda a: np.sqrt((a.astype(np.float64) / 255).sum() / np.pi)
    assert area_radius(run(circle, 'shrink')) - area_radius(circle) == pytest.approx(-1, abs=0.1)
    assert area_radius(run(circle, 'grow')) - area_radius(circle) == pytest.approx(1, abs=0.1)
    assert edge_width(run(circle, 'harder')) == pytest.approx(3, abs=0.5)


@pytest.mark.parametrize('operation', ['harder', 'softer', 'shrink', 'grow'])
def test_interior_and_empty_background_are_untouched(operation):
    alpha = vertical_edge(6)
    result = run(alpha, operation)
    np.testing.assert_array_equal(result[:, :40], alpha[:, :40])
    np.testing.assert_array_equal(result[:, 62:], alpha[:, 62:])


@pytest.mark.parametrize('operation', ['harder', 'softer', 'shrink', 'grow', 'smooth'])
def test_lasso_area_bounds_the_action(operation):
    alpha = vertical_edge(6)
    area = [[(30, 0), (70, 0), (70, 20), (30, 20)]]
    result = run(alpha, operation, area=area)
    scope = np.asarray(area_scope(alpha.shape[::-1], area)) > 0
    np.testing.assert_array_equal(result[~scope], alpha[~scope])
    if operation != 'smooth':          # smoothing leaves straight antialiased edges alone
        assert not np.array_equal(result[scope], alpha[scope])


def test_area_wins_over_point_selection_and_invalid_areas_are_rejected():
    alpha = vertical_edge(6)
    with pytest.raises(ValueError):
        run(alpha, 'shrink', area=[[(0, 0), (5, 5)]])
    with pytest.raises(ValueError):
        run(alpha, 'shrink', area=[[(0, 0), (1, 0), (0, 1)]] * 65)
    with pytest.raises(ValueError):
        run(alpha, 'unknown')


def test_mask_without_edge_is_unchanged():
    for value in (0, 255):
        flat = np.full((40, 40), value, np.uint8)
        for operation in ('harder', 'softer', 'shrink', 'grow'):
            np.testing.assert_array_equal(run(flat, operation), flat)


@pytest.mark.parametrize('operation, delta', [('shrink', -1), ('grow', 1)])
def test_shift_keeps_the_profile_of_a_real_blurred_edge(operation, delta):
    """A Gaussian edge has long faint tails; the shift must slide them, not cut them into a step."""
    import cv2
    binary = np.zeros((60, 100), np.float32)
    binary[:, :50] = 255
    alpha = np.rint(cv2.GaussianBlur(binary, (0, 0), 2.2)).astype(np.uint8)
    moved = run(alpha, operation)
    original, shifted = alpha[ROW].astype(int), moved[ROW].astype(int)
    # Every value of the profile reappears one pixel further in/out (within rounding).
    if delta < 0:
        assert np.all(np.abs(shifted[:-1][20:80] - original[1:][20:80]) <= 1)
    else:
        assert np.all(np.abs(shifted[1:][20:80] - original[:-1][20:80]) <= 1)
    assert transition(moved) == pytest.approx(transition(alpha), abs=1)
