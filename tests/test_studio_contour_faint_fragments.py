"""Proposal geometry must not delete faint raster details or block large PNGs."""
from threading import Event
from dataclasses import replace
import numpy as np
from studio_contour import ContourDocument, extract_contours, changed_path_roi
from v3_transparency_preview import _calculate_contour


def faint_fragments_mask():
    alpha = np.zeros((256, 256), np.uint8)
    alpha[90:230, 90:230] = 255
    # Hundreds of nondegenerate components that should remain raw alpha,
    # rather than exceeding the editable path budget.
    for y in range(2, 80, 4):
        for x in range(2, 250, 4):
            alpha[y:y+2, x:x+2] = 3
    alpha[140:160, 140:160] = 0
    return alpha


def test_faint_fragments_do_not_block_proposal_or_mutate_mask():
    alpha = faint_fragments_mask(); saved = alpha.copy()
    paths = extract_contours(alpha)
    assert len(paths) == 2  # the dominant object and its real hole
    assert {path.fill_value for path in paths} == {0, 255}
    np.testing.assert_array_equal(alpha, saved)
    doc = ContourDocument(alpha, paths)
    np.testing.assert_array_equal(doc.apply_path(0, paths[0], (0, 0, 256, 256)), saved)


def test_fallback_edit_preserves_detached_faint_details_and_holes():
    alpha = faint_fragments_mask()
    paths = extract_contours(alpha)
    index = next(i for i, path in enumerate(paths) if path.fill_value == 255)
    path = paths[index]; nodes = list(path.nodes)
    nodes[0] = replace(nodes[0], point=(nodes[0].point[0]+8, nodes[0].point[1]+6))
    replacement = replace(path, nodes=tuple(nodes))
    doc = ContourDocument(alpha, paths)
    result = doc.apply_path(index, replacement, changed_path_roi(path, replacement))
    assert not np.array_equal(result, alpha)
    np.testing.assert_array_equal(result[:80], alpha[:80])
    np.testing.assert_array_equal(result[140:160, 140:160], alpha[140:160, 140:160])


def test_5016_px_worker_extraction_preserves_full_resolution():
    alpha = np.zeros((5016, 5016), np.uint8)
    alpha[200:4800, 400:4400] = 255
    paths = _calculate_contour('extract', alpha, (), (), Event())
    assert len(paths) == 1
    assert paths[0].source_shape == (5016, 5016)
    assert alpha[300, 500] == 255 and alpha[0, 0] == 0


def test_normal_small_faint_subject_remains_editable_without_thresholding():
    alpha = np.zeros((64, 64), np.uint8)
    alpha[20:40, 20:40] = 3
    paths = extract_contours(alpha)
    assert len(paths) == 1
    assert paths[0].fill_value == 255
    np.testing.assert_array_equal(ContourDocument(alpha, paths).alpha, alpha)


def test_fallback_still_refuses_unbounded_strong_geometry():
    import pytest
    alpha = faint_fragments_mask()
    alpha[alpha == 3] = 255
    with pytest.raises(ValueError, match='too many contours'):
        extract_contours(alpha)


def test_fallback_exterior_shrink_preserves_faint_island_inside_hole():
    alpha = faint_fragments_mask()
    alpha[92:108, 92:108] = 0
    alpha[97:101, 97:101] = 3
    paths = extract_contours(alpha)
    index = next(i for i, path in enumerate(paths) if path.fill_value == 255)
    path = paths[index]; nodes = list(path.nodes)
    nodes[0] = replace(nodes[0], point=(110, 110))
    replacement = replace(path, nodes=tuple(nodes))
    doc = ContourDocument(alpha, paths)
    result = doc.apply_path(index, replacement, changed_path_roi(path, replacement))
    assert not np.array_equal(result, alpha)
    np.testing.assert_array_equal(result[97:101, 97:101], alpha[97:101, 97:101])
