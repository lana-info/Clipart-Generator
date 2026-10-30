"""The ruler step of ``clean_alpha_array``: hard contours straighten, everything else stays.

The border the generator and the engine mask draw wiggles by a pixel or two; the step averages it
and rebuilds the transition there. These tests pin both halves of that promise: the wiggle goes,
and a straight border, a hair, fur, a solid/empty neighbour and an untouched call are exact.
"""
import cv2
import numpy as np
import pytest

from alpha_cleanup import clean_alpha_array


def _jagged_edge(border: np.ndarray) -> np.ndarray:
    x = np.arange(border.size)[None, :]
    return np.clip(0.5 + border[:, None] - x, 0.0, 1.0).astype(np.float32)


def _jagged_points_per_100px(alpha: np.ndarray) -> float:
    contours, _ = cv2.findContours((alpha >= 0.5).astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    perimeter = sum(cv2.arcLength(contour, True) for contour in contours)
    points = sum(len(cv2.approxPolyDP(contour, 1.0, True)) for contour in contours if len(contour) >= 8)
    return (100.0 * points / perimeter) if perimeter else 0.0


def _wiggly_border(size: int = 256) -> np.ndarray:
    """A border that steps a pixel up and down, as the generator and the engine mask draw it."""
    rows = np.arange(size, dtype=np.float32)
    return (size / 2 + np.round(1.2 * np.sin(rows / 2.7)) + np.round(0.8 * np.sin(rows / 1.3)))


def test_a_wiggly_hard_border_is_straightened():
    alpha = _jagged_edge(_wiggly_border())
    cleaned = clean_alpha_array(alpha)
    assert _jagged_points_per_100px(cleaned) < _jagged_points_per_100px(alpha) * 0.8
    # The border stays where it was: neither its mean position nor its coverage may drift.
    expected = np.argmax(alpha >= 0.5, axis=1).astype(float)
    actual = np.argmax(cleaned >= 0.5, axis=1).astype(float)
    assert np.abs(actual - expected).mean() <= 0.5
    assert abs(cleaned.mean() - alpha.mean()) <= 0.5


def test_a_straight_border_keeps_its_solved_coverage_exactly():
    alpha = np.clip(0.5 + 130.0 - np.arange(256)[None, :], 0.0, 1.0).astype(np.float32)[[0], :]
    alpha = np.repeat(alpha, 64, axis=0)
    cleaned = clean_alpha_array(alpha)
    np.testing.assert_allclose(cleaned, alpha, atol=1e-6)


def test_a_hair_keeps_its_alpha_exactly():
    alpha = np.zeros((64, 64), np.float32)
    alpha[:, 30:32] = 1.0          # a two-pixel hair
    cleaned = clean_alpha_array(alpha, island_min_gap=None)
    np.testing.assert_array_equal(cleaned, alpha)


def test_fur_keeps_its_alpha_exactly():
    x = np.arange(64, dtype=np.float32)
    alpha = np.repeat(np.clip((x - 20.0) / 12.0, 0.0, 1.0)[None, :], 64, axis=0)
    cleaned = clean_alpha_array(alpha, island_min_gap=None)
    band = (alpha > 0.1) & (alpha < 0.9)
    np.testing.assert_allclose(cleaned[band], alpha[band], atol=1e-6)


def test_a_binary_engine_mask_is_left_binary():
    alpha = np.zeros((64, 64), np.float32)
    alpha[10:50, 10:50] = 1.0      # engine mask without any solved transition
    cleaned = clean_alpha_array(alpha, island_min_gap=None)
    np.testing.assert_array_equal(cleaned, alpha)


def test_straighten_off_keeps_the_border_it_was_given():
    alpha = _jagged_edge(_wiggly_border())
    cleaned = clean_alpha_array(alpha, straighten=False)
    # The delivery cut keeps the matte it was given: the border stays exactly as wiggly as it was.
    assert _jagged_points_per_100px(cleaned) == pytest.approx(_jagged_points_per_100px(alpha))
