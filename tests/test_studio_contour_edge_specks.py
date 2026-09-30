from dataclasses import replace

import cv2
import numpy as np
import pytest
from PIL import Image

from studio_contour import ContourDocument, changed_path_roi, rasterize_path
from v3_transparency_preview import MaskEditDocument


@pytest.mark.parametrize('tolerance', [0.5, 1.0, 2.0])
@pytest.mark.parametrize('feather', [0.0, 1.0, 2.0])
def test_shrinking_extracted_round_edge_does_not_leave_original_pixel_islands(tmp_path, tolerance, feather):
    alpha = np.zeros((128, 128), np.uint8)
    cv2.circle(alpha, (64, 64), 45, 255, -1)
    alpha[3, 3] = 77  # unrelated detail must survive
    alpha[17, 64] = 91  # separate pixel inside the cleanup band must survive
    doc = ContourDocument.from_alpha(alpha, tolerance=tolerance)
    index = next(i for i, path in enumerate(doc.paths) if path.fill_value == 255)
    old = doc.paths[index]
    replacement = replace(old, nodes=tuple(replace(node, point=(
        64 + (node.point[0] - 64) * .85,
        64 + (node.point[1] - 64) * .85,
    )) for node in old.nodes))
    doc.apply_path(index, replacement, changed_path_roi(old, replacement), feather=feather)
    expected = rasterize_path(replacement, (0, 0, 128, 128), feather=feather)
    expected[3, 3] = 77
    expected[17, 64] = 91
    np.testing.assert_array_equal(doc.alpha, expected)
    # Exercise the actual PNG/mask writer, rather than a screenshot of the canvas.
    rgba = np.zeros((128, 128, 4), np.uint8)
    rgba[..., :3] = (20, 60, 90)
    rgba[..., 3] = alpha
    editor = MaskEditDocument(Image.fromarray(rgba))
    editor.mask = Image.fromarray(doc.alpha)
    editor.save(tmp_path / 'edited.png', tmp_path / 'mask.png')
    with Image.open(tmp_path / 'edited.png') as saved:
        actual = np.asarray(saved)
    np.testing.assert_array_equal(actual[..., 3], expected)
    np.testing.assert_array_equal(actual[..., :3], rgba[..., :3])


def test_qt_save_pending_curve_edits_reopens_without_specks_and_supports_undo(tmp_path):
    import time
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtTest import QTest
    from v3_transparency_preview import ClipartTransparencyEditorPage

    app = QApplication.instance() or QApplication([])
    alpha = np.zeros((128, 128), np.uint8)
    cv2.circle(alpha, (64, 64), 45, 255, -1)
    rgba = np.zeros((128, 128, 4), np.uint8)
    rgba[..., :3] = (20, 60, 90)
    rgba[..., 3] = alpha
    source = tmp_path / 'circle.png'
    Image.fromarray(rgba).save(source)
    page = ClipartTransparencyEditorPage()
    def wait():
        deadline = time.monotonic() + 10
        while page.canvas.contour_busy and time.monotonic() < deadline:
            QTest.qWait(5)
        assert not page.canvas.contour_busy
    try:
        page.set_files([source])
        page.show()
        app.processEvents()
        page._set_tool('pen')
        page.canvas.auto_contour()
        wait()
        contour = page.canvas.contour
        index = next(i for i, path in enumerate(contour.paths) if path.fill_value == 255)
        old = contour.paths[index]
        contour.checkpoint()
        contour.paths[index] = replace(old, nodes=tuple(replace(node, point=(
            64 + (node.point[0] - 64) * .85,
            64 + (node.point[1] - 64) * .85,
        )) for node in old.nodes))
        expected = rasterize_path(contour.paths[index], (0, 0, 128, 128))
        assert contour.dirty
        page._save_clicked()  # applies pending geometry asynchronously before save
        wait()
        assert not contour.dirty
        with Image.open(source) as saved:
            reopened = np.asarray(saved)
        np.testing.assert_array_equal(reopened[..., 3], expected)
        np.testing.assert_array_equal(reopened[..., :3], rgba[..., :3])
        assert page.document.can_undo
        page.document.undo()
        np.testing.assert_array_equal(np.asarray(page.document.mask), alpha)
        page.document.redo()
        np.testing.assert_array_equal(np.asarray(page.document.mask), expected)
    finally:
        page.close()
        page.deleteLater()
        app.processEvents()


def test_cleanup_preserves_separate_pixel_inside_a_contour_hole():
    alpha = np.zeros((256, 256), np.uint8)
    cv2.circle(alpha, (128, 128), 80, 255, -1)
    cv2.circle(alpha, (128, 128), 78, 0, -1)
    alpha[52, 139] = 77
    doc = ContourDocument.from_alpha(alpha, tolerance=8)
    index = next(i for i, path in enumerate(doc.paths) if path.fill_value == 255)
    old = doc.paths[index]
    replacement = replace(old, nodes=tuple(replace(node, point=(
        128 + (node.point[0] - 128) * .85,
        128 + (node.point[1] - 128) * .85,
    )) for node in old.nodes))
    doc.apply_path(index, replacement, (0, 0, 256, 256))
    assert doc.alpha[52, 139] == 77


def test_multiple_draft_contours_and_repeated_edits_leave_no_edge_islands():
    from threading import Event
    from v3_transparency_preview import _calculate_contour

    alpha = np.zeros((160, 320), np.uint8)
    for center in ((75, 80), (245, 80)):
        cv2.circle(alpha, center, 45, 255, -1)
    alpha[4, 4] = 77
    originals = ContourDocument.from_alpha(alpha).paths
    edited = []
    expected = np.zeros_like(alpha)
    for path in originals:
        center = (75, 80) if path.nodes[0].point[0] < 160 else (245, 80)
        replacement = replace(path, nodes=tuple(replace(node, point=(
            center[0] + (node.point[0] - center[0]) * .85,
            center[1] + (node.point[1] - center[1]) * .85,
        )) for node in path.nodes))
        edited.append(replacement)
        expected = np.maximum(expected, rasterize_path(replacement, (0, 0, 320, 160)))
    expected[4, 4] = 77
    actual, _ = _calculate_contour('apply', alpha, originals, edited, Event())
    np.testing.assert_array_equal(actual, expected)
    doc = ContourDocument.from_alpha(actual)
    index = next(i for i, path in enumerate(doc.paths) if path.nodes[0].point[0] < 160)
    old = doc.paths[index]
    replacement = replace(old, nodes=tuple(replace(node, point=(
        75 + (node.point[0] - 75) * .85, 80 + (node.point[1] - 80) * .85,
    )) for node in old.nodes))
    doc.apply_path(index, replacement, changed_path_roi(old, replacement))
    expected[:, :160] = rasterize_path(replacement, (0, 0, 160, 160))
    expected[4, 4] = 77
    np.testing.assert_array_equal(doc.alpha, expected)


@pytest.mark.parametrize('tolerance', [0.5, 1.0, 2.0, 4.0, 8.0])
@pytest.mark.parametrize('feather', [0.0, 1.0, 2.0])
def test_local_curve_edit_matches_full_mask_for_supported_tolerances(tolerance, feather):
    alpha = np.zeros((256, 256), np.uint8)
    cv2.circle(alpha, (128, 128), 80, 255, -1)
    paths = ContourDocument.from_alpha(alpha, tolerance=tolerance).paths
    old = paths[0]
    for node_index, node in enumerate(old.nodes):
        nodes = list(old.nodes)
        nodes[node_index] = replace(node, point=(
            128 + (node.point[0] - 128) * .8,
            128 + (node.point[1] - 128) * .8,
        ))
        replacement = replace(old, nodes=tuple(nodes))
        local = ContourDocument(alpha, list(paths), tolerance)
        full = ContourDocument(alpha, list(paths), tolerance)
        roi = changed_path_roi(old, replacement)
        local.apply_path(0, replacement, roi, feather=feather)
        full.apply_path(0, replacement, (0, 0, 256, 256), feather=feather)
        np.testing.assert_array_equal(local.alpha, full.alpha)
        outside = np.ones_like(alpha, dtype=bool)
        left, top, right, bottom = roi
        outside[top:bottom, left:right] = False
        np.testing.assert_array_equal(local.alpha[outside], alpha[outside])
