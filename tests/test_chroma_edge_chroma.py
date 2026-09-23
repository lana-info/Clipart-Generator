"""Protect coverage and genuine colours while repairing contaminated rim RGB."""
import numpy as np
import pytest
from PIL import Image

from chroma_rim import repair_edge_chroma


def edge_fixture():
    source = np.full((64, 64, 4), [0, 2, 253, 255], np.uint8)
    result = np.zeros_like(source)
    source[12:52, 12:52] = [240, 210, 150, 255]
    result[12:52, 12:52] = [240, 210, 150, 255]
    # Antialiased contour surrounding an opaque interior.
    result[12, 12:52, 3] = 128
    source[12, 12:52, :3] = [120, 106, 202]
    return source, result


@pytest.mark.parametrize("order", [[0, 1, 2], [2, 0, 1], [1, 2, 0]])
@pytest.mark.parametrize("defect", ["key_mixture", "opponent_fringe"])
def test_boundary_speck_and_opponent_fringe_recover_colour_and_coverage(order, defect):
    source, provisional = edge_fixture()
    foreground = np.array([240, 210, 150])
    key = np.array([0, 2, 253])
    coverage = .45 if defect == "key_mixture" else 1.0
    colour = np.rint(coverage * foreground + (1-coverage) * key) if defect == "key_mixture" else [240, 135, 190]
    source[13, 32, :3] = colour
    provisional[13, 32, :3] = colour
    source = source[..., order + [3]]
    provisional = provisional[..., order + [3]]
    before_source = source.copy()
    before_result = provisional.copy()
    actual = np.asarray(repair_edge_chroma(
        Image.fromarray(source), Image.fromarray(provisional), np.array([0, 2, 253])[order],
    ))
    np.testing.assert_allclose(actual[13, 32, :3], foreground[order], atol=3)
    assert abs(int(actual[13, 32, 3]) - round(coverage * 255)) <= 2
    other_pixels = np.ones(source.shape[:2], bool)
    other_pixels[13, 32] = False
    np.testing.assert_array_equal(actual[..., 3][other_pixels], provisional[..., 3][other_pixels])
    np.testing.assert_array_equal(actual[16:48, 16:48], provisional[16:48, 16:48])
    np.testing.assert_array_equal(source, before_source)
    np.testing.assert_array_equal(provisional, before_result)


@pytest.mark.parametrize("source_alpha", [0, 64, 128, 254])
def test_supplied_source_alpha_is_not_recoloured(source_alpha):
    source, provisional = edge_fixture()
    source[13, 32] = [100, 95, 190, source_alpha]
    provisional[13, 32] = [100, 95, 190, min(255, source_alpha)]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


def test_genuine_partial_pink_that_recomposites_to_source_is_preserved():
    source, provisional = edge_fixture()
    colour = np.array([240, 100, 160])
    alpha = 128 / 255
    source[12, 32, :3] = np.rint(alpha * colour + (1-alpha) * np.array([0, 2, 253]))
    provisional[12, 32, :3] = colour
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


@pytest.mark.parametrize("order", [[0, 1, 2], [2, 0, 1], [1, 2, 0]])
def test_unmixing_a_key_speck_does_not_reintroduce_its_opponent_fringe(order):
    source, provisional = edge_fixture()
    # A darker feather at partial coverage, with a depleted non-key channel. Recovering
    # only alpha would leave the same abnormal pink chroma at higher RGB values.
    source[13, 32, :3] = [58, 27, 188]
    provisional[13, 32, :3] = source[13, 32, :3]
    source = source[..., order + [3]]
    provisional = provisional[..., order + [3]]
    actual = np.asarray(repair_edge_chroma(
        Image.fromarray(source), Image.fromarray(provisional), np.array([0, 2, 253])[order],
    ))
    colour = actual[13, 32, :3].astype(float)[np.argsort(order)]
    assert 0 < actual[13, 32, 3] < 255
    assert abs(colour[1] / colour[0] - 210/240) < .01
    assert abs(colour[2] / colour[0] - 150/240) < .01


def test_enclosed_coloured_dot_has_no_path_to_a_partial_contour():
    source, provisional = edge_fixture()
    source[14, 32, :3] = [100, 95, 190]
    provisional[14, 32, :3] = [100, 95, 190]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


def test_flat_painted_key_coloured_patch_at_contour_is_preserved():
    source, provisional = edge_fixture()
    source[12:18, 28:36, :3] = [100, 95, 190]
    provisional[12:18, 28:36, :3] = [100, 95, 190]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


def test_green_detail_cannot_be_repainted_with_nearby_yellow_material():
    source, provisional = edge_fixture()
    source[13, 32, :3] = [90, 180, 150]
    provisional[13, 32, :3] = [90, 180, 150]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


def test_disconnected_detail_cannot_borrow_the_large_subject_colour():
    source, provisional = edge_fixture()
    source[8:10, 30:33] = [100, 95, 190, 255]
    provisional[8:10, 30:33] = [100, 95, 190, 128]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


def test_inconsistent_interior_colours_cannot_supply_a_replacement():
    source, provisional = edge_fixture()
    source[16:48, 16:48, :3] = [100, 180, 120]
    provisional[16:48, 16:48, :3] = [100, 180, 120]
    source[13, 32, :3] = [100, 95, 190]
    provisional[13, 32, :3] = [100, 95, 190]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


def test_weak_mixture_uses_source_fit_without_borrowing_conflicting_reference_hue():
    source, provisional = edge_fixture()
    source[16:48, 16:48, :3] = [240, 165, 105]
    provisional[16:48, 16:48, :3] = [240, 165, 105]
    foreground = np.array([70, 75, 55], float)
    key = np.array([0, 2, 253], float)
    source[13, 32, :3] = np.rint(.5 * foreground + .5 * key)
    provisional[13, 32, :3] = source[13, 32, :3]
    actual = np.asarray(repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), key))
    assert 0 < actual[13, 32, 3] < 255
    # The source is greenward even though both references are redward. A
    # source-derived unmix may retain that hue; repainting from the prior may not.
    assert actual[13, 32, 1] > actual[13, 32, 0]
    for background in [0, 255]:
        target = .5 * foreground + .5 * background
        old = provisional[13, 32, :3].astype(float)
        alpha = actual[13, 32, 3] / 255
        new = alpha * actual[13, 32, :3] + (1-alpha) * background
        assert np.abs(new-target).mean() < np.abs(old-target).mean()
    np.testing.assert_array_equal(actual[16:48, 16:48], provisional[16:48, 16:48])


def test_weak_reference_agreement_cannot_repaint_a_bad_source_fit():
    source, provisional = edge_fixture()
    source[16:48, 16:48, :3] = [240, 165, 105]
    provisional[16:48, 16:48, :3] = [240, 165, 105]
    source[13, 32, :3] = [20, 70, 190]
    provisional[13, 32, :3] = source[13, 32, :3]
    actual = repair_edge_chroma(Image.fromarray(source), Image.fromarray(provisional), [0, 2, 253])
    np.testing.assert_array_equal(actual, provisional)


@pytest.mark.parametrize("order", [[0, 1, 2], [2, 0, 1], [1, 2, 0]])
def test_additive_key_speck_at_material_junction_keeps_non_key_hue_and_alpha(order):
    source, provisional = edge_fixture()
    # A warm sample touches a green interior. Its pure-mixture reconstruction
    # would exceed 255. Both reference depths still agree on the key excess.
    source[13:52, 12:52, :3] = [100, 180, 70]
    provisional[13:52, 12:52, :3] = [100, 180, 70]
    source[13, 32, :3] = [150, 100, 220]
    provisional[13, 32, :3] = source[13, 32, :3]
    source = source[..., order + [3]]
    provisional = provisional[..., order + [3]]
    actual = np.asarray(repair_edge_chroma(
        Image.fromarray(source), Image.fromarray(provisional), np.array([0, 2, 253])[order],
    ))
    colour = actual[13, 32, :3][np.argsort(order)]
    np.testing.assert_array_equal(colour[:2], [150, 100])
    assert colour[2] < 100
    np.testing.assert_array_equal(actual[..., 3], provisional[..., 3])
    np.testing.assert_array_equal(actual[16:48, 16:48], provisional[16:48, 16:48])
