"""Manual edge-paint replacement must preserve geometry and unselected paint."""
from concurrent.futures import CancelledError

import cv2
import numpy as np
from PIL import Image, ImageDraw
import pytest

import edge_colour_correction as correction
from edge_colour_correction import propose_edge_colour


def scene():
    pixels = np.zeros((88, 104, 4), np.uint8)
    pixels[..., :3] = (0, 0, 255)  # Hidden RGB must never become a donor.
    for y in range(12, 76):
        pixels[y, 18:86] = (200 + y // 8, 165 + y // 8, 105 + y // 8, 255)
        for x, alpha in [(15, 24), (16, 100), (17, 210)]:
            pixels[y, x] = (*pixels[y, 22, :3], alpha)
    return pixels


def apply(pixels, proposal):
    result = pixels.copy()
    if proposal is not None:
        l, t, r, b = proposal.bounds
        assert proposal.image_patch.mode == "RGB"
        result[t:b, l:r, :3] = np.array(proposal.image_patch)
    return result


def test_smooth_paint_recovers_selected_rim_without_speckles_or_geometry_changes():
    truth = scene()
    damaged = truth.copy()
    damaged[22:65, 15:21, :3] = (110, 95, 155)
    image = Image.fromarray(damaged)
    before = image.tobytes()
    bounds = (10, 22, 27, 65)
    proposal = propose_edge_colour(image, Image.new("L", (17, 43), 255), bounds)
    assert proposal is not None
    actual = apply(damaged, proposal)
    assert np.max(abs(actual[27:60, 15:21, :3].astype(int) - truth[27:60, 15:21, :3])) <= 2
    assert np.max(np.abs(np.diff(actual[27:60, 16, :3].astype(int), axis=0))) <= 1
    np.testing.assert_array_equal(actual[..., 3], damaged[..., 3])
    np.testing.assert_array_equal(actual[:, 22:], damaged[:, 22:])
    np.testing.assert_array_equal(actual[:22], damaged[:22])
    np.testing.assert_array_equal(actual[65:], damaged[65:])
    np.testing.assert_array_equal(actual[damaged[..., 3] == 0], damaged[damaged[..., 3] == 0])
    assert image.tobytes() == before
    assert proposal.changed_pixels == np.count_nonzero(np.any(actual != damaged, axis=2))


@pytest.mark.parametrize("line_colour", [(30, 25, 35), (200, 70, 150), (65, 135, 80)])
def test_real_coloured_line_changes_only_where_explicitly_selected(line_colour):
    pixels = scene()
    pixels[22:66, 17:21, :3] = line_colour
    image = Image.fromarray(pixels)
    selection = Image.new("L", (28, 64))
    ImageDraw.Draw(selection).ellipse((5, 7, 22, 42), fill=255)
    selection_before = selection.tobytes()
    proposal = propose_edge_colour(image, selection, (5, 12, 33, 76))
    assert proposal is not None
    actual = apply(pixels, proposal)
    full_selection = np.zeros(pixels.shape[:2], bool)
    full_selection[12:76, 5:33] = np.array(selection) > 0
    np.testing.assert_array_equal(actual[~full_selection], pixels[~full_selection])
    np.testing.assert_array_equal(actual[..., 3], pixels[..., 3])
    assert not np.array_equal(actual[35, 18, :3], pixels[35, 18, :3])
    np.testing.assert_array_equal(actual[65, 18], pixels[65, 18])
    assert selection.tobytes() == selection_before


@pytest.mark.parametrize("hidden", [(0, 0, 255), (255, 255, 255), (0, 0, 0)])
@pytest.mark.parametrize("foreground", [(196, 154, 98), (0, 0, 0), (255, 255, 255)])
def test_uniform_true_foreground_is_exact_no_op_even_with_unrelated_hidden_rgb(hidden, foreground):
    pixels = scene()
    pixels[pixels[..., 3] > 0, :3] = foreground
    pixels[pixels[..., 3] == 0, :3] = hidden
    image = Image.fromarray(pixels)
    assert propose_edge_colour(image, Image.new("L", image.size, 255), (0, 0, *image.size)) is None


def test_disconnected_faint_and_thin_components_cannot_borrow_large_subject_colour():
    pixels = np.zeros((80, 120, 4), np.uint8)
    pixels[8:72, 8:50] = (220, 190, 130, 255)
    pixels[15:65, 54:56] = (60, 130, 90, 80)
    pixels[15:65, 62:64] = (210, 70, 140, 255)
    image = Image.fromarray(pixels)
    assert propose_edge_colour(image, Image.new("L", (25, 70), 255), (50, 5, 75, 75)) is None


@pytest.mark.parametrize("alpha", [0, 40, 254, 255])
def test_no_reliable_core_or_all_opaque_is_no_op(alpha):
    image = Image.new("RGBA", (44, 39), (90, 130, 210, alpha))
    assert propose_edge_colour(image, Image.new("L", image.size, 255), (0, 0, *image.size)) is None


def test_current_editor_alpha_overrides_original_without_mutating_either():
    pixels = scene()
    pixels[22:65, 15:21, :3] = (120, 90, 150)
    current = Image.fromarray(pixels[..., 3])
    original = pixels.copy()
    original[..., 3] = 255
    image = Image.fromarray(original)
    assert propose_edge_colour(image, Image.new("L", (17, 43), 255), (10, 22, 27, 65)) is None
    before = image.tobytes(), current.tobytes()
    proposal = propose_edge_colour(image, Image.new("L", (17, 43), 255), (10, 22, 27, 65), alpha_mask=current)
    assert proposal is not None
    assert before == (image.tobytes(), current.tobytes())
    restored = apply(original, proposal)
    np.testing.assert_array_equal(restored[..., 3], original[..., 3])
    hidden = np.array(current) == 0
    np.testing.assert_array_equal(restored[hidden], original[hidden])


@pytest.mark.parametrize("flip", [False, True])
def test_rectangular_selection_at_image_edge_uses_real_alpha_not_crop_border(flip):
    pixels = scene()[:70]
    pixels[:12] = pixels[12]
    pixels[:55, 15:21, :3] = (110, 90, 150)
    if flip:
        pixels = np.ascontiguousarray(pixels[::-1, ::-1])
        bounds = (77, 15, 104, 70)
    else:
        bounds = (0, 0, 27, 55)
    l, t, r, b = bounds
    proposal = propose_edge_colour(Image.fromarray(pixels), Image.new("L", (r-l, b-t), 255), bounds)
    assert proposal is not None
    actual = apply(pixels, proposal)
    selected = np.zeros(pixels.shape[:2], bool)
    selected[t:b, l:r] = True
    np.testing.assert_array_equal(actual[~selected], pixels[~selected])
    np.testing.assert_array_equal(actual[..., 3], pixels[..., 3])


def test_same_selection_has_identical_result_with_extra_canvas_around_it():
    pixels = scene()
    pixels[22:65, 15:21, :3] = (110, 95, 155)
    selection = Image.new("L", (17, 43), 255)
    small = apply(pixels, propose_edge_colour(Image.fromarray(pixels), selection, (10, 22, 27, 65)))
    large = np.zeros((180, 210, 4), np.uint8)
    large[40:128, 60:164] = pixels
    changed = apply(large, propose_edge_colour(Image.fromarray(large), selection, (70, 62, 87, 105)))
    np.testing.assert_array_equal(small, changed[40:128, 60:164])


def test_large_canvas_only_allocates_bounded_local_arrays(monkeypatch):
    image = Image.new("RGBA", (5016, 5016), (0, 0, 255, 0))
    pixels = scene()
    pixels[22:65, 15:21, :3] = (110, 95, 155)
    image.paste(Image.fromarray(pixels), (2400, 2300))
    original_filter = cv2.filter2D
    seen = []
    def bounded_filter(array, *args, **kwargs):
        seen.append(array.shape)
        assert array.shape[0] * array.shape[1] <= 10_000
        return original_filter(array, *args, **kwargs)
    monkeypatch.setattr(correction.cv2, "filter2D", bounded_filter)
    proposal = propose_edge_colour(image, Image.new("L", (17, 43), 255), (2410, 2322, 2427, 2365))
    assert proposal is not None and seen
    assert proposal.image_patch.width * proposal.image_patch.height <= 17 * 43


def test_oversized_context_rejected_before_reading_image_pixels(monkeypatch):
    image = Image.new("RGBA", (1200, 1200))
    def forbidden(*args, **kwargs):
        raise AssertionError("Oversized image pixels were read")
    monkeypatch.setattr(image, "crop", forbidden)
    with pytest.raises(ValueError, match="меньший"):
        propose_edge_colour(image, Image.new("L", image.size, 255), (0, 0, *image.size))


def test_cancellation_preserves_inputs_and_never_returns_partial_proposal():
    image = Image.fromarray(scene())
    before = image.tobytes()
    calls = 0
    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 4
    with pytest.raises(CancelledError):
        propose_edge_colour(image, Image.new("L", (17, 43), 255), (10, 22, 27, 65), cancel_check=cancel)
    assert image.tobytes() == before


@pytest.mark.parametrize("bounds", [(-1, 0, 4, 4), (0, 0, 0, 4), (0, 0, 105, 4), (0, 0, 4.0, 4), (False, 0, 4, 4)])
def test_invalid_bounds_are_rejected(bounds):
    with pytest.raises(ValueError):
        propose_edge_colour(Image.fromarray(scene()), Image.new("L", (4, 4), 255), bounds)


def test_invalid_masks_width_and_empty_selection():
    image = Image.fromarray(scene())
    with pytest.raises(ValueError):
        propose_edge_colour(image, Image.new("RGB", (4, 4)), (0, 0, 4, 4))
    with pytest.raises(ValueError):
        propose_edge_colour(image, Image.new("L", (4, 4)), (0, 0, 4, 4), alpha_mask=Image.new("L", (2, 2)))
    with pytest.raises(ValueError):
        propose_edge_colour(image, Image.new("L", (4, 4)), (0, 0, 4, 4), band_width=8)
    assert propose_edge_colour(image, Image.new("L", (4, 4)), (0, 0, 4, 4)) is None
