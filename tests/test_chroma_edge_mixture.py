"""Colour/coverage regressions for opaque clipart boundary reconstruction."""
import cv2
import numpy as np
import pytest
from PIL import Image

from chroma_key import KEY_COLORS, remove_chroma_key_automatic, _remove_chroma_key_staged
from chroma_rim import refine_edge_mixture, suppress_edge_key_spill
from scripts.probe_chroma_fur import composite, fixture, measure
from scripts.probe_chroma_botanical import fixture as botanical_fixture


def _assert_approved_weak_selection(recovered, result, truth):
    before, after, expected = np.asarray(recovered), np.asarray(result), np.asarray(truth)
    np.testing.assert_array_equal(after[..., :3], before[..., :3])
    protected = (before[..., 3] >= 128) | (after[..., 3] > 0)
    np.testing.assert_array_equal(after[protected], before[protected])
    # These independent fixtures also prove that strong ground-truth paint stays.
    np.testing.assert_array_equal(after[expected[..., 3] >= 128], before[expected[..., 3] >= 128])
    removed = (before[..., 3] > 0) & (after[..., 3] == 0)
    assert np.any(removed & (expected[..., 3] > 0))  # True AA is deliberately lost.
    assert np.all(before[..., 3][removed] < 128)
    assert np.all(after[..., 3] <= before[..., 3])


@pytest.mark.parametrize("order", [[0, 1, 2], [2, 0, 1], [1, 2, 0]])
@pytest.mark.parametrize("coverage", [0.8, 1.0])
def test_additive_spill_does_not_turn_edge_into_a_clipped_highlight(order, coverage):
    key = np.array([0, 0, 255], np.float32)[order]
    foreground = np.array([240, 200, 70], np.float32)[order]
    source = np.broadcast_to(np.r_[key, 255], (64, 64, 4)).astype(np.uint8).copy()
    provisional = np.zeros_like(source)
    source[12:52, 12:52, :3] = foreground
    provisional[12:52, 12:52] = np.r_[foreground, 255]
    # Coverage .8 with the usual .2 background, plus .25 additive key spill.
    # Treating all key contamination as missing coverage produces RGB >255.
    source[12, 12:52, :3] = np.rint(coverage * foreground + (1-coverage+.25) * key)
    provisional[12, 12:52] = np.r_[foreground, 128]
    actual = np.asarray(refine_edge_mixture(
        Image.fromarray(source), Image.fromarray(provisional), key,
    ))
    np.testing.assert_allclose(actual[12, 32, :3], foreground, atol=2)
    assert abs(int(actual[12, 32, 3]) - round(coverage * 255)) <= 2


@pytest.mark.parametrize("order", [[0, 1, 2], [2, 0, 1], [1, 2, 0]])
def test_real_in_gamut_highlight_is_not_capped_to_its_darker_neighbour(order):
    key = np.array([0, 0, 255], np.float32)[order]
    neighbour = np.array([180, 150, 50], np.float32)[order]
    highlight = neighbour * 1.3
    source = np.broadcast_to(np.r_[key, 255], (64, 64, 4)).astype(np.uint8).copy()
    provisional = np.zeros_like(source)
    source[12:52, 12:52, :3] = neighbour
    provisional[12:52, 12:52] = np.r_[neighbour, 255]
    source[12, 12:52, :3] = np.rint(.8 * highlight + .2 * key)
    provisional[12, 12:52] = np.r_[neighbour, 128]
    actual = np.asarray(refine_edge_mixture(
        Image.fromarray(source), Image.fromarray(provisional), key,
    ))
    np.testing.assert_allclose(actual[12, 32, :3], highlight, atol=2)
    assert abs(int(actual[12, 32, 3]) - 204) <= 2


@pytest.mark.parametrize("key,order", [("blue", [0, 1, 2]), ("red", [2, 0, 1]), ("green", [1, 2, 0])])
@pytest.mark.parametrize("coverage", [0.8, 1.0])
def test_additive_spill_keeps_edge_brightness_through_the_staged_pipeline(key, order, coverage):
    background = np.array([20, 45, 240], np.float32)
    foreground = np.array([240, 200, 70], np.float32)
    source = np.broadcast_to(background, (96, 96, 3)).copy()
    source[20:76, 20:76] = foreground
    source[20, 20:76] = np.rint(coverage * foreground + (1-coverage+.25) * background)
    image = Image.fromarray(source.astype(np.uint8)[..., order])
    stages = {}
    result = remove_chroma_key_automatic(
        image, key, subject_profile="opaque_clipart",
        stage_observer=lambda name, stage: stages.update({name: stage}),
    )
    for stage, tolerance in [(stages["staged_result"], 6), (result, 2)]:
        actual = np.asarray(stage)
        np.testing.assert_allclose(actual[20, 48, :3], foreground[order], atol=2)
        assert abs(int(actual[20, 48, 3]) - round(coverage * 255)) <= tolerance
        np.testing.assert_array_equal(actual[30:66, 30:66, :3], np.asarray(image)[30:66, 30:66])
        assert np.all(actual[30:66, 30:66, 3] == 255)


@pytest.mark.parametrize("key,order", [("blue", [0, 1, 2]), ("red", [2, 0, 1]), ("green", [1, 2, 0])])
@pytest.mark.parametrize("brightness", [0.7, 1.0])
def test_staged_boundary_separates_brightness_from_coverage_before_restoration(key, order, brightness):
    background = np.array([20, 45, 240], np.float32)
    foreground = np.array([240, 210, 100], np.float32)
    source = np.broadcast_to(background, (96, 96, 3)).copy()
    source[20:76, 20:76] = foreground
    source[20, 20:76] = np.rint(.8 * brightness * foreground + .2 * background)
    source = source.astype(np.uint8)[..., order]
    actual = np.asarray(_remove_chroma_key_staged(Image.fromarray(source), key, opaque_subject=True))
    assert abs(int(actual[20, 48, 3]) - 204) <= 6
    np.testing.assert_allclose(actual[20, 48, :3], (foreground * brightness)[order], atol=3)
    np.testing.assert_array_equal(actual[30:66, 30:66, :3], source[30:66, 30:66])
    assert np.all(actual[30:66, 30:66, 3] == 255)


@pytest.mark.parametrize("key", ["blue", "green"])
@pytest.mark.parametrize("textured", [False, True])
def test_feather_colour_recovery_improves_before_approved_weak_edge_selection(key, textured):
    truth = fixture(textured)
    source = composite(truth, KEY_COLORS[key])
    stages = {}
    result = remove_chroma_key_automatic(
        source, key, subject_profile="opaque_clipart",
        stage_observer=lambda name, image: stages.update({name: image}),
    )
    before = measure(stages["rim_reclassification"], truth)
    recovered = stages["edge_chroma_repair"]
    after = measure(recovered, truth)
    for background in ("white", "black"):
        assert (after["partial_composites"][background]["mean_channel_error"]
                < before["partial_composites"][background]["mean_channel_error"] * .95)
    _assert_approved_weak_selection(recovered, result, truth)
    expected = np.asarray(truth)
    actual = np.asarray(result)
    opaque = expected[..., 3] == 255
    np.testing.assert_array_equal(actual[opaque], expected[opaque])
    assert np.all(actual[..., 3][expected[..., 3] == 0] == 0)


def test_darker_edge_does_not_confuse_foreground_brightness_with_coverage():
    key = np.array([0, 0, 255], np.float32)
    source = np.full((64, 64, 4), [0, 0, 255, 255], np.uint8)
    provisional = np.zeros_like(source)
    source[12:52, 12:52, :3] = [240, 200, 120]
    provisional[12:52, 12:52] = [240, 200, 120, 255]
    # A feather half as bright, at 50% coverage: s=.25 but alpha=.5.
    source[12, 12:52, :3] = [60, 50, 158]
    provisional[12, 12:52] = [240, 200, 120, 64]
    actual = np.asarray(refine_edge_mixture(
        Image.fromarray(source), Image.fromarray(provisional), key,
    ))
    assert abs(int(actual[12, 32, 3]) - 128) <= 1
    np.testing.assert_allclose(actual[12, 32, :3], [120, 100, 60], atol=1)
    depth = cv2.distanceTransform((provisional[..., 3] == 255).astype(np.uint8), cv2.DIST_L2, 5)
    np.testing.assert_array_equal(actual[depth > 3], provisional[depth > 3])


@pytest.mark.parametrize("source_alpha", [0, 64, 128, 254])
def test_existing_source_alpha_is_not_reinterpreted_as_key_coverage(source_alpha):
    source = np.full((48, 48, 4), [0, 0, 255, 255], np.uint8)
    provisional = np.zeros_like(source)
    source[8:40, 8:40] = [240, 200, 120, 255]
    provisional[8:40, 8:40] = [240, 200, 120, 255]
    source[8, 20] = [60, 50, 158, source_alpha]
    provisional[8, 20] = [240, 200, 120, min(64, source_alpha)]
    actual = np.asarray(refine_edge_mixture(
        Image.fromarray(source), Image.fromarray(provisional), np.array([0, 0, 255]),
    ))
    np.testing.assert_array_equal(actual[8, 20], provisional[8, 20])


def test_disconnected_partial_detail_cannot_take_colour_from_large_subject():
    source = np.full((64, 64, 3), [0, 0, 255], np.uint8)
    provisional = np.zeros((64, 64, 4), np.uint8)
    source[10:50, 10:40] = [240, 200, 120]
    provisional[10:50, 10:40] = [240, 200, 120, 255]
    source[25:28, 43:46] = [60, 50, 158]
    provisional[25:28, 43:46] = [120, 100, 60, 64]
    actual = refine_edge_mixture(Image.fromarray(source), Image.fromarray(provisional),
                                 np.array([0, 0, 255]))
    np.testing.assert_array_equal(actual, provisional)


def test_flat_painted_blue_patch_at_contour_keeps_its_colour_and_opacity():
    source = np.full((64, 64, 3), [0, 0, 255], np.uint8)
    provisional = np.zeros((64, 64, 4), np.uint8)
    source[10:50, 10:50] = [240, 200, 120]
    provisional[10:50, 10:50] = [240, 200, 120, 255]
    source[10:16, 22:28] = [120, 100, 188]
    provisional[10:16, 22:28] = [120, 100, 188, 255]
    actual = refine_edge_mixture(Image.fromarray(source), Image.fromarray(provisional),
                                 np.array([0, 0, 255]))
    np.testing.assert_array_equal(actual, provisional)


@pytest.mark.parametrize("size", [1, 2])
def test_small_enclosed_painted_key_tint_is_not_mistaken_for_edge_mixture(size):
    source = np.full((64, 64, 3), [0, 0, 255], np.uint8)
    provisional = np.zeros((64, 64, 4), np.uint8)
    source[10:50, 10:50] = [240, 200, 120]
    provisional[10:50, 10:50] = [240, 200, 120, 255]
    source[12:12+size, 22:22+size] = [120, 100, 188]
    provisional[12:12+size, 22:22+size] = [120, 100, 188, 255]
    actual = refine_edge_mixture(Image.fromarray(source), Image.fromarray(provisional),
                                 np.array([0, 0, 255]))
    np.testing.assert_array_equal(actual, provisional)


def test_already_consistent_partial_edge_keeps_its_exact_colour_and_coverage():
    truth = fixture(True)
    source = composite(truth, KEY_COLORS["blue"])
    actual = np.asarray(refine_edge_mixture(source, truth, np.array(KEY_COLORS["blue"])))
    expected = np.asarray(truth)
    partial = (expected[..., 3] > 0) & (expected[..., 3] < 255)
    np.testing.assert_array_equal(actual[partial], expected[partial])


@pytest.mark.parametrize("size", [256, 512])
@pytest.mark.parametrize("key", [(0, 0, 255), (20, 45, 240)])
def test_thin_green_stems_do_not_borrow_yellow_flower_colour(size, key):
    truth = botanical_fixture(size)
    stages = {}
    result = remove_chroma_key_automatic(
        composite(truth, key), "blue", subject_profile="opaque_clipart",
        stage_observer=lambda name, image: stages.update({name: image}),
    )
    before = measure(stages["rim_reclassification"], truth)
    recovered = stages["edge_chroma_repair"]
    after = measure(recovered, truth)
    for background in ("white", "black"):
        assert (after["partial_composites"][background]["mean_channel_error"]
                <= before["partial_composites"][background]["mean_channel_error"])
    _assert_approved_weak_selection(recovered, result, truth)
    expected, actual = np.asarray(truth), np.asarray(result)
    stems = ((expected[..., 1] > expected[..., 0]) & (expected[..., 3] >= 128))
    assert np.all(actual[..., 1][stems] > actual[..., 0][stems])


@pytest.mark.parametrize("key_channel", [0, 1, 2])
@pytest.mark.parametrize("alpha", [128, 255])
def test_residual_key_spill_is_removed_without_changing_coverage_or_other_channels(key_channel, alpha):
    order = [channel for channel in range(3) if channel != key_channel] + [key_channel]
    key = np.zeros(3, np.uint8)
    key[key_channel] = 255
    foreground = np.empty(3, np.uint8)
    foreground[order] = [240, 200, 120]
    source = np.broadcast_to(np.append(key, 255).astype(np.uint8), (80, 80, 4)).copy()
    source[12:68, 12:68, :3] = foreground
    provisional = np.zeros_like(source)
    provisional[12:68, 12:68, :3] = foreground
    provisional[12:68, 12:68, 3] = 255
    provisional[12, 12:68, key_channel] = 180
    provisional[12, 12:68, 3] = alpha
    source[12, 12:68, :3] = provisional[12, 12:68, :3]
    result = np.asarray(suppress_edge_key_spill(Image.fromarray(source), Image.fromarray(provisional), key))
    np.testing.assert_array_equal(result[..., 3], provisional[..., 3])
    np.testing.assert_array_equal(result[..., order[:2]], provisional[..., order[:2]])
    assert result[12, 40, key_channel] == 120
    np.testing.assert_array_equal(result[20:60, 20:60], provisional[20:60, 20:60])


def test_spill_cleanup_keeps_small_enclosed_painted_marks_and_disconnected_details():
    source = np.full((80, 80, 3), [0, 0, 255], np.uint8)
    provisional = np.zeros((80, 80, 4), np.uint8)
    source[12:68, 12:68] = [240, 200, 120]
    provisional[12:68, 12:68] = [240, 200, 120, 255]
    for y, x, size, alpha in [(14, 25, 1, 255), (14, 35, 2, 255), (30, 70, 2, 128)]:
        source[y:y+size, x:x+size] = [120, 100, 188]
        provisional[y:y+size, x:x+size] = [120, 100, 188, alpha]
    result = suppress_edge_key_spill(Image.fromarray(source), Image.fromarray(provisional), np.array([0, 0, 255]))
    np.testing.assert_array_equal(result, provisional)


def test_spill_cleanup_requires_agreement_at_two_interior_depths():
    source = np.full((80, 80, 3), [0, 0, 255], np.uint8)
    provisional = np.zeros((80, 80, 4), np.uint8)
    source[12:68, 12:68] = [240, 200, 120]
    provisional[12:68, 12:68] = [240, 200, 120, 255]
    source[12:20, 12:68] = [240, 200, 80]
    provisional[12, 12:68] = [240, 200, 200, 128]
    source[12, 12:68] = [240, 200, 200]
    result = np.asarray(suppress_edge_key_spill(Image.fromarray(source), Image.fromarray(provisional), np.array([0, 0, 255])))
    np.testing.assert_array_equal(result[12, 40], provisional[12, 40])


@pytest.mark.parametrize("key", ["red", "green", "blue"])
def test_spill_cleanup_preserves_source_consistent_partial_colours(key):
    truth = fixture(True)
    source = composite(truth, KEY_COLORS[key])
    actual = np.asarray(suppress_edge_key_spill(source, truth, np.array(KEY_COLORS[key])))
    expected = np.asarray(truth)
    partial = (expected[..., 3] > 0) & (expected[..., 3] < 255)
    np.testing.assert_array_equal(actual[partial], expected[partial])
