"""Local-region equivalence and cancellation publication barriers."""
from dataclasses import replace
from concurrent.futures import CancelledError
from threading import Event
import time
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image, ImageDraw
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from studio_contour import BezierNode, ContourDocument, changed_path_roi, extract_contours
from v3_transparency_preview import ClipartTransparencyEditorPage, _calculate_contour


def mask(size=256):
    image = Image.new('L', (size,size))
    draw = ImageDraw.Draw(image)
    draw.ellipse((20,20,size-20,size-20), fill=255)
    draw.ellipse((60,60,100,100), fill=0)
    draw.line((5,size//2,22,size//2), fill=70, width=1)
    return np.array(image)


@pytest.mark.parametrize('operation', ['move', 'smooth', 'insert', 'delete', 'hole', 'auto-smooth'])
def test_changed_roi_matches_full_raster(operation):
    alpha = mask()
    paths = extract_contours(alpha)
    i = next(i for i,p in enumerate(paths) if p.fill_value == (0 if operation == 'hole' else 255))
    previous = paths[i]
    nodes = list(previous.nodes)
    n = nodes[0]
    if operation == 'auto-smooth':
        nodes[0] = replace(n, kind='smooth')
    elif operation == 'smooth':
        nodes[0] = replace(n, kind='smooth', in_handle=(n.point[0]-8,n.point[1]+8), out_handle=(n.point[0]+8,n.point[1]+8))
    elif operation == 'insert':
        nodes.insert(1, BezierNode(((n.point[0]+nodes[1].point[0])/2+4, (n.point[1]+nodes[1].point[1])/2+4)))
    elif operation == 'delete':
        nodes.pop(0)
    else:
        nodes[0] = replace(n, point=(n.point[0]+7,n.point[1]+6))
    new = replace(previous, nodes=tuple(nodes))
    full = ContourDocument(alpha, list(paths))
    local = ContourDocument(alpha, list(paths))
    full.apply_path(i,new,(0,0,256,256))
    roi = changed_path_roi(previous,new)
    local.apply_path(i,new,roi)
    np.testing.assert_array_equal(local.alpha,full.alpha)
    if operation in ('move','hole'):
        assert (roi[2]-roi[0])*(roi[3]-roi[1]) < alpha.size//4


def wait(canvas):
    deadline = time.monotonic()+10
    while canvas.contour_busy and time.monotonic()<deadline:
        QTest.qWait(5)
    assert not canvas.contour_busy


def make_page(tmp_path):
    app = QApplication.instance() or QApplication([])
    source = tmp_path/'test.png'
    image = Image.new('RGBA',(256,256),(50,80,110,0))
    image.putalpha(Image.fromarray(mask()))
    image.save(source)
    page = ClipartTransparencyEditorPage()
    page._test_app = app
    page.set_files([source]); page.show()
    page._set_tool('pen')
    return page, source


def test_cancel_apply_does_not_save_or_publish_and_ui_keeps_ticking(tmp_path):
    page, source = make_page(tmp_path)
    try:
        canvas = page.canvas
        canvas.auto_contour(); wait(canvas)
        original = source.read_bytes()
        alpha = page.document.mask.tobytes()
        canvas.contour.selected = (0,0)
        canvas.contour.toggle()
        entered, release = Event(), Event()
        real = _calculate_contour
        def delayed(*args):
            entered.set()
            release.wait(5)
            return real(*args)
        ticks = []
        timer = QTimer(page); timer.timeout.connect(lambda: ticks.append(1)); timer.start(5)
        with patch('v3_transparency_preview._calculate_contour', side_effect=delayed):
            page._save_clicked()
            assert canvas.contour_busy
            assert not page.file_list.isEnabled()
            QTest.qWait(40)
            assert ticks and entered.is_set()
            QTest.keyClick(canvas,Qt.Key.Key_Escape)
            release.set(); wait(canvas)
        assert source.read_bytes() == original
        assert page.document.mask.tobytes() == alpha
        assert canvas.contour.dirty
        assert not page._save_after_contour
        assert page.file_list.isEnabled()
        page._save_clicked(); wait(canvas)
        assert not canvas.contour.dirty
    finally:
        page.close(); page.deleteLater()


def test_worker_failure_and_file_switch_do_not_publish_stale_result(tmp_path):
    page, source = make_page(tmp_path)
    try:
        with patch('v3_transparency_preview._calculate_contour', side_effect=RuntimeError('test failure')):
            page.canvas.auto_contour(); wait(page.canvas)
        assert 'test failure' in page.contour_status.text()
        assert not page.canvas.contour.paths
        entered, release = Event(), Event()
        def late(*args):
            entered.set(); release.wait(5)
            return extract_contours(args[1])  # deliberately ignores cancellation
        with patch('v3_transparency_preview._calculate_contour', side_effect=late):
            page.canvas.auto_contour()
            QTest.qWait(20)
            page.set_files([])
            release.set(); wait(page.canvas)
        assert page.canvas.document is None
        assert not page.canvas.contour.paths
    finally:
        page.close(); page.deleteLater()


def test_cancel_during_core_keeps_alpha_and_geometry_atomic():
    alpha = mask(); paths = extract_contours(alpha)
    core = ContourDocument(alpha, paths)
    nodes = list(paths[0].nodes); n = nodes[0]
    nodes[0] = replace(n, point=(n.point[0]+7,n.point[1]+6))
    new = replace(paths[0],nodes=tuple(nodes))
    count = 0
    def cancelled():
        nonlocal count
        count += 1
        return count > 2
    with pytest.raises(CancelledError):
        core.apply_path(0,new,(0,0,256,256),cancelled=cancelled)
    np.testing.assert_array_equal(core.alpha,alpha)
    assert core.paths == paths


def test_4100_side_allowed_and_4101_rejected():
    alpha = np.zeros((4100,4100),dtype=np.uint8)
    alpha[100:4000,100:4000] = 255
    assert _calculate_contour('extract',alpha,(),(),Event())
    with pytest.raises(ValueError, match='4100'):
        _calculate_contour('extract',np.zeros((1,4101),dtype=np.uint8),(),(),Event())
