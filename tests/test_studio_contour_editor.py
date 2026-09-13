import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QFileDialog

from studio_contour_editor import ContourEditorDialog


def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def qapp():
    return app()


def make_png(path: Path, opaque: bool = False) -> np.ndarray:
    data=np.zeros((80,100,4),dtype=np.uint8); data[...,0]=31; data[...,1]=99; data[...,2]=180
    if opaque: data[...,3]=255
    else: data[16:65,20:76,3]=255
    Image.fromarray(data,"RGBA").save(path); return data


def canvas_point(dialog, x, y):
    rect=dialog.canvas._image_rect()
    return QPointF(rect.left()+x*rect.width()/100,rect.top()+y*rect.height()/80)


def test_brush_is_limited_to_dragged_roi_and_rgb_is_unchanged(tmp_path):
    source=tmp_path/"source.png"; original=make_png(source)
    dialog=ContourEditorDialog(source); dialog.show(); app().processEvents()
    c=dialog.canvas
    start=canvas_point(dialog,25,20); end=canvas_point(dialog,70,60)
    c.tool="select"; QTest.mousePress(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,start.toPoint()); QTest.mouseMove(c,end.toPoint()); QTest.mouseRelease(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,end.toPoint())
    roi=c.roi; assert roi is not None
    c.tool="remove"; p=canvas_point(dialog,35,35); QTest.mouseClick(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,p.toPoint())
    outside=(0,0); assert c.alpha[outside] == original[outside][3]
    assert np.array_equal(c.rgba[...,:3],original[...,:3])
    dialog.close()


def test_auto_contour_rejects_opaque_rgb_and_node_drag_keeps_roi(tmp_path):
    opaque=tmp_path/"opaque.png"; make_png(opaque,opaque=True)
    dialog=ContourEditorDialog(opaque); dialog.show(); dialog.canvas.auto_contour(); app().processEvents()
    assert not dialog.canvas.nodes and "прозрачного PNG" in dialog.status.text()
    dialog.close()


def test_dragged_path_keeps_hole_and_unrelated_alpha_then_undoes(tmp_path):
    source=tmp_path/"detailed.png"; original=make_png(source)
    # A transparent hole and a disconnected one-pixel detail must not disappear
    # merely because the editor changes the exterior path within its ROI.
    original[33:43,39:51,3]=0; original[8,90,3]=255
    Image.fromarray(original,"RGBA").save(source)
    dialog=ContourEditorDialog(source); dialog.show(); app().processEvents()
    dialog.canvas.auto_contour(); app().processEvents(); app().processEvents()
    c=dialog.canvas; assert len(c.nodes)>=3 and c.roi is not None
    before=c.alpha.copy(); node=c._to_screen(c.nodes[0].point)
    QTest.mousePress(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,node.toPoint())
    QTest.mouseMove(c,QPointF(node.x()+5,node.y()+3).toPoint())
    QTest.mouseRelease(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPointF(node.x()+5,node.y()+3).toPoint())
    assert c.alpha[38,45] == 0
    assert c.alpha[8,90] == 255
    assert c.session.can_undo
    # The refreshed proposal supports a second drag instead of retaining a stale
    # path index after ContourDocument re-extracts its paths.
    next_node=c._to_screen(c.nodes[0].point)
    QTest.mousePress(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,next_node.toPoint())
    QTest.mouseMove(c,QPointF(next_node.x()+2,next_node.y()+2).toPoint())
    QTest.mouseRelease(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPointF(next_node.x()+2,next_node.y()+2).toPoint())
    before_handle=c.alpha.copy(); handle=c._to_screen(c.nodes[0].point)
    QTest.mousePress(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,handle.toPoint())
    QTest.mouseMove(c,QPointF(handle.x()+10,handle.y()+8).toPoint())
    QTest.mouseRelease(c,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.AltModifier,QPointF(handle.x()+10,handle.y()+8).toPoint())
    assert not np.array_equal(c.alpha,before_handle)
    QTest.keyClick(c,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); app().processEvents()
    assert np.array_equal(c.alpha,before_handle)
    QTest.keyClick(c,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); app().processEvents()
    QTest.keyClick(c,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier); app().processEvents()
    assert np.array_equal(c.alpha,before)
    QTest.keyClick(c,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier); app().processEvents()
    assert c.session.can_redo
    dialog.close()
    source=tmp_path/"alpha.png"; make_png(source)
    dialog=ContourEditorDialog(source); dialog.show(); dialog.canvas.auto_contour(); app().processEvents(); app().processEvents()
    assert len(dialog.canvas.nodes)>=3
    before=dialog.canvas._snapshot(); p=dialog.canvas._to_screen(dialog.canvas.nodes[0].point)
    QTest.mousePress(dialog.canvas,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,p.toPoint()); QTest.mouseMove(dialog.canvas,QPointF(p.x()+4,p.y()+4).toPoint()); QTest.mouseRelease(dialog.canvas,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,QPointF(p.x()+4,p.y()+4).toPoint())
    assert dialog.canvas.roi==before.roi
    dialog.close()


def test_save_is_separate_cancel_does_not_write_and_render(tmp_path, monkeypatch):
    source=tmp_path/"source.png"; original=make_png(source)
    dialog=ContourEditorDialog(source); dialog.show(); app().processEvents()
    target=tmp_path/"corrected.png"
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:(str(target),"PNG"))
    dialog._save_as()
    assert dialog.saved_path==target and target.exists()
    assert np.array_equal(np.asarray(Image.open(source).convert("RGBA")),original)
    shot=dialog.grab(); assert shot.width()>900 and shot.height()>650
    dialog.close()
    second=ContourEditorDialog(source); second.reject(); assert second.saved_path is None



def test_save_as_copies_hash_bound_result_kind_sidecar(tmp_path, monkeypatch):
    from chroma_generation_record import (
        bind_generation_record, load_generation_result_kind, write_generation_intent,
    )
    source=tmp_path/"source.png"; make_png(source)
    intent=write_generation_intent(source,color="green",prompt="flower",result_kind="clipart")
    bind_generation_record(source,intent,stage="final")
    dialog=ContourEditorDialog(source); dialog.show(); app().processEvents()
    target=tmp_path/"corrected.png"
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:(str(target),"PNG"))
    dialog._save_as()
    assert dialog.saved_path==target
    assert load_generation_result_kind(target)=="clipart"
    dialog.close()

def test_save_as_preserves_preexisting_destination_sidecar_on_collision(tmp_path, monkeypatch):
    from chroma_generation_record import (
        bind_generation_record, record_path, write_generation_intent,
    )
    source=tmp_path/"source.png"; make_png(source)
    intent=write_generation_intent(source,color="green",prompt="flower",result_kind="clipart")
    bind_generation_record(source,intent,stage="final")
    target=tmp_path/"corrected.png"
    existing_sidecar=record_path(target)
    existing_sidecar.write_bytes(b"preexisting-sidecar-must-survive")
    dialog=ContourEditorDialog(source); dialog.show(); app().processEvents()
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:(str(target),"PNG"))

    dialog._save_as()

    assert dialog.saved_path is None
    assert not target.exists()
    assert existing_sidecar.read_bytes()==b"preexisting-sidecar-must-survive"
    dialog.close()


def test_rgba_input_save_failure_and_missing_file_are_safe(tmp_path, monkeypatch):
    source=tmp_path/"source.png"; original=make_png(source)
    supplied=original.copy(); supplied[...,3]=128
    dialog=ContourEditorDialog(source,rgba=supplied); dialog.show(); app().processEvents()
    target=tmp_path/"already.png"; target.write_bytes(b"keep")
    monkeypatch.setattr(QFileDialog,"getSaveFileName",lambda *args:(str(target),"PNG"))
    dialog._save_as()
    assert dialog.saved_path is None and target.read_bytes()==b"keep"
    dialog.close()
    missing=ContourEditorDialog(tmp_path/"missing.png")
    assert not missing.save_button.isEnabled() and not missing.auto_button.isEnabled()


def test_fixed_brush_sizes_keyboard_and_space_pan(tmp_path):
    source = tmp_path / "source.png"
    make_png(source)
    dialog = ContourEditorDialog(source)
    dialog.show()
    app().processEvents()
    canvas = dialog.canvas
    assert tuple(dialog.brush_buttons) == (2, 8, 16, 32, 64)
    for size, button in dialog.brush_buttons.items():
        button.click()
        assert canvas.brush_radius * 2 == size
    canvas.setFocus()
    QTest.keyClick(canvas, Qt.Key.Key_BracketLeft)
    assert canvas.brush_radius * 2 == 32
    QTest.keyClick(canvas, Qt.Key.Key_E)
    assert canvas.tool == "remove"
    before = canvas.alpha.copy()
    old_pan = QPointF(canvas.pan)
    point = canvas._to_screen((40, 40)).toPoint()
    QTest.keyPress(canvas, Qt.Key.Key_Space)
    QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseMove(canvas, point + QPointF(20, 15).toPoint())
    QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=point + QPointF(20, 15).toPoint())
    QTest.keyRelease(canvas, Qt.Key.Key_Space)
    assert canvas.pan != old_pan and not canvas._space_pan
    assert np.array_equal(canvas.alpha, before)
    dialog.close()


def test_small_roi_does_not_bypass_full_image_extraction_limit(tmp_path):
    rgba = np.zeros((2049, 2048, 4), dtype=np.uint8)
    rgba[2:8, 2:8, 3] = 255
    dialog = ContourEditorDialog(tmp_path / "unused.png", rgba=rgba)
    dialog.canvas.roi = (0, 0, 10, 10)
    assert not dialog.canvas.can_auto_contour()[0]
    assert dialog.canvas.session.document.paths == []
    dialog.close()


def test_failed_open_keeps_current_edits_available(tmp_path):
    source = tmp_path / "source.png"
    make_png(source)
    dialog = ContourEditorDialog(source)
    canvas = dialog.canvas
    canvas.alpha[20, 30] = 0
    canvas.session.checkpoint()
    dialog._open_path(tmp_path / "absent.png")
    assert dialog.canvas is canvas and canvas.alpha[20, 30] == 0
    assert dialog.source_path == source and dialog.save_button.isEnabled()
    missing = ContourEditorDialog(tmp_path / "absent.png")
    assert not missing.undo_button.isEnabled() and not missing.redo_button.isEnabled()
    dialog.close()
    missing.close()
