import numpy as np
import pytest

from studio_contour import (
    BezierNode, BezierPath, ContourDocument, MAX_FEATHER_PX,
    extract_contours, rasterize_path,
)


def square(x0, y0, x1, y1, shape, fill=255):
    return BezierPath(tuple(BezierNode(point) for point in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))), fill, shape)


def test_extracts_rectangle_and_hole_geometry():
    alpha = np.zeros((40, 50), np.uint8)
    alpha[5:35, 7:43] = 255
    alpha[14:27, 18:32] = 0
    paths = extract_contours(alpha, tolerance=1)
    assert {path.fill_value for path in paths} == {0, 255}
    exterior = next(path for path in paths if path.fill_value == 255)
    hole = next(path for path in paths if path.fill_value == 0)
    assert min(node.point[0] for node in exterior.nodes) <= 7
    assert max(node.point[0] for node in exterior.nodes) >= 42
    assert min(node.point[0] for node in hole.nodes) >= 17
    assert max(node.point[0] for node in hole.nodes) <= 32


def test_nested_island_and_hole_survive_noop_apply_without_changing_thin_alpha():
    alpha = np.zeros((48, 48), np.uint8)
    alpha[4:44, 4:44] = 255
    alpha[12:36, 12:36] = 0
    alpha[19:29, 19:29] = 255  # an island inside a hole
    alpha[2, 2:5] = 120  # a thin, partially transparent detail outside paths
    document = ContourDocument.from_alpha(alpha, tolerance=1)
    assert [path.fill_value for path in document.paths].count(255) == 2
    assert [path.fill_value for path in document.paths].count(0) == 1
    before = document.alpha.copy()
    for index, path in enumerate(tuple(document.paths)):
        document.apply_path(index, path, (0, 0, 48, 48))
    assert np.array_equal(document.alpha, before)


def test_replacement_is_roi_local_and_preserves_rgb():
    alpha = np.zeros((30, 30), np.uint8)
    old = square(5, 5, 12, 12, alpha.shape)
    alpha[5:13, 5:13] = 255
    document = ContourDocument(alpha, [old])
    rgba = np.dstack((np.full_like(alpha, 11), np.full_like(alpha, 22), np.full_like(alpha, 33), alpha))
    before = document.alpha.copy()
    document.apply_path(0, square(8, 5, 15, 12, alpha.shape), (3, 3, 18, 16))
    outside = np.ones(alpha.shape, bool)
    outside[3:16, 3:18] = False
    assert np.array_equal(document.alpha[outside], before[outside])
    edited = document.apply_to_rgba(rgba)
    assert np.array_equal(edited[..., :3], rgba[..., :3])


def test_moving_outer_contour_does_not_fill_unchanged_hole():
    alpha = np.zeros((40, 40), np.uint8)
    alpha[5:35, 5:35] = 255
    alpha[14:26, 14:26] = 0
    outer = square(5, 5, 34, 34, alpha.shape)
    document = ContourDocument(alpha, [outer])
    document.apply_path(0, square(6, 5, 35, 34, alpha.shape), (1, 1, 39, 39))
    assert document.alpha[20, 20] == 0


def test_edit_elsewhere_keeps_unrepresented_single_pixels_and_thin_branches():
    alpha = np.zeros((45, 45), np.uint8)
    alpha[8:18, 8:18] = 255
    alpha[10:15, 10:15] = 0  # a hole in the edited component
    alpha[3, 3] = 77
    alpha[36, 30:36] = 181
    path = square(8, 8, 17, 17, alpha.shape)
    document = ContourDocument(alpha, [path])
    document.apply_path(0, square(10, 8, 19, 17, alpha.shape), (4, 4, 24, 22))
    assert document.alpha[3, 3] == 77
    assert np.array_equal(document.alpha[36, 30:36], np.full(6, 181, np.uint8))
    assert document.alpha[12, 12] == 0


def test_outer_expansion_preserves_other_component_hole_and_alpha_residual():
    alpha = np.zeros((60, 60), np.uint8)
    alpha[5:25, 5:25] = 255
    alpha[5:25, 30:55] = 255
    alpha[12:23, 38:49] = 0
    alpha[20, 27] = 137  # not a Bezier area, but not ordinary transparent background
    document = ContourDocument.from_alpha(alpha, tolerance=1)
    left_index = min((index for index, path in enumerate(document.paths) if path.fill_value == 255),
                     key=lambda index: min(node.point[0] for node in document.paths[index].nodes))
    document.apply_path(left_index, square(25, 5, 45, 24, alpha.shape), (0, 0, 60, 60))
    assert document.alpha[20, 43] == 0  # hole in the other component
    assert document.alpha[20, 27] == 137  # residual survives new-only coverage
    assert document.alpha[20, 26] == 255  # normal transparent background still fills


def test_disjoint_roi_is_a_noop_and_retains_editable_paths():
    alpha = np.zeros((30, 30), np.uint8)
    old = square(5, 5, 12, 12, alpha.shape)
    alpha[5:13, 5:13] = 255
    document = ContourDocument(alpha, [old])
    before = document.alpha.copy()
    document.apply_path(0, square(20, 5, 27, 12, alpha.shape), (3, 18, 18, 29))
    assert np.array_equal(document.alpha, before)
    assert document.paths == [old]


def test_partial_roi_edit_rebuilds_paths_for_a_following_edit():
    alpha = np.zeros((45, 45), np.uint8)
    alpha[5:35, 5:35] = 255
    old = square(5, 5, 34, 34, alpha.shape)
    document = ContourDocument(alpha, [old])
    before = document.alpha.copy()
    # Only the upper-left portion of the moved edge is allowed to change.
    document.apply_path(0, square(7, 5, 34, 34, alpha.shape), (3, 3, 12, 18))
    outside = np.ones(alpha.shape, bool)
    outside[3:18, 3:12] = False
    assert np.array_equal(document.alpha[outside], before[outside])
    fresh_index = next(i for i, path in enumerate(document.paths) if path.fill_value == 255)
    fresh = document.paths[fresh_index]
    nodes = list(fresh.nodes)
    x, y = nodes[0].point
    nodes[0] = BezierNode((min(x + 1, 43), y), nodes[0].kind,
                          nodes[0].in_handle, nodes[0].out_handle)
    document.apply_path(fresh_index, BezierPath(tuple(nodes), 255, alpha.shape), (0, 0, 45, 45))
    assert document.paths  # the second edit consumed the rebuilt proposal


def test_moving_node_changes_only_selected_area():
    alpha = np.zeros((32, 32), np.uint8)
    old = square(5, 5, 14, 14, alpha.shape)
    alpha[5:15, 5:15] = 255
    document = ContourDocument(alpha, [old])
    moved = square(10, 5, 19, 14, alpha.shape)
    output = document.apply_path(0, moved, (2, 2, 23, 18))
    assert output[9, 7] == 0
    assert output[9, 17] == 255


@pytest.mark.parametrize("bad", [(-1, 0, 4, 4), (0, 0, 0, 4), (0.0, 0, 4, 4)])
def test_rejects_invalid_roi_and_feather(bad):
    path = square(1, 1, 5, 5, (10, 10))
    with pytest.raises(ValueError):
        rasterize_path(path, bad)
    with pytest.raises(ValueError):
        rasterize_path(path, (0, 0, 10, 10), feather=MAX_FEATHER_PX + 0.01)


def test_rejects_nonfinite_node_coordinates():
    with pytest.raises(ValueError):
        BezierNode((float("nan"), 1))
    with pytest.raises(ValueError):
        BezierNode((1, float("inf")))


def test_feather_is_hard_at_zero_and_has_a_bounded_two_pixel_band():
    path = square(10, 8, 30, 32, (40, 40))
    hard = rasterize_path(path, (0, 0, 40, 40), feather=0)
    assert set(np.unique(hard)).issubset({0, 255})
    soft = rasterize_path(path, (0, 0, 40, 40), feather=2)
    middle = (soft[20] > 0) & (soft[20] < 255)
    # Each edge's transitional run is at most 2 final pixels, with no tails.
    runs = "".join("1" if value else "0" for value in middle).split("0")
    assert max((len(run) for run in runs), default=0) <= 2
    assert np.all(soft[20, :9] == 0)
    assert np.all(soft[20, 32:] == 0)
    one_pixel = rasterize_path(path, (0, 0, 40, 40), feather=1)
    one_pixel_middle = (one_pixel[20] > 0) & (one_pixel[20] < 255)
    one_pixel_runs = "".join("1" if value else "0" for value in one_pixel_middle).split("0")
    assert max((len(run) for run in one_pixel_runs), default=0) == 1


def test_feather_does_not_fade_at_an_roi_border_when_path_edge_is_outside_roi():
    path = square(1, 1, 18, 18, (20, 20))
    assert np.all(rasterize_path(path, (5, 5, 15, 15), feather=2) == 255)


def test_serialization_round_trip_and_image_bounds():
    path = square(1, 1, 5, 5, (10, 10))
    assert BezierPath.from_dict(path.to_dict()) == path
    with pytest.raises(ValueError):
        square(1, 1, 12, 5, (10, 10))


def test_curved_handles_rasterize_a_filled_curve():
    nodes = (
        BezierNode((5, 20), "smooth", out_handle=(5, 2)),
        BezierNode((25, 20), "smooth", in_handle=(25, 2)),
        BezierNode((25, 28)),
        BezierNode((5, 28)),
    )
    path = BezierPath(nodes, 255, (32, 32))
    raster = rasterize_path(path, (0, 0, 32, 32))
    assert raster[10, 15] == 255
    assert raster[4, 15] == 0
