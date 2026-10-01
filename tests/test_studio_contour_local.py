"""Known geometric features, locality, safety and finite repeated operations."""
from dataclasses import replace
from math import cos, sin, pi, hypot

import pytest

from studio_contour import BezierNode, BezierPath, sample_path
from studio_contour_local import simplify_selected, smooth_selected, local_changed_path_roi, local_changed_path_rois


def path(points, *, fill=255, size=(300, 300)):
    return BezierPath(tuple(BezierNode(p) for p in points), fill, size)


def edge():
    return path([(20, 30), (24, 30.4), (28, 29.6), (32, 30.4),
                 (36, 29.6), (40, 30.4), (44, 30), (44, 70), (20, 70)])


def selected(p, indices=None, pi=0):
    return frozenset((pi, i) for i in (range(len(p.nodes)) if indices is None else indices))


def repeat(operation, paths, selection, *, limit=200):
    changes = 0
    for _ in range(limit):
        result = operation(paths, selection)
        if not result.changed:
            assert result.paths == paths
            assert operation(result.paths, result.selection) == result
            return result, changes
        changes += 1
        paths, selection = result.paths, result.selection
    pytest.fail("operation did not reach a finite safe limit")


def test_smooth_small_visible_step_and_exact_locality():
    p = edge()
    result = smooth_selected((p,), selected(p, range(7)))
    assert result.changed
    for i in (0, 6, 7, 8):
        assert result.paths[0].nodes[i] == p.nodes[i]
    for before, after in zip(p.nodes, result.paths[0].nodes):
        assert hypot(after.point[0] - before.point[0], after.point[1] - before.point[1]) <= .35
    assert result.paths[0].nodes[2].point[1] > p.nodes[2].point[1]
    assert result.selection == selected(p, range(7))


def test_simplify_bounds_full_cubic_even_with_near_straight_handle():
    p = path([(20, 30), (24, 31.25), (28, 30), (28, 70), (20, 70)], size=(100, 100))
    p = replace(p, nodes=(p.nodes[0], replace(p.nodes[1], in_handle=(23.993, 31.2724)), *p.nodes[2:]))
    result = simplify_selected((p,), selected(p, range(3)))
    assert not result.changed
    assert result.paths == (p,)


def test_simplify_preserves_tip_beyond_replacement_segment_endpoint():
    p = path([(20, 30), (18, 30.7), (30, 30), (30, 70),
              (10, 70), (10, 20), (20, 20)], size=(100, 100))
    result = simplify_selected((p,), selected(p, range(3)))
    assert not result.changed
    assert result.paths == (p,)


@pytest.mark.parametrize("left", [38, 44])
def test_hole_edit_uses_parent_material_and_preserves_nested_island_alpha(left):
    import numpy as np
    from studio_contour import ContourDocument, rasterize_path
    outer = path([(5, 5), (95, 5), (95, 95), (5, 95)], size=(100, 100))
    hole = path([(40, 43), (60, 43), (60, 70), (40, 70)], fill=0, size=(100, 100))
    island = path([(41, 55), (43, 55), (43, 58), (41, 58)], size=(100, 100))
    roi = (0, 0, 100, 100)
    alpha = rasterize_path(outer, roi)
    old = rasterize_path(hole, roi) > 0
    protected = rasterize_path(island, roi) > 0
    alpha[old] = 0
    alpha[protected] = 77
    changed = replace(hole, nodes=tuple(replace(n, point=(left, n.point[1]))
                                       if n.point[0] == 40 else n for n in hole.nodes))
    new = rasterize_path(changed, roi) > 0
    expected = alpha.copy()
    expected[old & ~new] = 255
    expected[new & ~old] = 0
    expected[protected] = 77
    actual = ContourDocument(alpha, [outer, hole, island]).apply_path(1, changed, roi)
    assert np.array_equal(actual, expected)
    assert np.any(actual != alpha)


def test_nested_island_expands_through_ancestor_hole_without_filling_child_hole():
    import numpy as np
    from studio_contour import ContourDocument, rasterize_path
    roi = (0, 0, 100, 100)
    outer = path([(5, 5), (95, 5), (95, 95), (5, 95)], size=(100, 100))
    parent = path([(20, 20), (80, 20), (80, 80), (20, 80)], fill=0, size=(100, 100))
    island = path([(40, 43), (45, 43.7), (50, 43), (60, 43), (60, 70), (40, 70)], size=(100, 100))
    child = path([(45, 48), (48, 48), (48, 52), (45, 52)], fill=0, size=(100, 100))
    paths = (outer, parent, island, child)
    alpha = rasterize_path(outer, roi)
    alpha[rasterize_path(parent, roi) > 0] = 0
    alpha[rasterize_path(island, roi) > 0] = 255
    alpha[rasterize_path(child, roi) > 0] = 0
    result = simplify_selected(paths, {(2, 0), (2, 1), (2, 2)})
    assert result.changed
    edited = ContourDocument(alpha, list(paths)).apply_path(2, result.paths[2], roi)
    expected = alpha.copy()
    expected[(rasterize_path(result.paths[2], roi) > 0) & (rasterize_path(island, roi) == 0)] = 255
    assert np.array_equal(edited, expected)
    assert np.count_nonzero(edited != alpha) == 3


def test_hole_expansion_preserves_unrepresented_raw_island_after_brush():
    import numpy as np
    from studio_contour import ContourDocument, rasterize_path
    roi = (0, 0, 100, 100)
    outer = path([(5, 5), (95, 5), (95, 95), (5, 95)], size=(100, 100))
    hole = path([(40, 43), (45, 43.7), (50, 43), (60, 43), (60, 70), (40, 70)], fill=0, size=(100, 100))
    alpha = rasterize_path(outer, roi)
    alpha[rasterize_path(hole, roi) > 0] = 0
    alpha[42:45, 44:47] = 0  # prior brush leaves an unrepresented tiny detail
    alpha[43, 45] = 77
    result = simplify_selected((outer, hole), {(1, 0), (1, 1), (1, 2)})
    assert result.changed
    edited = ContourDocument(alpha, [outer, hole]).apply_path(1, result.paths[1], roi)
    assert edited[43, 45] == 77
    assert np.array_equal(edited, alpha)


def test_repeated_smooth_stops_without_flattening_macro_shape():
    p = edge()
    result, changes = repeat(smooth_selected, (p,), selected(p, range(7)))
    assert 2 <= changes < 100
    assert max(abs(n.point[1] - 30) for n in result.paths[0].nodes[:7]) < .2
    assert result.paths[0].nodes[7:] == p.nodes[7:]


def test_noisy_flower_keeps_petals_and_reaches_limit():
    points = []
    for i in range(120):
        a = i * 2 * pi / 120
        radius = 65 + 13 * cos(5 * a) + (.4 if i % 2 else -.4)
        points.append((145 + radius * cos(a), 145 + radius * sin(a)))
    p = path(points)
    result, changes = repeat(smooth_selected, (p,), selected(p))
    assert changes > 0
    # Supported petal peaks and valleys retain their large radial difference.
    radii = [hypot(n.point[0] - 145, n.point[1] - 145) for n in result.paths[0].nodes]
    assert max(radii) - min(radii) > 24
    assert max(hypot(a.point[0] - b.point[0], a.point[1] - b.point[1])
               for a, b in zip(p.nodes, result.paths[0].nodes)) < 1.5


def test_sharp_tip_fur_gap_and_all_rectangle_corners_unchanged():
    p = path([(20, 30), (24, 30.4), (28, 30), (30, 15), (32, 30),
              (34, 30), (36, 42), (38, 30), (42, 30.4), (46, 30),
              (46, 80), (20, 80)])
    tips = (3, 6, 9, 10, 11, 0)
    for operation in (smooth_selected, simplify_selected):
        result, _ = repeat(operation, (p,), selected(p))
        for i in tips:
            assert p.nodes[i] in result.paths[0].nodes
        assert (30., 15.) in [n.point for n in result.paths[0].nodes]
        assert (36., 42.) in [n.point for n in result.paths[0].nodes]


def test_simplify_one_small_step_per_run_and_remap_selection():
    p = replace(edge(), nodes=tuple(replace(n, point=(n.point[0], 30 + (n.point[1] - 30) / 2)) if i < 7 else n for i, n in enumerate(edge().nodes)))
    result = simplify_selected((p,), selected(p, range(7)))
    assert result.changed
    assert len(result.paths[0].nodes) == len(p.nodes) - 1
    assert result.paths[0].nodes[0] == p.nodes[0]
    assert result.paths[0].nodes[5:] == p.nodes[6:]
    assert result.selection == frozenset((0, i) for i in range(6))
    final, changes = repeat(simplify_selected, (p,), selected(p, range(7)))
    assert 1 <= changes < 20
    assert len(final.paths[0].nodes) == 4


def test_disjoint_runs_and_cyclic_run_keep_each_endpoint():
    p = path([(20, 30), (24, 30.2), (28, 30), (28, 40), (28, 50),
              (28, 54.2), (28, 58), (20, 58), (20, 54), (20, 50), (20, 40), (20, 35)])
    disjoint = simplify_selected((p,), selected(p, (0, 1, 2, 4, 5, 6)))
    assert disjoint.changed
    assert len(disjoint.paths[0].nodes) == len(p.nodes) - 2
    assert all(p.nodes[i] in disjoint.paths[0].nodes for i in (0, 2, 3, 4, 6, 7, 8, 9, 10, 11))
    wrapped = simplify_selected((p,), selected(p, (8, 9, 10, 11, 0, 1)))
    assert wrapped.changed
    assert p.nodes[8] in wrapped.paths[0].nodes and p.nodes[1] in wrapped.paths[0].nodes
    assert p.nodes[2:8] == tuple(n for n in wrapped.paths[0].nodes if n in p.nodes[2:8])


def test_other_paths_and_holes_unchanged():
    p = edge()
    hole = path([(25, 40), (35, 40), (35, 50), (25, 50)], fill=0)
    separate = path([(100, 100), (110, 100), (110, 110), (100, 110)])
    p = replace(p, nodes=tuple(replace(n, point=(n.point[0], 30 + (n.point[1] - 30) / 2)) if i < 7 else n for i, n in enumerate(p.nodes)))
    for operation in (simplify_selected, smooth_selected):
        result = operation((p, hole, separate), selected(p, range(7)))
        assert result.changed
        assert result.paths[1] is hole and result.paths[2] is separate
        assert result.paths[0].fill_value == p.fill_value
        assert result.paths[0].source_shape == p.source_shape


def test_curved_segments_not_removed_and_unselected_implicit_tangent_stable():
    p = edge()
    nodes = list(p.nodes)
    nodes[2] = replace(nodes[2], out_handle=(29, 20))
    curved = replace(p, nodes=tuple(nodes))
    result = simplify_selected((curved,), selected(curved, (1, 2, 3)))
    assert not result.changed
    nodes = list(p.nodes)
    nodes[0] = replace(nodes[0], kind="smooth")
    implicit = replace(p, nodes=tuple(nodes))
    result = smooth_selected((implicit,), selected(implicit, range(7)))
    assert result.paths[0].nodes[1] == implicit.nodes[1]
    # The segment with the unselected endpoint retains the exact automatic cubic.
    assert (sample_path(result.paths[0])[-12:] == sample_path(implicit)[-12:]).all()


def test_explicit_handles_translate_only_with_selected_anchor():
    p = edge()
    nodes = list(p.nodes)
    n = nodes[2]
    nodes[2] = replace(n, in_handle=(27.5, 29.6), out_handle=(28.5, 29.6))
    p = replace(p, nodes=tuple(nodes))
    result = smooth_selected((p,), selected(p, range(7)))
    assert result.changed
    n2 = result.paths[0].nodes[2]
    shift = n2.point[1] - n.point[1]
    assert n2.in_handle == (27.5, 29.6 + shift)
    assert n2.out_handle == (28.5, 29.6 + shift)
    assert result.paths[0].nodes[7:] == p.nodes[7:]


def test_unsafe_degenerate_self_intersection_and_crossing_other_path_noop():
    bow = path([(20, 20), (25, 25.2), (30, 30), (20, 30), (30, 20)])
    flat = path([(20, 20), (24, 20), (28, 20), (24, 20)])
    for p in (bow, flat):
        assert not simplify_selected((p,), selected(p)).changed
        assert not smooth_selected((p,), selected(p)).changed
    p = edge()
    # Existing crossing contours are unsafe to adjust, rather than silently join.
    crossed = path([(25, 25), (35, 25), (35, 35), (25, 35)])
    for operation in (smooth_selected, simplify_selected):
        assert not operation((p, crossed), selected(p, range(7))).changed


def test_insufficient_empty_invalid_and_bounded_inputs():
    p = edge()
    for operation in (simplify_selected, smooth_selected):
        for selection in (frozenset(), selected(p, (1,)), selected(p, (1, 2))):
            result = operation((p,), selection)
            assert not result.changed and result.paths == (p,)
        for selection in (None, {(1, 0)}, {(0, -1)}, {(0, 100)}, {(True, 1)}, {(0, 1.5)}, {(0, 1, 2)}):
            with pytest.raises(ValueError):
                operation((p,), selection)
        with pytest.raises(ValueError):
            operation((p,) * 257, frozenset())
        with pytest.raises(ValueError):
            operation([object()], frozenset())


def test_changed_roi_cancels_unchanged_segments_after_deletion():
    p = path([(20, 30), (24, 30.2), (28, 30), (200, 30), (200, 200), (20, 200)])
    result = simplify_selected((p,), selected(p, (0, 1, 2)))
    assert result.changed
    roi = local_changed_path_roi(p, result.paths[0])
    assert roi == (7, 17, 42, 45)
    assert local_changed_path_roi(p, p) == (0, 0, 1, 1)


def test_large_zigzag_requires_smooth_before_safe_simplify():
    p = replace(edge(), nodes=tuple(replace(n, point=(n.point[0], 30 + (n.point[1] - 30) * 2.25)) if i < 7 else n for i, n in enumerate(edge().nodes)))
    assert not simplify_selected((p,), selected(p, range(7))).changed
    smoothed = smooth_selected((p,), selected(p, range(7)))
    assert smoothed.changed
    assert simplify_selected(smoothed.paths, smoothed.selection).changed


def test_simplify_batch_visible_and_each_chord_within_half_pixel():
    p = path([(20 + 2 * i, 30 + (.2 if i % 2 else -.2)) for i in range(26)] + [(70, 80), (20, 80)])
    first = simplify_selected((p,), selected(p, range(26)))
    assert first.changed
    assert len(p.nodes) - len(first.paths[0].nodes) == 6
    # Every removed anchor lies at most half a pixel off its replacement chord.
    from studio_contour_local import _distance
    remaining = first.paths[0].nodes
    for i, a in enumerate(remaining):
        b = remaining[(i + 1) % len(remaining)]
        ia, ib = p.nodes.index(a), p.nodes.index(b)
        if ib == ia + 2:
            assert _distance(p.nodes[ia + 1].point, a.point, b.point) <= .5
    final, changes = repeat(simplify_selected, (p,), selected(p, range(26)))
    assert changes < 15
    assert final.paths[0].nodes[0] == p.nodes[0]
    assert p.nodes[25:] == final.paths[0].nodes[-3:]


def test_fixed_smooth_tip_retains_automatic_incident_cubics():
    p = path([(20, 30), (24, 30.4), (28, 30), (30, 15), (32, 30),
              (36, 30.4), (40, 30), (40, 80), (20, 80)])
    nodes = list(p.nodes)
    nodes[3] = replace(nodes[3], kind="smooth")
    p = replace(p, nodes=tuple(nodes))
    result = smooth_selected((p,), selected(p, range(7)))
    from studio_contour import _auto_handles
    assert result.paths[0].nodes[3] == p.nodes[3]
    assert _auto_handles(result.paths[0].nodes, 3) == _auto_handles(p.nodes, 3)


def test_separate_roi_supports_preserve_raw_unselected_fur_in_gap():
    import numpy as np
    from studio_contour import ContourDocument, rasterize_path
    p = path([(20, 30.2), (24, 30.6), (28, 30.2), (100, 30.2), (180, 30.2),
              (184, 30.6), (188, 30.2), (200, 30.2), (200, 90), (20, 90)])
    selection = selected(p, (0, 1, 2, 4, 5, 6))
    changed = simplify_selected((p,), selection)
    assert changed.changed
    rois = local_changed_path_rois(p, changed.paths[0])
    assert len(rois) == 2
    assert all(not (r[0] <= 100 < r[2]) for r in rois)
    assert local_changed_path_rois(p, p) == ()
    alpha = rasterize_path(p, (0, 0, 300, 300))
    alpha[27:31, 100] = [117, 137, 177, 255]  # raw fur absent from proposal
    before = alpha.copy()
    composed = before.copy()
    for roi in rois:
        document = ContourDocument(before, [p], extraction_tolerance=1)
        updated = document.apply_path(0, changed.paths[0], roi)
        left, top, right, bottom = roi
        composed[top:bottom, left:right] = updated[top:bottom, left:right]
    assert np.array_equal(composed[:, 80:120], before[:, 80:120])
    assert np.any(composed != before)


def test_long_straight_redundant_anchors_reach_only_necessary_corners():
    p = path([(20 + 8 * i, 30) for i in range(26)] + [(220, 200), (20, 200)])
    first = simplify_selected((p,), selected(p))
    assert len(p.nodes) - len(first.paths[0].nodes) == 7
    final, clicks = repeat(simplify_selected, (p,), selected(p))
    assert clicks < 20
    assert len(final.paths[0].nodes) == 4
    assert final.paths[0].nodes == (p.nodes[0], p.nodes[25], p.nodes[26], p.nodes[27])


def test_tiny_hole_cannot_jump_across_replacement_chord():
    p = path([(20, 30.6), (24, 30.2), (28, 30.6), (44, 30.6), (44, 70), (20, 70)])
    # Hole lies inside the original tiny edge bay, but outside the new straight edge.
    hole = path([(23.9, 30.4), (24.1, 30.4), (24.1, 30.45), (23.9, 30.45)], fill=0)
    assert not simplify_selected((p, hole), selected(p, (0, 1, 2))).changed
    assert simplify_selected((p,), selected(p, (0, 1, 2))).changed


def test_default_simplify_budget_is_exactly_one_and_quarter_image_pixels():
    p = path([(20, 30), (24, 31.25), (28, 30), (44, 30), (44, 70), (20, 70)])
    result = simplify_selected((p,), selected(p, (0, 1, 2)))
    assert result.changed
    from studio_contour_local import _distance
    assert _distance(p.nodes[1].point, result.paths[0].nodes[0].point, result.paths[0].nodes[1].point) == 1.25
    over = replace(p, nodes=(p.nodes[0], replace(p.nodes[1], point=(24, 31.26)), *p.nodes[2:]))
    assert not simplify_selected((over,), selected(over, (0, 1, 2))).changed


def test_distant_raster_backtracking_contacts_stay_exact_while_local_edit_works():
    p = path([(20, 30.2), (24, 30.6), (28, 30.2), (100, 30.2), (100, 80),
              (70, 80), (69, 81), (70, 80), (20, 80)])
    from studio_contour_local import _geometry_contacts, _polyline
    before = _geometry_contacts(_polyline(p))
    assert before
    for operation in (simplify_selected, smooth_selected):
        result = operation((p,), selected(p, (0, 1, 2)))
        assert result.changed
        assert _geometry_contacts(_polyline(result.paths[0])) == before
        assert result.paths[0].nodes[-6:] == p.nodes[-6:]


def test_distant_interpath_touch_is_preserved_and_does_not_disable_local_edit():
    p = path([(20, 30.2), (24, 30.6), (28, 30.2), (100, 30.2), (100, 80), (20, 80)])
    touching = path([(60, 80), (62, 84), (60, 88), (58, 84)])
    from studio_contour_local import _cross_contacts, _polyline
    before = _cross_contacts(_polyline(p), _polyline(touching))
    assert before
    for operation in (simplify_selected, smooth_selected):
        result = operation((p, touching), selected(p, (0, 1, 2)))
        assert result.changed
        assert result.paths[1] is touching
        assert _cross_contacts(_polyline(result.paths[0]), _polyline(touching)) == before


def test_exact_approved_mockup_extraction_has_useful_local_actions():
    from PIL import Image, ImageDraw
    from math import tau
    import numpy as np
    from studio_contour import extract_contours
    image = Image.new("RGBA", (640, 560), (0, 0, 0, 0))
    points = []
    for i in range(240):
        a = i * tau / 240
        radius = 1 + .018 * sin(37 * a) + .008 * sin(83 * a)
        points.append((320 + 220 * radius * cos(a), 280 + 180 * radius * sin(a)))
    ImageDraw.Draw(image).polygon(points, fill=(238, 212, 153, 255))
    paths = tuple(extract_contours(np.asarray(image)[:, :, 3]))
    p = paths[0]
    selection = frozenset((0, i) for i, node in enumerate(p.nodes)
                          if node.point[0] < 200 and 245 < node.point[1] < 425)
    assert len(p.nodes) == 141 and len(selection) == 26
    simplified = simplify_selected(paths, selection)
    assert simplified.changed and len(simplified.selection) == 24
    assert smooth_selected(paths, selection).changed
    from studio_contour_local import _distance
    removed = [n for n in p.nodes if n not in simplified.paths[0].nodes]
    assert len(removed) == 2
    for node in removed:
        i = p.nodes.index(node)
        assert _distance(node.point, p.nodes[i - 1].point, p.nodes[i + 1].point) <= 1.25
    repeat(simplify_selected, paths, selection)
    repeat(smooth_selected, paths, selection)
